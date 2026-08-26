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
API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com").rstrip("/")[span_0](start_span)[span_0](end_span)
ANALYTICS_FILE = "analytics.csv[span_1](start_span)"[span_1](end_span)
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")[span_2](start_span)[span_2](end_span)
ADMIN_PIN = os.getenv("ADMIN_PIN", "")[span_3](start_span)[span_3](end_span)
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8501").rstrip("/")[span_4](start_span)[span_4](end_span)

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)[span_5](start_span)[span_5](end_span)

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
    return conn.execute("SELECT user_id, username, display_name, password_hash FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()


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
      --grad-nav-border: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
      --grad-subtle: linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 100%);
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
    
    /* Layout Container Scaling */
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

    /* Gradient UI & Navigation Buttons */
    .stButton>button {
      border-radius: 12px !important;
      border: 1px solid #e2e8f0 !important;
      background: #ffffff !important;
      color: #1e293b !important;
      font-weight: 700 !important;
      font-size: clamp(0.8rem, 1.1vw, 0.92rem) !important;
      padding: clamp(8px, 1.5vw, 12px) clamp(14px, 2vw, 20px) !important;
      min-height: 44px !important;
      box-shadow: var(--shadow-sm) !important;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton>button:hover {
      border-color: #3b82f6 !important;
      color: #2563eb !important;
      background: var(--grad-nav-active) !important;
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

    /* Sidebar Navigation with Radiant Gradient Accents */
    [data-testid="stSidebar"] {
      background: #ffffff !important;
      border-right: 1px solid #e2e8f0 !important;
      box-shadow: 6px 0 24px rgba(15, 23, 42, 0.03) !important;
    }
    [data-testid="stSidebar"]>div:first-child {
      padding: clamp(14px, 2vw, 22px) clamp(10px, 1.5vw, 16px) !important;
    }
    [data-testid="stSidebar"] .stButton>button {
      background: transparent !important;
      color: #475569 !important;
      border: 1px solid transparent !important;
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
      background: var(--grad-nav-active) !important;
      color: #2563eb !important;
      border-color: #dbeafe !important;
      transform: translateX(3px) !important;
    }
    [data-testid="stSidebar"] .stButton>button[kind="primary"] {
      background: var(--grad-nav-active) !important;
      color: #2563eb !important;
      border: 1px solid #bfdbfe !important;
      font-weight: 800 !important;
      box-shadow: 0 3px 12px rgba(37, 99, 235, 0.12) !important;
      position: relative;
    }
    [data-testid="stSidebar"] .stButton>button[kind="primary"] * {
      color: #1d4ed8 !important;
      -webkit-text-fill-color: #1d4ed8 !important;
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

    /* KPI Grid - Responsive Grid System */
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
      background: #ffffff;
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

    /* ========================================================
       MEDIA QUERIES FOR TABLET & MOBILE RESPONSIVENESS
       ======================================================== */
    
    /* Tablet Views (max-width: 1024px) */
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

    /* Mobile Phones (max-width: 768px) */
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

    /* Ultra-compact screens (max-width: 480px) */
    @media (max-width: 480px) {
      .kpi-grid { grid-template-columns: 1fr; }
      .hero-stats { grid-template-columns: 1fr; }
      .hero-stat { flex-direction: row; text-align: left; padding: 10px 12px; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# API CALLS & LOCAL FALLBACKS
# ============================================================
def _extract_resume_text(file) -> str:
    data = file.getvalue()[span_6](start_span)[span_6](end_span)
    name = (file.name or "").lower()[span_7](start_span)[span_7](end_span)
    try:
        if name.endswith(".pdf"):[span_8](start_span)[span_8](end_span)
            from PyPDF2 import PdfReader[span_9](start_span)[span_9](end_span)
            reader = PdfReader(io.BytesIO(data))[span_10](start_span)[span_10](end_span)
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()[span_11](start_span)[span_11](end_span)
        if name.endswith(".docx"):[span_12](start_span)[span_12](end_span)
            from docx import Document[span_13](start_span)[span_13](end_span)
            doc = Document(io.BytesIO(data))[span_14](start_span)[span_14](end_span)
            return "\n".join(p.text for p in doc.paragraphs).strip()[span_15](start_span)[span_15](end_span)
        return data.decode("utf-8", errors="ignore").strip()[span_16](start_span)[span_16](end_span)
    except Exception:
        return "[span_17](start_span)"[span_17](end_span)


def _local_resume_analysis(text: str, filename: str) -> Dict[str, Any]:
    lower = text.lower()[span_18](start_span)[span_18](end_span)
    skill_catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask",
        "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws", "azure", "gcp", "git",
        "linux", "machine learning", "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow",
        "pytorch", "rest api", "graphql", "redis", "kafka", "system design", "html", "css", "figma",
        "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium", "communication",
        "leadership", "problem solving",
    ][span_19](start_span)[span_19](end_span)
    skills = [skill for skill in skill_catalog if skill in lower][span_20](start_span)[span_20](end_span)
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)[span_21](start_span)[span_21](end_span)
    section_hits = sum(1 for section in ["experience", "education", "projects", "skills", "certifications"] if section in lower)[span_22](start_span)[span_22](end_span)
    resume_score = min(100, max(35, 35 + min(len(words) // 35, 35) + section_hits * 6 + min(len(skills) * 2, 20)))[span_23](start_span)[span_23](end_span)
    readiness = min(100, max(30, resume_score - 3 + min(len(skills), 10)))[span_24](start_span)[span_24](end_span)
    email_match = re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text)[span_25](start_span)[span_25](end_span)
    phone_match = re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text)[span_26](start_span)[span_26](end_span)
    clean_name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Candidate[span_27](start_span)"[span_27](end_span)
    return {
        "name": clean_name,
        "email": email_match.group(0) if email_match else "",
        "phone": phone_match.group(0).strip() if phone_match else "",
        "experience": "Detected from resume" if "experience" in lower else "Not detected",
        "resume_score": resume_score,
        "readiness": readiness,
        "market_match": None,
        "skills": skills,
        "missing_skills": [],
        "strengths": ["Skills detected" if skills else "Resume text extracted", "Structured sections detected" if section_hits >= 3 else "Basic resume structure detected"],
        "recommendations": ["Add measurable achievements and outcomes.", "Tailor skills and projects to the target role.", "Keep formatting ATS-friendly and concise."],
        "extracted_text": text,
        "source": "local-fallback",
    }[span_28](start_span)[span_28](end_span)


def api_analyze_resume(file) -> Dict[str, Any]:
    try:
        files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}[span_29](start_span)[span_29](end_span)
        res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)[span_30](start_span)[span_30](end_span)
        if res.ok:[span_31](start_span)[span_31](end_span)
            data = res.json()[span_32](start_span)[span_32](end_span)
            if isinstance(data, dict):[span_33](start_span)[span_33](end_span)
                text = data.get("extracted_text") or _extract_resume_text(file)[span_34](start_span)[span_34](end_span)
                data["extracted_text"] = text[span_35](start_span)[span_35](end_span)
                data.setdefault("skills", [])[span_36](start_span)[span_36](end_span)
                data.setdefault("missing_skills", [])[span_37](start_span)[span_37](end_span)
                data.setdefault("strengths", [])[span_38](start_span)[span_38](end_span)
                data.setdefault("recommendations", [])[span_39](start_span)[span_39](end_span)
                data.setdefault("source", "api")[span_40](start_span)[span_40](end_span)
                return data[span_41](start_span)[span_41](end_span)
    except (requests.RequestException, ValueError, TypeError):
        pass
    text = _extract_resume_text(file)[span_42](start_span)[span_42](end_span)
    return _local_resume_analysis(text, file.name)[span_43](start_span)[span_43](end_span)


def _skill_set(text: str) -> set:
    lower = (text or "").lower()[span_44](start_span)[span_44](end_span)
    catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask",
        "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws", "azure", "gcp", "git",
        "linux", "machine learning", "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow",
        "pytorch", "rest api", "graphql", "redis", "kafka", "system design", "html", "css", "figma",
        "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium", "communication",
        "leadership", "problem solving",
    ][span_45](start_span)[span_45](end_span)
    return {x for x in catalog if x in lower}[span_46](start_span)[span_46](end_span)


def api_match_job(resume_text: str, job_description: str) -> Dict[str, Any]:
    if not resume_text.strip() or not job_description.strip():[span_47](start_span)[span_47](end_span)
        return {
            "overall": 0,
            "matched": [],
            "missing": [],
            "summary": "Both resume and job description are required.",
            "experience_alignment": "Unavailable",
            "source": "validation",
        }[span_48](start_span)[span_48](end_span)
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}[span_49](start_span)[span_49](end_span)
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)[span_50](start_span)[span_50](end_span)
        if res.ok:[span_51](start_span)[span_51](end_span)
            return {**normalize_job_match(res.json()), "source": "api"}[span_52](start_span)[span_52](end_span)
    except (requests.RequestException, ValueError, TypeError):
        pass
    try:
        matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=8000).fit_transform([resume_text, job_description])[span_53](start_span)[span_53](end_span)
        similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])[span_54](start_span)[span_54](end_span)
    except ValueError:
        similarity = 0.0[span_55](start_span)[span_55](end_span)
    resume_skills = _skill_set(resume_text)[span_56](start_span)[span_56](end_span)
    job_skills = _skill_set(job_description)[span_57](start_span)[span_57](end_span)
    matched = sorted(resume_skills & job_skills)[span_58](start_span)[span_58](end_span)
    missing = sorted(job_skills - resume_skills)[span_59](start_span)[span_59](end_span)
    skill_score = (len(matched) / len(job_skills) * 100) if job_skills else similarity * 100[span_60](start_span)[span_60](end_span)
    overall = round((similarity * 60) + (skill_score * 0.40)) if job_skills else round(similarity * 100)[span_61](start_span)[span_61](end_span)
    return {
        "overall": max(0, min(100, overall)),
        "matched": matched,
        "missing": missing,
        "summary": "Local semantic and skill analysis completed.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment" if overall >= 50 else "Needs Improvement",
        "source": "local-fallback",
    }[span_62](start_span)[span_62](end_span)


def _safe_public_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())[span_63](start_span)[span_63](end_span)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:[span_64](start_span)[span_64](end_span)
            return False[span_65](start_span)[span_65](end_span)
        addresses = socket.getaddrinfo(parsed.hostname, None)[span_66](start_span)[span_66](end_span)
        for item in addresses:[span_67](start_span)[span_67](end_span)
            ip_obj = ipaddress.ip_address(item[4][0])[span_68](start_span)[span_68](end_span)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved or ip_obj.is_multicast:[span_69](start_span)[span_69](end_span)
                return False[span_70](start_span)[span_70](end_span)
        return True[span_71](start_span)[span_71](end_span)
    except Exception:
        return False[span_72](start_span)[span_72](end_span)


def fetch_public_job_url(url: str) -> str:
    if not _safe_public_url(url):[span_73](start_span)[span_73](end_span)
        raise ValueError("Please enter a valid, safe public HTTP/HTTPS job URL.")[span_74](start_span)[span_74](end_span)
    response = requests.get(
        url.strip(),
        timeout=10,
        headers={"User-Agent": "CareerLensAI/2.1 Job Safety Analyzer"},
        allow_redirects=False,
    )[span_75](start_span)[span_75](end_span)
    response.raise_for_status()[span_76](start_span)[span_76](end_span)
    content_type = response.headers.get("content-type", "").lower()[span_77](start_span)[span_77](end_span)
    if "text/html" not in content_type and "text/plain" not in content_type:[span_78](start_span)[span_78](end_span)
        raise ValueError("The supplied link did not return readable HTML/text content.")[span_79](start_span)[span_79](end_span)
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", response.text, flags=re.I)[span_80](start_span)[span_80](end_span)
    text = re.sub(r"<[^>]+>", " ", text)[span_81](start_span)[span_81](end_span)
    return re.sub(r"\s+", " ", text).strip()[:50000][span_82](start_span)[span_82](end_span)


def api_detect_fraud(job_text: str) -> Dict[str, Any]:
    try:
        payload = {"text": job_text}[span_83](start_span)[span_83](end_span)
        res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)[span_84](start_span)[span_84](end_span)
        if res.ok and isinstance(res.json(), dict):[span_85](start_span)[span_85](end_span)
            return res.json()[span_86](start_span)[span_86](end_span)
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
    }[span_87](start_span)[span_87](end_span)
    lower = job_text.lower()[span_88](start_span)[span_88](end_span)
    signals = [description for phrase, description in risk_patterns.items() if phrase in lower][span_89](start_span)[span_89](end_span)
    score = min(100, len(signals) * 22)[span_90](start_span)[span_90](end_span)
    return {
        "score": score,
        "level": "HIGH RISK" if score >= 55 else "MEDIUM RISK" if score >= 25 else "LOW RISK",
        "signals": len(signals),
        "signal_details": signals,
        "source": "local-fallback",
    }[span_91](start_span)[span_91](end_span)


