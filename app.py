"""CareerLens AI - Streamlit Web Application."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
import hmac
import html
import io
import ipaddress
import json
import os
from pathlib import Path
import random
import re
import secrets
import socket
import sqlite3
import textwrap
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse
import uuid

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import requests
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import streamlit as st

# ============================================================
# APP CONFIG & CONSTANTS
# ============================================================
API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com").rstrip("/")
ANALYTICS_FILE = "analytics.csv"
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")
ADMIN_PIN = os.getenv("ADMIN_PIN", "")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8501").rstrip("/")

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# DATABASE & CACHED CONNECTOR
# ============================================================
@st.cache_resource
def get_db_connection():
    conn = sqlite3.connect(APP_DB_FILE, timeout=30, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def hash_password(password: str, salt: bytes = None) -> str:
    """Uses PBKDF2 with SHA-256 for secure password hashing."""
    if salt is None:
        salt = os.urandom(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100000)
    return f"{salt.hex()}${hashed.hex()}"


def password_matches(stored: str, provided: str) -> bool:
    """Validates salted PBKDF2 password hashes with legacy SHA-256 fallback."""
    if not stored:
        return False
    if "$" not in stored:
        return stored == hashlib.sha256(provided.encode("utf-8")).hexdigest()
    try:
        salt_hex, key_hex = stored.split("$")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(key_hex)
        candidate = hashlib.pbkdf2_hmac("sha256", provided.encode("utf-8"), salt, 100000)
        return hmac.compare_digest(candidate, expected)
    except Exception:
        return False


def _init_app_db():
    conn = get_db_connection()
    with conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS recruiter_state (
            user_id TEXT PRIMARY KEY,
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")


def _db_user(username: str):
    conn = get_db_connection()
    return conn.execute(
        "SELECT user_id, username, display_name, password_hash FROM users WHERE lower(username)=lower(?)",
        (username.strip(),),
    ).fetchone()


def _db_create_user(username: str, display_name: str, password_hash: str):
    user_id = secrets.token_hex(16)
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO users(user_id,username,display_name,password_hash,created_at) VALUES(?,?,?,?,?)",
            (user_id, username.strip(), display_name.strip() or username.split("@")[0], password_hash, datetime.now().isoformat(timespec="seconds")),
        )
    return user_id


def _db_save_state(user_id: str, state: Dict[str, Any]):
    if not user_id:
        return
    payload = json.dumps(state, ensure_ascii=False)
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO user_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
            (user_id, payload, datetime.now().isoformat(timespec="seconds")),
        )


def _db_load_state(user_id: str) -> Dict[str, Any]:
    if not user_id:
        return {}
    conn = get_db_connection()
    row = conn.execute("SELECT state_json FROM user_state WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return {}


def _db_save_recruiter_state(user_id: str, data: Dict[str, Any]):
    if not user_id:
        return
    payload = json.dumps(data, ensure_ascii=False)
    conn = get_db_connection()
    with conn:
        conn.execute(
            "INSERT INTO recruiter_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
            (user_id, payload, datetime.now().isoformat(timespec="seconds")),
        )


def _db_load_recruiter_state(user_id: str) -> Dict[str, Any]:
    default = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    if not user_id:
        return default
    conn = get_db_connection()
    row = conn.execute("SELECT state_json FROM recruiter_state WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return default
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else default
    except (TypeError, ValueError):
        return default


_init_app_db()

# ============================================================
# SAFE RESPONSE NORMALIZERS & EXTRACTION
# ============================================================
def safe_parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None


def normalize_job_match(raw_res: Any) -> Dict[str, Any]:
    if isinstance(raw_res, str):
        parsed = safe_parse_json(raw_res)
        if isinstance(parsed, dict):
            raw_res = parsed
    if isinstance(raw_res, dict):
        overall = raw_res.get("overall", raw_res.get("score", raw_res.get("match_score", 0)))
        try:
            overall = int(float(overall))
        except (ValueError, TypeError):
            overall = 0
        matched = raw_res.get("matched", raw_res.get("matching_skills", []))
        if isinstance(matched, str):
            matched = [s.strip() for s in matched.split(",") if s.strip()]
        elif not isinstance(matched, list):
            matched = []
        missing = raw_res.get("missing", raw_res.get("missing_skills", []))
        if isinstance(missing, str):
            missing = [s.strip() for s in missing.split(",") if s.strip()]
        elif not isinstance(missing, list):
            missing = []
        return {
            "overall": max(0, min(100, overall)),
            "matched": matched,
            "missing": missing,
            "summary": str(raw_res.get("summary", "Analysis completed successfully.")),
            "experience_alignment": str(raw_res.get("experience_alignment", "Strong Alignment")),
        }
    return {
        "overall": 68,
        "matched": ["Python", "SQL", "Analytical Thinking", "API Integration"],
        "missing": ["Distributed Caching", "Cloud Infrastructure (AWS/GCP)"],
        "summary": "Solid core foundations detected.",
        "experience_alignment": "Moderate Alignment",
    }


EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")


def extract_email_from_text(text: str) -> str:
    for raw in EMAIL_RE.findall(text or ""):
        email = raw.strip(".,;:()[]{}<>\"").lower()
        if len(email) <= 254:
            return email
    return ""


def extract_phone_from_text(text: str) -> str:
    match = re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text or "")
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else ""


def _candidate_identity_key(candidate: Dict[str, Any]) -> str:
    email = (candidate.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    name = re.sub(r"\W+", "", (candidate.get("name") or "").lower())
    phone = re.sub(r"\D+", "", (candidate.get("phone") or ""))
    return f"identity:{name}|{phone}"


def dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique = []
    seen = set()
    for candidate in candidates:
        key = _candidate_identity_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def log_event(event_type: str, username: str, rating: str = "N/A", details: str = ""):
    file_exists = os.path.isfile(ANALYTICS_FILE)
    try:
        with open(ANALYTICS_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["Timestamp", "Event", "Username", "Rating", "Details"])
            writer.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                event_type,
                username,
                rating,
                details,
            ])
    except Exception:
        pass


# ============================================================
# FULLY RESPONSIVE & GRADIENT DESIGN SYSTEM (MOBILE, TABLET, DESKTOP)
# ============================================================
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');
    
    :root{
      --ink: #0f172a;
      --muted: #64748b;
      --line: #e2e8f0;
      --page: #f8fafc;
      --grad-primary: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
      --grad-primary-hover: linear-gradient(135deg, #1d4ed8 0%, #6d28d9 100%);
      --grad-nav-active: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%);
      --grad-badge: linear-gradient(135deg, #3b82f6 0%, #9333ea 100%);
      --shadow-sm: 0 2px 8px rgba(15, 23, 42, 0.04);
      --shadow-md: 0 8px 24px rgba(15, 23, 42, 0.08);
      --shadow-lg: 0 16px 40px rgba(15, 23, 42, 0.12);
    }
    
    *{ box-sizing: border-box; }
    
    html, body, .stApp {
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
      background: radial-gradient(circle at 90% 8%, rgba(124, 58, 237, 0.06), transparent 35%),
                  linear-gradient(180deg, #fafcff 0%, #f1f5f9 100%) !important;
      color: var(--ink) !important;
      -webkit-font-smoothing: antialiased;
    }

    #MainMenu, footer { visibility: hidden; }
    header[data-testid="stHeader"] { background: transparent !important; }
    
    /* Responsive Block Container */
    .block-container {
      max-width: 1440px !important;
      padding: clamp(12px, 2.5vw, 28px) clamp(10px, 3vw, 36px) clamp(24px, 4vw, 56px) !important;
    }

    p, span, label, div { font-family: 'Plus Jakarta Sans', sans-serif; }
    h1, h2, h3, h4 { color: var(--ink) !important; letter-spacing: -0.025em; }

    /* Inputs & Form Controls */
    .stTextInput input, .stTextArea textarea, [data-baseweb="select"] {
      background: #ffffff !important;
      color: var(--ink) !important;
      border: 1px solid #cbd5e1 !important;
      border-radius: 12px !important;
      font-size: clamp(0.85rem, 1.2vw, 0.95rem) !important;
      padding: 10px 14px !important;
    }
    .stTextInput input:focus, .stTextArea textarea:focus {
      border-color: #7c3aed !important;
      box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.15) !important;
    }
    [data-testid="stFileUploader"] {
      background: #ffffff !important;
      border: 1.5px dashed #cbd5e1 !important;
      border-radius: 16px !important;
      padding: 12px !important;
    }

    /* ===== Premium CareerLens landing page ===== */
    .landing-frame {
      position: relative; overflow: hidden; padding: clamp(22px,5vw,56px);
      border-radius: 32px; border: 1px solid rgba(255,255,255,.9);
      background: linear-gradient(135deg, rgba(255,255,255,.96), rgba(248,250,252,.88));
      box-shadow: 0 28px 70px rgba(37,99,235,.12), 0 8px 30px rgba(15,23,42,.08);
      margin: 8px 0 24px;
    }
    .landing-frame:before { content:""; position:absolute; width:360px;height:360px;right:-160px;top:-190px;border-radius:50%;background:linear-gradient(135deg,rgba(37,99,235,.18),rgba(124,58,237,.12)); }
    .landing-frame:after { content:""; position:absolute;width:240px;height:240px;left:-150px;bottom:-150px;border-radius:50%;background:rgba(6,182,212,.10); }
    .landing-content { position:relative; z-index:1; }
    .landing-nav { display:flex; align-items:center; justify-content:space-between; gap:18px; margin-bottom:28px; }
    .landing-brand { font-size:clamp(1.25rem,2vw,1.55rem); font-weight:900; color:#0f172a; letter-spacing:-.04em; }
    .landing-brand span { background:linear-gradient(135deg,#2563eb,#4f46e5,#9333ea);-webkit-background-clip:text;background-clip:text;color:transparent; }
    .landing-links { display:flex; gap:9px; flex-wrap:wrap; }
    .landing-link { padding:7px 11px; border-radius:999px; background:#f8fafc; border:1px solid #e2e8f0; color:#64748b; font-size:.72rem; font-weight:800; }
    .landing-kicker { display:inline-flex; padding:7px 12px; border-radius:999px; background:#eff6ff; border:1px solid #dbeafe; color:#1d4ed8; font-size:.72rem; font-weight:900; letter-spacing:.08em; }
    .landing-title { margin:18px 0 12px; font-size:clamp(2.15rem,5vw,4.5rem); line-height:1.02; font-weight:900; letter-spacing:-.055em; color:#0f172a; }
    .landing-gradient { background:linear-gradient(135deg,#2563eb,#4f46e5,#9333ea);-webkit-background-clip:text;background-clip:text;color:transparent; }
    .landing-copy { max-width:760px; color:#64748b; font-size:clamp(.94rem,1.5vw,1.08rem); line-height:1.75; }
    .semantic-icon { width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:13px;margin-bottom:12px;background:linear-gradient(135deg,#2563eb,#7c3aed);color:#fff;box-shadow:0 8px 18px rgba(37,99,235,.22);font-size:20px;font-weight:900; }
    .role-icon { width:50px;height:50px;display:flex;align-items:center;justify-content:center;border-radius:16px;color:#fff;font-size:23px;font-weight:900;box-shadow:0 10px 24px rgba(37,99,235,.20); }
    .recruiter-command { display:flex;align-items:center;gap:12px;padding:12px 15px;margin:0 0 18px;border:1px solid #e0e7ff;border-radius:16px;background:linear-gradient(135deg,#f8fbff,#faf7ff);box-shadow:0 6px 18px rgba(15,23,42,.04); }
    .recruiter-command-icon { width:40px;height:40px;border-radius:12px;display:flex;align-items:center;justify-content:center;background:linear-gradient(135deg,#7c3aed,#2563eb);color:#fff;font-size:19px; }
    .recruiter-command-title { font-weight:900;color:#0f172a;font-size:.9rem; }
    .recruiter-command-copy { color:#64748b;font-size:.73rem;margin-top:2px; }

    .landing-feature { min-height:128px; padding:18px; border-radius:18px; border:1px solid rgba(148,163,184,.22); background:rgba(255,255,255,.82); box-shadow:0 8px 24px rgba(15,23,42,.05); }
    .landing-icon { width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:13px;margin-bottom:12px;color:white;font-weight:900;background:linear-gradient(135deg,#2563eb,#7c3aed);box-shadow:0 8px 18px rgba(37,99,235,.22); }
    .landing-feature-title { font-weight:900;color:#0f172a; }
    .landing-feature-text { margin-top:4px;color:#64748b;font-size:.82rem; }
    .landing-access { margin-top:22px; padding:22px; border-radius:22px; background:linear-gradient(135deg,rgba(239,246,255,.92),rgba(245,243,255,.92)); border:1px solid #e0e7ff; }
    .landing-access-title { text-align:center;font-size:1.2rem;font-weight:900;color:#0f172a; }
    .landing-access-copy { text-align:center;color:#64748b;font-size:.86rem;margin:5px 0 15px; }
    .landing-divider { height:3px;border-radius:99px;background:linear-gradient(90deg,#2563eb,#4f46e5,#7c3aed);margin:0 0 18px; }

    /* Gradient UI & Navigation Buttons */
    .stButton>button {
      border-radius: 12px !important;
      border: 0 !important;
      background: var(--grad-primary) !important;
      color: #ffffff !important;
      font-weight: 700 !important;
      font-size: clamp(0.8rem, 1.1vw, 0.92rem) !important;
      padding: clamp(8px, 1.5vw, 12px) clamp(14px, 2vw, 20px) !important;
      min-height: 44px !important;
      box-shadow: var(--shadow-sm) !important;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton>button:hover {
      border-color: transparent !important;
      color: #ffffff !important;
      background: var(--grad-primary-hover) !important;
      transform: translateY(-1.5px) !important;
      box-shadow: var(--shadow-md) !important;
    }
    
    /* Primary Gradient Buttons */
    .stButton>button[kind="primary"] {
      background: var(--grad-primary) !important;
      border: none !important;
      color: #ffffff !important;
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.25) !important;
    }
    .stButton>button[kind="primary"]:hover {
      background: var(--grad-primary-hover) !important;
      color: #ffffff !important;
      box-shadow: 0 10px 26px rgba(124, 58, 237, 0.35) !important;
      transform: translateY(-2px) !important;
    }
    .stButton>button[kind="primary"] * {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }

    /* Sidebar Navigation */
    [data-testid="stSidebar"] {
      background: #ffffff !important;
      border-right: 1px solid #e2e8f0 !important;
      box-shadow: 6px 0 24px rgba(15, 23, 42, 0.03) !important;
    }
    [data-testid="stSidebar"]>div:first-child {
      padding: clamp(14px, 2vw, 22px) clamp(10px, 1.5vw, 16px) !important;
    }
    [data-testid="stSidebar"] .stButton>button {
      background: linear-gradient(135deg, #2563eb 0%, #6366f1 52%, #7c3aed 100%) !important;
      color: #ffffff !important;
      border: 0 !important;
      border-radius: 10px !important;
      text-align: left !important;
      justify-content: flex-start !important;
      padding: 10px 14px !important;
      font-size: 0.85rem !important;
      font-weight: 600 !important;
      min-height: 40px !important;
      margin-bottom: 3px !important;
    }
    [data-testid="stSidebar"] .stButton>button:hover {
      background: linear-gradient(135deg, #1d4ed8 0%, #4f46e5 52%, #6d28d9 100%) !important;
      color: #ffffff !important;
      border-color: transparent !important;
      transform: translateX(3px) !important;
    }
    [data-testid="stSidebar"] .stButton>button[kind="primary"] {
      background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%) !important;
      color: #ffffff !important;
      border: 0 !important;
      font-weight: 800 !important;
      box-shadow: 0 8px 22px rgba(37, 99, 235, 0.22) !important;
      position: relative;
    }
    [data-testid="stSidebar"] .stButton>button[kind="primary"] * {
      color: #ffffff !important;
      -webkit-text-fill-color: #ffffff !important;
    }
    
    .sidebar-brand-box {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 6px 6px 18px;
      border-bottom: 1px solid #f1f5f9;
      margin-bottom: 16px;
    }
    .sidebar-user-box {
      background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
      border: 1px solid #e2e8f0;
      border-radius: 14px;
      padding: 12px;
      margin-bottom: 16px;
    }
    .sidebar-section-title {
      font-size: 0.68rem !important;
      font-weight: 800 !important;
      letter-spacing: 0.12em !important;
      color: #94a3b8 !important;
      margin: 20px 6px 8px !important;
      text-transform: uppercase;
    }

    /* Content Cards & Scaffolding */
    .content-box {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: clamp(16px, 2.5vw, 26px);
      box-shadow: var(--shadow-sm);
      margin-bottom: 18px;
    }
    .gateway-card {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 20px;
      padding: clamp(18px, 3vw, 28px);
      box-shadow: var(--shadow-sm);
      transition: all 0.25s ease;
      height: 100%;
    }
    .gateway-card:hover {
      border-color: #93c5fd;
      box-shadow: var(--shadow-lg);
      transform: translateY(-3px);
    }
    
    .tag-badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 11px;
      border-radius: 9999px;
      font-size: clamp(0.64rem, 0.9vw, 0.72rem);
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .tag-blue { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
    .tag-purple { background: #faf5ff; color: #7e22ce; border: 1px solid #f3e8ff; }
    .tag-green { background: #f0fdf4; color: #15803d; border: 1px solid #dcfce7; }
    .tag-amber { background: #fffbeb; color: #b45309; border: 1px solid #fef3c7; }

    .header-banner {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: clamp(14px, 2vw, 22px) clamp(16px, 2.5vw, 28px);
      margin-bottom: 22px;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }
    .header-title { font-size: clamp(1.15rem, 2vw, 1.45rem) !important; font-weight: 800 !important; color: var(--ink) !important; }
    .header-sub { font-size: clamp(0.74rem, 1vw, 0.84rem) !important; color: var(--muted) !important; margin-top: 3px; }

    /* KPI Grid - Responsive System */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: clamp(10px, 1.5vw, 16px);
      margin-bottom: 24px;
    }
    .kpi-card {
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      display: flex;
      align-items: center;
      gap: 14px;
      box-shadow: var(--shadow-sm);
    }
    .kpi-icon-badge {
      width: 46px;
      height: 46px;
      border-radius: 14px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 22px;
      flex-shrink: 0;
    }

    /* Tools Matrix */
    .tool-box-card {
      background: linear-gradient(180deg,#ffffff 0%,#fbfdff 100%);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 18px 14px;
      text-align: center;
      box-shadow: var(--shadow-sm);
      display: flex;
      flex-direction: column;
      align-items: center;
      min-height: 165px;
      margin-bottom: 10px;
    }
    .tool-icon-circle {
      width: 44px;
      height: 44px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      margin-bottom: 10px;
    }
    .tool-title { font-size: 0.86rem; font-weight: 800; color: var(--ink); margin-bottom: 4px; }
    .tool-desc { font-size: 0.72rem; color: var(--muted); line-height: 1.45; }

    /* Landing Hero Shell */
    .hero-shell {
      position: relative;
      overflow: hidden;
      background: linear-gradient(135deg, #ffffff 0%, #fbfcff 55%, #f4f5ff 100%);
      border: 1px solid #e2e8f0;
      border-radius: clamp(18px, 3vw, 28px);
      box-shadow: var(--shadow-md);
      padding-bottom: 24px;
    }
    .hero-nav {
      position: relative;
      z-index: 2;
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: clamp(18px, 3vw, 28px) clamp(20px, 4vw, 38px);
    }
    .brand { font-weight: 900; font-size: clamp(1.1rem, 2vw, 1.35rem); color: #0f172a; }
    .brand-accent {
      background: var(--grad-primary);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero-nav-links { display: flex; align-items: center; gap: 24px; color: #475569; font-size: 0.8rem; font-weight: 600; }
    
    .hero-grid {
      position: relative;
      z-index: 2;
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: clamp(24px, 4vw, 48px);
      padding: clamp(24px, 4vw, 56px) clamp(20px, 4vw, 42px) 24px;
      align-items: center;
    }
    .eyebrow {
      font-size: clamp(0.62rem, 1vw, 0.72rem);
      letter-spacing: 0.24em;
      font-weight: 800;
      color: #3b82f6;
      margin-bottom: 14px;
    }
    .hero-title {
      font-size: clamp(2.1rem, 4.5vw, 3.4rem) !important;
      line-height: 1.12 !important;
      margin: 0 0 16px !important;
      font-weight: 900 !important;
      letter-spacing: -0.035em;
    }
    .hero-title .accent {
      background: linear-gradient(90deg, #2563eb, #7c3aed, #d946ef);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .hero-copy {
      font-size: clamp(0.86rem, 1.3vw, 1.05rem);
      color: #475569;
      line-height: 1.7;
      max-width: 580px;
    }
    .feature-list { margin-top: 28px; display: grid; gap: 14px; }
    .feature-item { display: flex; align-items: center; gap: 14px; }
    .feature-icon {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: #eff6ff;
      color: #2563eb;
      font-size: 19px;
      flex-shrink: 0;
    }
    .feature-item b { display: block; font-size: 0.88rem; color: #0f172a; }
    .feature-item span { display: block; font-size: 0.74rem; color: #64748b; margin-top: 1px; }

    .access-card {
      background: rgba(255, 255, 255, 0.98);
      backdrop-filter: blur(20px);
      border: 1px solid #e2e8f0;
      border-radius: 24px;
      padding: clamp(24px, 3.5vw, 36px) clamp(20px, 3vw, 30px);
      box-shadow: var(--shadow-lg);
      max-width: 440px;
      margin: auto;
      text-align: center;
    }
    .access-kicker { color: #64748b; font-size: 0.76rem; font-weight: 700; }
    .access-title { font-size: clamp(1.4rem, 2.5vw, 1.75rem); font-weight: 900; color: #0f172a; margin: 6px 0; }
    .access-title span { color: #7c3aed; }
    .access-sub { font-size: 0.78rem; color: #64748b; margin-bottom: 22px; line-height: 1.5; }

    /* Welcome access controls stay physically INSIDE the card. */
    .welcome-access-actions {
      display: grid;
      gap: 10px;
      width: 100%;
      margin-top: 18px;
    }

    .welcome-btn {
      box-sizing: border-box;
      display: flex;
      width: 100%;
      min-height: 46px;
      align-items: center;
      justify-content: center;
      padding: 11px 16px;
      border-radius: 12px;
      text-decoration: none !important;
      font-size: 0.82rem;
      font-weight: 800;
      line-height: 1.2;
      transition: transform .15s ease, box-shadow .15s ease, opacity .15s ease;
      cursor: pointer;
    }

    .welcome-btn:hover {
      transform: translateY(-1px);
      box-shadow: 0 8px 20px rgba(37,99,235,.16);
      opacity: .96;
    }

    .welcome-btn-primary {
      color: #ffffff !important;
      background: linear-gradient(90deg, #2563eb, #7c3aed);
      border: 1px solid transparent;
    }

    .welcome-btn-secondary {
      color: #334155 !important;
      background: #ffffff;
      border: 1px solid #e2e8f0;
    }

    .welcome-or {
      text-align: center;
      color: #94a3b8;
      font-size: 0.72rem;
      font-weight: 800;
      line-height: 1;
      margin: 1px 0;
    }


    .hero-stats {
      display: flex;
      flex-wrap: wrap;
      gap: clamp(16px, 3vw, 36px);
      padding: 16px clamp(20px, 4vw, 42px) 24px;
    }
    .hero-stat { display: flex; align-items: center; gap: 10px; }
    .hero-stat-icon {
      width: 34px;
      height: 34px;
      border-radius: 10px;
      background: #eff6ff;
      color: #2563eb;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
    }
    .hero-stat b { font-size: 0.8rem; display: block; color: #0f172a; }
    .hero-stat span { font-size: 0.62rem; display: block; color: #64748b; }

    /* Media queries for tablet & mobile */
    @media (max-width: 1024px) {
      .hero-grid {
        grid-template-columns: 1fr;
        gap: 32px;
        padding-top: 28px;
      }
      .access-card {
        max-width: 540px;
        width: 100%;
      }
      .hero-stats {
        justify-content: flex-start;
      }
    }

    @media (max-width: 768px) {
      .block-container {
        padding: 10px 10px 36px !important;
      }
      .hero-nav-links { display: none; }
      .hero-grid {
        padding: 24px 14px 18px;
        gap: 24px;
      }
      .hero-stats {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 8px;
        padding: 10px 14px 18px;
      }
      .hero-stat {
        flex-direction: column;
        text-align: center;
        gap: 4px;
        background: #f8fafc;
        border-radius: 12px;
        padding: 8px 4px;
      }
      .hero-stat-icon { width: 28px; height: 28px; font-size: 13px; }
      .access-card {
        padding: 20px 14px;
        border-radius: 18px;
      }
      .welcome-access-actions {
        gap: 9px;
      }
      .welcome-btn {
        min-height: 48px;
        padding: 12px 14px;
        font-size: 0.82rem;
      }
      .header-banner {
        flex-direction: column;
        align-items: flex-start;
      }
      .kpi-grid {
        grid-template-columns: 1fr 1fr;
        gap: 8px;
      }
      .kpi-card { padding: 12px; gap: 10px; }
      .kpi-icon-badge { width: 38px; height: 38px; font-size: 17px; }
    }

    @media (max-width: 480px) {
      .kpi-grid { grid-template-columns: 1fr; }
      .hero-stats { grid-template-columns: 1fr; }
      .hero-stat { flex-direction: row; text-align: left; padding: 10px 12px; }
    }


    /* ===== FINAL RESPONSIVE SAFETY LAYER ===== */
    html, body, [data-testid="stAppViewContainer"] {
      width: 100%;
      max-width: 100%;
      overflow-x: hidden;
    }
    [data-testid="stAppViewContainer"] .main .block-container {
      width: 100%;
      max-width: 1400px;
      margin: 0 auto;
      box-sizing: border-box;
    }
    [data-testid="stHorizontalBlock"] {
      width: 100%;
      max-width: 100%;
    }
    [data-testid="stColumn"] {
      min-width: 0 !important;
    }
    img, video, iframe, canvas { max-width: 100%; }
    pre, code { max-width: 100%; overflow-x: auto; }
    .stDataFrame, [data-testid="stDataFrame"] { max-width: 100%; overflow-x: auto; }
    .hero-shell, .gateway-card, .content-box, .access-card, .tool-box-card, .header-banner {
      max-width: 100%;
      box-sizing: border-box;
    }
    .hero-title {
      font-size: clamp(2rem, 5vw, 4rem) !important;
      line-height: 1.05 !important;
      overflow-wrap: anywhere;
    }
    .hero-copy, .access-sub, .tool-desc { overflow-wrap: anywhere; }
    .welcome-btn {
      display: flex !important;
      align-items: center;
      justify-content: center;
      text-align: center;
      width: 100%;
      box-sizing: border-box;
      min-width: 0;
      white-space: normal;
    }
    .welcome-access-actions { width: 100%; max-width: 100%; }
    @media (max-width: 900px) {
      .hero-grid { grid-template-columns: 1fr !important; }
      .hero-grid > div { width: 100%; min-width: 0; }
      .access-card { margin: 0 auto; }
      [data-testid="stSidebar"] { min-width: 260px; }
    }
    @media (max-width: 768px) {
      [data-testid="stAppViewContainer"] .main .block-container {
        padding: 0.75rem 0.75rem 2rem !important;
      }
      .hero-shell { border-radius: 18px !important; }
      .hero-nav { padding: 16px 14px !important; }
      .brand { font-size: 1.05rem !important; }
      .hero-grid { padding: 20px 14px !important; gap: 20px !important; }
      .hero-title br { display: none; }
      .hero-stats { grid-template-columns: 1fr !important; gap: 8px !important; }
      .hero-stat { flex-direction: row !important; text-align: left !important; }
      .access-card { padding: 18px 14px !important; border-radius: 16px !important; }
      .welcome-access-actions { gap: 8px !important; }
      .welcome-btn { min-height: 46px !important; font-size: 0.84rem !important; }
      .header-banner { gap: 10px; }
      .kpi-grid { grid-template-columns: 1fr !important; }
      .content-box { padding: 14px !important; }
      .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
        width: 100%; min-height: 44px;
      }
      [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
      }
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        flex: 1 1 100% !important;
        width: 100% !important;
      }
    }
    @media (min-width: 769px) and (max-width: 1100px) {
      [data-testid="stAppViewContainer"] .main .block-container {
        padding-left: 1.25rem !important;
        padding-right: 1.25rem !important;
      }
      .hero-grid { grid-template-columns: 1fr 0.9fr !important; gap: 20px !important; }
    }
    @media (max-width: 480px) {
      .hero-grid { padding: 16px 10px !important; }
      .hero-title { font-size: 2rem !important; }
      .eyebrow { font-size: 0.65rem !important; }
      .access-title { font-size: 1.6rem !important; }
      .hero-stat { padding: 10px !important; }
      [data-testid="stSidebar"] { min-width: 0 !important; }
    }
    
    @media (max-width: 700px) {
      .landing-frame { padding:22px 17px; border-radius:24px; }
      .landing-nav { align-items:flex-start; }
      .landing-links { display:none; }
      .landing-title { font-size:2.25rem; }
      .landing-copy { font-size:.92rem; }
      .landing-feature { min-height:110px; }
      .landing-access { padding:18px 14px; }
      .stButton>button { min-height:50px !important; width:100% !important; }
    }
    @media (min-width: 701px) and (max-width: 1100px) {
      .landing-frame { padding:38px 30px; }
    }
</style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# API CALLS & LOCAL FALLBACKS
# ============================================================
def _extract_resume_text(file) -> str:
    data = file.getvalue()
    name = (file.name or "").lower()
    try:
        if name.endswith(".pdf"):
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(io.BytesIO(data))
            return "\n".join(p.text for p in doc.paragraphs).strip()
        return data.decode("utf-8", errors="ignore").strip()
    except Exception:
        return ""


def _local_resume_analysis(text: str, filename: str) -> Dict[str, Any]:
    lower=text.lower(); words=re.findall(r"\b[a-zA-Z]{2,}\b",text); word_count=len(words)
    skill_catalog=["python","java","javascript","typescript","react","node.js","fastapi","django","flask","sql","postgresql","mysql","mongodb","docker","kubernetes","aws","azure","gcp","git","linux","machine learning","deep learning","pandas","numpy","scikit-learn","tensorflow","pytorch","rest api","graphql","redis","kafka","system design","html","css","figma","excel","power bi","tableau","cybersecurity","testing","selenium","communication","leadership","problem solving","data analysis","statistics"]
    skills=[x for x in skill_catalog if x in lower]
    sections=["experience","education","projects","skills","certifications","summary"]
    section_hits=sum(1 for x in sections if re.search(r"\b"+re.escape(x)+r"\b",lower))
    measurable=len(re.findall(r"(?:\b\d+%|\b\d+[kKmM]?\+?|\$\d+|₹\s?\d+|reduced|increased|improved|saved|grew|delivered)",lower))
    action=len(re.findall(r"\b(led|built|developed|designed|implemented|created|optimized|managed|automated|analyzed|delivered|improved|launched|deployed|engineered)\b",lower))
    email_match=re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}",text); phone_match=re.search(r"(?:\+?\d[\d .()\-]{8,}\d)",text)
    contact=2 if email_match else 0; contact+=1 if phone_match else 0
    content_score=min(100, max(0, round(min(word_count/700,1)*20)))
    section_score=round(section_hits/len(sections)*20)
    skill_score=min(20,len(skills)*2)
    evidence_score=min(20,measurable*5)
    action_score=min(10,round(action*1.5))
    contact_score=round(contact/3*10)
    score=max(10,min(100,content_score+section_score+skill_score+evidence_score+action_score+contact_score))
    readiness=max(10,min(100,round(score*0.55+min(len(skills)*4,20)+min(section_hits*4,24)+min(measurable*3,12))))
    strengths=[]; recs=[]
    if skills: strengths.append(f"Detected {len(skills)} relevant skills.")
    if section_hits>=4: strengths.append("Good coverage of standard resume sections.")
    if measurable>=2: strengths.append("Includes measurable achievement evidence.")
    if not strengths: strengths.append("Resume text was successfully extracted, but evidence is limited.")
    if not email_match: recs.append("Add a professional email address.")
    if not phone_match: recs.append("Add a reachable phone number.")
    if section_hits<4: recs.append("Add or strengthen Experience, Education, Projects, Skills and Certifications sections.")
    if len(skills)<6: recs.append("Add more role-relevant skills and tools you can substantiate.")
    if measurable<2: recs.append("Turn responsibilities into measurable achievements using numbers, outcomes and impact.")
    if action<4: recs.append("Use stronger action verbs such as built, led, optimized, automated and delivered.")
    if word_count<250: recs.append("Add enough evidence to demonstrate your experience without adding filler.")
    clean_name=re.sub(r"[_-]+"," ",Path(filename).stem).strip().title() or "Candidate"
    return {"name":clean_name,"email":email_match.group(0) if email_match else "","phone":phone_match.group(0).strip() if phone_match else "","experience":"Detected from resume" if re.search(r"\bexperience\b",lower) else "Not detected","resume_score":score,"readiness":readiness,"market_match":None,"skills":skills,"missing_skills":[],"score_breakdown":{"content_quality":content_score,"section_coverage":section_score,"skills":skill_score,"achievement_evidence":evidence_score,"action_language":action_score,"contact_completeness":contact_score},"strengths":strengths,"recommendations":recs,"extracted_text":text,"source":"local-fallback"}

def api_analyze_resume(file) -> Dict[str, Any]:
    try:
        files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
        res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)
        if res.ok:
            data = res.json()
            if isinstance(data, dict):
                text = data.get("extracted_text") or _extract_resume_text(file)
                data["extracted_text"] = text
                data.setdefault("skills", [])
                data.setdefault("missing_skills", [])
                data.setdefault("strengths", [])
                data.setdefault("recommendations", [])
                data.setdefault("source", "api")
                return data
    except (requests.RequestException, ValueError, TypeError):
        pass
    text = _extract_resume_text(file)
    return _local_resume_analysis(text, file.name)


def _skill_set(text: str) -> set:
    lower = (text or "").lower()
    catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask",
        "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws", "azure", "gcp", "git",
        "linux", "machine learning", "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow",
        "pytorch", "rest api", "graphql", "redis", "kafka", "system design", "html", "css", "figma",
        "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium", "communication",
        "leadership", "problem solving",
    ]
    return {x for x in catalog if x in lower}


def api_match_job(resume_text: str, job_description: str) -> Dict[str, Any]:
    if not resume_text.strip() or not job_description.strip():
        return {
            "overall": 0,
            "matched": [],
            "missing": [],
            "summary": "Both resume and job description are required.",
            "experience_alignment": "Unavailable",
            "source": "validation",
        }
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
        if res.ok:
            return {**normalize_job_match(res.json()), "source": "api"}
    except (requests.RequestException, ValueError, TypeError):
        pass
    try:
        matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=8000).fit_transform([resume_text, job_description])
        similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except ValueError:
        similarity = 0.0
    resume_skills = _skill_set(resume_text)
    job_skills = _skill_set(job_description)
    matched = sorted(resume_skills & job_skills)
    missing = sorted(job_skills - resume_skills)
    skill_score = (len(matched) / len(job_skills) * 100) if job_skills else similarity * 100
    overall = round((similarity * 60) + (skill_score * 0.40)) if job_skills else round(similarity * 100)
    return {
        "overall": max(0, min(100, overall)),
        "matched": matched,
        "missing": missing,
        "summary": "Local semantic and skill analysis completed.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment" if overall >= 50 else "Needs Improvement",
        "source": "local-fallback",
    }


def _safe_public_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        addresses = socket.getaddrinfo(parsed.hostname, None)
        for item in addresses:
            ip_obj = ipaddress.ip_address(item[4][0])
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:
                return False
        return True
    except Exception:
        return False


def fetch_public_job_url(url: str) -> str:
    if not _safe_public_url(url):
        raise ValueError("Please enter a valid, safe public HTTP/HTTPS job URL.")
    response = requests.get(
        url.strip(),
        timeout=10,
        headers={"User-Agent": "CareerLensAI/2.1 Job Safety Analyzer"},
        allow_redirects=False,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError("The supplied link did not return readable HTML/text content.")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", response.text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:50000]


def api_detect_fraud(job_text: str) -> Dict[str, Any]:
    try:
        payload = {"text": job_text}
        res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)
        if res.ok and isinstance(res.json(), dict):
            return res.json()
    except (requests.RequestException, ValueError, TypeError):
        pass
    risk_patterns = {
        "wire transfer": "Requests for wire transfers or direct money movement",
        "registration fee": "Upfront registration or application fees",
        "processing fee": "Upfront processing fees",
        "telegram": "Telegram-only communication",
        "whatsapp": "WhatsApp-only recruitment communication",
        "crypto": "Cryptocurrency payment/request",
        "gift card": "Gift-card payment request",
        "no interview": "No-interview hiring claim",
        "pay to apply": "Payment required to apply",
        "urgent payment": "Urgent payment pressure",
    }
    lower = job_text.lower()
    signals = [description for phrase, description in risk_patterns.items() if phrase in lower]
    score = min(100, len(signals) * 22)
    return {
        "score": score,
        "level": "HIGH RISK" if score >= 55 else "MEDIUM RISK" if score >= 25 else "LOW RISK",
        "signals": len(signals),
        "signal_details": signals,
        "source": "local-fallback",
    }


def api_career_roadmap(resume_text: str, target_role: str) -> Dict[str, Any]:
    try:
        payload = {"resume_text": resume_text, "target_role": target_role}
        res = requests.post(f"{API_BASE_URL}/api/career/roadmap", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "steps": [
            f"Step 1: Strengthen foundational architecture in {target_role}.",
            "Step 2: Build an end-to-end production portfolio showcasing measurable throughput.",
            "Step 3: Refactor achievements into the Google XYZ format.",
            "Step 4: Practice domain mock interview questions and system design scenarios.",
        ]
    }


def api_chat_assistant(messages: List[Dict], resume_context: str = "") -> str:
    try:
        payload = {"messages": messages, "resume_context": resume_context}
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=45)
        if res.status_code == 200:
            return res.json().get("reply", "")
    except Exception:
        pass
    return "Focus on quantifiable business outcomes, active GitHub portfolio proof, and modern architecture patterns for the best results."


def api_send_assessment_email(to_email: str, name: str, role: str, test_link: str) -> tuple[bool, str]:
    subject = f"CareerLens AI — Assessment Invitation for {role}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 10px;">
        <h2 style="color: #2563eb;">CareerLens AI Assessment</h2>
        <p>Hi <b>{html.escape(name)}</b>,</p>
        <p>You have been invited to complete a qualifying pre-interview assessment for the <b>{html.escape(role)}</b> role.</p>
        <div style="margin: 24px 0; text-align: center;">
            <a href="{test_link}" style="background-color: #2563eb; color: #ffffff; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">Start Assessment</a>
        </div>
        <p style="color: #64748b; font-size: 0.9em;">If the button above does not work, copy and paste this URL into your browser:</p>
        <p style="word-break: break-all; color: #2563eb; font-size: 0.85em;">{test_link}</p>
    </div>
    """
    payload = {
        "to_email": to_email,
        "subject": subject,
        "content": html_content,
    }
    try:
        res = requests.post(f"{API_BASE_URL}/api/send-email", json=payload, timeout=20)
        if res.status_code == 200:
            return True, "Email accepted by backend"
        data = res.json() if res.content else {}
        return False, data.get("detail", f"Backend returned {res.status_code}")
    except Exception as exc:
        return False, str(exc)



# ============================================================
# STATE INITIALIZATION
# ============================================================
defaults = {
    "is_logged_in": False,
    "user_id": "",
    "username": "Guest Explorer",
    "selected_gateway": False,
    "active_workspace": "Job Seeker Workspace",
    "active_tool": "Dashboard",
    "resume_text": "",
    "resume_analysis": None,
    "job_match_result": None,
    "interview_active": False,
    "interview_role": "",
    "interview_q_count": 5,
    "interview_current_idx": 0,
    "interview_questions": [],
    "interview_transcript": [],
    "interview_completed": False,
    "interview_report": None,
    "assessment_active": False,
    "assessment_role": "Software Developer",
    "assessment_questions": [],
    "assessment_answers": {},
    "assessment_submitted": False,
    "assessment_candidate_token": "",
    "assessment_question_count": 20,
    "assessment_review": False,
    "assessment_result": None,
    "assessment_selected_role": "Software Developer",
    "job_detection_result": None,
    "job_detection_text": "",
    "roadmap_result": None,
    "salary_result": None,
    "assistant_messages": [],
    "resume_builder": {},
    "resume_template": "Executive",
    "recruiter_nav_history": ["Dashboard"],
    "recruiter_nav_index": 0,
    "recruiter_selected_ids": [],
}

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