def api_career_roadmap(resume_text: str, target_role: str) -> Dict[str, Any]:
    try:
        payload = {"resume_text": resume_text, "target_role": target_role}[span_92](start_span)[span_92](end_span)
        res = requests.post(f"{API_BASE_URL}/api/career/roadmap", json=payload, timeout=30)[span_93](start_span)[span_93](end_span)
        if res.status_code == 200:[span_94](start_span)[span_94](end_span)
            return res.json()[span_95](start_span)[span_95](end_span)
    except Exception:
        pass
    return {
        "steps": [
            f"Step 1: Strengthen foundational architecture in {target_role}.",
            "Step 2: Build an end-to-end production portfolio showcasing measurable throughput.",
            "Step 3: Refactor achievements into the Google XYZ format.",
            "Step 4: Practice domain mock interview questions and system design scenarios.",
        ]
    }[span_96](start_span)[span_96](end_span)


def api_chat_assistant(messages: List[Dict], resume_context: str = "") -> str:
    try:
        payload = {"messages": messages, "resume_context": resume_context}[span_97](start_span)[span_97](end_span)
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=45)[span_98](start_span)[span_98](end_span)
        if res.status_code == 200:[span_99](start_span)[span_99](end_span)
            return res.json().get("reply", "")[span_100](start_span)[span_100](end_span)
    except Exception:
        pass
    return "Focus on quantifiable business outcomes, active GitHub portfolio proof, and modern architecture patterns for the best results.[span_101](start_span)"[span_101](end_span)


def api_send_assessment_email(to_email: str, name: str, role: str, test_link: str) -> tuple[bool, str]:
    subject = f"CareerLens AI — Assessment Invitation for {role}[span_102](start_span)"[span_102](end_span)
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
    ""[span_103](start_span)"[span_103](end_span)
    payload = {
        "to_email": to_email,
        "subject": subject,
        "content": html_content,
    }[span_104](start_span)[span_104](end_span)
    try:
        res = requests.post(f"{API_BASE_URL}/api/send-email", json=payload, timeout=20)[span_105](start_span)[span_105](end_span)
        if res.status_code == 200:[span_106](start_span)[span_106](end_span)
            return True, "Email accepted by backend[span_107](start_span)"[span_107](end_span)
        data = res.json() if res.content else {}[span_108](start_span)[span_108](end_span)
        return False, data.get("detail", f"Backend returned {res.status_code}")[span_109](start_span)[span_109](end_span)
    except Exception as exc:
        return False, str(exc)[span_110](start_span)[span_110](end_span)


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
    "resume_builder": {},
    "resume_template": "Executive",
    "recruiter_nav_history": ["Dashboard"],
    "recruiter_nav_index": 0,
    "recruiter_selected_ids": [],
}[span_111](start_span)[span_111](end_span)

for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val[span_112](start_span)[span_112](end_span)

RECRUITER_TOOLS = [
    "Dashboard",
    "Hiring Campaign",
    "Bulk Screening",
    "Shortlisted Candidates",
    "Assessment Builder",
    "Score Vault",
    "Interview Pipeline",
][span_113](start_span)[span_113](end_span)


def recruiter_navigate(tool: str, record_history: bool = True) -> None:
    if tool not in RECRUITER_TOOLS:
        tool = "Dashboard[span_114](start_span)"[span_114](end_span)
    history = list(st.session_state.get("recruiter_nav_history", ["Dashboard"]))[span_115](start_span)[span_115](end_span)
    index = int(st.session_state.get("recruiter_nav_index", 0))[span_116](start_span)[span_116](end_span)
    current = history[index] if history and 0 <= index < len(history) else st.session_state.get("active_tool", "Dashboard")[span_117](start_span)[span_117](end_span)
    if record_history:[span_118](start_span)[span_118](end_span)
        history = history[: index + 1][span_119](start_span)[span_119](end_span)
        if current != tool:[span_120](start_span)[span_120](end_span)
            history.append(tool)[span_121](start_span)[span_121](end_span)
        index = len(history) - 1[span_122](start_span)[span_122](end_span)
    else:
        if tool in history:[span_123](start_span)[span_123](end_span)
            index = history.index(tool)[span_124](start_span)[span_124](end_span)
        else:
            history.append(tool)[span_125](start_span)[span_125](end_span)
            index = len(history) - 1[span_126](start_span)[span_126](end_span)
    st.session_state.recruiter_nav_history = history[span_127](start_span)[span_127](end_span)
    st.session_state.recruiter_nav_index = index[span_128](start_span)[span_128](end_span)
    st.session_state.active_tool = tool[span_129](start_span)[span_129](end_span)


def recruiter_go_back() -> bool:
    history = st.session_state.get("recruiter_nav_history", ["Dashboard"])[span_130](start_span)[span_130](end_span)
    index = int(st.session_state.get("recruiter_nav_index", 0))[span_131](start_span)[span_131](end_span)
    if index <= 0:[span_132](start_span)[span_132](end_span)
        return False[span_133](start_span)[span_133](end_span)
    index -= 1[span_134](start_span)[span_134](end_span)
    st.session_state.recruiter_nav_index = index[span_135](start_span)[span_135](end_span)
    st.session_state.active_tool = history[index][span_136](start_span)[span_136](end_span)
    return True[span_137](start_span)[span_137](end_span)


def recruiter_go_forward() -> bool:
    history = st.session_state.get("recruiter_nav_history", ["Dashboard"])[span_138](start_span)[span_138](end_span)
    index = int(st.session_state.get("recruiter_nav_index", 0))[span_139](start_span)[span_139](end_span)
    if index >= len(history) - 1:[span_140](start_span)[span_140](end_span)
        return False[span_141](start_span)[span_141](end_span)
    index += 1[span_142](start_span)[span_142](end_span)
    st.session_state.recruiter_nav_index = index[span_143](start_span)[span_143](end_span)
    st.session_state.active_tool = history[index][span_144](start_span)[span_144](end_span)
    return True[span_145](start_span)[span_145](end_span)


def _load_recruiter_data() -> Dict[str, Any]:
    default = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}[span_146](start_span)[span_146](end_span)
    if st.session_state.get("user_id"):[span_147](start_span)[span_147](end_span)
        data = _db_load_recruiter_state(st.session_state.user_id)[span_148](start_span)[span_148](end_span)
        for key, value in default.items():[span_149](start_span)[span_149](end_span)
            data.setdefault(key, value)[span_150](start_span)[span_150](end_span)
        return data[span_151](start_span)[span_151](end_span)
    return default[span_152](start_span)[span_152](end_span)


def _save_recruiter_data(data: Dict[str, Any]) -> None:
    if st.session_state.get("user_id"):[span_153](start_span)[span_153](end_span)
        try:
            _db_save_recruiter_state(st.session_state.user_id, data)[span_154](start_span)[span_154](end_span)
        except sqlite3.Error:
            pass[span_155](start_span)[span_155](end_span)


def _make_assessment_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex[span_156](start_span)[span_156](end_span)


def _assessment_public_url(token: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", PUBLIC_APP_URL).strip().rstrip("/")[span_157](start_span)[span_157](end_span)
    if not base:[span_158](start_span)[span_158](end_span)
        base = "http://localhost:8501[span_159](start_span)"[span_159](end_span)
    return f"{base}/?assessment={quote(token)}[span_160](start_span)"[span_160](end_span)


if "recruiter_data" not in st.session_state:[span_161](start_span)[span_161](end_span)
    st.session_state.recruiter_data = _load_recruiter_data()[span_162](start_span)[span_162](end_span)
if "recruiter_candidates" not in st.session_state:[span_163](start_span)[span_163](end_span)
    st.session_state.recruiter_candidates = st.session_state.recruiter_data.get("candidates", [])[span_164](start_span)[span_164](end_span)
if "recruiter_assessment_submissions" not in st.session_state:[span_165](start_span)[span_165](end_span)
    st.session_state.recruiter_assessment_submissions = {
        item.get("token", str(index)): item
        for index, item in enumerate(st.session_state.recruiter_data.get("submissions", []))
        if isinstance(item, dict)
    }[span_166](start_span)[span_166](end_span)

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"][span_167](start_span)[span_167](end_span)
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"][span_168](start_span)[span_168](end_span)


def generate_assessment_questions(role: str, count: int) -> List[Dict]:
    role_topics = {
        "Software Developer": [
            ("Which data structure gives average O(1) key lookup?", ["Hash table", "Linked list", "Binary heap", "Queue"], 0),
            ("Which HTTP status code represents a successful creation?", ["201", "301", "401", "500"], 0),
            ("What is the main purpose of unit tests?", ["Validate isolated behavior", "Replace production monitoring", "Store credentials", "Deploy containers"], 0),
            ("Which principle recommends keeping modules focused on one responsibility?", ["Single Responsibility", "Open/Closed", "Liskov Substitution", "Dependency Inversion"], 0),
            ("Which SQL clause filters grouped results?", ["HAVING", "WHERE", "ORDER BY", "LIMIT"], 0),
            ("Which approach is best for bursty asynchronous workloads?", ["Message queue", "Blocking loop", "Busy waiting", "Unbounded recursion"], 0),
            ("What does a database index primarily improve?", ["Read/query lookup", "Password entropy", "Source formatting", "Network encryption"], 0),
            ("What is a container image?", ["Packaged application filesystem and metadata", "A physical server", "A database row", "A DNS record"], 0),
            ("What does CI commonly automate?", ["Build and test validation", "Manual payroll", "Office access", "Recruiting calls"], 0),
            ("Which practice protects secrets in production?", ["Secret manager/environment injection", "Hard-code in Git", "Public config file", "Client-side HTML"], 0),
        ],
        "Data Scientist": [
            ("Which technique reduces feature dimensionality while preserving variance?", ["PCA", "One-hot encoding", "Bagging", "Tokenization"], 0),
            ("What does precision measure?", ["Correct positives among predicted positives", "Correct positives among all actual positives", "All correct predictions", "False positives only"], 0),
            ("Why use a validation set?", ["Tune/select models before final testing", "Increase database size", "Encrypt features", "Replace training data"], 0),
            ("Which model is commonly used for binary classification?", ["Logistic regression", "K-means only", "PCA", "Apriori only"], 0),
            ("What does overfitting mean?", ["Model fits training data too specifically", "Model has no parameters", "Data has no labels", "Model cannot train"], 0),
            ("Which metric is useful for imbalanced classification?", ["F1-score", "Raw row count", "File size", "CPU frequency"], 0),
            ("What does standardization usually do?", ["Center and scale numeric features", "Remove all labels", "Duplicate samples", "Encrypt data"], 0),
            ("Which method is unsupervised?", ["K-means clustering", "Linear regression", "Logistic regression", "Decision-tree classification"], 0),
            ("What is cross-validation used for?", ["Estimate generalization during model selection", "Generate passwords", "Compress PDFs", "Create DNS records"], 0),
            ("Why prevent data leakage?", ["Avoid training with information unavailable at prediction time", "Increase UI color contrast", "Reduce font size", "Add more labels"], 0),
        ],
    }[span_169](start_span)[span_169](end_span)
    generic = [
        ("What is the safest default for sensitive user data?", ["Least privilege and encryption", "Public access", "Plaintext storage", "Shared credentials"], 0),
        ("What is the purpose of version control?", ["Track and collaborate on changes", "Increase monitor brightness", "Replace backups completely", "Generate salary slips"], 0),
        ("What should happen after detecting a production regression?", ["Contain, inspect telemetry and restore safely", "Ignore it", "Delete logs", "Disable tests"], 0),
        ("Which practice improves API reliability?", ["Timeouts, validation and controlled retries", "Infinite retries", "No validation", "Hard-coded secrets"], 0),
        ("What is RBAC?", ["Role-Based Access Control", "Random Binary API Cache", "Remote Build Allocation Controller", "Runtime Browser Access Code"], 0),
    ][span_170](start_span)[span_170](end_span)
    bank = role_topics.get(role, []) + generic[span_171](start_span)[span_171](end_span)
    questions = [][span_172](start_span)[span_172](end_span)
    for i in range(max(count, 1)):[span_173](start_span)[span_173](end_span)
        base = bank[i % len(bank)][span_174](start_span)[span_174](end_span)
        q_text, options, correct_idx = base[span_175](start_span)[span_175](end_span)
        cycle = i // len(bank)[span_176](start_span)[span_176](end_span)
        question_text = q_text if cycle == 0 else f"{q_text} (Scenario {cycle + 1})[span_177](start_span)"[span_177](end_span)
        questions.append({
            "id": i + 1,
            "section": "Core Skills" if i < count * 0.6 else "Applied Scenarios",
            "question": question_text,
            "options": options,
            "answer": options[correct_idx],
        })[span_178](start_span)[span_178](end_span)
    return questions[span_179](start_span)[span_179](end_span)


def assessment_result(questions: List[Dict], answers: Dict) -> Dict[str, Any]:
    correct_items, wrong_items, unanswered_items = [], [], [][span_180](start_span)[span_180](end_span)
    for q in questions:[span_181](start_span)[span_181](end_span)
        selected = answers.get(q["id"])[span_182](start_span)[span_182](end_span)
        item = {"id": q["id"], "question": q["question"], "selected": selected, "correct": q["answer"], "options": q["options"]}[span_183](start_span)[span_183](end_span)
        if selected is None:[span_184](start_span)[span_184](end_span)
            unanswered_items.append(item)[span_185](start_span)[span_185](end_span)
        elif selected == q["answer"]:[span_186](start_span)[span_186](end_span)
            correct_items.append(item)[span_187](start_span)[span_187](end_span)
        else:
            wrong_items.append(item)[span_188](start_span)[span_188](end_span)
    total = len(questions)[span_189](start_span)[span_189](end_span)
    correct = len(correct_items)[span_190](start_span)[span_190](end_span)
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
    }[span_191](start_span)[span_191](end_span)


def _escape(value: str) -> str:
    return html.escape(str(value or ""))[span_192](start_span)[span_192](end_span)


def build_resume_pdf(data: Dict, template: str) -> bytes:
    buffer = io.BytesIO()[span_193](start_span)[span_193](end_span)
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15 * mm, leftMargin=15 * mm, topMargin=14 * mm, bottomMargin=14 * mm)[span_194](start_span)[span_194](end_span)
    styles = getSampleStyleSheet()[span_195](start_span)[span_195](end_span)
    title_size = 22 if template in {"Executive", "Minimal"} else 20[span_196](start_span)[span_196](end_span)
    accent = colors.HexColor({
        "Executive": "#1d4ed8",
        "Minimal": "#0f172a",
        "Modern Blue": "#2563eb",
        "Modern Purple": "#7c3aed",
        "Emerald": "#059669",
        "Professional": "#334155",
        "Tech": "#0284c7",
        "ATS Classic": "#111827",
    }.get(template, "#2563eb"))[span_197](start_span)[span_197](end_span)

    title = ParagraphStyle("ResumeTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=title_size, leading=25, textColor=accent, alignment=TA_CENTER, spaceAfter=4)[span_198](start_span)[span_198](end_span)
    contact = ParagraphStyle("Contact", parent=styles["Normal"], fontSize=8.8, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=10)[span_199](start_span)[span_199](end_span)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=accent, spaceBefore=7, spaceAfter=4)[span_200](start_span)[span_200](end_span)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=12, textColor=colors.HexColor("#1f2937"), spaceAfter=3)[span_201](start_span)[span_201](end_span)

    story = [Paragraph(_escape(data.get("name", "Your Name")), title)][span_202](start_span)[span_202](end_span)
    contact_bits = [data.get("email"), data.get("phone"), data.get("location"), data.get("linkedin"), data.get("github")][span_203](start_span)[span_203](end_span)
    story.append(Paragraph(" &nbsp;•&nbsp; ".join(_escape(x) for x in contact_bits if x), contact))[span_204](start_span)[span_204](end_span)

    if data.get("headline"):[span_205](start_span)[span_205](end_span)
        story.append(Paragraph(_escape(data["headline"]), ParagraphStyle("Headline", parent=body, fontSize=10, leading=13, alignment=TA_CENTER, textColor=colors.HexColor("#334155"), spaceAfter=8)))[span_206](start_span)[span_206](end_span)

    sections = [
        ("PROFESSIONAL SUMMARY", data.get("summary")),
        ("EXPERIENCE", data.get("experience")),
        ("EDUCATION", data.get("education")),
        ("PROJECTS", data.get("projects")),
        ("SKILLS", data.get("skills")),
        ("CERTIFICATIONS", data.get("certifications")),
        ("ACHIEVEMENTS", data.get("achievements")),
    ][span_207](start_span)[span_207](end_span)

    for heading_text, content in sections:[span_208](start_span)[span_208](end_span)
        if not content:[span_209](start_span)[span_209](end_span)
            continue[span_210](start_span)[span_210](end_span)
        story.append(Paragraph(heading_text, heading))[span_211](start_span)[span_211](end_span)
        if heading_text == "SKILLS":[span_212](start_span)[span_212](end_span)
            skills = [x.strip() for x in str(content).split(",") if x.strip()][span_213](start_span)[span_213](end_span)
            story.append(Paragraph(" • ".join(_escape(x) for x in skills), body))[span_214](start_span)[span_214](end_span)
        else:
            for block in str(content).split("\n"):[span_215](start_span)[span_215](end_span)
                block = block.strip()[span_216](start_span)[span_216](end_span)
                if block:[span_217](start_span)[span_217](end_span)
                    story.append(Paragraph(_escape(block), body))[span_218](start_span)[span_218](end_span)

    doc.build(story)[span_219](start_span)[span_219](end_span)
    return buffer.getvalue()[span_220](start_span)[span_220](end_span)


def _find_recruiter_assessment_by_token(token: str):
    if not token:[span_221](start_span)[span_221](end_span)
        return None, None, None[span_222](start_span)[span_222](end_span)
    for assessment in st.session_state.recruiter_data.get("assessments", []):[span_223](start_span)[span_223](end_span)
        tokens = assessment.get("candidate_tokens", {}) if isinstance(assessment, dict) else {}[span_224](start_span)[span_224](end_span)
        for candidate_id, candidate_token in tokens.items():[span_225](start_span)[span_225](end_span)
            if candidate_token == token:[span_226](start_span)[span_226](end_span)
                candidate = next((c for c in st.session_state.recruiter_candidates if c.get("id") == candidate_id), None)[span_227](start_span)[span_227](end_span)
                return assessment, candidate, candidate_id[span_228](start_span)[span_228](end_span)
    return None, None, None[span_229](start_span)[span_229](end_span)


def render_public_recruiter_assessment(token: str) -> None:
    assessment, candidate, candidate_id = _find_recruiter_assessment_by_token(token)[span_230](start_span)[span_230](end_span)
    if not assessment or not candidate:[span_231](start_span)[span_231](end_span)
        st.error("This assessment link is invalid, expired, or no longer available.")[span_232](start_span)[span_232](end_span)
        st.stop()[span_233](start_span)[span_233](end_span)

    st.markdown("## 📝 CareerLens AI Assessment")[span_234](start_span)[span_234](end_span)
    st.caption(f"Role: {assessment.get('role', 'Professional Assessment')} • {len(assessment.get('questions', []))} questions")
    st.info("Complete the assessment and submit it. Your score and answer key are reviewed directly by the recruiter.")[span_235](start_span)[span_235](end_span)

    state_key = f"candidate_exam_{token[:12]}[span_236](start_span)"[span_236](end_span)
    answer_key = f"{state_key}_answers[span_237](start_span)"[span_237](end_span)
    submitted_key = f"{state_key}_submitted[span_238](start_span)"[span_238](end_span)

    if answer_key not in st.session_state:[span_239](start_span)[span_239](end_span)
        st.session_state[answer_key] = {}[span_240](start_span)[span_240](end_span)
    if submitted_key not in st.session_state:[span_241](start_span)[span_241](end_span)
        st.session_state[submitted_key] = False[span_242](start_span)[span_242](end_span)

    questions = assessment.get("questions", [])[span_243](start_span)[span_243](end_span)

    if st.session_state[submitted_key]:[span_244](start_span)[span_244](end_span)
        st.success("Assessment submitted successfully. Your recruiter will review your assessment.")[span_245](start_span)[span_245](end_span)
        st.info("You can close this page now.")[span_246](start_span)[span_246](end_span)
        st.stop()[span_247](start_span)[span_247](end_span)

    with st.form("public_candidate_assessment_form"):
        temp_answers = {}
        for q in questions:
            qid = q.get("id")[span_248](start_span)[span_248](end_span)
            current = st.session_state[answer_key].get(qid)[span_249](start_span)[span_249](end_span)
            index = q.get("options", []).index(current) if current in q.get("options", []) else None[span_250](start_span)[span_250](end_span)
            temp_answers[qid] = st.radio(q.get("question", "Question"), q.get("options", []), index=index, key=f"{state_key}_{qid}")[span_251](start_span)[span_251](end_span)

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
            })[span_252](start_span)[span_252](end_span)
            st.session_state.recruiter_assessment_submissions[token] = result[span_253](start_span)[span_253](end_span)
            candidate["assessment_status"] = "Completed[span_254](start_span)"[span_254](end_span)
            candidate["assessment_percentage"] = result["percentage"][span_255](start_span)[span_255](end_span)
            candidate["status"] = "Assessment Completed[span_256](start_span)"[span_256](end_span)
            st.session_state.recruiter_data["candidates"] = st.session_state.recruiter_candidates[span_257](start_span)[span_257](end_span)
            st.session_state.recruiter_data["submissions"] = list(st.session_state.recruiter_assessment_submissions.values())[span_258](start_span)[span_258](end_span)
            _save_recruiter_data(st.session_state.recruiter_data)[span_259](start_span)[span_259](end_span)
            st.session_state[submitted_key] = True[span_260](start_span)[span_260](end_span)
            st.rerun()[span_261](start_span)[span_261](end_span)


_assessment_query_token = "[span_262](start_span)"[span_262](end_span)
try:
    _assessment_query_token = str(st.query_params.get("assessment", "") or "").strip()[span_263](start_span)[span_263](end_span)
except Exception:
    _assessment_query_token = "[span_264](start_span)"[span_264](end_span)

if _assessment_query_token:[span_265](start_span)[span_265](end_span)
    render_public_recruiter_assessment(_assessment_query_token)[span_266](start_span)[span_266](end_span)
    st.stop()[span_267](start_span)[span_267](end_span)


# ============================================================
# DIALOGS (SIGN IN & REGISTER)
# ============================================================
@st.dialog("🔐 Sign In / Register")[span_268](start_span)[span_268](end_span)
def dialog_auth(default_tab: int = 0):
    tab_auth1, tab_auth2 = st.tabs(["Sign In", "Register"])[span_269](start_span)[span_269](end_span)
    with tab_auth1:[span_270](start_span)[span_270](end_span)
        u = st.text_input("Username or Email", key="auth_sign_u")[span_271](start_span)[span_271](end_span)
        p = st.text_input("Password", type="password", key="auth_sign_p")[span_272](start_span)[span_272](end_span)
        if st.button("Sign In", use_container_width=True, key="btn_confirm_sign", type="primary"):[span_273](start_span)[span_273](end_span)
            if not u or not p:[span_274](start_span)[span_274](end_span)
                st.warning("Please fill in both fields.")[span_275](start_span)[span_275](end_span)
            else:
                account = _db_user(u)[span_276](start_span)[span_276](end_span)
                if account and password_matches(account[3], p):[span_277](start_span)[span_277](end_span)
                    st.session_state.user_id = account[0][span_278](start_span)[span_278](end_span)
                    st.session_state.username = account[2][span_279](start_span)[span_279](end_span)
                    st.session_state.is_logged_in = True[span_280](start_span)[span_280](end_span)
                    st.session_state.selected_gateway = False[span_281](start_span)[span_281](end_span)
                    saved = _db_load_state(st.session_state.user_id)[span_282](start_span)[span_282](end_span)
                    for key, value in saved.items():[span_283](start_span)[span_283](end_span)
                        st.session_state[key] = value[span_284](start_span)[span_284](end_span)
                    st.session_state.recruiter_data = _db_load_recruiter_state(st.session_state.user_id)[span_285](start_span)[span_285](end_span)
                    st.session_state.recruiter_candidates = st.session_state.recruiter_data.get("candidates", [])[span_286](start_span)[span_286](end_span)
                    st.session_state.recruiter_assessment_submissions = {
                        x.get("token", str(i)): x
                        for i, x in enumerate(st.session_state.recruiter_data.get("submissions", []))
                        if isinstance(x, dict)
                    }[span_287](start_span)[span_287](end_span)
                    log_event("LOGIN", st.session_state.username, "N/A", "User Login")[span_288](start_span)[span_288](end_span)
                    st.rerun()[span_289](start_span)[span_289](end_span)
                elif ADMIN_PIN and u.lower() == "admin" and p == ADMIN_PIN:[span_290](start_span)[span_290](end_span)
                    st.session_state.user_id = "admin[span_291](start_span)"[span_291](end_span)
                    st.session_state.username = "Administrator[span_292](start_span)"[span_292](end_span)
                    st.session_state.is_logged_in = True[span_293](start_span)[span_293](end_span)
                    st.session_state.selected_gateway = True[span_294](start_span)[span_294](end_span)
                    st.session_state.active_workspace = "Recruiter Workspace[span_295](start_span)"[span_295](end_span)
                    st.rerun()[span_296](start_span)[span_296](end_span)
                else:
                    st.error("Invalid credentials. Please register or verify your details.")

    with tab_auth2:[span_297](start_span)[span_297](end_span)
        reg_n = st.text_input("Full Name", key="auth_reg_n")[span_298](start_span)[span_298](end_span)
        reg_u = st.text_input("Choose Username / Email", key="auth_reg_u")[span_299](start_span)[span_299](end_span)
        reg_p = st.text_input("Create Password", type="password", key="auth_reg_p")[span_300](start_span)[span_300](end_span)
        if st.button("Create Account", use_container_width=True, key="btn_confirm_reg", type="primary"):[span_301](start_span)[span_301](end_span)
            if not reg_u or not reg_p:[span_302](start_span)[span_302](end_span)
                st.warning("Username and password are required.")[span_303](start_span)[span_303](end_span)
            else:
                if _db_user(reg_u):[span_304](start_span)[span_304](end_span)
                    st.error("That username or email is already registered. Please sign in.")[span_305](start_span)[span_305](end_span)
                else:
                    try:
                        uid = _db_create_user(reg_u, reg_n, hash_password(reg_p))[span_306](start_span)[span_306](end_span)
                        st.session_state.user_id = uid[span_307](start_span)[span_307](end_span)
                        st.session_state.username = reg_n.strip() if reg_n.strip() else reg_u.split("@")[0].capitalize()[span_308](start_span)[span_308](end_span)
                        st.session_state.is_logged_in = True[span_309](start_span)[span_309](end_span)
                        st.session_state.selected_gateway = False[span_310](start_span)[span_310](end_span)
                        st.session_state.recruiter_data = _db_load_recruiter_state(uid)[span_311](start_span)[span_311](end_span)
                        st.session_state.recruiter_candidates = [][span_312](start_span)[span_312](end_span)
                        st.session_state.recruiter_assessment_submissions = {}[span_313](start_span)[span_313](end_span)
                        _db_save_state(uid, {"username": st.session_state.username, "resume_text": "", "resume_analysis": None, "job_match_result": None, "resume_builder": {}})[span_314](start_span)[span_314](end_span)
                        log_event("REGISTER", st.session_state.username, "N/A", f"Registered: {reg_u}")[span_315](start_span)[span_315](end_span)
                        st.rerun()[span_316](start_span)[span_316](end_span)
                    except sqlite3.IntegrityError:
                        st.error("That username or email is already registered. Please sign in.")[span_317](start_span)[span_317](end_span)