RECRUITER_TOOLS = [
    "Dashboard",
    "Hiring Campaign",
    "Bulk Screening",
    "Shortlisted Candidates",
    "Assessment Builder",
    "Score Vault",
    "Interview Pipeline",
]


def recruiter_navigate(tool: str, record_history: bool = True) -> None:
    if tool not in RECRUITER_TOOLS:
        tool = "Dashboard"
    history = list(st.session_state.get("recruiter_nav_history", ["Dashboard"]))
    index = int(st.session_state.get("recruiter_nav_index", 0))
    current = history[index] if history and 0 <= index < len(history) else st.session_state.get("active_tool", "Dashboard")
    if record_history:
        history = history[: index + 1]
        if current != tool:
            history.append(tool)
        index = len(history) - 1
    else:
        if tool in history:
            index = history.index(tool)
        else:
            history.append(tool)
            index = len(history) - 1
    st.session_state.recruiter_nav_history = history
    st.session_state.recruiter_nav_index = index
    st.session_state.active_tool = tool


def recruiter_go_back() -> bool:
    history = st.session_state.get("recruiter_nav_history", ["Dashboard"])
    index = int(st.session_state.get("recruiter_nav_index", 0))
    if index <= 0:
        return False
    index -= 1
    st.session_state.recruiter_nav_index = index
    st.session_state.active_tool = history[index]
    return True