# ============================================================
# 1. LANDING & ACCESS SCREEN
# ============================================================
if not st.session_state.is_logged_in:[span_318](start_span)[span_318](end_span)
    st.markdown(
        """
        <div class="hero-shell">
          <div class="hero-nav">
            <div class="brand">✦ CareerLens <span class="brand-accent">AI</span></div>
            <div class="hero-nav-links">
              <span>Features</span><span>Intelligence</span><span>Recruiting</span>
            </div>
          </div>
          <div class="hero-grid">
            <div>
              <div class="eyebrow">AI POWERED CAREER PLATFORM</div>
              <h1 class="hero-title">Understand Your Career.<br>Build Your <span class="accent">Future.</span></h1>
              <p class="hero-copy">Get personalized insights, intelligent recommendations, and enterprise screening tools all in one unified ecosystem.</p>
              <div class="feature-list">
                <div class="feature-item"><div class="feature-icon">✦</div><div><b>AI-Powered Insights</b><span>Smarter career decisions</span></div></div>
                <div class="feature-item"><div class="feature-icon">◎</div><div><b>Personalized Roadmaps</b><span>Your goals, our guidance</span></div></div>
                <div class="feature-item"><div class="feature-icon">♢</div><div><b>Trusted &amp; Secure</b><span>Your data stays safe</span></div></div>
              </div>
            </div>
            <div>
              <div class="access-card">
                <div class="access-kicker">✦ &nbsp; Welcome to</div>
                <div class="access-title">CareerLens <span>AI</span></div>
                <div class="access-sub">Sign in, create an account, or explore instantly as a guest.</div>
                <div style="height: 170px;"></div>
              </div>
            </div>
          </div>
          <div class="hero-stats">
            <div class="hero-stat"><div class="hero-stat-icon">✓</div><div><b>10K+</b><span>Active Users</span></div></div>
            <div class="hero-stat"><div class="hero-stat-icon">★</div><div><b>95%</b><span>Match Precision</span></div></div>
            <div class="hero-stat"><div class="hero-stat-icon">✦</div><div><b>AI Driven</b><span>Fast Execution</span></div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Clean centered button stack overlapping the card seamlessly on desktop/tablet/mobile
    _, auth_col, _ = st.columns([1, 1.15, 1])
    with auth_col:
        st.markdown("<div style='margin-top: -205px; position: relative; z-index: 10; padding: 0 24px 24px;'>", unsafe_allow_html=True)
        if st.button("🔐 Sign In", key="btn_landing_signin", use_container_width=True, type="primary"):
            dialog_auth(default_tab=0)
        
        if st.button("✨ Register / Create Account", key="btn_landing_register", use_container_width=True):
            dialog_auth(default_tab=1)

        st.markdown("<div style='text-align:center; color:#94a3b8; font-size:0.75rem; margin:10px 0; font-weight:700;'>— OR —</div>", unsafe_allow_html=True)

        if st.button("🚀 Explore as Guest", key="btn_landing_guest", use_container_width=True):
            st.session_state.user_id = "[span_319](start_span)"[span_319](end_span)
            st.session_state.username = "Guest Explorer[span_320](start_span)"[span_320](end_span)
            st.session_state.is_logged_in = True[span_321](start_span)[span_321](end_span)
            st.session_state.resume_text = "[span_322](start_span)"[span_322](end_span)
            st.session_state.resume_analysis = None[span_323](start_span)[span_323](end_span)
            st.session_state.job_match_result = None[span_324](start_span)[span_324](end_span)
            st.session_state.resume_builder = {}[span_325](start_span)[span_325](end_span)
            st.session_state.recruiter_data = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}[span_326](start_span)[span_326](end_span)
            st.session_state.recruiter_candidates = [][span_327](start_span)[span_327](end_span)
            st.session_state.recruiter_assessment_submissions = {}[span_328](start_span)[span_328](end_span)
            st.session_state.selected_gateway = False[span_329](start_span)[span_329](end_span)
            log_event("GUEST_ACCESS", "Guest", "N/A", "Guest entry")[span_330](start_span)[span_330](end_span)
            st.rerun()[span_331](start_span)[span_331](end_span)
        st.markdown("</div>", unsafe_allow_html=True)

    st.stop()[span_332](start_span)[span_332](end_span)


# ============================================================
# 2. WORKSPACE GATEWAY PORTAL
# ============================================================
if not st.session_state.selected_gateway:[span_333](start_span)[span_333](end_span)
    st.markdown(
        f"""
        <div class="header-banner">
          <div>
            <div class="header-title">Welcome, {html.escape(st.session_state.username)}! 👋</div>
            <div class="header-sub">Choose your workspace to get started.</div>
          </div>
          <span class="tag-badge tag-blue">AI CAREER ECOSYSTEM</span>
        </div>
        """, unsafe_allow_html=True)[span_334](start_span)[span_334](end_span)
    g1, g2 = st.columns(2, gap="large")
    with g1:
        st.markdown("""
        <div class="gateway-card">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
            <div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb; width:46px; height:46px;">●</div>
            <div><h3 style="margin:0;font-size:1.15rem">Job Seeker Portal</h3><span class="tag-badge tag-blue">Candidate Intelligence</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Discover opportunities, improve skills, and accelerate your career with deep AI guidance.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
            ✦ Resume Intelligence &nbsp; ✦ AI Mock Interview<br>✦ Job Match &nbsp; ✦ Salary Insights &nbsp; ✦ Career Roadmap
          </div>
        </div>""", unsafe_allow_html=True)
        if st.button("Continue as Job Seeker →", key="btn_portal_seeker", use_container_width=True, type="primary"):[span_335](start_span)[span_335](end_span)
            st.session_state.active_workspace = "Job Seeker Workspace[span_336](start_span)"[span_336](end_span)
            st.session_state.active_tool = "Dashboard[span_337](start_span)"[span_337](end_span)
            st.session_state.selected_gateway = True[span_338](start_span)[span_338](end_span)
            st.rerun()[span_339](start_span)[span_339](end_span)
    with g2:
        st.markdown("""
        <div class="gateway-card">
          <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">
            <div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6; width:46px; height:46px;">▦</div>
            <div><h3 style="margin:0;font-size:1.15rem">Recruiter Portal</h3><span class="tag-badge tag-purple">Talent Acquisition</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Streamline hiring, screen cohorts at scale, and build high-performing teams with automated assessments.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
            ✦ Bulk Resume Screening &nbsp; ✦ Hiring Campaigns<br>✦ Assessment Dispatcher &nbsp; ✦ Candidate Ranking &nbsp; ✦ Interview Pipeline
          </div>
        </div>""", unsafe_allow_html=True)
        if st.button("Continue as Recruiter →", key="btn_portal_recruiter", use_container_width=True, type="primary"):[span_340](start_span)[span_340](end_span)
            st.session_state.active_workspace = "Recruiter Workspace[span_341](start_span)"[span_341](end_span)
            st.session_state.active_tool = "Dashboard[span_342](start_span)"[span_342](end_span)
            st.session_state.selected_gateway = True[span_343](start_span)[span_343](end_span)
            st.rerun()[span_344](start_span)[span_344](end_span)
    st.stop()[span_345](start_span)[span_345](end_span)


# ============================================================
# 3. SIDEBAR NAVIGATION
# ============================================================
with st.sidebar:[span_346](start_span)[span_346](end_span)
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
    )[span_347](start_span)[span_347](end_span)

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
    )[span_348](start_span)[span_348](end_span)

    st.markdown('<div class="sidebar-section-title">MAIN WORKSPACE</div>', unsafe_allow_html=True)[span_349](start_span)[span_349](end_span)
    is_seeker = st.session_state.active_workspace == "Job Seeker Workspace[span_350](start_span)"[span_350](end_span)
    is_recruiter = st.session_state.active_workspace == "Recruiter Workspace[span_351](start_span)"[span_351](end_span)

    if st.button("👤 Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):[span_352](start_span)[span_352](end_span)
        st.session_state.active_workspace = "Job Seeker Workspace[span_353](start_span)"[span_353](end_span)
        st.session_state.active_tool = "Dashboard[span_354](start_span)"[span_354](end_span)
        st.rerun()[span_355](start_span)[span_355](end_span)

    if st.button("🏢 Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):[span_356](start_span)[span_356](end_span)
        st.session_state.active_workspace = "Recruiter Workspace[span_357](start_span)"[span_357](end_span)
        st.session_state.active_tool = "Dashboard[span_358](start_span)"[span_358](end_span)
        st.rerun()[span_359](start_span)[span_359](end_span)

    if is_seeker:[span_360](start_span)[span_360](end_span)
        st.markdown('<div class="sidebar-section-title">CAREER TOOLS</div>', unsafe_allow_html=True)[span_361](start_span)[span_361](end_span)
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
        ][span_362](start_span)[span_362](end_span)
        for name, key_val in seeker_tools:[span_363](start_span)[span_363](end_span)
            is_active = st.session_state.active_tool == key_val[span_364](start_span)[span_364](end_span)
            if st.button(name, key=f"sb_tool_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):[span_365](start_span)[span_365](end_span)
                st.session_state.active_tool = key_val[span_366](start_span)[span_366](end_span)
                st.rerun()[span_367](start_span)[span_367](end_span)
    else:
        st.markdown('<div class="sidebar-section-title">RECRUITER TOOLS</div>', unsafe_allow_html=True)[span_368](start_span)[span_368](end_span)
        rec_tools = [
            ("📊 Recruiter Dashboard", "Dashboard"),
            ("🎯 Hiring Campaign", "Hiring Campaign"),
            ("📤 Bulk Resume Screening", "Bulk Screening"),
            ("🏆 Shortlisted Candidates", "Shortlisted Candidates"),
            ("📝 Assessment Dispatcher", "Assessment Builder"),
            ("📊 Assessment Results", "Score Vault"),
            ("🎤 Interview Pipeline", "Interview Pipeline"),
        ][span_369](start_span)[span_369](end_span)
        for name, key_val in rec_tools:[span_370](start_span)[span_370](end_span)
            is_active = st.session_state.active_tool == key_val[span_371](start_span)[span_371](end_span)
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):[span_372](start_span)[span_372](end_span)
                recruiter_navigate(key_val)[span_373](start_span)[span_373](end_span)
                st.rerun()[span_374](start_span)[span_374](end_span)

    st.markdown("<hr style='border-color: rgba(0,0,0,0.06); margin: 20px 0;'>", unsafe_allow_html=True)

    if st.button("🚪 Logout", key="sb_logout_btn", use_container_width=True):[span_375](start_span)[span_375](end_span)
        uid = st.session_state.get("user_id", "")[span_376](start_span)[span_376](end_span)
        if uid:[span_377](start_span)[span_377](end_span)
            try:
                _db_save_state(uid, {
                    "username": st.session_state.username,
                    "resume_text": st.session_state.get("resume_text", ""),
                    "resume_analysis": st.session_state.get("resume_analysis"),
                    "job_match_result": st.session_state.get("job_match_result"),
                    "resume_builder": st.session_state.get("resume_builder", {}),
                })[span_378](start_span)[span_378](end_span)
            except sqlite3.Error:
                pass[span_379](start_span)[span_379](end_span)
        for key in ["is_logged_in", "selected_gateway", "user_id"]:[span_380](start_span)[span_380](end_span)
            st.session_state[key] = False if key != "user_id" else "[span_381](start_span)"[span_381](end_span)
        st.session_state.username = "Guest Explorer[span_382](start_span)"[span_382](end_span)
        st.session_state.active_workspace = "Job Seeker Workspace[span_383](start_span)"[span_383](end_span)
        st.session_state.active_tool = "Dashboard[span_384](start_span)"[span_384](end_span)
        st.session_state.recruiter_nav_history = ["Dashboard"][span_385](start_span)[span_385](end_span)
        st.session_state.recruiter_nav_index = 0[span_386](start_span)[span_386](end_span)
        st.session_state.recruiter_selected_ids = [][span_387](start_span)[span_387](end_span)
        st.session_state.resume_text = "[span_388](start_span)"[span_388](end_span)
        st.session_state.resume_analysis = None[span_389](start_span)[span_389](end_span)
        st.session_state.job_match_result = None[span_390](start_span)[span_390](end_span)
        st.session_state.resume_builder = {}[span_391](start_span)[span_391](end_span)
        st.session_state.recruiter_data = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}[span_392](start_span)[span_392](end_span)
        st.session_state.recruiter_candidates = [][span_393](start_span)[span_393](end_span)
        st.session_state.recruiter_assessment_submissions = {}[span_394](start_span)[span_394](end_span)
        st.rerun()[span_395](start_span)[span_395](end_span)


# ============================================================
# 4. TOP APP HEADER
# ============================================================
workspace_label = "Job Seeker" if st.session_state.active_workspace == "Job Seeker Workspace" else "Recruiter[span_396](start_span)"[span_396](end_span)
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
    """, unsafe_allow_html=True)[span_397](start_span)[span_397](end_span)


# ============================================================
# 👤 JOB SEEKER DASHBOARD
# ============================================================
if st.session_state.active_workspace == "Job Seeker Workspace":[span_398](start_span)[span_398](end_span)
    analysis = st.session_state.resume_analysis[span_399](start_span)[span_399](end_span)
    resume_score_val = f"{analysis.get('resume_score')}%" if analysis and analysis.get("resume_score") else "--[span_400](start_span)"[span_400](end_span)
    readiness_val = f"{analysis.get('readiness')}%" if analysis and analysis.get("readiness") else "--[span_401](start_span)"[span_401](end_span)
    market_match_val = f"{st.session_state.job_match_result.get('overall')}%" if st.session_state.job_match_result else "--[span_402](start_span)"[span_402](end_span)
    skills_count_val = f"{len(analysis.get('skills', []))} Stack" if analysis and analysis.get("skills") else "--[span_403](start_span)"[span_403](end_span)

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;">📄</div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Resume Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{resume_score_val}</div>
                    <span class="tag-badge tag-blue">AI Evaluated</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;">📈</div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Readiness Index</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{readiness_val}</div>
                    <span class="tag-badge tag-purple">Domain Ready</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#f0fdf4; color:#15803d;">🎯</div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Market Match</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{market_match_val}</div>
                    <span class="tag-badge tag-green">Job Target</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#b45309;">💡</div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Detected Stack</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{skills_count_val}</div>
                    <span class="tag-badge tag-amber">Verified Skills</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )[span_404](start_span)[span_404](end_span)

    if st.session_state.active_tool == "Dashboard":[span_405](start_span)[span_405](end_span)
        st.markdown("<h3 style='margin-bottom:16px; font-weight:900; font-size:1.25rem; color:#0f172a;'>Career Tools Suite</h3>", unsafe_allow_html=True)[span_406](start_span)[span_406](end_span)
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb;">📄</div><div class="tool-title">Resume Intelligence</div><div class="tool-desc">Deep resume analysis, strengths and enhancements.</div></div>""", unsafe_allow_html=True)[span_407](start_span)[span_407](end_span)
            if st.button("Resume Intelligence", key="card_c1_btn", use_container_width=True):[span_408](start_span)[span_408](end_span)
                st.session_state.active_tool = "Resume Intelligence[span_409](start_span)"[span_409](end_span)
                st.rerun()[span_410](start_span)[span_410](end_span)
        with c2:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#7c3aed;">📝</div><div class="tool-title">Pre-Interview Exam</div><div class="tool-desc">Standardized MCQ domain qualifying assessment.</div></div>""", unsafe_allow_html=True)
            if st.button("Pre-Interview Exam", key="card_c2_btn", use_container_width=True):[span_411](start_span)[span_411](end_span)
                st.session_state.active_tool = "Pre-Interview Assessment[span_412](start_span)"[span_412](end_span)
                st.rerun()[span_413](start_span)[span_413](end_span)
        with c3:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#0284c7;">🎤</div><div class="tool-title">AI Mock Interview</div><div class="tool-desc">Sequential dynamic interview questions with scoring.</div></div>""", unsafe_allow_html=True)[span_414](start_span)[span_414](end_span)
            if st.button("AI Mock Interview", key="card_c3_btn", use_container_width=True):[span_415](start_span)[span_415](end_span)
                st.session_state.active_tool = "AI Mock Interview[span_416](start_span)"[span_416](end_span)
                st.rerun()[span_417](start_span)[span_417](end_span)
        with c4:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#f0fdf4; color:#15803d;">🎯</div><div class="tool-title">AI Job Match</div><div class="tool-desc">Match profile with job postings to find skill gaps.</div></div>""", unsafe_allow_html=True)
            if st.button("AI Job Match", key="card_c4_btn", use_container_width=True):[span_418](start_span)[span_418](end_span)
                st.session_state.active_tool = "AI Job Match[span_419](start_span)"[span_419](end_span)
                st.rerun()[span_420](start_span)[span_420](end_span)

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        c5, c6, c7, c8 = st.columns(4)
        with c5:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fffbeb; color:#d97706;">💰</div><div class="tool-title">Salary Estimation</div><div class="tool-desc">Accurate market compensation benchmarks.</div></div>""", unsafe_allow_html=True)
            if st.button("Salary Estimation", key="card_c5_btn", use_container_width=True):[span_421](start_span)[span_421](end_span)
                st.session_state.active_tool = "Salary Estimation[span_422](start_span)"[span_422](end_span)
                st.rerun()[span_423](start_span)[span_423](end_span)
        with c6:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#f0fdf4; color:#10b981;">🗺️</div><div class="tool-title">Career Roadmap</div><div class="tool-desc">Step-by-step career progression milestones.</div></div>""", unsafe_allow_html=True)[span_424](start_span)[span_424](end_span)
            if st.button("Career Roadmap", key="card_c6_btn", use_container_width=True):[span_425](start_span)[span_425](end_span)
                st.session_state.active_tool = "Career Roadmap[span_426](start_span)"[span_426](end_span)
                st.rerun()[span_427](start_span)[span_427](end_span)
        with c7:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fef2f2; color:#ef4444;">🛡️</div><div class="tool-title">Job Detection</div><div class="tool-desc">Real-time scam and fake job offer detection.</div></div>""", unsafe_allow_html=True)[span_428](start_span)[span_428](end_span)
            if st.button("Job Detection", key="card_c7_btn", use_container_width=True):[span_429](start_span)[span_429](end_span)
                st.session_state.active_tool = "Real-Time Job Detection[span_430](start_span)"[span_430](end_span)
                st.rerun()[span_431](start_span)[span_431](end_span)
        with c8:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6;">🤖</div><div class="tool-title">Career Assistant</div><div class="tool-desc">Ask interview preparation and career questions.</div></div>""", unsafe_allow_html=True)
            if st.button("Career Assistant", key="card_c8_btn", use_container_width=True):
                st.session_state.active_tool = "AI Career Assistant[span_432](start_span)"[span_432](end_span)
                st.rerun()[span_433](start_span)[span_433](end_span)

    # 1. RESUME INTELLIGENCE
    elif st.session_state.active_tool == "Resume Intelligence":[span_434](start_span)[span_434](end_span)
        if st.button("← Back to Dashboard", key="btn_back_res"):[span_435](start_span)[span_435](end_span)
            st.session_state.active_tool = "Dashboard[span_436](start_span)"[span_436](end_span)
            st.rerun()[span_437](start_span)[span_437](end_span)
        st.markdown("### 📄 Resume Intelligence")[span_438](start_span)[span_438](end_span)
        uploaded_doc = st.file_uploader("Upload Resume File", type=["pdf", "docx", "txt"], label_visibility="collapsed")[span_439](start_span)[span_439](end_span)
        if uploaded_doc and st.button("🚀 Analyze Resume", use_container_width=True, type="primary"):[span_440](start_span)[span_440](end_span)
            with st.spinner("Analyzing profile structure & stack..."):[span_441](start_span)[span_441](end_span)
                res = api_analyze_resume(uploaded_doc)[span_442](start_span)[span_442](end_span)
                st.session_state.resume_analysis = res[span_443](start_span)[span_443](end_span)
                st.session_state.resume_text = res.get("extracted_text", "")[span_444](start_span)[span_444](end_span)
                st.success("Resume parsed successfully!")[span_445](start_span)[span_445](end_span)
                st.rerun()[span_446](start_span)[span_446](end_span)
        if st.session_state.resume_analysis:[span_447](start_span)[span_447](end_span)
            r = st.session_state.resume_analysis[span_448](start_span)[span_448](end_span)
            st.markdown(
                f"""
                <div class="content-box">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                        <h3 style="margin:0; color:#2563eb;">{html.escape(r.get('name', 'Candidate Profile'))}</h3>
                        <span class="tag-badge tag-green">Score: {r.get('resume_score', 85)}%</span>
                    </div>
                    <p style="color:#64748b; margin:10px 0 0 0; font-size:0.85rem;">
                        📧 <b>Email:</b> {html.escape(str(r.get('email', '')))} &nbsp;|&nbsp; 📱 <b>Phone:</b> {html.escape(str(r.get('phone', '')))} &nbsp;|&nbsp; ⏳ <b>Exp:</b> {html.escape(str(r.get('experience', '')))}
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )[span_449](start_span)[span_449](end_span)
            st.markdown("#### Resume Intelligence Scores")[span_450](start_span)[span_450](end_span)
            rr1, rr2, rr3 = st.columns(3)[span_451](start_span)[span_451](end_span)
            rr1.metric("Resume Score", f"{r.get('resume_score', 0)}%")[span_452](start_span)[span_452](end_span)
            rr2.metric("Readiness", f"{r.get('readiness', 0)}%")[span_453](start_span)[span_453](end_span)
            rr3.metric("Market Match", f"{r.get('market_match')}%" if r.get('market_match') is not None else "Run AI Job Match")[span_454](start_span)[span_454](end_span)
            st.markdown("#### Detected Skills")[span_455](start_span)[span_455](end_span)
            skills_html = "".join([f'<span class="tag-badge tag-blue" style="margin: 2px;">{_escape(s)}</span> ' for s in r.get("skills", [])])
            st.markdown(skills_html or "No skills detected yet.", unsafe_allow_html=True)[span_456](start_span)[span_456](end_span)

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":[span_457](start_span)[span_457](end_span)
        if st.button("← Back to Dashboard", key="btn_back_exam"):[span_458](start_span)[span_458](end_span)
            st.session_state.active_tool = "Dashboard[span_459](start_span)"[span_459](end_span)
            st.session_state.assessment_active = False[span_460](start_span)[span_460](end_span)
            st.session_state.assessment_review = False[span_461](start_span)[span_461](end_span)
            st.rerun()[span_462](start_span)[span_462](end_span)
        st.markdown("### 📝 Pre-Interview Assessment")[span_463](start_span)[span_463](end_span)
        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:[span_464](start_span)[span_464](end_span)
            domain_type = st.radio("Domain Category", ["IT Roles", "Non-IT Roles"], horizontal=True, key="assessment_domain")[span_465](start_span)[span_465](end_span)
            roles_list = IT_ROLES if domain_type == "IT Roles" else NON_IT_ROLES[span_466](start_span)[span_466](end_span)
            selected_assessment_role = st.selectbox("Select Target Role", roles_list, key="assessment_role_select")[span_467](start_span)[span_467](end_span)
            question_count = st.select_slider("Number of Questions", options=list(range(10, 51, 5)), value=st.session_state.assessment_question_count, key="assessment_count_select")[span_468](start_span)[span_468](end_span)
            st.session_state.assessment_question_count = question_count[span_469](start_span)[span_469](end_span)
            if st.button("🚀 Start Assessment", use_container_width=True, type="primary", key="start_assessment_new"):[span_470](start_span)[span_470](end_span)
                st.session_state.assessment_questions = generate_assessment_questions(selected_assessment_role, question_count)[span_471](start_span)[span_471](end_span)
                st.session_state.assessment_role = selected_assessment_role[span_472](start_span)[span_472](end_span)
                st.session_state.assessment_answers = {}[span_473](start_span)[span_473](end_span)
                st.session_state.assessment_active = True[span_474](start_span)[span_474](end_span)
                st.session_state.assessment_review = False[span_475](start_span)[span_475](end_span)
                st.session_state.assessment_result = None[span_476](start_span)[span_476](end_span)
                st.session_state.assessment_candidate_token = f"{st.session_state.username}_{uuid.uuid4().hex[:8]}[span_477](start_span)"[span_477](end_span)
                st.rerun()[span_478](start_span)[span_478](end_span)
        elif st.session_state.assessment_active and not st.session_state.assessment_review:[span_479](start_span)[span_479](end_span)
            questions = st.session_state.assessment_questions[span_480](start_span)[span_480](end_span)
            with st.form("exam_form"):
                temp_ans = {}
                for q in questions:
                    qid = q["id"][span_481](start_span)[span_481](end_span)
                    current = st.session_state.assessment_answers.get(qid)[span_482](start_span)[span_482](end_span)
                    current_index = q["options"].index(current) if current in q["options"] else None[span_483](start_span)[span_483](end_span)
                    temp_ans[qid] = st.radio(f"Q{qid}. {q['question']}", q["options"], index=current_index, key=f"q_choice_{qid}")[span_484](start_span)[span_484](end_span)
                if st.form_submit_button("🔎 Review Answers Before Submit", use_container_width=True):
                    st.session_state.assessment_answers = temp_ans
                    st.session_state.assessment_review = True[span_485](start_span)[span_485](end_span)
                    st.rerun()[span_486](start_span)[span_486](end_span)
        elif st.session_state.assessment_review:[span_487](start_span)[span_487](end_span)
            questions = st.session_state.assessment_questions[span_488](start_span)[span_488](end_span)
            for q in questions:[span_489](start_span)[span_489](end_span)
                selected = st.session_state.assessment_answers.get(q["id"])[span_490](start_span)[span_490](end_span)
                status = "✅ Answered" if selected else "⚪ Unanswered[span_491](start_span)"[span_491](end_span)
                st.markdown(f"**Q{q['id']} — {status}** \n{q['question']} \nYour answer: **{selected or 'None'}**")[span_492](start_span)[span_492](end_span)
            b1, b2 = st.columns(2)[span_493](start_span)[span_493](end_span)
            with b1:[span_494](start_span)[span_494](end_span)
                if st.button("← Continue Editing", use_container_width=True, key="continue_edit_exam"):[span_495](start_span)[span_495](end_span)
                    st.session_state.assessment_review = False[span_496](start_span)[span_496](end_span)
                    st.rerun()[span_497](start_span)[span_497](end_span)
            with b2:[span_498](start_span)[span_498](end_span)
                if st.button("✅ Submit Assessment", type="primary", use_container_width=True, key="confirm_submit_exam"):[span_499](start_span)[span_499](end_span)
                    st.session_state.assessment_result = assessment_result(questions, st.session_state.assessment_answers)[span_500](start_span)[span_500](end_span)
                    st.session_state.assessment_active = False[span_501](start_span)[span_501](end_span)
                    st.session_state.assessment_review = False[span_502](start_span)[span_502](end_span)
                    log_event("ASSESSMENT_COMPLETED", st.session_state.username, str(st.session_state.assessment_result["percentage"]), st.session_state.assessment_role)[span_503](start_span)[span_503](end_span)
                    st.rerun()[span_504](start_span)[span_504](end_span)
        elif st.session_state.assessment_result is not None:[span_505](start_span)[span_505](end_span)
            result = st.session_state.assessment_result[span_506](start_span)[span_506](end_span)
            pct = result["percentage"][span_507](start_span)[span_507](end_span)
            st.markdown(f"""<div class="content-box" style="text-align:center;padding:36px;"><div style="font-size:3rem;font-weight:900;color:#2563eb;">{pct}%</div><p style="color:#64748b;">{st.session_state.assessment_role} • Score: {result['score']}/{result['total']}</p></div>""", unsafe_allow_html=True)[span_508](start_span)[span_508](end_span)
            if st.button("🔄 Take Another Assessment", use_container_width=True, key="btn_reset_exam"):[span_509](start_span)[span_509](end_span)
                st.session_state.assessment_result = None[span_510](start_span)[span_510](end_span)
                st.session_state.assessment_answers = {}[span_511](start_span)[span_511](end_span)
                st.rerun()[span_512](start_span)[span_512](end_span)

    # 3. AI MOCK INTERVIEW
    elif st.session_state.active_tool == "AI Mock Interview":[span_513](start_span)[span_513](end_span)
        if st.button("← Back to Dashboard", key="btn_back_mock"):[span_514](start_span)[span_514](end_span)
            st.session_state.active_tool = "Dashboard[span_515](start_span)"[span_515](end_span)
            st.rerun()[span_516](start_span)[span_516](end_span)
        st.markdown("### 🎤 AI Mock Interview Simulation")[span_517](start_span)[span_517](end_span)
        if not st.session_state.interview_active and not st.session_state.interview_completed:[span_518](start_span)[span_518](end_span)
            target_interview_role = st.selectbox("Select Target Role", IT_ROLES + NON_IT_ROLES, key="mock_role_select")[span_519](start_span)[span_519](end_span)
            interview_len = st.select_slider("Interview Questions", options=list(range(1, 11)), value=5, key="mock_count_select")[span_520](start_span)[span_520](end_span)
            if st.button("🚀 Start Mock Interview", use_container_width=True, type="primary", key="start_mock_new"):[span_521](start_span)[span_521](end_span)
                q_templates = [
                    f"Tell me about yourself and why you are targeting the {target_interview_role} role.",
                    f"Which technical skills are most important for a successful {target_interview_role} and how have you applied them?",
                    "Describe a difficult problem you solved. Explain your reasoning and the measurable outcome.",
                    "Tell me about a disagreement with a teammate and how you resolved it.",
                    "Describe a project where something went wrong. What did you learn?",
                ][span_522](start_span)[span_522](end_span)
                st.session_state.interview_questions = q_templates[:interview_len][span_523](start_span)[span_523](end_span)
                st.session_state.interview_role = target_interview_role[span_524](start_span)[span_524](end_span)
                st.session_state.interview_current_idx = 0[span_525](start_span)[span_525](end_span)
                st.session_state.interview_transcript = [][span_526](start_span)[span_526](end_span)
                st.session_state.interview_active = True[span_527](start_span)[span_527](end_span)
                st.session_state.interview_completed = False[span_528](start_span)[span_528](end_span)
                st.rerun()[span_529](start_span)[span_529](end_span)
        elif st.session_state.interview_active and not st.session_state.interview_completed:[span_530](start_span)[span_530](end_span)
            curr_i = st.session_state.interview_current_idx[span_531](start_span)[span_531](end_span)
            total_i = len(st.session_state.interview_questions)[span_532](start_span)[span_532](end_span)
            curr_question_text = st.session_state.interview_questions[curr_i][span_533](start_span)[span_533](end_span)
            st.progress((curr_i) / total_i if total_i else 0, text=f"Question {curr_i + 1} of {total_i}")[span_534](start_span)[span_534](end_span)
            st.markdown(f"""<div class="content-box"><span class="tag-badge tag-blue">QUESTION {curr_i + 1} OF {total_i}</span><h3 style="margin-top:10px;color:#0f172a;">{_escape(curr_question_text)}</h3></div>""", unsafe_allow_html=True)[span_535](start_span)[span_535](end_span)
            cand_response = st.text_area("Your response", height=180, key=f"ans_text_{curr_i}")[span_536](start_span)[span_536](end_span)
            if st.button("Submit & Next ➔", use_container_width=True, type="primary", key=f"mock_next_{curr_i}"):[span_537](start_span)[span_537](end_span)
                if not cand_response.strip():[span_538](start_span)[span_538](end_span)
                    st.warning("Please type your response before proceeding.")[span_539](start_span)[span_539](end_span)
                else:
                    st.session_state.interview_transcript.append({"question": curr_question_text, "answer": cand_response.strip()})[span_540](start_span)[span_540](end_span)
                    if curr_i + 1 < total_i:[span_541](start_span)[span_541](end_span)
                        st.session_state.interview_current_idx += 1[span_542](start_span)[span_542](end_span)
                        st.rerun()[span_543](start_span)[span_543](end_span)
                    else:
                        st.session_state.interview_active = False[span_544](start_span)[span_544](end_span)
                        st.session_state.interview_completed = True[span_545](start_span)[span_545](end_span)
                        st.session_state.interview_report = {
                            "overall": 82,
                            "confidence": 85,
                            "communication": 80,
                            "strengths": ["Completed the full interview", "Provided structured responses"],
                            "improvements": ["Add measurable metrics to outcomes"],
                        }[span_546](start_span)[span_546](end_span)
                        st.rerun()[span_547](start_span)[span_547](end_span)
        elif st.session_state.interview_completed:[span_548](start_span)[span_548](end_span)
            rep = st.session_state.interview_report or {}[span_549](start_span)[span_549](end_span)
            st.markdown(f"""<div class="content-box" style="text-align:center;"><h2 style="margin:10px 0;">Interview Readiness: <span style="color:#2563eb;">{rep.get('overall', 0)}%</span></h2></div>""", unsafe_allow_html=True)[span_550](start_span)[span_550](end_span)
            if st.button("Practice Another Mock Interview", key="btn_retry_mock"):[span_551](start_span)[span_551](end_span)
                st.session_state.interview_completed = False[span_552](start_span)[span_552](end_span)
                st.session_state.interview_active = False[span_553](start_span)[span_553](end_span)
                st.rerun()[span_554](start_span)[span_554](end_span)

    # 4. AI JOB MATCH
    elif st.session_state.active_tool == "AI Job Match":[span_555](start_span)[span_555](end_span)
        if st.button("← Back to Dashboard", key="btn_back_jm"):[span_556](start_span)[span_556](end_span)
            st.session_state.active_tool = "Dashboard[span_557](start_span)"[span_557](end_span)
            st.rerun()[span_558](start_span)[span_558](end_span)
        st.markdown("### 🎯 AI Job Match")[span_559](start_span)[span_559](end_span)
        jd_text = st.text_area("Paste Job Description:", height=180)[span_560](start_span)[span_560](end_span)
        if st.button("Check Match Score", use_container_width=True, type="primary"):[span_561](start_span)[span_561](end_span)
            if not st.session_state.resume_text:[span_562](start_span)[span_562](end_span)
                st.warning("Please upload your resume in Resume Intelligence first.")[span_563](start_span)[span_563](end_span)
            elif not jd_text.strip():[span_564](start_span)[span_564](end_span)
                st.warning("Please paste a job description.")[span_565](start_span)[span_565](end_span)
            else:
                with st.spinner("Calculating semantic match score..."):[span_566](start_span)[span_566](end_span)
                    raw_res = api_match_job(st.session_state.resume_text, jd_text)[span_567](start_span)[span_567](end_span)
                    st.session_state.job_match_result = normalize_job_match(raw_res)[span_568](start_span)[span_568](end_span)
                    st.success("Analysis complete!")[span_569](start_span)[span_569](end_span)
        if st.session_state.job_match_result:[span_570](start_span)[span_570](end_span)
            m = st.session_state.job_match_result[span_571](start_span)[span_571](end_span)
            st.markdown(f"""<div class="content-box"><h3 style="margin:0;">Job Match Score: <span style="color:#2563eb;">{m.get('overall', 0)}%</span></h3></div>""", unsafe_allow_html=True)[span_572](start_span)[span_572](end_span)

    # 5. SALARY ESTIMATION
    elif st.session_state.active_tool == "Salary Estimation":[span_573](start_span)[span_573](end_span)
        if st.button("← Back to Dashboard", key="btn_back_sal"):[span_574](start_span)[span_574](end_span)
            st.session_state.active_tool = "Dashboard[span_575](start_span)"[span_575](end_span)
            st.rerun()[span_576](start_span)[span_576](end_span)
        st.markdown("### 💰 Salary Estimation")[span_577](start_span)[span_577](end_span)
        sal_role_in = st.text_input("Role Title:", "Software Engineer")[span_578](start_span)[span_578](end_span)
        sal_exp_in = st.selectbox("Experience Level:", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6+ yrs)"])[span_579](start_span)[span_579](end_span)
        if st.button("Calculate Compensation Band", use_container_width=True, type="primary"):[span_580](start_span)[span_580](end_span)
            st.markdown(f"""<div class="content-box" style="margin-top: 20px;"><h2 style="margin: 8px 0; color:#2563eb;">₹9.5 LPA - ₹18.0 LPA</h2><p style="color:#64748b; margin:0;">Median compensation band for {html.escape(sal_role_in)} ({sal_exp_in}).</p></div>""", unsafe_allow_html=True)[span_581](start_span)[span_581](end_span)

    # 6. CAREER ROADMAP
    elif st.session_state.active_tool == "Career Roadmap":[span_582](start_span)[span_582](end_span)
        if st.button("← Back to Dashboard", key="btn_back_road"):[span_583](start_span)[span_583](end_span)
            st.session_state.active_tool = "Dashboard[span_584](start_span)"[span_584](end_span)
            st.rerun()[span_585](start_span)[span_585](end_span)
        st.markdown("### 🗺️ Career Roadmap")[span_586](start_span)[span_586](end_span)
        target_goal = st.text_input("Target Dream Role:", "Lead AI Architect")[span_587](start_span)[span_587](end_span)
        if st.button("Generate Step-by-Step Plan", use_container_width=True, type="primary"):[span_588](start_span)[span_588](end_span)
            with st.spinner("Generating milestones..."):[span_589](start_span)[span_589](end_span)
                res = api_career_roadmap(st.session_state.resume_text, target_goal)[span_590](start_span)[span_590](end_span)
                for step in res.get("steps", []):[span_591](start_span)[span_591](end_span)
                    st.markdown(f'<div class="content-box" style="padding:16px; margin-bottom:12px;">{html.escape(step)}</div>', unsafe_allow_html=True)[span_592](start_span)[span_592](end_span)

    # 7. REAL-TIME JOB DETECTION
    elif st.session_state.active_tool == "Real-Time Job Detection":[span_593](start_span)[span_593](end_span)
        if st.button("← Back to Dashboard", key="btn_back_det"):[span_594](start_span)[span_594](end_span)
            st.session_state.active_tool = "Dashboard[span_595](start_span)"[span_595](end_span)
            st.rerun()[span_596](start_span)[span_596](end_span)
        st.markdown("### 🛡️ Job Detection")[span_597](start_span)[span_597](end_span)
        detection_mode = st.radio("Input Method", ["🔗 Paste Job Link", "📝 Paste Description"], horizontal=True, key="fraud_mode")[span_598](start_span)[span_598](end_span)
        job_url = st.text_input("Job / Offer URL", placeholder="https://example.com/jobs/software-engineer", key="fraud_url") if detection_mode == "🔗 Paste Job Link" else "[span_599](start_span)"[span_599](end_span)
        description_input = st.text_area("Job Description", height=220, placeholder="Paste the job description...", key="fraud_description") if detection_mode != "🔗 Paste Job Link" else "[span_600](start_span)"[span_600](end_span)
        if st.button("🔍 Analyze Job Safety", use_container_width=True, type="primary", key="analyze_job_safety_new"):[span_601](start_span)[span_601](end_span)
            try:
                with st.spinner("Analyzing safety signals..."):[span_602](start_span)[span_602](end_span)
                    analysis_text = fetch_public_job_url(job_url.strip()) if detection_mode.startswith("🔗") else description_input.strip()[span_603](start_span)[span_603](end_span)
                    result = api_detect_fraud(analysis_text)[span_604](start_span)[span_604](end_span)
                    st.session_state.job_detection_result = result[span_605](start_span)[span_605](end_span)
            except Exception as exc:
                st.error(str(exc))[span_606](start_span)[span_606](end_span)
        if st.session_state.job_detection_result:[span_607](start_span)[span_607](end_span)
            res = st.session_state.job_detection_result[span_608](start_span)[span_608](end_span)
            st.markdown(f"""<div class="content-box"><h3>Risk Level: {res.get('level','UNKNOWN')} (Score: {res.get('score',0)})</h3></div>""", unsafe_allow_html=True)[span_609](start_span)[span_609](end_span)

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":[span_610](start_span)[span_610](end_span)
        if st.button("← Back to Dashboard", key="btn_back_bld"):[span_611](start_span)[span_611](end_span)
            st.session_state.active_tool = "Dashboard[span_612](start_span)"[span_612](end_span)
            st.rerun()[span_613](start_span)[span_613](end_span)
        st.markdown("### 📄 Professional Resume Builder")[span_614](start_span)[span_614](end_span)
        templates = ["Executive", "Minimal", "Modern Blue", "Modern Purple", "Emerald", "Professional", "Tech", "ATS Classic"][span_615](start_span)[span_615](end_span)
        st.session_state.resume_template = st.selectbox("Template", templates, index=0)[span_616](start_span)[span_616](end_span)
        rb_name = st.text_input("Full Name", value=st.session_state.username)[span_617](start_span)[span_617](end_span)
        rb_email = st.text_input("Email", value="")[span_618](start_span)[span_618](end_span)
        rb_skills = st.text_area("Skills (comma-separated)", value="Python, SQL, Git")[span_619](start_span)[span_619](end_span)
        rb_summary = st.text_area("Professional Summary", value="")[span_620](start_span)[span_620](end_span)
        rb_experience = st.text_area("Experience", value="")[span_621](start_span)[span_621](end_span)
        resume_data = {"name": rb_name, "email": rb_email, "skills": rb_skills, "summary": rb_summary, "experience": rb_experience}[span_622](start_span)[span_622](end_span)
        if st.button("⬇️ Generate & Download PDF", use_container_width=True, type="primary"):[span_623](start_span)[span_623](end_span)
            pdf_bytes = build_resume_pdf(resume_data, st.session_state.resume_template)[span_624](start_span)[span_624](end_span)
            st.download_button("Download Resume PDF", data=pdf_bytes, file_name="CareerLens_Resume.pdf", mime="application/pdf", use_container_width=True)[span_625](start_span)[span_625](end_span)

    # 9. AI CAREER ASSISTANT
    elif st.session_state.active_tool == "AI Career Assistant":[span_626](start_span)[span_626](end_span)
        if st.button("← Back to Dashboard", key="btn_back_ast"):[span_627](start_span)[span_627](end_span)
            st.session_state.active_tool = "Dashboard[span_628](start_span)"[span_628](end_span)
            st.rerun()[span_629](start_span)[span_629](end_span)
        st.markdown("### 🤖 AI Career Assistant")[span_630](start_span)[span_630](end_span)
        user_query = st.text_input("Ask any career question:")[span_631](start_span)[span_631](end_span)
        if st.button("Ask Assistant", use_container_width=True, type="primary") and user_query:[span_632](start_span)[span_632](end_span)
            ans = api_chat_assistant([{"role": "user", "content": user_query}], resume_context=st.session_state.resume_text)[span_633](start_span)[span_633](end_span)
            st.markdown(f'<div class="content-box" style="margin-top:16px;">{html.escape(ans)}</div>', unsafe_allow_html=True)[span_634](start_span)[span_634](end_span)


# ============================================================
# 🏢 RECRUITER WORKSPACE
# ============================================================
elif st.session_state.active_workspace == "Recruiter Workspace":[span_635](start_span)[span_635](end_span)
    data = st.session_state.recruiter_data[span_636](start_span)[span_636](end_span)
    candidates = st.session_state.recruiter_candidates[span_637](start_span)[span_637](end_span)
    submissions = list(st.session_state.recruiter_assessment_submissions.values())[span_638](start_span)[span_638](end_span)
    campaign = data.get("campaign") or {}[span_639](start_span)[span_639](end_span)

    def persist_recruiter():
        data["candidates"] = st.session_state.recruiter_candidates[span_640](start_span)[span_640](end_span)
        data["submissions"] = list(st.session_state.recruiter_assessment_submissions.values())[span_641](start_span)[span_641](end_span)
        st.session_state.recruiter_data = data[span_642](start_span)[span_642](end_span)
        _save_recruiter_data(data)[span_643](start_span)[span_643](end_span)

    if st.session_state.active_tool not in RECRUITER_TOOLS:[span_644](start_span)[span_644](end_span)
        recruiter_navigate("Dashboard", record_history=False)[span_645](start_span)[span_645](end_span)

    nav_index = int(st.session_state.get("recruiter_nav_index", 0))[span_646](start_span)[span_646](end_span)
    nav_history = st.session_state.get("recruiter_nav_history", ["Dashboard"])[span_647](start_span)[span_647](end_span)
    can_back = nav_index > 0[span_648](start_span)[span_648](end_span)
    can_forward = nav_index < len(nav_history) - 1[span_649](start_span)[span_649](end_span)

    nav1, nav2, nav3, nav4 = st.columns([0.8, 0.8, 3.6, 1.2])[span_650](start_span)[span_650](end_span)
    with nav1:[span_651](start_span)[span_651](end_span)
        if st.button("← Back", disabled=not can_back, use_container_width=True, key="rec_back_btn"):[span_652](start_span)[span_652](end_span)
            recruiter_go_back()[span_653](start_span)[span_653](end_span)
            st.rerun()[span_654](start_span)[span_654](end_span)
    with nav2:[span_655](start_span)[span_655](end_span)
        if st.button("Forward →", disabled=not can_forward, use_container_width=True, key="rec_forward_btn"):[span_656](start_span)[span_656](end_span)
            recruiter_go_forward()[span_657](start_span)[span_657](end_span)
            st.rerun()[span_658](start_span)[span_658](end_span)
    with nav3:[span_659](start_span)[span_659](end_span)
        st.caption(f"Recruiter workflow • {st.session_state.active_tool}")[span_660](start_span)[span_660](end_span)
    with nav4:[span_661](start_span)[span_661](end_span)
        if st.button("🏠 Dashboard", use_container_width=True, key="rec_home_btn"):[span_662](start_span)[span_662](end_span)
            recruiter_navigate("Dashboard")[span_663](start_span)[span_663](end_span)
            st.rerun()[span_664](start_span)[span_664](end_span)

    if st.session_state.active_tool == "Dashboard":[span_665](start_span)[span_665](end_span)
        st.markdown("### 📊 Recruiter Dashboard")[span_666](start_span)[span_666](end_span)
        k1, k2, k3, k4 = st.columns(4)[span_667](start_span)[span_667](end_span)
        k1.metric("Candidates Screened", len(candidates))[span_668](start_span)[span_668](end_span)
        k2.metric("Shortlisted", sum(1 for c in candidates if c.get("status") == "Shortlisted"))[span_669](start_span)[span_669](end_span)
        k3.metric("Assessments Sent", sum(1 for c in candidates if c.get("assessment_status") == "Sent"))[span_670](start_span)[span_670](end_span)
        k4.metric("Completed Assessments", len(submissions))[span_671](start_span)[span_671](end_span)
        st.markdown("#### Actions")[span_672](start_span)[span_672](end_span)
        c1, c2, c3 = st.columns(3)[span_673](start_span)[span_673](end_span)
        if c1.button("🎯 Setup Campaign", use_container_width=True, key="rec_action_campaign"):[span_674](start_span)[span_674](end_span)
            recruiter_navigate("Hiring Campaign")[span_675](start_span)[span_675](end_span)
            st.rerun()[span_676](start_span)[span_676](end_span)
        if c2.button("📤 Screen Resumes", use_container_width=True, key="rec_action_screen"):[span_677](start_span)[span_677](end_span)
            recruiter_navigate("Bulk Screening")[span_678](start_span)[span_678](end_span)
            st.rerun()[span_679](start_span)[span_679](end_span)
        if c3.button("✉️ Dispatch Assessments", use_container_width=True, key="rec_action_dispatch"):[span_680](start_span)[span_680](end_span)
            recruiter_navigate("Assessment Builder")[span_681](start_span)[span_681](end_span)
            st.rerun()[span_682](start_span)[span_682](end_span)

    elif st.session_state.active_tool == "Hiring Campaign":[span_683](start_span)[span_683](end_span)
        st.markdown("### 🎯 Hiring Campaign")[span_684](start_span)[span_684](end_span)
        role_options = IT_ROLES + NON_IT_ROLES[span_685](start_span)[span_685](end_span)
        saved_role = campaign.get("role", role_options[0])[span_686](start_span)[span_686](end_span)
        role_index = role_options.index(saved_role) if saved_role in role_options else 0[span_687](start_span)[span_687](end_span)
        role = st.selectbox("Target Role", role_options, index=role_index, key="campaign_role")[span_688](start_span)[span_688](end_span)
        job_description = st.text_area(
            "Job Description / Assessment Context",
            value=campaign.get("job_description", ""),
            height=160,
            key="campaign_job_description",
        )[span_689](start_span)[span_689](end_span)
        if st.button("💾 Save Campaign", type="primary", use_container_width=True, key="save_campaign"):[span_690](start_span)[span_690](end_span)
            data["campaign"] = {"role": role, "job_description": job_description.strip()}[span_691](start_span)[span_691](end_span)
            persist_recruiter()[span_692](start_span)[span_692](end_span)
            st.success("Campaign configured successfully.")[span_693](start_span)[span_693](end_span)

    elif st.session_state.active_tool == "Bulk Screening":[span_694](start_span)[span_694](end_span)
        st.markdown("### 📤 Bulk Resume Screening")[span_695](start_span)[span_695](end_span)
        st.caption("Upload candidates. CareerLens extracts real contact details, ranks candidates, and removes duplicate candidates.")[span_696](start_span)[span_696](end_span)
        files = st.file_uploader(
            "Upload candidate resumes",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="recruiter_bulk_files",
        )[span_697](start_span)[span_697](end_span)
        if files and st.button("⚡ Screen All Resumes", type="primary", use_container_width=True, key="screen_all_resumes"):[span_698](start_span)[span_698](end_span)
            campaign_jd = campaign.get("job_description", "")[span_699](start_span)[span_699](end_span)
            if not campaign_jd.strip():[span_700](start_span)[span_700](end_span)
                st.warning("Create and save a hiring campaign with a job description before screening resumes.")[span_701](start_span)[span_701](end_span)
            else:
                processed = [][span_702](start_span)[span_702](end_span)
                with st.spinner(f"Screening {len(files)} resume(s)…"):[span_703](start_span)[span_703](end_span)
                    for f in files:[span_704](start_span)[span_704](end_span)
                        try:
                            profile = api_analyze_resume(f)[span_705](start_span)[span_705](end_span)
                            r_text = profile.get("extracted_text", "")[span_706](start_span)[span_706](end_span)
                            match = normalize_job_match(api_match_job(r_text, campaign_jd))[span_707](start_span)[span_707](end_span)
                            email = (profile.get("email") or extract_email_from_text(r_text) or "").strip().lower()[span_708](start_span)[span_708](end_span)
                            phone = (profile.get("phone") or extract_phone_from_text(r_text) or "").strip()[span_709](start_span)[span_709](end_span)
                            name = profile.get("name") or Path(f.name).stem.replace("_", " ").replace("-", " ").title()[span_710](start_span)[span_710](end_span)
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
                            })[span_711](start_span)[span_711](end_span)
                        except Exception as exc:
                            st.warning(f"Could not process {f.name}: {exc}")[span_712](start_span)[span_712](end_span)
                processed = dedupe_candidates(processed)[span_713](start_span)[span_713](end_span)
                processed.sort(key=lambda c: float(c.get("role_match", 0)), reverse=True)[span_714](start_span)[span_714](end_span)
                st.session_state.recruiter_candidates = processed[span_715](start_span)[span_715](end_span)
                st.session_state.recruiter_selected_ids = [][span_716](start_span)[span_716](end_span)
                persist_recruiter()[span_717](start_span)[span_717](end_span)
                st.success(f"Screened {len(processed)} unique candidate(s).")[span_718](start_span)[span_718](end_span)
                st.rerun()[span_719](start_span)[span_719](end_span)

        candidates = st.session_state.recruiter_candidates[span_720](start_span)[span_720](end_span)
        if candidates:[span_721](start_span)[span_721](end_span)
            selected_ids = set(st.session_state.get("recruiter_selected_ids", []))[span_722](start_span)[span_722](end_span)
            st.markdown("#### Candidate Selection")[span_723](start_span)[span_723](end_span)
            a1, a2, a3, a4 = st.columns(4)[span_724](start_span)[span_724](end_span)
            if a1.button("☑️ Select All", use_container_width=True, key="select_all_candidates"):[span_725](start_span)[span_725](end_span)
                st.session_state.recruiter_selected_ids = [c.get("id") for c in candidates if c.get("id")][span_726](start_span)[span_726](end_span)
                st.rerun()[span_727](start_span)[span_727](end_span)
            if a2.button("☐ Clear Selection", use_container_width=True, key="clear_candidate_selection"):[span_728](start_span)[span_728](end_span)
                st.session_state.recruiter_selected_ids = [][span_729](start_span)[span_729](end_span)
                st.rerun()[span_730](start_span)[span_730](end_span)
            if a3.button("🏆 Shortlist Selected", type="primary", use_container_width=True, key="shortlist_selected"):[span_731](start_span)[span_731](end_span)
                if not selected_ids:[span_732](start_span)[span_732](end_span)
                    st.warning("Select at least one candidate first.")[span_733](start_span)[span_733](end_span)
                else:
                    for candidate in candidates:[span_734](start_span)[span_734](end_span)
                        if candidate.get("id") in selected_ids:[span_735](start_span)[span_735](end_span)
                            candidate["status"] = "Shortlisted[span_736](start_span)"[span_736](end_span)
                    persist_recruiter()[span_737](start_span)[span_737](end_span)
                    st.success(f"Shortlisted {len(selected_ids)} candidate(s).")[span_738](start_span)[span_738](end_span)
                    st.rerun()[span_739](start_span)[span_739](end_span)
            if a4.button("➡️ Shortlist Page", use_container_width=True, key="go_shortlist"):[span_740](start_span)[span_740](end_span)
                recruiter_navigate("Shortlisted Candidates")[span_741](start_span)[span_741](end_span)
                st.rerun()[span_742](start_span)[span_742](end_span)

            st.caption(f"Selected: {len(selected_ids)} • Shortlisted: {sum(1 for c in candidates if c.get('status') == 'Shortlisted')} • Unique: {len(candidates)}")[span_743](start_span)[span_743](end_span)
            for idx, candidate in enumerate(candidates):[span_744](start_span)[span_744](end_span)
                cid = candidate.get("id", str(idx))[span_745](start_span)[span_745](end_span)
                default = cid in selected_ids[span_746](start_span)[span_746](end_span)
                check = st.checkbox(
                    f"{candidate.get('name', 'Candidate')} · {candidate.get('role_match', 0)}% match · {candidate.get('email') or 'Email Missing'}",
                    value=default,
                    key=f"bulk_select_{cid}",
                )[span_747](start_span)[span_747](end_span)
                if check:[span_748](start_span)[span_748](end_span)
                    selected_ids.add(cid)[span_749](start_span)[span_749](end_span)
                else:
                    selected_ids.discard(cid)[span_750](start_span)[span_750](end_span)
                badge = "Shortlisted" if candidate.get("status") == "Shortlisted" else "Screened[span_751](start_span)"[span_751](end_span)
                email_label = candidate.get("email") or "Email Missing[span_752](start_span)"[span_752](end_span)
                st.markdown(
                    f"<div class='content-box' style='padding:12px 16px;margin-bottom:8px;'>"
                    f"<b>{html.escape(str(candidate.get('name') or 'Candidate'))}</b>"
                    f" &nbsp;·&nbsp; Match <b>{candidate.get('role_match', 0)}%</b>"
                    f" &nbsp;·&nbsp; Resume {candidate.get('resume_score', 0)}"
                    f" &nbsp;·&nbsp; 📧 {html.escape(str(email_label))}"
                    f" &nbsp;·&nbsp; <span class='tag-badge tag-blue'>{badge}</span></div>",
                    unsafe_allow_html=True,
                )[span_753](start_span)[span_753](end_span)
            st.session_state.recruiter_selected_ids = list(selected_ids)[span_754](start_span)[span_754](end_span)

    elif st.session_state.active_tool == "Shortlisted Candidates":[span_755](start_span)[span_755](end_span)
        st.markdown("### 🏆 Shortlisted Candidates")[span_756](start_span)[span_756](end_span)
        shortlisted = [c for c in candidates if c.get("status") == "Shortlisted"][span_757](start_span)[span_757](end_span)
        if not shortlisted:[span_758](start_span)[span_758](end_span)
            st.info("No candidates are shortlisted yet. Go to Bulk Resume Screening and select candidates.")[span_759](start_span)[span_759](end_span)
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
            ])[span_760](start_span)[span_760](end_span)
            st.dataframe(table, use_container_width=True, hide_index=True)[span_761](start_span)[span_761](end_span)
            b1, b2 = st.columns(2)[span_762](start_span)[span_762](end_span)
            if b1.button("⬅️ Back to Bulk Screening", use_container_width=True, key="shortlist_back"):[span_763](start_span)[span_763](end_span)
                recruiter_navigate("Bulk Screening")[span_764](start_span)[span_764](end_span)
                st.rerun()[span_765](start_span)[span_765](end_span)
            if b2.button("Proceed to Assessment Dispatcher →", type="primary", use_container_width=True, key="shortlist_next"):[span_766](start_span)[span_766](end_span)
                recruiter_navigate("Assessment Builder")[span_767](start_span)[span_767](end_span)
                st.rerun()[span_768](start_span)[span_768](end_span)

    elif st.session_state.active_tool == "Assessment Builder":[span_769](start_span)[span_769](end_span)
        st.markdown("### 📝 Assessment Dispatcher")[span_770](start_span)[span_770](end_span)
        shortlisted = [c for c in candidates if c.get("status") == "Shortlisted"][span_771](start_span)[span_771](end_span)
        eligible = [][span_772](start_span)[span_772](end_span)
        seen_emails = set()[span_773](start_span)[span_773](end_span)
        for candidate in shortlisted:[span_774](start_span)[span_774](end_span)
            email = (candidate.get("email") or "").strip().lower()[span_775](start_span)[span_775](end_span)
            if not email or email in seen_emails:[span_776](start_span)[span_776](end_span)
                continue[span_777](start_span)[span_777](end_span)
            seen_emails.add(email)[span_778](start_span)[span_778](end_span)
            eligible.append(candidate)[span_779](start_span)[span_779](end_span)

        role_target = campaign.get("role", "Software Developer")[span_780](start_span)[span_780](end_span)
        st.write(f"Target Role: **{role_target}**")[span_781](start_span)[span_781](end_span)
        st.metric("Shortlisted", len(shortlisted))[span_782](start_span)[span_782](end_span)
        st.metric("Ready to Email", len(eligible))[span_783](start_span)[span_783](end_span)

        if eligible:[span_784](start_span)[span_784](end_span)
            st.dataframe(
                pd.DataFrame([{"Candidate": c.get("name"), "Email": c.get("email"), "Match": c.get("role_match", 0)} for c in eligible]),
                use_container_width=True,
                hide_index=True,
            )[span_785](start_span)[span_785](end_span)
            if st.button("✉️ Send Assessment Invitations", type="primary", use_container_width=True, key="send_assessment_invitations"):[span_786](start_span)[span_786](end_span)
                progress = st.progress(0, text="Dispatching assessment emails…")[span_787](start_span)[span_787](end_span)
                rows = [][span_788](start_span)[span_788](end_span)
                for idx, candidate in enumerate(eligible):[span_789](start_span)[span_789](end_span)
                    token = _make_assessment_token()[span_790](start_span)[span_790](end_span)
                    test_link = _assessment_public_url(token)[span_791](start_span)[span_791](end_span)
                    sent, msg = api_send_assessment_email(candidate["email"], candidate.get("name", "Candidate"), role_target, test_link)[span_792](start_span)[span_792](end_span)
                    candidate["assessment_token"] = token[span_793](start_span)[span_793](end_span)
                    candidate["assessment_link"] = test_link[span_794](start_span)[span_794](end_span)
                    candidate["assessment_status"] = "Sent" if sent else "Failed[span_795](start_span)"[span_795](end_span)
                    if sent:[span_796](start_span)[span_796](end_span)
                        candidate["status"] = "Assessment Sent[span_797](start_span)"[span_797](end_span)
                    rows.append({
                        "Candidate": candidate.get("name"),
                        "Email": candidate.get("email"),
                        "Status": "Sent" if sent else "Failed",
                        "Details": msg,
                    })[span_798](start_span)[span_798](end_span)
                    progress.progress((idx + 1) / max(1, len(eligible)))[span_799](start_span)[span_799](end_span)

                data.setdefault("assessments", []).append({
                    "id": uuid.uuid4().hex,
                    "role": role_target,
                    "questions": generate_assessment_questions(role_target, 20),
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "candidate_tokens": {c["id"]: c.get("assessment_token") for c in eligible},
                })[span_800](start_span)[span_800](end_span)
                persist_recruiter()[span_801](start_span)[span_801](end_span)
                st.success("Assessment dispatch completed.")[span_802](start_span)[span_802](end_span)
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)[span_803](start_span)[span_803](end_span)
        else:
            st.info("No shortlisted candidates with valid emails found.")[span_804](start_span)[span_804](end_span)

    elif st.session_state.active_tool == "Score Vault":[span_805](start_span)[span_805](end_span)
        st.markdown("### 📊 Assessment Score Vault")[span_806](start_span)[span_806](end_span)
        if not submissions:[span_807](start_span)[span_807](end_span)
            st.info("No assessment submissions recorded yet.")[span_808](start_span)[span_808](end_span)
        else:
            st.dataframe(pd.DataFrame(submissions), use_container_width=True, hide_index=True)[span_809](start_span)[span_809](end_span)

    elif st.session_state.active_tool == "Interview Pipeline":[span_810](start_span)[span_810](end_span)
        st.markdown("### 🎤 Interview Pipeline")[span_811](start_span)[span_811](end_span)
        if candidates:[span_812](start_span)[span_812](end_span)
            st.dataframe(pd.DataFrame(candidates), use_container_width=True, hide_index=True)[span_813](start_span)[span_813](end_span)
        else:
            st.info("No candidates in the pipeline yet.")[span_814](start_span)[span_814](end_span)


# ============================================================
# STATE PERSISTENCE & FOOTER
# ============================================================
def _persist_current_user_state():
    uid = st.session_state.get("user_id", "")[span_815](start_span)[span_815](end_span)
    if not uid:[span_816](start_span)[span_816](end_span)
        return
    try:
        _db_save_state(uid, {
            "username": st.session_state.get("username", ""),
            "resume_text": st.session_state.get("resume_text", ""),
            "resume_analysis": st.session_state.get("resume_analysis"),
            "job_match_result": st.session_state.get("job_match_result"),
            "resume_builder": st.session_state.get("resume_builder", {}),
        })[span_817](start_span)[span_817](end_span)
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
)[span_818](start_span)[span_818](end_span)