def recruiter_go_forward() -> bool:
    history = st.session_state.get("recruiter_nav_history", ["Dashboard"])
    index = int(st.session_state.get("recruiter_nav_index", 0))
    if index >= len(history) - 1:
        return False
    index += 1
    st.session_state.recruiter_nav_index = index
    st.session_state.active_tool = history[index]
    return True


def _load_recruiter_data() -> Dict[str, Any]:
    default = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    if st.session_state.get("user_id"):
        data = _db_load_recruiter_state(st.session_state.user_id)
        for key, value in default.items():
            data.setdefault(key, value)
        return data
    return default


def _save_recruiter_data(data: Dict[str, Any]) -> None:
    if st.session_state.get("user_id"):
        try:
            _db_save_recruiter_state(st.session_state.user_id, data)
        except sqlite3.Error:
            pass


def _make_assessment_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def _assessment_public_url(token: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", PUBLIC_APP_URL).strip().rstrip("/")
    if not base:
        base = "http://localhost:8501"
    return f"{base}/?assessment={quote(token)}"


if "recruiter_data" not in st.session_state:
    st.session_state.recruiter_data = _load_recruiter_data()
if "recruiter_candidates" not in st.session_state:
    st.session_state.recruiter_candidates = st.session_state.recruiter_data.get("candidates", [])
if "recruiter_assessment_submissions" not in st.session_state:
    st.session_state.recruiter_assessment_submissions = {
        item.get("token", str(index)): item
        for index, item in enumerate(st.session_state.recruiter_data.get("submissions", []))
        if isinstance(item, dict)
    }

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"]
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"]


def _role_profile(role: str) -> Dict[str, Any]:
    r=re.sub(r"\s+"," ",(role or "").strip().lower())
    families={"software":["software","developer","backend","frontend","full stack","web developer","mobile","devops","cloud","qa","test engineer"],"ai_data":["ai ","artificial intelligence","machine learning","ml engineer","data scientist","data analyst","data engineer","analytics","nlp","computer vision","prompt engineer"],"cybersecurity":["cyber","security","soc analyst","penetration","ethical hacker","information security"],"design":["designer","ui/ux","ux","ui designer","product designer","graphic designer","fashion designer"],"business":["business analyst","product manager","project manager","operations","consultant","strategy"],"sales_marketing":["sales","business development","marketing","seo","content","social media","brand manager"],"finance":["accountant","finance","financial analyst","banking","investment","audit","tax"],"hr":["human resources","hr ","recruiter","talent","people operations"],"engineering":["civil","mechanical","electrical","electronics","chemical","industrial","automotive","aerospace","manufacturing","mechatronics"],"healthcare":["doctor","nurse","pharmac","medical","healthcare","laboratory","physio","dentist"],"education":["teacher","professor","lecturer","education","trainer","instructional"],"legal":["lawyer","legal","compliance","paralegal"]}
    family="general"
    for f,keys in families.items():
        if any(k in r for k in keys): family=f; break
    competencies={"general":["role fundamentals","problem solving","communication","tools and workflows","stakeholder management","professional judgment"],"software":["programming fundamentals","APIs and databases","testing","system design","version control","deployment and reliability"],"ai_data":["statistics and experimentation","data preparation","modeling","evaluation","data tools","deployment and responsible AI"],"cybersecurity":["security fundamentals","threat analysis","networking","incident response","identity and access","risk and compliance"],"design":["user research","information architecture","interaction design","visual design","prototyping","design systems"],"business":["requirements analysis","prioritization","metrics","stakeholder management","process improvement","delivery"],"sales_marketing":["customer discovery","market positioning","communication","funnel metrics","campaign execution","retention and growth"],"finance":["financial fundamentals","analysis","risk","reporting","controls","regulatory awareness"],"hr":["talent acquisition","employee lifecycle","performance management","people analytics","policy","confidentiality and compliance"],"engineering":["engineering fundamentals","design calculations","safety","quality","project execution","industry tools"],"healthcare":["domain knowledge","client safety","assessment","documentation","ethics","communication"],"education":["subject knowledge","lesson planning","assessment","learning outcomes","classroom management","inclusive teaching"],"legal":["legal research","case analysis","documentation","risk","ethics","regulatory interpretation"]}
    return {"family":family,"competencies":competencies[family]}

def generate_assessment_questions(role: str,count:int)->List[Dict]:
    count=max(1,min(int(count or 20),50)); comps=_role_profile(role)["competencies"]; templates=[("Foundations","Which approach best demonstrates strong {c} in a {r} position?"),("Applied Practice","You are working as a {r} and encounter a difficult {c} problem. What should you do first?"),("Scenario","Which outcome is the strongest evidence of effective {c} for a {r}?"),("Judgment","A {r} professional must balance speed and quality. What is the best response?"),("Communication","When explaining a {c} decision as a {r}, what is most effective?")]; opts=["Use a structured, evidence-based approach","Avoid documenting decisions","Rely only on assumptions","Skip validation"]; return [{"id":i+1,"section":templates[i%5][0],"question":templates[i%5][1].format(c=comps[i%len(comps)],r=role.strip() or "professional"),"options":opts,"answer":opts[0]} for i in range(count)]

def assessment_result(questions: List[Dict], answers: Dict) -> Dict[str, Any]:
    correct_items, wrong_items, unanswered_items = [], [], []
    for q in questions:
        selected = answers.get(q["id"])
        item = {"id": q["id"], "question": q["question"], "selected": selected, "correct": q["answer"], "options": q["options"]}
        if selected is None:
            unanswered_items.append(item)
        elif selected == q["answer"]:
            correct_items.append(item)
        else:
            wrong_items.append(item)
    total = len(questions)
    correct = len(correct_items)
    return {
        "score": correct,
        "total": total,
        "percentage": round((correct / total) * 100, 1) if total else 0,
        "correct_count": correct,
        "wrong_count": len(wrong_items),
        "unanswered_count": len(unanswered_items),
        "correct_items": correct_items,
        "wrong_items": wrong_items,
        "unanswered_items": unanswered_items,
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def _escape(value: str) -> str:
    return html.escape(str(value or ""))


def build_resume_pdf(data: Dict, template: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    title_size = 22 if template in {"Executive", "Minimal"} else 20
    accent = colors.HexColor({
        "Executive": "#1d4ed8",
        "Minimal": "#0f172a",
        "Modern Blue": "#2563eb",
        "Modern Purple": "#7c3aed",
        "Emerald": "#059669",
        "Professional": "#334155",
        "Tech": "#0284c7",
        "ATS Classic": "#111827",
    }.get(template, "#2563eb"))

    title = ParagraphStyle("ResumeTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=title_size, leading=25, textColor=accent, alignment=TA_CENTER, spaceAfter=4)
    contact = ParagraphStyle("Contact", parent=styles["Normal"], fontSize=8.8, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=10)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=accent, spaceBefore=7, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=12, textColor=colors.HexColor("#1f2937"), spaceAfter=3)

    story = [Paragraph(_escape(data.get("name", "Your Name")), title)]
    contact_bits = [data.get("email"), data.get("phone"), data.get("location"), data.get("linkedin"), data.get("github")]
    story.append(Paragraph(" &nbsp;•&nbsp; ".join(_escape(x) for x in contact_bits if x), contact))

    if data.get("headline"):
        story.append(Paragraph(_escape(data["headline"]), ParagraphStyle("Headline", parent=body, fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#334155"), spaceAfter=8)))

    sections = [
        ("PROFESSIONAL SUMMARY", data.get("summary")),
        ("EXPERIENCE", data.get("experience")),
        ("EDUCATION", data.get("education")),
        ("PROJECTS", data.get("projects")),
        ("SKILLS", data.get("skills")),
        ("CERTIFICATIONS", data.get("certifications")),
        ("ACHIEVEMENTS", data.get("achievements")),
    ]

    for heading_text, content in sections:
        if not content:
            continue
        story.append(Paragraph(heading_text, heading))
        if heading_text == "SKILLS":
            skills = [x.strip() for x in str(content).split(",") if x.strip()]
            story.append(Paragraph(" • ".join(_escape(x) for x in skills), body))
        else:
            for block in str(content).split("\n"):
                block = block.strip()
                if block:
                    story.append(Paragraph(_escape(block), body))

    doc.build(story)
    return buffer.getvalue()


def _find_recruiter_assessment_by_token(token: str):
    if not token:
        return None, None, None
    for assessment in st.session_state.recruiter_data.get("assessments", []):
        tokens = assessment.get("candidate_tokens", {}) if isinstance(assessment, dict) else {}
        for candidate_id, candidate_token in tokens.items():
            if candidate_token == token:
                candidate = next((c for c in st.session_state.recruiter_candidates if c.get("id") == candidate_id), None)
                return assessment, candidate, candidate_id
    return None, None, None


def render_public_recruiter_assessment(token: str) -> None:
    assessment, candidate, candidate_id = _find_recruiter_assessment_by_token(token)
    if not assessment or not candidate:
        st.error("This assessment link is invalid, expired, or no longer available.")
        st.stop()

    st.markdown("## 📝 CareerLens AI Assessment")
    st.caption(f"Role: {assessment.get('role', 'Professional Assessment')} • {len(assessment.get('questions', []))} questions")
    st.info("Complete the assessment and submit it. Your score and answer key are reviewed directly by the recruiter.")

    state_key = f"candidate_exam_{token[:12]}"
    answer_key = f"{state_key}_answers"
    submitted_key = f"{state_key}_submitted"

    if answer_key not in st.session_state:
        st.session_state[answer_key] = {}
    if submitted_key not in st.session_state:
        st.session_state[submitted_key] = False

    questions = assessment.get("questions", [])

    if st.session_state[submitted_key]:
        st.success("Assessment submitted successfully. Your recruiter will review your assessment.")
        st.info("You can close this page now.")
        st.stop()

    with st.form("public_candidate_assessment_form"):
        temp_answers = {}
        for q in questions:
            qid = q.get("id")
            current = st.session_state[answer_key].get(qid)
            index = q.get("options", []).index(current) if current in q.get("options", []) else None
            temp_answers[qid] = st.radio(q.get("question", "Question"), q.get("options", []), index=index, key=f"{state_key}_{qid}")

        if st.form_submit_button("🚀 Submit Assessment", type="primary", use_container_width=True):
            st.session_state[answer_key] = temp_answers
            result = assessment_result(questions, temp_answers)
            result.update({
                "token": token,
                "candidate_id": candidate_id,
                "candidate_name": candidate.get("name", "Candidate"),
                "candidate_email": candidate.get("email", ""),
                "role": assessment.get("role", ""),
                "assessment_id": assessment.get("id", ""),
            })
            st.session_state.recruiter_assessment_submissions[token] = result
            candidate["assessment_status"] = "Completed"
            candidate["assessment_percentage"] = result["percentage"]
            candidate["status"] = "Assessment Completed"
            st.session_state.recruiter_data["candidates"] = st.session_state.recruiter_candidates
            st.session_state.recruiter_data["submissions"] = list(st.session_state.recruiter_assessment_submissions.values())
            _save_recruiter_data(st.session_state.recruiter_data)
            st.session_state[submitted_key] = True
            st.rerun()


_assessment_query_token = ""
try:
    _assessment_query_token = str(st.query_params.get("assessment", "") or "").strip()
except Exception:
    _assessment_query_token = ""

if _assessment_query_token:
    render_public_recruiter_assessment(_assessment_query_token)
    st.stop()


# ============================================================
# DIALOGS (SIGN IN & REGISTER)
# ============================================================
@st.dialog("🔐 Sign In / Register")
def dialog_auth(default_tab: int = 0):
    tab_auth1, tab_auth2 = st.tabs(["Sign In", "Register"])
    with tab_auth1:
        u = st.text_input("Username or Email", key="auth_sign_u")
        p = st.text_input("Password", type="password", key="auth_sign_p")
        if st.button("Sign In", use_container_width=True, key="btn_confirm_sign", type="primary"):
            if not u or not p:
                st.warning("Please fill in both fields.")
            else:
                account = _db_user(u)
                if account and password_matches(account[3], p):
                    st.session_state.user_id = account[0]
                    st.session_state.username = account[2]
                    st.session_state.is_logged_in = True
                    st.session_state.selected_gateway = False
                    saved = _db_load_state(st.session_state.user_id)
                    for key, value in saved.items():
                        st.session_state[key] = value
                    st.session_state.recruiter_data = _db_load_recruiter_state(st.session_state.user_id)
                    st.session_state.recruiter_candidates = st.session_state.recruiter_data.get("candidates", [])
                    st.session_state.recruiter_assessment_submissions = {
                        x.get("token", str(i)): x
                        for i, x in enumerate(st.session_state.recruiter_data.get("submissions", []))
                        if isinstance(x, dict)
                    }
                    log_event("LOGIN", st.session_state.username, "N/A", "User Login")
                    st.rerun()
                elif ADMIN_PIN and u.lower() == "admin" and p == ADMIN_PIN:
                    st.session_state.user_id = "admin"
                    st.session_state.username = "Administrator"
                    st.session_state.is_logged_in = True
                    st.session_state.selected_gateway = True
                    st.session_state.active_workspace = "Recruiter Workspace"
                    st.rerun()
                else:
                    st.error("Invalid credentials. Please register or verify your details.")

    with tab_auth2:
        reg_n = st.text_input("Full Name", key="auth_reg_n")
        reg_u = st.text_input("Choose Username / Email", key="auth_reg_u")
        reg_p = st.text_input("Create Password", type="password", key="auth_reg_p")
        if st.button("Create Account", use_container_width=True, key="btn_confirm_reg", type="primary"):
            if not reg_u or not reg_p:
                st.warning("Username and password are required.")
            else:
                if _db_user(reg_u):
                    st.error("That username or email is already registered. Please sign in.")
                else:
                    try:
                        uid = _db_create_user(reg_u, reg_n, hash_password(reg_p))
                        st.session_state.user_id = uid
                        st.session_state.username = reg_n.strip() if reg_n.strip() else reg_u.split("@")[0].capitalize()
                        st.session_state.is_logged_in = True
                        st.session_state.selected_gateway = False
                        st.session_state.recruiter_data = _db_load_recruiter_state(uid)
                        st.session_state.recruiter_candidates = []
                        st.session_state.recruiter_assessment_submissions = {}
                        _db_save_state(uid, {"username": st.session_state.username, "resume_text": "", "resume_analysis": None, "job_match_result": None, "resume_builder": {}})
                        log_event("REGISTER", st.session_state.username, "N/A", f"Registered: {reg_u}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("That username or email is already registered. Please sign in.")


# ============================================================
# 1. LANDING & ACCESS SCREEN
# ============================================================
if not st.session_state.is_logged_in:
    # IMPORTANT: Keep the complete landing HTML inside ONE st.markdown()
    # call with unsafe_allow_html=True. If these tags are placed outside
    # the markdown string, Streamlit will display the HTML as plain text.
    _access_action = str(st.query_params.get("access", "") or "").strip().lower()

    if _access_action:
        try:
            del st.query_params["access"]
        except Exception:
            pass

        if _access_action == "signin":
            dialog_auth(default_tab=0)
        elif _access_action == "register":
            dialog_auth(default_tab=1)
        elif _access_action == "guest":
            st.session_state.user_id = ""
            st.session_state.username = "Guest Explorer"
            st.session_state.is_logged_in = True
            st.session_state.resume_text = ""
            st.session_state.resume_analysis = None
            st.session_state.job_match_result = None
            st.session_state.resume_builder = {}
            st.session_state.recruiter_data = {
                "campaign": None,
                "candidates": [],
                "assessments": [],
                "submissions": [],
            }
            st.session_state.recruiter_candidates = []
            st.session_state.recruiter_assessment_submissions = {}
            st.session_state.selected_gateway = False
            log_event("GUEST_ACCESS", "Guest", "N/A", "Guest entry")
            st.rerun()

    st.markdown("""
    <div class="landing-frame">
      <div class="landing-content">
        <div class="landing-nav">
          <div class="landing-brand">✦ CareerLens <span>AI</span></div>
          <div class="landing-links"><span class="landing-link">Features</span><span class="landing-link">Intelligence</span><span class="landing-link">Recruiting</span></div>
        </div>
        <div class="landing-kicker">✦ AI POWERED CAREER PLATFORM</div>
        <div class="landing-title">Understand Your Career.<br>Build Your <span class="landing-gradient">Future.</span></div>
        <div class="landing-copy">Get personalized insights, intelligent recommendations, and enterprise screening tools all in one unified ecosystem.</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    f1, f2, f3 = st.columns(3, gap="medium")
    with f1:
        st.markdown('<div class="landing-feature"><div class="landing-icon">🧠</div><div class="landing-feature-title">AI-Powered Insights</div><div class="landing-feature-text">Smarter career decisions</div></div>', unsafe_allow_html=True)
    with f2:
        st.markdown('<div class="landing-feature"><div class="landing-icon">🧭</div><div class="landing-feature-title">Personalized Roadmaps</div><div class="landing-feature-text">Your goals, our guidance</div></div>', unsafe_allow_html=True)
    with f3:
        st.markdown('<div class="landing-feature"><div class="landing-icon">🛡️</div><div class="landing-feature-title">Trusted &amp; Secure</div><div class="landing-feature-text">Your data stays safe</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="landing-access"><div class="landing-access-title">✦ Welcome to CareerLens AI</div><div class="landing-access-copy">Sign in, create an account, or explore instantly as a guest.</div><div class="landing-divider"></div></div>', unsafe_allow_html=True)
    a1, a2, a3 = st.columns(3, gap="small")
    with a1:
        if st.button("🔐 Sign In", use_container_width=True, type="primary", key="landing_signin"):
            dialog_auth(default_tab=0)
    with a2:
        if st.button("✨ Register / Create Account", use_container_width=True, key="landing_register"):
            dialog_auth(default_tab=1)
    with a3:
        if st.button("🚀 Explore as Guest", use_container_width=True, key="landing_guest"):
            st.session_state.user_id = ""
            st.session_state.username = "Guest Explorer"
            st.session_state.is_logged_in = True
            st.session_state.resume_text = ""
            st.session_state.resume_analysis = None
            st.session_state.job_match_result = None
            st.session_state.resume_builder = {}
            st.session_state.recruiter_data = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
            st.session_state.recruiter_candidates = []
            st.session_state.recruiter_assessment_submissions = {}
            st.session_state.selected_gateway = False
            log_event("GUEST_ACCESS", "Guest", "N/A", "Guest entry")
            st.rerun()

    st.stop()


# ============================================================
# 2. WORKSPACE GATEWAY PORTAL
# ============================================================
if not st.session_state.selected_gateway:
    st.markdown(
        f"""
        <div class="header-banner">
          <div>
            <div class="header-title">Welcome, {html.escape(st.session_state.username)}! 👋</div>
            <div class="header-sub">Choose your workspace to get started.</div>
          </div>
          <span class="tag-badge tag-blue">AI CAREER ECOSYSTEM</span>
        </div>
        """, unsafe_allow_html=True)
    g1, g2 = st.columns(2, gap="large")
    with g1:
        st.markdown("""
        <div class="gateway-card">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
            <div class="role-icon" style="background:linear-gradient(135deg,#2563eb,#06b6d4);">💼</div>
            <div><h3 style="margin:0;font-size:1.15rem">Job Seeker Portal</h3><span class="tag-badge tag-blue">Candidate Intelligence</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Discover opportunities, improve skills, and accelerate your career with deep AI guidance.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
            ✦ Resume Intelligence &nbsp; ✦ AI Mock Interview<br>✦ Job Match &nbsp; ✦ Salary Insights &nbsp; ✦ Career Roadmap
          </div>
        </div>""", unsafe_allow_html=True)
        if st.button("Continue as Job Seeker →", key="btn_portal_seeker", use_container_width=True, type="primary"):
            st.session_state.active_workspace = "Job Seeker Workspace"
            st.session_state.active_tool = "Dashboard"
            st.session_state.selected_gateway = True
            st.rerun()
    with g2:
        st.markdown("""
        <div class="gateway-card">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
            <div class="role-icon" style="background:linear-gradient(135deg,#7c3aed,#ec4899);">👥</div>
            <div><h3 style="margin:0;font-size:1.15rem">Recruiter Portal</h3><span class="tag-badge tag-purple">Talent Acquisition</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Streamline hiring, screen cohorts at scale, and build high-performing teams with automated assessments.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
            ✦ Bulk Resume Screening &nbsp; ✦ Hiring Campaigns<br>✦ Assessment Dispatcher &nbsp; ✦ Candidate Ranking &nbsp; ✦ Interview Pipeline
          </div>
        </div>""", unsafe_allow_html=True)
        if st.button("Continue as Recruiter →", key="btn_portal_recruiter", use_container_width=True, type="primary"):
            st.session_state.active_workspace = "Recruiter Workspace"
            st.session_state.active_tool = "Dashboard"
            st.session_state.selected_gateway = True
            st.rerun()
    st.stop()


# ============================================================
# 3. SIDEBAR NAVIGATION
# ============================================================
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand-box">
            <div style="font-size: 26px; color: #2563eb;">✨</div>
            <div>
                <div style="font-size: 1.15rem; font-weight: 900; color: #091224; line-height: 1.1;">
                    Career<span style="color: #2563eb;">lens</span> <span style="color: #7c3aed;">AI</span>
                </div>
                <div style="font-size: 0.68rem; color: #64748b; font-weight: 700;">
                    Your Career, Our Intelligence
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="sidebar-user-box">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg, #2563eb, #7c3aed); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800;">
                    👤
                </div>
                <div>
                    <div style="font-size:0.88rem; font-weight:800; color:#1e293b;">{html.escape(st.session_state.username)}</div>
                    <div style="font-size:0.72rem; color:#16a34a; font-weight:700;">● Active User</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="sidebar-section-title">MAIN WORKSPACE</div>', unsafe_allow_html=True)
    is_seeker = st.session_state.active_workspace == "Job Seeker Workspace"
    is_recruiter = st.session_state.active_workspace == "Recruiter Workspace"

    if st.button("👤 Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.button("🏢 Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if is_seeker:
        st.markdown('<div class="sidebar-section-title">CAREER TOOLS</div>', unsafe_allow_html=True)
        seeker_tools = [
            ("📊 Dashboard", "Dashboard"),
            ("📄 Resume Intelligence", "Resume Intelligence"),
            ("📝 Pre-Interview Assessment", "Pre-Interview Assessment"),
            ("🎤 AI Mock Interview", "AI Mock Interview"),
            ("🎯 AI Job Match", "AI Job Match"),
            ("💰 Salary Estimation", "Salary Estimation"),
            ("🗺️ Career Roadmap", "Career Roadmap"),
            ("🛡️ Job Detection", "Real-Time Job Detection"),
            ("📄 Resume Builder", "Resume Builder"),
            ("🤖 AI Assistant", "AI Career Assistant"),
        ]
        for name, key_val in seeker_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_tool_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()
    else:
        st.markdown('<div class="sidebar-section-title">RECRUITER TOOLS</div>', unsafe_allow_html=True)
        rec_tools = [
            ("📊 Recruiter Dashboard", "Dashboard"),
            ("🎯 Hiring Campaign", "Hiring Campaign"),
            ("📤 Bulk Resume Screening", "Bulk Screening"),
            ("🏆 Shortlisted Candidates", "Shortlisted Candidates"),
            ("📝 Assessment Dispatcher", "Assessment Builder"),
            ("📊 Assessment Results", "Score Vault"),
            ("🎤 Interview Pipeline", "Interview Pipeline"),
        ]
        for name, key_val in rec_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                recruiter_navigate(key_val)
                st.rerun()

    st.markdown("<hr style='border-color: rgba(0,0,0,0.06); margin: 20px 0;'>", unsafe_allow_html=True)

    if st.button("🚪 Logout", key="sb_logout_btn", use_container_width=True):
        uid = st.session_state.get("user_id", "")
        if uid:
            try:
                _db_save_state(uid, {
                    "username": st.session_state.username,
                    "resume_text": st.session_state.get("resume_text", ""),
                    "resume_analysis": st.session_state.get("resume_analysis"),
                    "job_match_result": st.session_state.get("job_match_result"),
                    "resume_builder": st.session_state.get("resume_builder", {}),
                })
            except sqlite3.Error:
                pass
        for key in ["is_logged_in", "selected_gateway", "user_id"]:
            st.session_state[key] = False if key != "user_id" else ""
        st.session_state.username = "Guest Explorer"
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.session_state.recruiter_nav_history = ["Dashboard"]
        st.session_state.recruiter_nav_index = 0
        st.session_state.recruiter_selected_ids = []
        st.session_state.resume_text = ""
        st.session_state.resume_analysis = None
        st.session_state.job_match_result = None
        st.session_state.resume_builder = {}
        st.session_state.recruiter_data = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
        st.session_state.recruiter_candidates = []
        st.session_state.recruiter_assessment_submissions = {}
        st.rerun()


# ============================================================
# 4. TOP APP HEADER
# ============================================================
workspace_label = "Job Seeker" if st.session_state.active_workspace == "Job Seeker Workspace" else "Recruiter"
st.markdown(
    f"""
    <div style="background:#fff;border-bottom:1px solid #edf0f6;margin:-4px 0 18px;padding:2px 2px 15px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
      <div>
        <div style="font-weight:900;font-size:1.02rem;color:#0f172a">CareerLens <span style="color:#7c3aed">AI</span></div>
        <div style="font-size:.7rem;color:#64748b">{workspace_label} Workspace · Intelligent Career Decisions</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span style="font-size:.78rem;font-weight:700;color:#334155">{html.escape(st.session_state.username)}</span>
        <span style="width:32px;height:32px;border-radius:50%;background:linear-gradient(135deg,#dbeafe,#f3e8ff);display:flex;align-items:center;justify-content:center;color:#2563eb;font-weight:900;font-size:12px;">●</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 👤 JOB SEEKER DASHBOARD
# ============================================================
if st.session_state.active_workspace == "Job Seeker Workspace":
    analysis = st.session_state.resume_analysis or {}
    resume_score_val = f"{analysis.get('resume_score')}%" if analysis.get('resume_score') is not None else "--"
    readiness_val = f"{analysis.get('readiness')}%" if analysis.get('readiness') is not None else "--"
    market_match_val = f"{st.session_state.job_match_result.get('overall')}%" if st.session_state.job_match_result else "--"
    skills_count_val = str(len(analysis.get('skills', []))) if analysis.get('skills') else "--"
    st.markdown(f'<div class="kpi-grid"><div class="kpi-card"><div class="kpi-icon-badge">📄</div><div><div class="kpi-label">Resume Score</div><div class="kpi-value">{resume_score_val}</div></div></div><div class="kpi-card"><div class="kpi-icon-badge">📈</div><div><div class="kpi-label">Readiness</div><div class="kpi-value">{readiness_val}</div></div></div><div class="kpi-card"><div class="kpi-icon-badge">🎯</div><div><div class="kpi-label">Market Match</div><div class="kpi-value">{market_match_val}</div></div></div><div class="kpi-card"><div class="kpi-icon-badge">💡</div><div><div class="kpi-label">Detected Skills</div><div class="kpi-value">{skills_count_val}</div></div></div></div>', unsafe_allow_html=True)

    def seeker_back():
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.session_state.active_tool == "Dashboard":
        st.markdown("### Career Tools Suite")
        tools=[("📄","Resume Intelligence","Evidence-based resume scoring, skills and improvement plan."),("📝","Pre-Interview Assessment","Generate role-specific assessments for any career."),("🎤","AI Mock Interview","Practice up to 50 questions for any target role."),("🎯","AI Job Match","Compare your resume against any job description."),("💰","Salary Estimation","Estimate compensation using role, experience and skill signals."),("🗺️","Career Roadmap","Build a personalized path for any target career."),("🛡️","Real-Time Job Detection","Analyze a job link and/or description for risk signals."),("📄","Resume Builder","Build a resume with live editing and live preview."),("🤖","AI Career Assistant","Chat naturally about careers, skills, interviews and jobs.")]
        cols=st.columns(3)
        for i,(icon,title,desc) in enumerate(tools):
            with cols[i%3]:
                st.markdown(f'<div class="tool-box-card"><div class="tool-icon-circle">{icon}</div><div class="tool-title">{html.escape(title)}</div><div class="tool-desc">{html.escape(desc)}</div></div>',unsafe_allow_html=True)
                if st.button(f"Open {title}",key=f"seeker_tool_{i}",use_container_width=True): st.session_state.active_tool=title; st.rerun()

    elif st.session_state.active_tool == "Resume Intelligence":
        if st.button("← Back",key="seeker_back_resume"): seeker_back()
        st.markdown("### 📄 Resume Intelligence")
        target_role=st.text_input("Target role (optional)",placeholder="e.g. AI Engineer, Accountant, Civil Engineer",key="resume_target_role")
        uploaded_doc=st.file_uploader("Upload Resume",type=["pdf","docx","txt"],key="resume_upload")
        if uploaded_doc and st.button("Analyze Resume",use_container_width=True,type="primary",key="resume_analyze_btn"):
            with st.spinner("Analyzing resume evidence..."):
                res=api_analyze_resume(uploaded_doc); st.session_state.resume_analysis=res; st.session_state.resume_text=res.get("extracted_text","")
                if target_role.strip() and st.session_state.resume_text:
                    profile=_role_profile(target_role); jd=f"Target role: {target_role}. Required competencies: {', '.join(profile['competencies'])}."
                    match=api_match_job(st.session_state.resume_text,jd); st.session_state.resume_analysis["target_role"]=target_role.strip(); st.session_state.resume_analysis["market_match"]=match.get("overall",0)
                st.rerun()
        if st.session_state.resume_analysis:
            r=st.session_state.resume_analysis; st.markdown(f'<div class="content-box"><h3>{html.escape(r.get("name","Candidate Profile"))}</h3><p>Score <b>{r.get("resume_score",0)}%</b> · Readiness <b>{r.get("readiness",0)}%</b></p></div>',unsafe_allow_html=True)
            a,b,c,d=st.columns(4); a.metric("Resume Score",f"{r.get('resume_score',0)}%"); b.metric("Readiness",f"{r.get('readiness',0)}%"); c.metric("Market Match",f"{r.get('market_match')}%" if r.get('market_match') is not None else "—"); d.metric("Skills",len(r.get("skills",[])))
            st.markdown("#### Detected Skills"); st.write(", ".join(r.get("skills",[])) or "No skills confidently detected.")
            if r.get("score_breakdown"): st.markdown("#### Score Breakdown"); st.json(r["score_breakdown"])
            st.markdown("#### Strengths"); [st.success(x) for x in r.get("strengths",[])]
            st.markdown("#### Improvement Plan"); [st.warning(x) for x in r.get("recommendations",[])]

    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back",key="seeker_back_exam"): seeker_back()
        st.markdown("### 📝 Pre-Interview Assessment")
        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:
            role=st.text_input("Search / enter any job role",placeholder="e.g. AI Engineer, HR Manager, Mechanical Engineer",key="assessment_role_any")
            question_count=st.select_slider("Questions",options=list(range(10,51,5)),value=20,key="assessment_count_any")
            if st.button("🚀 Start Assessment",use_container_width=True,type="primary",key="start_assessment_any"):
                if not role.strip(): st.warning("Enter a target role first.")
                else:
                    st.session_state.assessment_questions=generate_assessment_questions(role.strip(),question_count); st.session_state.assessment_role=role.strip(); st.session_state.assessment_answers={}; st.session_state.assessment_active=True; st.session_state.assessment_review=False; st.session_state.assessment_result=None; st.rerun()
        elif st.session_state.assessment_active and not st.session_state.assessment_review:
            qs=st.session_state.assessment_questions
            with st.form("assessment_answer_form"):
                for q in qs:
                    st.markdown(f"**{q['id']}. {q['question']}**"); st.radio("",q["options"],key=f"assessment_q_{q['id']}",index=None)
                submit=st.form_submit_button("Review Answers",use_container_width=True,type="primary")
            if submit:
                st.session_state.assessment_answers={q["id"]:st.session_state.get(f"assessment_q_{q['id']}") for q in qs}; st.session_state.assessment_review=True; st.rerun()
        elif st.session_state.assessment_review:
            st.markdown(f"### Review — {html.escape(st.session_state.assessment_role)}")
            for q in st.session_state.assessment_questions: st.write(f"**{q['id']}.** {st.session_state.assessment_answers.get(q['id']) or 'Unanswered'}")
            c1,c2=st.columns(2)
            if c1.button("← Change Answers",use_container_width=True): st.session_state.assessment_review=False; st.rerun()
            if c2.button("Submit Assessment",use_container_width=True,type="primary"):
                st.session_state.assessment_result=assessment_result(st.session_state.assessment_questions,st.session_state.assessment_answers); st.session_state.assessment_active=False; st.rerun()
        elif st.session_state.assessment_result:
            result=st.session_state.assessment_result; st.metric("Assessment Score",f"{result.get('percentage',0)}%"); st.write(result.get("feedback","Assessment completed."))
            if st.button("Take Another Assessment",use_container_width=True): st.session_state.assessment_result=None; st.rerun()

    elif st.session_state.active_tool == "AI Mock Interview":
        if st.button("← Back",key="seeker_back_mock"): seeker_back()
        st.markdown("### 🎤 AI Mock Interview")
        if not st.session_state.interview_active and not st.session_state.interview_completed:
            role=st.text_input("Search / enter interview role",placeholder="e.g. AI Engineer, Product Manager, Nurse",key="mock_role_any")
            count=st.select_slider("Interview questions",options=list(range(10,51,5)),value=20,key="mock_count_any")
            if st.button("Start Mock Interview",use_container_width=True,type="primary",key="start_mock_any"):
                if not role.strip(): st.warning("Enter an interview role first.")
                else:
                    profile=_role_profile(role); qs=[]
                    templates=["Tell me about your experience relevant to {c} in a {r} role.","Describe a challenging {c} problem you would expect in a {r} role and how you would solve it.","What tools or methods do you use to improve {c} as a {r}?","Give an example of a measurable result you would aim for as a {r} professional.","How would you explain a difficult {c} decision to a stakeholder?"]
                    for i in range(count): qs.append(templates[i%len(templates)].format(c=profile["competencies"][i%len(profile["competencies"])],r=role.strip()))
                    st.session_state.interview_questions=qs; st.session_state.interview_role=role.strip(); st.session_state.interview_current_idx=0; st.session_state.interview_transcript=[]; st.session_state.interview_active=True; st.session_state.interview_completed=False; st.session_state.interview_report=None; st.rerun()
        elif st.session_state.interview_active:
            idx=st.session_state.interview_current_idx; total=len(st.session_state.interview_questions); q=st.session_state.interview_questions[idx]; st.progress(idx/max(1,total),text=f"Question {idx+1} of {total}"); st.markdown(f"### {q}"); answer=st.text_area("Your answer",height=180,key=f"mock_answer_{idx}")
            if st.button("Submit & Next →",use_container_width=True,type="primary",key=f"mock_submit_{idx}"):
                if not answer.strip(): st.warning("Please answer before continuing.")
                else:
                    st.session_state.interview_transcript.append({"question":q,"answer":answer.strip()})
                    if idx+1<total: st.session_state.interview_current_idx+=1; st.rerun()
                    else:
                        scores=[min(100,round(45+min(len(x["answer"].split()),120)*0.45)) for x in st.session_state.interview_transcript]; avg=round(sum(scores)/max(1,len(scores)))
                        st.session_state.interview_report={"overall":avg,"confidence":min(100,avg+3),"communication":min(100,avg+5),"strengths":["Completed the selected interview length","Provided responses across role competencies"],"improvements":["Add specific examples and measurable outcomes","Use a clear situation-action-result structure"]}; st.session_state.interview_active=False; st.session_state.interview_completed=True; st.rerun()
        else:
            rep=st.session_state.interview_report or {}; st.metric("Interview Readiness",f"{rep.get('overall',0)}%"); [st.success(x) for x in rep.get("strengths",[])]; [st.warning(x) for x in rep.get("improvements",[])]
            if st.button("Practice Another Interview",use_container_width=True): st.session_state.interview_completed=False; st.rerun()

    elif st.session_state.active_tool == "AI Job Match":
        if st.button("← Back",key="seeker_back_match"): seeker_back()
        st.markdown("### 🎯 AI Job Match"); jd=st.text_area("Paste the full job description",height=240,key="job_match_jd")
        if st.button("Analyze Job Match",use_container_width=True,type="primary"):
            if not st.session_state.resume_text: st.warning("Upload a resume in Resume Intelligence first.")
            elif not jd.strip(): st.warning("Paste a job description first.")
            else: st.session_state.job_match_result=api_match_job(st.session_state.resume_text,jd); st.rerun()
        if st.session_state.job_match_result:
            m=st.session_state.job_match_result; st.metric("Match Score",f"{m.get('overall',0)}%"); st.write(m.get("summary","")); st.success("Matched: "+(", ".join(m.get("matched",[])) or "None detected")); st.warning("Missing: "+(", ".join(m.get("missing",[])) or "None detected"))

    elif st.session_state.active_tool == "Salary Estimation":
        if st.button("← Back",key="seeker_back_salary"): seeker_back()
        st.markdown("### 💰 Salary Estimation"); role=st.text_input("Job role",placeholder="Any job role",key="salary_role"); exp=st.selectbox("Experience",["0–2 years","3–5 years","6–10 years","10+ years"],key="salary_exp"); location=st.text_input("Location",value="India",key="salary_location"); skills=st.text_input("Key skills (optional)",value=", ".join(analysis.get("skills",[])[:12]),key="salary_skills")
        if st.button("Estimate Market Range",use_container_width=True,type="primary"):
            if not role.strip(): st.warning("Enter a role first.")
            else:
                bands={"software":(5,10,18),"ai_data":(6,12,24),"cybersecurity":(5,11,22),"design":(4,8,16),"business":(5,10,20),"sales_marketing":(4,8,18),"finance":(4,8,18),"hr":(4,8,16),"engineering":(3.5,7,16),"healthcare":(3,7,15),"education":(3,6,12),"legal":(4,9,20),"general":(3,7,15)}; lo,mid,hi=bands[_role_profile(role)["family"]]; mult={"0–2 years":1,"3–5 years":1.25,"6–10 years":1.55,"10+ years":1.9}[exp]; bonus=min(.25,len([x for x in skills.split(',') if x.strip()])); lo,mid,hi=[round(x*mult*(1+bonus),1) for x in (lo,mid,hi)]; st.session_state.salary_result={"low":lo,"median":mid,"high":hi,"role":role.strip(),"experience":exp,"location":location.strip() or "India"}
        if st.session_state.get("salary_result"):
            sr=st.session_state.salary_result; st.metric("Estimated annual range",f"₹{sr['low']}–₹{sr['high']} LPA"); st.write(f"Indicative midpoint: ₹{sr['median']} LPA · {sr['role']} · {sr['experience']} · {sr['location']}"); st.caption("Indicative estimate only; connect a verified market-data provider before using it as a current compensation benchmark.")

    elif st.session_state.active_tool == "Career Roadmap":
        if st.button("← Back",key="seeker_back_roadmap"): seeker_back()
        st.markdown("### 🗺️ Career Roadmap"); role=st.text_input("Target career / role",placeholder="Any role",key="roadmap_role")
        if st.button("Generate Roadmap",use_container_width=True,type="primary"):
            if not role.strip(): st.warning("Enter a target role first.")
            else: st.session_state.roadmap_result=api_career_roadmap(st.session_state.resume_text,role.strip()); st.rerun()
        if st.session_state.get("roadmap_result"):
            rm=st.session_state.roadmap_result; st.write(f"Target: **{rm.get('target_role',role)}**")
            for i,step in enumerate(rm.get("steps",[]),1): st.markdown(f"**Phase {i}.** {step}")
            if rm.get("current_skills"): st.success("Current skills: "+", ".join(rm["current_skills"]))

    elif st.session_state.active_tool == "Real-Time Job Detection":
        if st.button("← Back",key="seeker_back_detect"): seeker_back()
        st.markdown("### 🛡️ Job Detection"); job_url=st.text_input("Job / Offer Link (optional)",placeholder="https://company.com/jobs/...",key="detect_url"); description=st.text_area("Job Description (optional)",height=240,key="detect_description")
        if st.button("🔍 Analyze Job",use_container_width=True,type="primary",key="detect_both"):
            if not job_url.strip() and not description.strip(): st.warning("Provide a job link, job description, or both.")
            else:
                with st.spinner("Analyzing job safety signals..."):
                    source_text=description.strip()
                    if job_url.strip(): source_text=(source_text+"\n"+fetch_public_job_url(job_url.strip())).strip()
                    st.session_state.job_detection_result=api_detect_fraud(source_text); st.rerun()
        if st.session_state.job_detection_result:
            rr=st.session_state.job_detection_result; st.metric("Risk Score",f"{rr.get('score',0)}/100"); st.write(f"Risk level: **{rr.get('level','UNKNOWN')}**"); [st.warning(x) for x in rr.get("signal_details",[])]

    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back",key="seeker_back_builder"): seeker_back()
        st.markdown("### 📄 Live Resume Builder"); templates=["Executive","Minimal","Modern Blue","Modern Purple","Emerald","Professional","Tech","ATS Classic"]; template=st.selectbox("Template",templates,key="builder_template")
        left,right=st.columns([1,1.2])
        with left:
            data0=st.session_state.get("resume_builder") or {}; name=st.text_input("Full name",value=data0.get("name",st.session_state.get("username","")),key="rb_name"); email=st.text_input("Email",value=data0.get("email",""),key="rb_email"); phone=st.text_input("Phone",value=data0.get("phone",""),key="rb_phone"); headline=st.text_input("Professional headline",value=data0.get("headline",""),key="rb_headline"); summary=st.text_area("Professional summary",value=data0.get("summary",""),height=110,key="rb_summary"); skills=st.text_area("Skills (comma-separated)",value=data0.get("skills",""),height=90,key="rb_skills"); experience=st.text_area("Experience",value=data0.get("experience",""),height=120,key="rb_experience"); education=st.text_area("Education",value=data0.get("education",""),height=100,key="rb_education"); projects=st.text_area("Projects",value=data0.get("projects",""),height=100,key="rb_projects"); certifications=st.text_area("Certifications",value=data0.get("certifications",""),height=90,key="rb_certifications")
            data={"name":name,"email":email,"phone":phone,"headline":headline,"summary":summary,"skills":skills,"experience":experience,"education":education,"projects":projects,"certifications":certifications}; st.session_state.resume_builder=data; pdf=build_resume_pdf(data,template); st.download_button("⬇️ Download PDF",data=pdf,file_name="CareerLens_Resume.pdf",mime="application/pdf",use_container_width=True)
        with right:
            preview=f'<div style="background:white;padding:28px;border:1px solid #e2e8f0;border-radius:12px;min-height:760px;color:#0f172a;"><h1>{html.escape(name or "Your Name")}</h1><p><b>{html.escape(headline)}</b></p><p style="color:#64748b;">{html.escape(email)}{(" · "+html.escape(phone)) if phone else ""}</p><hr><h3>Professional Summary</h3><p>{html.escape(summary or "Add your summary")}</p><h3>Skills</h3><p>{html.escape(skills or "Add your skills")}</p><h3>Experience</h3><p style="white-space:pre-wrap;">{html.escape(experience or "Add experience")}</p><h3>Projects</h3><p style="white-space:pre-wrap;">{html.escape(projects or "Add projects")}</p><h3>Education</h3><p style="white-space:pre-wrap;">{html.escape(education or "Add education")}</p><h3>Certifications</h3><p style="white-space:pre-wrap;">{html.escape(certifications or "Add certifications")}</p></div>'
            st.markdown("#### Live Preview"); st.markdown(preview,unsafe_allow_html=True)

    elif st.session_state.active_tool == "AI Career Assistant":
        if st.button("← Back",key="seeker_back_assistant"): seeker_back()
        st.markdown("### 🤖 AI Career Assistant")
        for msg in st.session_state.assistant_messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
        prompt=st.chat_input("Ask anything about careers, skills, interviews, jobs, salary or your resume...")
        if prompt:
            st.session_state.assistant_messages.append({"role":"user","content":prompt})
            answer=api_chat_assistant(st.session_state.assistant_messages,resume_context=st.session_state.resume_text); st.session_state.assistant_messages.append({"role":"assistant","content":answer}); st.rerun()

# ============================================================
# 🏢 RECRUITER WORKSPACE
# ============================================================
elif st.session_state.active_workspace == "Recruiter Workspace":
    data = st.session_state.recruiter_data
    candidates = st.session_state.recruiter_candidates
    submissions = list(st.session_state.recruiter_assessment_submissions.values())
    campaign = data.get("campaign") or {}

    def persist_recruiter():
        data["candidates"] = st.session_state.recruiter_candidates
        data["submissions"] = list(st.session_state.recruiter_assessment_submissions.values())
        st.session_state.recruiter_data = data
        _save_recruiter_data(data)

    if st.session_state.active_tool not in RECRUITER_TOOLS:
        recruiter_navigate("Dashboard", record_history=False)

    nav_index = int(st.session_state.get("recruiter_nav_index", 0))
    nav_history = st.session_state.get("recruiter_nav_history", ["Dashboard"])
    can_back = nav_index > 0
    can_forward = nav_index < len(nav_history) - 1

    nav1, nav2, nav3, nav4 = st.columns([0.8, 0.8, 3.6, 1.2])
    with nav1:
        if st.button("← Back", disabled=not can_back, use_container_width=True, key="rec_back_btn"):
            recruiter_go_back()
            st.rerun()
    with nav2:
        if st.button("Forward →", disabled=not can_forward, use_container_width=True, key="rec_forward_btn"):
            recruiter_go_forward()
            st.rerun()
    with nav3:
        st.caption(f"Recruiter workflow • {st.session_state.active_tool}")
    with nav4:
        if st.button("🏠 Dashboard", use_container_width=True, key="rec_home_btn"):
            recruiter_navigate("Dashboard")
            st.rerun()

    if st.session_state.active_tool == "Dashboard":
        st.markdown("### 🏢 Recruiter Dashboard")
        st.markdown("""<div class="recruiter-command"><div class="recruiter-command-icon">👥</div><div><div class="recruiter-command-title">Talent Command Center</div><div class="recruiter-command-copy">Screen, shortlist, assess, and move candidates through your hiring pipeline.</div></div></div>""", unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Candidates Screened", len(candidates))
        k2.metric("Shortlisted", sum(1 for c in candidates if c.get("status") == "Shortlisted"))
        k3.metric("Assessments Sent", sum(1 for c in candidates if c.get("assessment_status") == "Sent"))
        k4.metric("Completed Assessments", len(submissions))
        st.markdown("#### Actions")
        c1, c2, c3 = st.columns(3)
        if c1.button("🎯 Setup Campaign", use_container_width=True, key="rec_action_campaign"):
            recruiter_navigate("Hiring Campaign")
            st.rerun()
        if c2.button("📤 Screen Resumes", use_container_width=True, key="rec_action_screen"):
            recruiter_navigate("Bulk Screening")
            st.rerun()
        if c3.button("✉️ Dispatch Assessments", use_container_width=True, key="rec_action_dispatch"):
            recruiter_navigate("Assessment Builder")
            st.rerun()

    elif st.session_state.active_tool == "Hiring Campaign":
        st.markdown("### 🎯 Hiring Campaign")
        role_options = IT_ROLES + NON_IT_ROLES
        saved_role = campaign.get("role", role_options[0])
        role_index = role_options.index(saved_role) if saved_role in role_options else 0
        role = st.selectbox("Target Role", role_options, index=role_index, key="campaign_role")
        job_description = st.text_area(
            "Job Description / Assessment Context",
            value=campaign.get("job_description", ""),
            height=160,
            key="campaign_job_description",
        )
        if st.button("💾 Save Campaign", type="primary", use_container_width=True, key="save_campaign"):
            data["campaign"] = {"role": role, "job_description": job_description.strip()}
            persist_recruiter()
            st.success("Campaign configured successfully.")

    elif st.session_state.active_tool == "Bulk Screening":
        st.markdown("### 📤 Bulk Resume Screening")
        st.caption("Upload candidates. CareerLens extracts real contact details, ranks candidates, and removes duplicate candidates.")
        files = st.file_uploader(
            "Upload candidate resumes",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="recruiter_bulk_files",
        )
        if files and st.button("⚡ Screen All Resumes", type="primary", use_container_width=True, key="screen_all_resumes"):
            campaign_jd = campaign.get("job_description", "")
            if not campaign_jd.strip():
                st.warning("Create and save a hiring campaign with a job description before screening resumes.")
            else:
                processed = []
                with st.spinner(f"Screening {len(files)} resume(s)…"):
                    for f in files:
                        try:
                            profile = api_analyze_resume(f)
                            r_text = profile.get("extracted_text", "")
                            match = normalize_job_match(api_match_job(r_text, campaign_jd))
                            email = (profile.get("email") or extract_email_from_text(r_text) or "").strip().lower()
                            phone = (profile.get("phone") or extract_phone_from_text(r_text) or "").strip()
                            name = profile.get("name") or Path(f.name).stem.replace("_", " ").replace("-", " ").title()
                            processed.append({
                                "id": uuid.uuid4().hex[:16],
                                "name": name,
                                "email": email,
                                "phone": phone,
                                "resume_score": profile.get("resume_score", 0),
                                "role_match": match.get("overall", 0),
                                "status": "Screened",
                                "assessment_status": "Not Sent",
                                "email_status": "Found" if email else "Missing",
                                "skills": profile.get("skills", []),
                                "missing_skills": match.get("missing", []),
                                "source_file": f.name,
                            })
                        except Exception as exc:
                            st.warning(f"Could not process {f.name}: {exc}")
                processed = dedupe_candidates(processed)
                processed.sort(key=lambda c: float(c.get("role_match", 0)), reverse=True)
                st.session_state.recruiter_candidates = processed
                st.session_state.recruiter_selected_ids = []
                persist_recruiter()
                st.success(f"Screened {len(processed)} unique candidate(s).")
                st.rerun()

        candidates = st.session_state.recruiter_candidates
        if candidates:
            selected_ids = set(st.session_state.get("recruiter_selected_ids", []))
            st.markdown("#### Candidate Selection")
            a1, a2, a3, a4 = st.columns(4)
            if a1.button("☑️ Select All", use_container_width=True, key="select_all_candidates"):
                st.session_state.recruiter_selected_ids = [c.get("id") for c in candidates if c.get("id")]
                st.rerun()
            if a2.button("☐ Clear Selection", use_container_width=True, key="clear_candidate_selection"):
                st.session_state.recruiter_selected_ids = []
                st.rerun()
            if a3.button("🏆 Shortlist Selected", type="primary", use_container_width=True, key="shortlist_selected"):
                if not selected_ids:
                    st.warning("Select at least one candidate first.")
                else:
                    for candidate in candidates:
                        if candidate.get("id") in selected_ids:
                            candidate["status"] = "Shortlisted"
                    persist_recruiter()
                    st.success(f"Shortlisted {len(selected_ids)} candidate(s).")
                    st.rerun()
            if a4.button("➡️ Shortlist Page", use_container_width=True, key="go_shortlist"):
                recruiter_navigate("Shortlisted Candidates")
                st.rerun()

            st.caption(f"Selected: {len(selected_ids)} • Shortlisted: {sum(1 for c in candidates if c.get('status') == 'Shortlisted')} • Unique: {len(candidates)}")
            for idx, candidate in enumerate(candidates):
                cid = candidate.get("id", str(idx))
                default = cid in selected_ids
                check = st.checkbox(
                    f"{candidate.get('name', 'Candidate')} · {candidate.get('role_match', 0)}% match · {candidate.get('email') or 'Email Missing'}",
                    value=default,
                    key=f"bulk_select_{cid}",
                )
                if check:
                    selected_ids.add(cid)
                else:
                    selected_ids.discard(cid)
                badge = "Shortlisted" if candidate.get("status") == "Shortlisted" else "Screened"
                email_label = candidate.get("email") or "Email Missing"
                st.markdown(
                    f"<div class='content-box' style='padding:12px 16px;margin-bottom:8px;'>"
                    f"<b>{html.escape(str(candidate.get('name') or 'Candidate'))}</b>"
                    f" &nbsp;·&nbsp; Match <b>{candidate.get('role_match', 0)}%</b>"
                    f" &nbsp;·&nbsp; Resume {candidate.get('resume_score', 0)}"
                    f" &nbsp;·&nbsp; 📧 {html.escape(str(email_label))}"
                    f" &nbsp;·&nbsp; <span class='tag-badge tag-blue'>{badge}</span></div>",
                    unsafe_allow_html=True,
                )
            st.session_state.recruiter_selected_ids = list(selected_ids)

    elif st.session_state.active_tool == "Shortlisted Candidates":
        st.markdown("### 🏆 Shortlisted Candidates")
        shortlisted = [c for c in candidates if c.get("status") == "Shortlisted"]
        if not shortlisted:
            st.info("No candidates are shortlisted yet. Go to Bulk Resume Screening and select candidates.")
        else:
            table = pd.DataFrame([
                {
                    "Name": c.get("name"),
                    "Email": c.get("email") or "Email Missing",
                    "Match": f"{c.get('role_match', 0)}%",
                    "Email Status": c.get("email_status", "Missing"),
                    "Assessment": c.get("assessment_status", "Not Sent"),
                }
                for c in shortlisted
            ])
            st.dataframe(table, use_container_width=True, hide_index=True)
            b1, b2 = st.columns(2)
            if b1.button("⬅️ Back to Bulk Screening", use_container_width=True, key="shortlist_back"):
                recruiter_navigate("Bulk Screening")
                st.rerun()
            if b2.button("Proceed to Assessment Dispatcher →", type="primary", use_container_width=True, key="shortlist_next"):
                recruiter_navigate("Assessment Builder")
                st.rerun()

    elif st.session_state.active_tool == "Assessment Builder":
        st.markdown("### 📝 Assessment Dispatcher")
        shortlisted = [c for c in candidates if c.get("status") == "Shortlisted"]
        eligible = []
        seen_emails = set()
        for candidate in shortlisted:
            email = (candidate.get("email") or "").strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            eligible.append(candidate)

        role_target = campaign.get("role", "Software Developer")
        st.write(f"Target Role: **{role_target}**")
        st.metric("Shortlisted", len(shortlisted))
        st.metric("Ready to Email", len(eligible))

        if eligible:
            st.dataframe(
                pd.DataFrame([{"Candidate": c.get("name"), "Email": c.get("email"), "Match": c.get("role_match", 0)} for c in eligible]),
                use_container_width=True,
                hide_index=True,
            )
            if st.button("✉️ Send Assessment Invitations", type="primary", use_container_width=True, key="send_assessment_invitations"):
                progress = st.progress(0, text="Dispatching assessment emails…")
                rows = []
                for idx, candidate in enumerate(eligible):
                    token = _make_assessment_token()
                    test_link = _assessment_public_url(token)
                    sent, msg = api_send_assessment_email(candidate["email"], candidate.get("name", "Candidate"), role_target, test_link)
                    candidate["assessment_token"] = token
                    candidate["assessment_link"] = test_link
                    candidate["assessment_status"] = "Sent" if sent else "Failed"
                    if sent:
                        candidate["status"] = "Assessment Sent"
                    rows.append({
                        "Candidate": candidate.get("name"),
                        "Email": candidate.get("email"),
                        "Status": "Sent" if sent else "Failed",
                        "Details": msg,
                    })
                    progress.progress((idx + 1) / max(1, len(eligible)))

                data.setdefault("assessments", []).append({
                    "id": uuid.uuid4().hex,
                    "role": role_target,
                    "questions": generate_assessment_questions(role_target, 20),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "candidate_tokens": {c["id"]: c.get("assessment_token") for c in eligible},
                })
                persist_recruiter()
                st.success("Assessment dispatch completed.")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No shortlisted candidates with valid emails found.")

    elif st.session_state.active_tool == "Score Vault":
        st.markdown("### 📊 Assessment Score Vault")
        if not submissions:
            st.info("No assessment submissions recorded yet.")
        else:
            st.dataframe(pd.DataFrame(submissions), use_container_width=True, hide_index=True)

    elif st.session_state.active_tool == "Interview Pipeline":
        st.markdown("### 🎤 Interview Pipeline")
        if candidates:
            st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)
        else:
            st.info("No candidates in the pipeline yet.")


# ============================================================
# STATE PERSISTENCE & FOOTER
# ============================================================
def _persist_current_user_state():
    uid = st.session_state.get("user_id", "")
    if not uid:
        return
    try:
        _db_save_state(uid, {
            "username": st.session_state.get("username", ""),
            "resume_text": st.session_state.get("resume_text", ""),
            "resume_analysis": st.session_state.get("resume_analysis"),
            "job_match_result": st.session_state.get("job_match_result"),
            "resume_builder": st.session_state.get("resume_builder", {}),
        })
    except (sqlite3.Error, TypeError, ValueError):
        pass


_persist_current_user_state()

st.markdown(
    """
    <div style="text-align: center; color: #94a3b8; font-size: 0.82rem; padding: 40px 0 10px;">
        © 2026 CareerLens AI. All rights reserved.
    </div>
    """,
    unsafe_allow_html=True,
)
