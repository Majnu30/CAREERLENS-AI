"""CareerLens AI - Streamlit Web Application (Recruiter Workflow v7 Assessment Experience)."""

from __future__ import annotations

import base64
import binascii
import csv
from datetime import datetime, timedelta
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
PUBLIC_APP_URL = "https://career-lens-ai.streamlit.app"

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon=None,
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
        conn.execute("""CREATE TABLE IF NOT EXISTS public_assessments (
            token TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            assessment_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            used INTEGER NOT NULL DEFAULT 0
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_public_assessments_owner ON public_assessments(owner_user_id)")


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
            "recommended_skills": raw_res.get("recommended_skills", missing[:10]) if isinstance(raw_res.get("recommended_skills", missing[:10]), list) else missing[:10],
            "semantic_similarity": float(raw_res.get("semantic_similarity", 0) or 0),
            "summary": str(raw_res.get("summary", "Analysis completed successfully.")),
            "experience_alignment": str(raw_res.get("experience_alignment", "Strong Alignment")),
        }
    return {
        "overall": 0,
        "matched": [],
        "missing": [],
        "summary": "No valid job-match result was returned.",
        "experience_alignment": "Unavailable",
        "recommended_skills": [],
        "source": "validation",
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
# FULLY RESPONSIVE DESIGN SYSTEM (MOBILE, TABLET, DESKTOP)
# ============================================================
st.markdown("""<style>
:root{--ink:#172033;--muted:#667085;--line:#e4e7ec;--page:#f7f8fa;--blue:#2457d6;--blue-dark:#1d46ad;--blue-soft:#eef4ff;--shadow:0 8px 24px rgba(16,24,40,.055)}
*{box-sizing:border-box}html,body,.stApp{font-family:Inter,'Segoe UI',sans-serif!important;background:var(--page)!important;color:var(--ink)!important}.stApp{background:#f7f8fa!important}#MainMenu,footer{visibility:hidden}header[data-testid="stHeader"]{background:transparent!important}.block-container{max-width:1440px!important;padding:clamp(12px,2.2vw,28px) clamp(10px,3vw,36px) 50px!important}p,span,label,div{font-family:Inter,'Segoe UI',sans-serif}h1,h2,h3,h4{color:var(--ink)!important;letter-spacing:-.025em}
.stTextInput input,.stTextArea textarea,[data-baseweb="select"]{background:#fff!important;color:var(--ink)!important;border:1px solid #d0d5dd!important;border-radius:10px!important}.stTextInput input:focus,.stTextArea textarea:focus{border-color:#2457d6!important;box-shadow:0 0 0 3px rgba(36,87,214,.10)!important}[data-testid="stFileUploader"]{background:#fff!important;border:1px dashed #b8c2d0!important;border-radius:12px!important}
.stButton>button{border-radius:9px!important;border:1px solid #d0d5dd!important;background:#fff!important;color:#344054!important;font-weight:700!important;min-height:42px!important;box-shadow:0 1px 2px rgba(16,24,40,.03)!important;transition:background .16s ease,border-color .16s ease,box-shadow .16s ease,transform .16s ease!important}.stButton>button:hover{background:#f8fafc!important;border-color:#98a2b3!important;color:#172033!important;transform:translateY(-1px)!important}.stButton>button[kind="primary"]{background:var(--blue)!important;border-color:var(--blue)!important;color:#fff!important;box-shadow:0 4px 10px rgba(36,87,214,.16)!important}.stButton>button[kind="primary"]:hover{background:var(--blue-dark)!important;border-color:var(--blue-dark)!important}
.content-box,.gateway-card,.landing-feature,.kpi-card,.tool-box-card{background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow)}.content-box{padding:20px;margin-bottom:16px}.gateway-card{padding:20px;height:100%}.landing-feature{min-height:130px;padding:18px}.landing-feature-title{font-weight:800;color:var(--ink);font-size:.92rem}.landing-feature-text{margin-top:5px;color:var(--muted);font-size:.76rem;line-height:1.5}.kpi-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:18px}.kpi-card{padding:15px;display:flex;align-items:center;gap:11px}.kpi-icon-badge{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;flex-shrink:0;background:var(--blue-soft);color:var(--blue)}.tool-box-card{padding:17px 13px 12px;text-align:center;min-height:148px}.tool-icon-circle{width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;margin:0 auto 9px;background:#f2f4f7;color:#344054}.tool-title{font-size:.82rem;font-weight:800;color:var(--ink);margin-bottom:4px}.tool-desc{font-size:.68rem;color:var(--muted);line-height:1.42}.header-banner{background:#fff;border:1px solid var(--line);border-radius:12px;padding:17px 20px;margin-bottom:18px;box-shadow:var(--shadow);display:flex;justify-content:space-between;align-items:center}.header-title{font-size:1.3rem!important;font-weight:800!important}.header-sub{font-size:.76rem!important;color:var(--muted)!important;margin-top:3px}.tag-badge{display:inline-flex;align-items:center;padding:4px 8px;border-radius:999px;font-size:.64rem;font-weight:700}.tag-blue{background:var(--blue-soft);color:var(--blue);border:1px solid #dbe7ff}.tag-green{background:#ecfdf3;color:#16794c;border:1px solid #ccebd9}.tag-amber{background:#fff7e6;color:#a15c07;border:1px solid #f1dfb8}.tag-purple{background:#f4f3ff;color:#5146a8;border:1px solid #e4e2ff}
.landing-frame{background:#fff;border:1px solid #e4e7ec;border-radius:18px;box-shadow:0 12px 34px rgba(16,24,40,.06);padding:clamp(18px,3vw,34px);margin:8px 0 16px}.landing-content{max-width:1160px;margin:0 auto}.landing-nav{display:flex;align-items:center;justify-content:space-between;gap:18px;padding-bottom:18px;border-bottom:1px solid #eef0f3}.landing-brand{display:flex;align-items:center;gap:9px;font-size:1.15rem;font-weight:800;color:#172033;letter-spacing:-.035em}.brand-mark{width:30px;height:30px;border:1.5px solid #2457d6;border-radius:9px;display:flex;align-items:center;justify-content:center;color:#2457d6;background:#f7f9ff;font-size:.62rem;font-weight:800}.landing-links{display:flex;gap:24px;align-items:center;color:#667085;font-size:.72rem;font-weight:600}.landing-link{white-space:nowrap}.landing-hero{display:grid;grid-template-columns:1.18fr .82fr;gap:50px;align-items:center;padding:70px 2px 58px}.landing-kicker{display:inline-flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid #dbe7ff;border-radius:7px;background:#f5f8ff;color:#2457d6;font-size:.63rem;font-weight:800;letter-spacing:.08em}.landing-title{margin:17px 0 15px;font-size:clamp(2.25rem,5vw,4.15rem);line-height:1.03;font-weight:800;letter-spacing:-.055em;color:#111827}.landing-title .accent{color:#2457d6}.landing-copy{max-width:670px;color:#667085;font-size:clamp(.9rem,1.4vw,1.03rem);line-height:1.75}.landing-note{margin-top:13px;color:#98a2b3;font-size:.67rem}.career-panel{border:1px solid #dfe3e8;border-radius:14px;background:#fff;padding:22px;box-shadow:0 10px 30px rgba(16,24,40,.06)}.career-panel-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}.career-panel-title{font-size:.78rem;font-weight:800;color:#344054}.career-status{font-size:.61rem;color:#16794c;background:#ecfdf3;border:1px solid #ccebd9;border-radius:999px;padding:4px 7px;font-weight:700}.progress-track{height:7px;background:#eef1f5;border-radius:99px;overflow:hidden}.progress-fill{height:100%;width:78%;background:#2457d6;border-radius:99px}.panel-score{display:flex;align-items:end;gap:8px;margin:9px 0 18px}.panel-score strong{font-size:2.4rem;line-height:1;color:#172033}.panel-score span{font-size:.67rem;color:#667085;padding-bottom:3px}.panel-row{display:flex;align-items:center;gap:10px;padding:11px 0;border-top:1px solid #eef0f3}.panel-row-icon{width:30px;height:30px;border-radius:8px;background:#f2f4f7;color:#344054;display:flex;align-items:center;justify-content:center;font-size:.62rem;font-weight:800}.panel-row-copy{flex:1}.panel-row-copy b{display:block;font-size:.72rem;color:#344054}.panel-row-copy span{display:block;font-size:.6rem;color:#98a2b3;margin-top:2px}.panel-check{font-size:.65rem;color:#16794c;font-weight:800}.landing-section-title{text-align:center;font-size:1.55rem;font-weight:800;color:#172033;margin:32px 0 5px}.landing-section-copy{text-align:center;color:#667085;font-size:.78rem;margin-bottom:18px}.role-card{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:20px;box-shadow:0 6px 18px rgba(16,24,40,.04);height:100%}.role-card-head{display:flex;align-items:center;gap:11px;margin-bottom:10px}.role-icon{width:42px;height:42px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:#f2f4f7;color:#344054;font-size:.62rem;font-weight:800}.role-card h3{font-size:.95rem;margin:0!important}.role-card p{font-size:.72rem;color:#667085;line-height:1.6;margin:0 0 12px}.role-list{display:grid;gap:7px}.role-list div{font-size:.67rem;color:#475467;display:flex;gap:8px;align-items:center}.role-list i{width:6px;height:6px;border-radius:50%;background:#2457d6;display:block}.landing-trust{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid #e4e7ec;border-bottom:1px solid #e4e7ec;margin:28px 0;padding:18px 0}.trust-item{text-align:center;border-right:1px solid #eef0f3}.trust-item:last-child{border-right:0}.trust-item strong{display:block;font-size:1.05rem;color:#172033}.trust-item span{font-size:.62rem;color:#98a2b3}.landing-footer{display:flex;justify-content:space-between;gap:15px;align-items:center;padding-top:18px;color:#98a2b3;font-size:.64rem}
[data-testid="stSidebar"]{background:#fff!important;border-right:1px solid #e4e7ec!important;box-shadow:3px 0 16px rgba(16,24,40,.025)!important}[data-testid="stSidebar"]>div:first-child{padding:16px 12px!important}[data-testid="stSidebar"] .stButton>button{background:transparent!important;color:#667085!important;border:0!important;box-shadow:none!important;border-radius:8px!important;text-align:left!important;justify-content:flex-start!important;padding:9px 10px!important;font-size:.78rem!important;font-weight:600!important;min-height:36px!important}[data-testid="stSidebar"] .stButton>button:hover{background:#f5f7fa!important;color:#2457d6!important;transform:none!important;box-shadow:none!important}[data-testid="stSidebar"] .stButton>button[kind="primary"]{background:#eef4ff!important;color:#2457d6!important;border:0!important;box-shadow:none!important}[data-testid="stSidebar"] .stButton>button[kind="primary"] *{color:#2457d6!important;-webkit-text-fill-color:#2457d6!important}.sidebar-brand-box{display:flex;align-items:center;gap:9px;padding:3px 5px 15px;border-bottom:1px solid #eef0f3;margin-bottom:13px}.sidebar-brand-box>div:first-child{font-size:0!important;width:29px;height:29px;border:1.5px solid #2457d6;border-radius:8px;background:#f7f9ff;position:relative}.sidebar-brand-box>div:first-child:after{content:'CL';font-size:8px;font-weight:800;color:#2457d6;position:absolute;inset:0;display:flex;align-items:center;justify-content:center}.sidebar-user-box{background:#f8fafc;border:1px solid #eef0f3;border-radius:9px;padding:9px 10px;margin-bottom:12px}.sidebar-section-title{font-size:.58rem!important;font-weight:800!important;letter-spacing:.10em!important;color:#98a2b3!important;margin:16px 4px 6px!important}
@media(max-width:1000px){.landing-hero{grid-template-columns:1fr;gap:28px;padding:52px 0 40px}.career-panel{max-width:620px}.kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.block-container{padding:9px 10px 30px!important}.landing-frame{border-radius:13px;padding:14px}.landing-nav{align-items:flex-start}.landing-links{display:none}.landing-hero{padding:38px 0 30px;gap:25px}.landing-title{font-size:clamp(2rem,11vw,3rem)}.landing-copy{font-size:.82rem}.landing-trust{grid-template-columns:repeat(2,1fr);gap:14px}.trust-item:nth-child(2){border-right:0}.landing-footer{flex-direction:column;align-items:flex-start}.landing-feature{min-height:0}.role-card{padding:17px}.header-banner{display:block!important}.header-title{font-size:1.1rem!important}.content-box{padding:15px;border-radius:10px}.kpi-grid{grid-template-columns:1fr!important}}@media(max-width:420px){.landing-title{font-size:1.9rem}.landing-kicker{font-size:.56rem}.career-panel{padding:16px}.panel-score strong{font-size:2rem}}@media(prefers-reduced-motion:reduce){*,*:before,*:after{transition:none!important;animation:none!important;scroll-behavior:auto!important}}
</style>""",unsafe_allow_html=True)
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


def _resume_sections(text: str) -> Dict[str, str]:
    """Best-effort section extraction used for transparent resume scoring."""
    lines = [re.sub(r"\s+", " ", x).strip() for x in (text or "").splitlines() if x.strip()]
    headings = {
        "summary": ("summary", "professional summary", "profile", "objective"),
        "experience": ("experience", "work experience", "professional experience", "employment"),
        "education": ("education", "academic background"),
        "projects": ("projects", "personal projects", "academic projects"),
        "skills": ("skills", "technical skills", "core skills"),
        "certifications": ("certifications", "certificates", "licenses"),
        "achievements": ("achievements", "accomplishments", "awards"),
    }
    found = {}
    for line in lines:
        clean = re.sub(r"[^a-z ]", "", line.lower()).strip()
        for key, variants in headings.items():
            if clean in variants:
                found[key] = line
    return found


def _role_skill_hints(role: str) -> List[str]:
    role_l = (role or "").lower()
    role_map = {
        "ai": ["python", "machine learning", "deep learning", "pytorch", "tensorflow", "statistics", "sql"],
        "machine learning": ["python", "machine learning", "statistics", "pandas", "numpy", "scikit-learn"],
        "data scientist": ["python", "statistics", "sql", "pandas", "numpy", "machine learning"],
        "data analyst": ["sql", "excel", "power bi", "tableau", "statistics", "data analysis"],
        "software": ["python", "java", "javascript", "git", "sql", "rest api", "testing"],
        "developer": ["programming", "git", "sql", "testing", "api"],
        "devops": ["linux", "docker", "kubernetes", "aws", "git", "ci/cd"],
        "cloud": ["aws", "azure", "gcp", "docker", "kubernetes", "linux"],
        "cyber": ["cybersecurity", "linux", "networking", "python", "security"],
        "qa": ["testing", "selenium", "automation", "api testing", "git"],
        "hr": ["recruitment", "employee relations", "communication", "hr analytics"],
        "human resources": ["recruitment", "employee relations", "communication", "hr analytics"],
        "marketing": ["digital marketing", "seo", "content marketing", "analytics", "communication"],
        "sales": ["sales", "negotiation", "communication", "crm", "lead generation"],
        "finance": ["excel", "financial analysis", "accounting", "forecasting", "communication"],
        "account": ["accounting", "excel", "financial analysis", "tax", "audit"],
        "project manager": ["project management", "stakeholder management", "communication", "agile", "risk management"],
        "product manager": ["product management", "roadmapping", "user research", "analytics", "stakeholder management"],
        "teacher": ["lesson planning", "communication", "classroom management", "assessment"],
        "nurse": ["patient care", "clinical", "communication", "documentation"],
        "civil": ["autocad", "structural", "project management", "construction", "safety"],
        "mechanical": ["cad", "solidworks", "mechanical design", "manufacturing", "thermodynamics"],
    }
    hints=[]
    for key, vals in role_map.items():
        if key in role_l:
            hints.extend(vals)
    return list(dict.fromkeys(hints))


def _local_resume_analysis(text: str, filename: str, target_role: str = "") -> Dict[str, Any]:
    text = (text or "").strip()
    lower = text.lower()
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    sections = _resume_sections(text)
    skills = sorted(_skill_set(text))
    quantified = len(re.findall(r"(?:\b\d+%|\b\d+[+]?(?:\s*years?|\s*users?|\s*clients?)|\b(?:increased|reduced|improved|saved|grew|generated)\b[^.]{0,60}\b\d+)", lower))
    action_verbs = len(re.findall(r"\b(led|built|developed|designed|implemented|improved|optimized|automated|created|managed|analyzed|delivered|launched|reduced|increased|deployed|tested|trained)\b", lower))
    bullets = len(re.findall(r"(?:^|\n)\s*[•▪●*-]\s+", text))
    contact_email = bool(re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text))
    contact_phone = bool(re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text))

    # Transparent 100-point model. A score is intentionally not allowed to be
    # inflated by word count alone; missing evidence lowers the result.
    content = min(100, 25 + min(len(words), 700) / 700 * 45 + min(bullets, 18) / 18 * 15 + min(action_verbs, 12) / 12 * 15)
    section_score = min(100, len(sections) / 7 * 100)
    skill_score = min(100, len(skills) / 12 * 100)
    achievement_score = min(100, quantified / 5 * 70 + min(action_verbs, 10) / 10 * 30)
    contact_score = (50 if contact_email else 0) + (50 if contact_phone else 0)
    role_hints = _role_skill_hints(target_role)
    role_match = (len([x for x in role_hints if x in lower]) / len(role_hints) * 100) if role_hints else None

    weighted = content * .25 + section_score * .20 + skill_score * .20 + achievement_score * .15 + contact_score * .10 + (role_match * .10 if role_match is not None else 0)
    if role_match is None:
        weighted += 5
    resume_score = int(round(max(5, min(98, weighted))))

    experience_signals = len(re.findall(r"\b(experience|intern|internship|work history|employment|years?)\b", lower))
    readiness = int(round(max(5, min(97, resume_score * .55 + min(len(skills), 10) * 3 + min(quantified, 5) * 2 + min(experience_signals, 3) * 2))))
    missing_sections = [x.title() for x in ("summary", "experience", "education", "projects", "skills", "certifications", "achievements") if x not in sections]
    recommendations=[]
    if "experience" in missing_sections: recommendations.append("Add relevant work experience, internships, or substantial project experience.")
    if "projects" in missing_sections: recommendations.append("Add 2–3 relevant projects with your contribution, tools, and measurable outcomes.")
    if quantified < 2: recommendations.append("Add measurable results such as %, time saved, revenue, users, accuracy, or scale.")
    if action_verbs < 4: recommendations.append("Rewrite bullet points with strong action verbs and clear ownership.")
    if not contact_email or not contact_phone: recommendations.append("Complete the contact section with a professional email and phone number.")
    if len(skills) < 6: recommendations.append("Add more role-relevant skills supported by projects or experience.")
    if target_role and role_match is not None and role_match < 50: recommendations.append(f"Tailor the resume toward {target_role} and add evidence for the missing role skills.")
    if not recommendations: recommendations.append("Maintain this structure and tailor achievements to each target job.")

    strengths=[]
    if len(skills) >= 6: strengths.append(f"Detected {len(skills)} relevant skills.")
    if len(sections) >= 5: strengths.append("Good coverage of standard resume sections.")
    if quantified >= 2: strengths.append("Includes measurable achievement evidence.")
    if contact_email and contact_phone: strengths.append("Complete contact information detected.")
    if not strengths: strengths.append("Resume text was extracted successfully; additional evidence can improve the score.")

    return {
        "name": re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Candidate",
        "email": (re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text).group(0).lower() if re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text) else ""),
        "phone": (re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text).group(0).strip() if re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text) else ""),
        "experience": "Experience evidence detected" if experience_signals else "Experience not clearly detected",
        "resume_score": resume_score,
        "readiness": readiness,
        "market_match": None,
        "skills": skills,
        "missing_skills": [x for x in role_hints if x not in lower][:8],
        "strengths": strengths,
        "recommendations": recommendations,
        "score_breakdown": {
            "content_quality": round(content, 1),
            "section_coverage": round(section_score, 1),
            "skills": round(skill_score, 1),
            "achievement_evidence": round(achievement_score, 1),
            "contact_completeness": round(contact_score, 1),
            "target_role_alignment": round(role_match, 1) if role_match is not None else None,
        },
        "extracted_text": text,
        "source": "local-analysis-v4",
        "analysis_version": 4,
    }

def api_analyze_resume(file, target_role: str = "") -> Dict[str, Any]:
    # The local scorer is the safety net and also protects the UI from an old
    # deployed API returning the previous demo scoring formula.
    text = _extract_resume_text(file)
    local = _local_resume_analysis(text, file.name, target_role)
    try:
        files = {"file": (file.name, file.getvalue(), file.type or "application/octet-stream")}
        data_payload = {"target_role": target_role.strip()}
        res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, data=data_payload, timeout=60)
        if res.ok and isinstance(res.json(), dict):
            data = res.json()
            # Only trust the new versioned API result. Otherwise keep the local
            # analysis so an older Render deployment cannot reintroduce 100%.
            if int(data.get("analysis_version", 0) or 0) >= 5 and data.get("score_breakdown"):
                data["extracted_text"] = data.get("extracted_text") or text
                return data
    except (requests.RequestException, ValueError, TypeError):
        pass
    return local

def _skill_set(text: str) -> set:
    lower = (text or "").lower()
    catalog = [
        "python", "java", "javascript", "typescript", "c++", "c#", "react", "node.js", "fastapi", "django", "flask",
        "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws", "azure", "gcp", "git", "linux",
        "machine learning", "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch", "statistics",
        "rest api", "graphql", "redis", "kafka", "system design", "html", "css", "figma", "excel", "power bi", "tableau",
        "cybersecurity", "testing", "selenium", "communication", "leadership", "problem solving", "data analysis",
        "project management", "stakeholder management", "agile", "seo", "digital marketing", "content marketing", "crm",
        "sales", "negotiation", "accounting", "financial analysis", "forecasting", "audit", "tax", "autocad", "solidworks",
        "mechanical design", "manufacturing", "construction", "safety", "recruitment", "employee relations", "hr analytics",
        "lesson planning", "classroom management", "assessment", "patient care", "clinical", "documentation", "networking",
        "automation", "ci/cd", "product management", "roadmapping", "user research", "risk management",
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
        if res.ok and isinstance(res.json(), dict) and int(res.json().get("analysis_version", 0) or 0) >= 5:
            return {**normalize_job_match(res.json()), "source": "api-v4"}
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


def api_salary_estimate(role: str, experience: str, location: str) -> Dict[str, Any]:
    try:
        res = requests.post(f"{API_BASE_URL}/api/salary/estimate", json={"role":role,"experience":experience,"location":location}, timeout=20)
        if res.ok and isinstance(res.json(), dict): return res.json()
    except (requests.RequestException, ValueError, TypeError):
        pass
    role_l=role.lower()
    base=4.5
    if any(x in role_l for x in ("ai", "machine learning", "data scientist", "cloud", "cyber")): base=7.0
    elif any(x in role_l for x in ("software", "developer", "devops")): base=5.5
    elif any(x in role_l for x in ("product", "manager")): base=6.0
    elif any(x in role_l for x in ("finance", "account")): base=4.0
    if "Mid" in experience: base*=1.45
    elif "Senior" in experience: base*=2.0
    elif "Lead" in experience: base*=2.6
    return {"role":role,"experience":experience,"location":location,"min_lpa":round(base*.85,1),"max_lpa":round(base*1.8,1),"note":"Indicative India estimate based on role family and experience. Verify against current market listings before making decisions.","source":"local-estimate-v4"}


def api_chat_assistant(messages: List[Dict], resume_context: str = "") -> str:
    try:
        payload = {"messages": messages, "resume_context": resume_context}
        res = requests.post(f"{API_BASE_URL}/api/chat/ask", json=payload, timeout=45)
        if res.status_code == 200:
            return res.json().get("reply", "")
    except Exception:
        pass
    return "Focus on quantifiable business outcomes, active GitHub portfolio proof, and modern architecture patterns for the best results."


def api_send_assessment_email(to_email: str, name: str, role: str, test_link: str, company: str = "", recruiter_name: str = "", recruiter_email: str = "", duration_minutes: int = 30, question_count: int = 20) -> tuple[bool, str]:
    subject = f"{company or 'CareerLens AI'} — Assessment Invitation for {role}"
    recruiter_line = html.escape(recruiter_name or "Recruiting Team")
    company_line = html.escape(company or "CareerLens AI")
    recruiter_email_line = f"<div style=\"font-size:12px;color:#64748b;margin-top:4px;\">Contact: {html.escape(recruiter_email)}</div>" if recruiter_email else ""
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 620px; margin: auto; padding: 24px; border: 1px solid #e2e8f0; border-radius: 14px; background:#ffffff;">
        <div style="font-size:12px;color:#64748b;font-weight:bold;letter-spacing:.08em;text-transform:uppercase;">Assessment Invitation</div>
        <h2 style="color: #2563eb; margin-bottom:6px;">{company_line}</h2>
        <div style="font-size:13px;color:#475569;margin-bottom:20px;">Recruiter: <b>{recruiter_line}</b>{recruiter_email_line}</div>
        <p>Hi <b>{html.escape(name)}</b>,</p>
        <p>You have been invited to complete a qualifying <b>Role-Based Pre-Employment Assessment</b> for the <b>{html.escape(role)}</b> position.</p>
        <p style="color:#475569;font-size:13px;"><b>{int(question_count)} questions</b> · <b>{int(duration_minutes)} minutes</b> · one question at a time · review before submission.</p>
        <div style="margin: 26px 0; text-align: center;">
            <a href="{test_link}" style="background-color: #2563eb; color: #ffffff; padding: 13px 26px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Start Assessment</a>
        </div>
        <p style="color: #64748b; font-size: 0.9em;">Assessment link:</p>
        <p style="word-break: break-all; color: #2563eb; font-size: 0.85em;">{test_link}</p>
        <div style="margin-top:22px;padding-top:14px;border-top:1px solid #e2e8f0;color:#64748b;font-size:12px;">Please contact the recruiter above if you have questions about this assessment.</div>
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
    "interview_company": "",
    "interview_q_count": 20,
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
    "recruiter_assessment_duration": 30,
    "assessment_selected_role": "Software Developer",
    "job_detection_result": None,
    "job_detection_text": "",
    "resume_builder": {},
    "resume_template": "Executive",
    "salary_result": None,
    "assistant_messages": [],
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


def _assessment_signing_secret() -> bytes:
    """Stable signing secret for public assessment links."""
    secret = os.getenv("ASSESSMENT_SIGNING_SECRET", "").strip()
    if not secret:
        try:
            secret = str(st.secrets.get("ASSESSMENT_SIGNING_SECRET", "") or "").strip()
        except Exception:
            secret = ""
    # A stable fallback keeps links functional even when the optional secret is not configured.
    if not secret:
        secret = "CareerLensAI-public-assessment-v1-2026"
    return secret.encode("utf-8")


def _make_assessment_token(payload: Optional[Dict[str, Any]] = None) -> str:
    """Create a compact, signed token so a public assessment does not depend on a browser session."""
    data = dict(payload or {})
    data.setdefault("v", 1)
    data.setdefault("id", uuid.uuid4().hex)
    data.setdefault("iat", int(datetime.now().timestamp()))
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    signature = hmac.new(_assessment_signing_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{encoded}.{sig}"


def _decode_assessment_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify and decode a signed public assessment token."""
    try:
        encoded, sig = str(token or "").split(".", 1)
        expected = hmac.new(_assessment_signing_secret(), encoded.encode("ascii"), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return None
        issued = int(payload.get("iat", 0) or 0)
        # Public assessment links remain valid for 30 days.
        if issued and datetime.now().timestamp() - issued > 30 * 24 * 60 * 60:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError, binascii.Error):
        return None


def _assessment_public_url(token: str) -> str:
    """Return the only public URL used for recruiter assessments."""
    token = str(token or "").strip()
    if not token:
        raise ValueError("Assessment token is required.")
    return f"https://career-lens-ai.streamlit.app/?assessment={quote(token, safe="")}"


def _save_public_assessment_record(owner_user_id: str, candidate_id: str, assessment: Dict[str, Any], token: str) -> None:
    """Persist each public assessment independently of recruiter browser session state."""
    if not owner_user_id or not candidate_id or not token:
        return
    conn = get_db_connection()
    payload = json.dumps(assessment, ensure_ascii=False)
    expires_at = (datetime.now() + timedelta(days=30)).isoformat(timespec="seconds")
    with conn:
        conn.execute(
            """INSERT INTO public_assessments(token, owner_user_id, candidate_id, assessment_json, created_at, expires_at, used)
               VALUES(?,?,?,?,?,?,0)
               ON CONFLICT(token) DO UPDATE SET owner_user_id=excluded.owner_user_id, candidate_id=excluded.candidate_id, assessment_json=excluded.assessment_json, created_at=excluded.created_at, expires_at=excluded.expires_at""",
            (token, owner_user_id, candidate_id, payload, datetime.now().isoformat(timespec="seconds"), expires_at),
        )


def _load_public_assessment_record(token: str):
    token = str(token or "").strip()
    if not token:
        return None, None, None, None
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT owner_user_id, candidate_id, assessment_json, expires_at, used FROM public_assessments WHERE token=?",
            (token,),
        ).fetchone()
        if not row:
            return None, None, None, None
        owner_user_id, candidate_id, assessment_json, expires_at, used = row
        if expires_at:
            try:
                if datetime.fromisoformat(expires_at) < datetime.now():
                    return None, None, None, None
            except ValueError:
                pass
        assessment = json.loads(assessment_json) if isinstance(assessment_json, str) else {}
        if not isinstance(assessment, dict):
            return None, None, None, None
        assessment["used"] = bool(used)
        data = _db_load_recruiter_state(owner_user_id)
        candidate = next((c for c in data.get("candidates", []) if c.get("id") == candidate_id), None)
        if candidate is None:
            return None, None, None, None
        return assessment, candidate, candidate_id, owner_user_id
    except (sqlite3.Error, TypeError, ValueError, json.JSONDecodeError):
        return None, None, None, None


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


def _resume_interview_context(resume_text: str) -> Dict[str, Any]:
    text = (resume_text or "").strip()
    lower = text.lower()
    skills = sorted(_skill_set(text))
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
    project_lines = [x for x in lines if any(k in x.lower() for k in ("project", "developed", "built", "implemented", "created"))][:6]
    experience_lines = [x for x in lines if any(k in x.lower() for k in ("experience", "intern", "worked", "employment", "developer", "engineer"))][:6]
    return {
        "skills": skills[:20],
        "projects": project_lines,
        "experience": experience_lines,
        "name": (re.search(r"(?:^|\n)\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,4})\s*(?:\n|$)", text) or ["", ""])[1] if text else "",
        "has_resume": bool(text),
        "word_count": len(re.findall(r"\b[a-zA-Z]{2,}\b", text)),
    }


def generate_mock_interview_questions(role: str, count: int, resume_text: str = "", company: str = "") -> List[str]:
    """Build a resume-aware interview bank. The UI can continue through this bank until the candidate stops."""
    role = role.strip() or "the target role"
    ctx = _resume_interview_context(resume_text)
    company_name = company.strip() or "this company"
    bank: List[str] = [
        f"Please introduce yourself and walk me through your background, focusing on what makes you a strong candidate for the {role} role.",
        f"Why have you chosen to pursue a career as a {role}, and what interests you most about this role?",
        f"Why do you want to work at {company_name}, and what do you think you could contribute here?",
        "Which achievement on your resume are you most proud of, and why?",
    ]
    if ctx["skills"]:
        for skill in ctx["skills"][:8]:
            bank.append(f"Your resume mentions {skill}. How have you used {skill} in a real project, job, internship, or academic setting? Give me a specific example.")
            bank.append(f"How would you rate your {skill} ability today, and what have you done recently to improve it?")
    if ctx["projects"]:
        for project in ctx["projects"][:4]:
            bank.append(f"I noticed this resume evidence: \"{project}\". Walk me through what you personally did, the main challenge, and the result.")
    if ctx["experience"]:
        for item in ctx["experience"][:3]:
            bank.append(f"Your resume includes this experience: \"{item}\". What was your responsibility, and how did your work create value?")
    bank.extend([
        "Tell me about a difficult problem you solved. What was your reasoning, what actions did you take, and what was the outcome?",
        "Tell me about a mistake or failure in a project or job. What did you learn and what did you change afterward?",
        "Describe a disagreement with a teammate or stakeholder and how you resolved it.",
        "Tell me about a time you received difficult feedback. How did you respond?",
        "How do you prioritize when several important tasks are competing for your attention?",
        "What would you want to accomplish during your first 30, 60, and 90 days in this role?",
        f"What is the biggest skill gap you currently have for the {role} role, and how are you working on it?",
        "Where do you want your career to develop over the next few years?",
        "Do you have any questions you would ask me as the interviewer?",
    ])
    # Keep a generous safety bank while the interview itself ends only when the user presses Stop.
    target = max(20, min(50, int(count or 20)))
    if len(bank) < target:
        bank.extend([f"As a {role}, describe how you would approach a realistic high-priority situation and explain your reasoning."] * (target - len(bank)))
    return bank[:max(target, len(bank))]


def generate_next_interview_question(role: str, resume_text: str, transcript: List[Dict[str, Any]], bank: List[str]) -> str:
    """Select a useful next question based on resume evidence and the previous answer."""
    used = {str(x.get("question", "")) for x in transcript}
    remaining = [q for q in bank if q not in used]
    if not remaining:
        idx = len(transcript) + 1
        return f"Question {idx}: As a {role}, describe a realistic challenge you would face and explain how you would solve it step by step."
    if transcript:
        answer = str(transcript[-1].get("answer", "")).lower()
        if len(answer.split()) < 20:
            follow = "Can you give me a specific example from your resume or experience that supports that answer?"
            if follow not in used:
                return follow
        if any(k in answer for k in ("project", "built", "developed", "implemented")):
            follow = "What was the hardest technical or practical decision you made in that project, and what trade-off did you consider?"
            if follow not in used:
                return follow
    return remaining[0]


def score_mock_interview(transcript: List[Dict[str, Any]], role: str) -> Dict[str, Any]:
    if not transcript:
        return {"overall": 0, "communication": 0, "completeness": 0, "relevance": 0, "evidence": 0, "strengths": [], "improvements": ["Provide answers before ending the interview."]}
    lengths = [len(str(x.get("answer", "")).split()) for x in transcript]
    substantive = sum(1 for n in lengths if n >= 30)
    completeness = round(substantive / len(lengths) * 100)
    avg = min(100, round(sum(lengths) / len(lengths) * 2.2))
    evidence_words = ("because", "result", "impact", "example", "metric", "improved", "learned", "built", "developed", "implemented")
    evidence_hits = sum(1 for x in transcript if any(k in str(x.get("answer", "")).lower() for k in evidence_words))
    relevance_hits = sum(1 for x in transcript if role.lower() in str(x.get("answer", "")).lower() or any(k in str(x.get("answer", "")).lower() for k in ("project", "experience", "skill", "role")))
    evidence = min(100, round(evidence_hits / len(transcript) * 100))
    relevance = min(100, round(relevance_hits / len(transcript) * 100))
    communication = min(100, round(avg * .60 + evidence * .20 + relevance * .20))
    overall = max(5, min(98, round(communication * .45 + completeness * .25 + evidence * .15 + relevance * .15)))
    strengths = [f"Completed {len(transcript)} interview responses for {role}."]
    if avg >= 55: strengths.append("Answers generally contain useful detail rather than one-line responses.")
    if evidence >= 50: strengths.append("Several answers use examples, actions, outcomes or measurable evidence.")
    if relevance >= 60: strengths.append("Responses show reasonable alignment with the target role and experience.")
    improvements = []
    if completeness < 70: improvements.append("Use fuller answers with context, action and result instead of short statements.")
    if evidence < 50: improvements.append("Use concrete resume examples and quantify outcomes whenever possible.")
    if relevance < 60: improvements.append(f"Tie more answers directly to the {role} responsibilities and your actual experience.")
    if not improvements: improvements.append("Keep practicing concise, evidence-based answers and prepare deeper follow-up examples.")
    return {"overall": overall, "communication": communication, "completeness": completeness, "relevance": relevance, "evidence": evidence, "strengths": strengths, "improvements": improvements}


def generate_assessment_questions(role: str, count: int, seed: str = "") -> List[Dict[str, Any]]:
    """Build a role-aware MCQ bank and randomize each candidate's questions/options.

    The seed is candidate-specific (normally the signed assessment token), so every
    candidate receives a stable but different question/option ordering.
    """
    role_l = (role or "").lower().strip()
    bank: List[tuple[str, List[str], int]] = []

    def add(items):
        bank.extend(items)

    if any(x in role_l for x in ("ai", "machine learning", "ml engineer")):
        add([
            ("Which practice helps detect overfitting in a machine-learning model?", ["Validation data", "More UI colors", "Disabling metrics", "Removing labels"], 0),
            ("What should be monitored after deploying an ML model?", ["Prediction quality and data drift", "Only file names", "Keyboard layout", "Screen brightness"], 0),
            ("Why is feature leakage dangerous?", ["It gives the model information unavailable at prediction time", "It improves security", "It removes all bias", "It reduces storage cost"], 0),
            ("Which metric is useful for an imbalanced classification problem?", ["F1-score", "File size", "CPU temperature", "Row height"], 0),
            ("Why is a separate test set useful?", ["It provides a final estimate on unseen data", "It trains the model twice", "It removes all missing values", "It guarantees perfect accuracy"], 0),
        ])
    elif any(x in role_l for x in ("data scientist", "data analyst", "analytics")):
        add([
            ("What is the first step when an analysis produces a surprising result?", ["Validate data quality and assumptions", "Publish immediately", "Delete outliers without review", "Change the chart colors"], 0),
            ("What does precision measure in classification?", ["Correct positives among predicted positives", "Correct positives among all actual positives", "All correct predictions", "Only false negatives"], 0),
            ("Why use cross-validation?", ["Estimate generalization during model selection", "Encrypt the dataset", "Create invoices", "Remove all missing values automatically"], 0),
            ("Which tool is commonly used for spreadsheet-based business analysis?", ["Excel", "Docker", "Kubernetes", "Git"], 0),
            ("What is a useful first check before building a dashboard?", ["Confirm definitions, data quality and business questions", "Add as many charts as possible", "Hide missing values", "Remove filters"], 0),
        ])
    elif any(x in role_l for x in ("software", "developer", "programmer", "devops", "cloud", "cyber", "qa", "engineer")):
        add([
            ("Which practice improves software reliability before release?", ["Automated tests and review", "Skipping validation", "Hard-coding secrets", "Ignoring errors"], 0),
            ("What does version control primarily provide?", ["A history of code changes and collaboration", "Automatic salary calculation", "Network encryption by itself", "Hardware monitoring"], 0),
            ("Which approach is safer for production secrets?", ["Secret management/environment injection", "Hard-coding them in source control", "Putting them in client HTML", "Sharing them in chat"], 0),
            ("What is a useful response to a production regression?", ["Contain, inspect telemetry, fix and verify", "Delete logs", "Disable monitoring", "Ignore it"], 0),
            ("Which HTTP status normally indicates successful resource creation?", ["201", "301", "401", "500"], 0),
            ("Which data structure is best suited for fast average O(1) key lookup?", ["Hash table", "Linked list", "Stack only", "Binary file"], 0),
            ("Why are code reviews valuable?", ["They catch defects and improve maintainability through shared knowledge", "They replace all testing", "They guarantee zero bugs", "They remove the need for documentation"], 0),
            ("What is a good API design practice?", ["Validate input and return clear, consistent responses", "Expose secrets in responses", "Ignore malformed input", "Change response formats randomly"], 0),
        ])
    elif any(x in role_l for x in ("hr", "human resource", "recruit", "talent")):
        add([
            ("Which metric can help evaluate recruitment efficiency?", ["Time to hire", "Monitor brightness", "Keyboard speed", "File extension"], 0),
            ("What is a good approach to a sensitive employee issue?", ["Listen, document facts, follow policy and protect confidentiality", "Discuss it publicly", "Ignore documentation", "Share private details widely"], 0),
            ("What improves candidate experience?", ["Clear communication and timely updates", "Unexplained delays", "Hidden requirements", "Repeated duplicate forms"], 0),
            ("Why should structured interview criteria be used?", ["To improve consistency and fair comparison", "To avoid taking notes", "To guarantee every candidate gets the same answer", "To remove role requirements"], 0),
        ])
    elif any(x in role_l for x in ("marketing", "seo", "brand")):
        add([
            ("Which metric helps evaluate campaign efficiency?", ["Conversion rate", "Screen resolution", "File size", "Keyboard layout"], 0),
            ("What should a marketer do when conversion suddenly drops?", ["Check funnel data and test likely causes", "Change everything randomly", "Delete analytics", "Ignore the change"], 0),
            ("Why segment an audience?", ["To tailor messages to meaningful groups", "To remove all analytics", "To guarantee every user behaves identically", "To avoid testing"], 0),
        ])
    elif any(x in role_l for x in ("finance", "account", "audit")):
        add([
            ("What should happen before relying on a financial report?", ["Reconcile and validate the underlying data", "Skip checks", "Delete source records", "Publish without review"], 0),
            ("What is variance analysis used for?", ["Understand differences between actual and planned values", "Encrypt passwords", "Design a website", "Manage source code"], 0),
            ("Which skill is commonly useful in financial analysis?", ["Spreadsheet modeling", "Container orchestration", "CSS animation", "DNS routing"], 0),
        ])
    elif any(x in role_l for x in ("project manager", "product manager", "operations manager")):
        add([
            ("How should competing priorities be handled?", ["Evaluate impact, urgency, dependencies and stakeholder needs", "Pick randomly", "Ignore dependencies", "Do everything simultaneously"], 0),
            ("What is a useful project success measure?", ["Delivery against agreed outcomes, scope, quality and time", "Number of meetings only", "Number of emails", "Screen size"], 0),
            ("How should stakeholder disagreement be handled?", ["Clarify goals, evidence, constraints and trade-offs", "Hide the disagreement", "Choose without context", "Stop documenting decisions"], 0),
        ])
    else:
        add([
            (f"What is most important when performing the {role or 'target'} role?", ["Delivering role-relevant outcomes with quality and accountability", "Avoiding feedback", "Ignoring requirements", "Skipping validation"], 0),
            ("What is a strong way to demonstrate competence?", ["Concrete examples with actions and measurable outcomes", "Only listing buzzwords", "Avoiding examples", "Using copied answers"], 0),
            ("How should you approach an unfamiliar task?", ["Clarify the goal, research, plan, execute and verify", "Guess and never check", "Avoid the task", "Hide uncertainty"], 0),
            ("What helps professional growth?", ["Deliberate practice, feedback and evidence of improvement", "Avoiding new tasks", "Never reviewing work", "Ignoring feedback"], 0),
        ])

    bank.extend([
        (f"Why are measurable outcomes valuable for a {role or 'professional'}?", ["They show the impact of the work", "They replace all skills", "They remove the need for communication", "They guarantee promotion"], 0),
        ("What is the best response when you discover an error in your work?", ["Acknowledge it, assess impact, correct it and learn from it", "Hide it", "Delete evidence", "Blame someone else"], 0),
        ("Which behavior demonstrates ownership?", ["Following through, communicating risks and delivering agreed outcomes", "Waiting for every instruction", "Ignoring blockers", "Avoiding accountability"], 0),
        ("Which approach is strongest when requirements are unclear?", ["Clarify assumptions and confirm the expected outcome", "Start coding without context", "Ignore the requirement", "Wait indefinitely"], 0),
        ("What makes an assessment answer stronger?", ["Accurate reasoning supported by relevant knowledge", "Guessing quickly", "Copying another person's response", "Leaving every answer blank"], 0),
    ])

    target = max(10, min(50, int(count or 10)))
    rng = random.Random(str(seed or role_l or "careerlens"))
    indexed = list(enumerate(bank))
    rng.shuffle(indexed)

    selected: List[tuple[str, List[str], int]] = []
    for _, item in indexed:
        selected.append(item)
        if len(selected) >= min(target, len(bank)):
            break

    # If the recruiter requested more questions than the base bank, cycle with unique scenario labels.
    while len(selected) < target:
        base = bank[(len(selected) - len(bank)) % len(bank)]
        cycle = (len(selected) // max(1, len(bank))) + 1
        selected.append((f"{base[0]} (Scenario {cycle})", list(base[1]), base[2]))

    questions: List[Dict[str, Any]] = []
    for i, (q_text, options, correct_idx) in enumerate(selected[:target], start=1):
        option_pairs = list(enumerate(options))
        rng.shuffle(option_pairs)
        shuffled_options = [text for _, text in option_pairs]
        correct_answer = options[correct_idx]
        questions.append({
            "id": i,
            "section": "Core Skills" if i <= round(target * 0.6) else "Applied Scenarios",
            "question": q_text,
            "options": shuffled_options,
            "answer": correct_answer,
        })
    return questions

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
    """Build a resume PDF using a template-specific visual system."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()

    template_config = {
        "Executive": {"accent": "#1d4ed8", "title": 23, "align": TA_CENTER, "line": True},
        "Minimal": {"accent": "#111827", "title": 22, "align": TA_LEFT, "line": False},
        "Modern Blue": {"accent": "#2563eb", "title": 24, "align": TA_LEFT, "line": True},
        "Modern Purple": {"accent": "#7c3aed", "title": 24, "align": TA_LEFT, "line": True},
        "Emerald": {"accent": "#059669", "title": 23, "align": TA_LEFT, "line": True},
        "Professional": {"accent": "#334155", "title": 21, "align": TA_CENTER, "line": True},
        "Tech": {"accent": "#0284c7", "title": 24, "align": TA_LEFT, "line": True},
        "ATS Classic": {"accent": "#111827", "title": 20, "align": TA_LEFT, "line": False},
        "Classic Serif": {"accent": "#374151", "title": 23, "align": TA_CENTER, "line": True},
        "Corporate": {"accent": "#0f172a", "title": 22, "align": TA_LEFT, "line": True},
        "Clean Grid": {"accent": "#475569", "title": 22, "align": TA_LEFT, "line": True},
        "Modern ATS": {"accent": "#1e293b", "title": 21, "align": TA_LEFT, "line": True},
        "Creative": {"accent": "#db2777", "title": 24, "align": TA_CENTER, "line": True},
        "Elegant": {"accent": "#6b21a8", "title": 23, "align": TA_CENTER, "line": False},
        "Compact": {"accent": "#0f766e", "title": 20, "align": TA_LEFT, "line": True},
        "Bold Header": {"accent": "#b45309", "title": 25, "align": TA_LEFT, "line": True},
    }
    cfg = template_config.get(template, template_config["Executive"])
    accent = colors.HexColor(cfg["accent"])

    title = ParagraphStyle(
        f"ResumeTitle_{template}", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=cfg["title"], leading=27, textColor=accent, alignment=cfg["align"], spaceAfter=4
    )
    contact = ParagraphStyle(
        f"Contact_{template}", parent=styles["Normal"], fontSize=8.8, leading=12,
        textColor=colors.HexColor("#475569"), alignment=cfg["align"], spaceAfter=10
    )
    heading = ParagraphStyle(
        f"Heading_{template}", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=accent, spaceBefore=7, spaceAfter=4
    )
    body = ParagraphStyle(
        f"Body_{template}", parent=styles["BodyText"], fontSize=8.8, leading=12,
        textColor=colors.HexColor("#1f2937"), spaceAfter=3
    )

    story = [Paragraph(_escape(data.get("name", "Your Name")), title)]
    contact_bits = [data.get("email"), data.get("phone"), data.get("location"), data.get("linkedin"), data.get("github")]
    story.append(Paragraph(" &nbsp;•&nbsp; ".join(_escape(x) for x in contact_bits if x), contact))

    if data.get("headline"):
        story.append(Paragraph(
            _escape(data["headline"]),
            ParagraphStyle(
                f"Headline_{template}", parent=body, fontSize=10, leading=13,
                alignment=cfg["align"], textColor=colors.HexColor("#334155"), spaceAfter=8
            ),
        ))

    if cfg["line"]:
        story.append(Table([[""]], colWidths=[doc.width], rowHeights=[1.2], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), accent),
            ("LINEBELOW", (0, 0), (-1, -1), 0, accent),
        ])))
        story.append(Spacer(1, 4))

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
    """Resolve a public assessment without requiring recruiter authentication or session state."""
    token = str(token or "").strip()
    if not token:
        return None, None, None, None

    # Resolve the persisted candidate-specific assessment first. This is what guarantees
    # that Candidate A and Candidate B do not silently receive the same question set.
    try:
        persisted = _load_public_assessment_record(token)
        if persisted[0] is not None:
            return persisted
    except Exception:
        pass

    # New links are self-contained and cryptographically signed. This fallback keeps links
    # usable even if the public record cannot be read; the token itself still identifies the candidate.
    payload = _decode_assessment_token(token)
    if payload:
        owner_user_id = str(payload.get("owner_user_id", ""))
        candidate_id = str(payload.get("candidate_id", ""))
        role = str(payload.get("role", "Professional Assessment"))
        company = str(payload.get("company", "Company"))
        recruiter_name = str(payload.get("recruiter_name", "Recruiting Team"))
        recruiter_email = str(payload.get("recruiter_email", ""))
        candidate_snapshot = payload.get("candidate", {}) if isinstance(payload.get("candidate"), dict) else {}
        candidate = dict(candidate_snapshot)

        # Refresh from recruiter state when available so the latest candidate details are used.
        if owner_user_id:
            try:
                owner_data = _db_load_recruiter_state(owner_user_id)
                stored = next((c for c in owner_data.get("candidates", []) if c.get("id") == candidate_id), None)
                if stored:
                    candidate = stored
            except Exception:
                pass

        assessment = {
            "id": str(payload.get("assessment_id", payload.get("id", ""))),
            "role": role,
            "company": company,
            "recruiter_name": recruiter_name,
            "recruiter_email": recruiter_email,
            "questions": generate_assessment_questions(role, int(payload.get("question_count", 20) or 20), seed=token),
            "duration_minutes": int(payload.get("duration_minutes", 30) or 30),
            "created_at": datetime.fromtimestamp(int(payload.get("iat", datetime.now().timestamp()))).isoformat(timespec="seconds"),
            "candidate_tokens": {candidate_id: token},
        }
        if candidate.get("id") or candidate_id:
            candidate.setdefault("id", candidate_id)
        candidate.setdefault("name", "Candidate")
        candidate.setdefault("email", "")
        candidate.setdefault("assessment_status", "Sent")
        if candidate:
            return assessment, candidate, candidate_id, owner_user_id

    # Backward compatibility for links created by the previous database-backed implementation.
    try:
        found = _load_public_assessment_record(token)
        if found[0] is not None:
            return found
    except Exception:
        pass

    try:
        conn = get_db_connection()
        rows = conn.execute("SELECT user_id, state_json FROM recruiter_state").fetchall()
        for owner_user_id, state_json in rows:
            try:
                owner_data = json.loads(state_json) if isinstance(state_json, str) else {}
            except (TypeError, ValueError):
                continue
            if not isinstance(owner_data, dict):
                continue
            owner_candidates = owner_data.get("candidates", []) or []
            for assessment in owner_data.get("assessments", []) or []:
                tokens = assessment.get("candidate_tokens", {}) if isinstance(assessment, dict) else {}
                for candidate_id, candidate_token in tokens.items():
                    if str(candidate_token) == token:
                        candidate = next((c for c in owner_candidates if c.get("id") == candidate_id), None)
                        if candidate:
                            _save_public_assessment_record(owner_user_id, candidate_id, assessment, token)
                            return assessment, candidate, candidate_id, owner_user_id
    except sqlite3.Error:
        pass
    return None, None, None, None


def _save_public_assessment_result(owner_user_id: str, assessment: Dict[str, Any], candidate_id: str, result: Dict[str, Any]) -> None:
    """Persist candidate assessment results back to the recruiter workspace."""
    if not owner_user_id:
        return
    data = _db_load_recruiter_state(owner_user_id)
    owner_candidates = data.get("candidates", []) or []
    candidate = next((c for c in owner_candidates if c.get("id") == candidate_id), None)
    if candidate is None:
        candidate = {
            "id": candidate_id,
            "name": result.get("candidate_name", "Candidate"),
            "email": result.get("candidate_email", ""),
            "role_match": 0,
            "resume_score": 0,
            "status": "Assessment Completed",
            "assessment_status": "Completed",
            "assessment_company": result.get("company", assessment.get("company", "")),
            "assessment_recruiter": result.get("recruiter_name", assessment.get("recruiter_name", "")),
        }
        owner_candidates.append(candidate)
    candidate["assessment_status"] = "Completed"
    candidate["assessment_percentage"] = result.get("percentage", 0)
    candidate["assessment_score"] = result.get("score", 0)
    candidate["assessment_total"] = result.get("total", 0)
    candidate["assessment_completed_at"] = result.get("submitted_at", datetime.now().strftime("%Y-%m-%d %H:%M"))
    candidate["status"] = "Assessment Completed"
    submissions = [x for x in (data.get("submissions", []) or []) if isinstance(x, dict) and x.get("token") != result.get("token")]
    submissions.append(result)
    data["candidates"] = owner_candidates
    data["submissions"] = submissions
    _db_save_recruiter_state(owner_user_id, data)

    # Also mark the independent public record as used when it exists.
    try:
        conn = get_db_connection()
        with conn:
            conn.execute("UPDATE public_assessments SET used=1 WHERE token=?", (result.get("token", ""),))
    except sqlite3.Error:
        pass


def render_public_recruiter_assessment(token: str) -> None:
    """Professional public assessment flow: welcome -> start -> one question -> review -> submit."""
    assessment, candidate, candidate_id, owner_user_id = _find_recruiter_assessment_by_token(token)
    if not assessment or not candidate:
        st.error("This assessment link is invalid, expired, or no longer available.")
        st.stop()

    company = str(assessment.get("company") or "Company")
    recruiter_name = str(assessment.get("recruiter_name") or "Recruiting Team")
    recruiter_email = str(assessment.get("recruiter_email") or "")
    role = str(assessment.get("role") or "Professional Assessment")
    questions = assessment.get("questions", []) or []
    duration_minutes = max(5, min(180, int(assessment.get("duration_minutes", 30) or 30)))

    state_key = f"candidate_exam_{token[:16]}"
    answers_key = f"{state_key}_answers"
    started_key = f"{state_key}_started_at"
    current_key = f"{state_key}_current"
    review_key = f"{state_key}_review"
    submitted_key = f"{state_key}_submitted"

    for key, default in ((answers_key, {}), (started_key, ""), (current_key, 0), (review_key, False), (submitted_key, False)):
        if key not in st.session_state:
            st.session_state[key] = default

    # If the public DB record is already used, do not allow another attempt.
    if assessment.get("used") and not st.session_state[submitted_key]:
        st.markdown("##  Assessment Already Submitted")
        st.info("This assessment has already been submitted. You cannot start another attempt using this link.")
        st.stop()

    if not questions:
        st.error("This assessment currently has no questions.")
        st.stop()

    st.markdown(
        f"""
        <div style='padding:28px;border:1px solid #e2e8f0;border-radius:20px;background:#ffffff;margin-bottom:18px;'>
            <div style='font-size:12px;font-weight:800;letter-spacing:.12em;color:#64748b;text-transform:uppercase;'>CAREERLENS AI · PRE-EMPLOYMENT ASSESSMENT</div>
            <h1 style='margin:8px 0 4px;color:#0f172a;'>{_escape(company)}</h1>
            <h3 style='margin:0;color:#334155;'>{_escape(role)}</h3>
            <p style='margin:12px 0 0;color:#64748b;'>Invited by <b>{_escape(recruiter_name)}</b>{(' · ' + _escape(recruiter_email)) if recruiter_email else ''}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state[submitted_key]:
        st.success("Assessment submitted successfully.")
        st.markdown("### Thank you for completing the assessment")
        st.write("Your responses have been securely recorded and returned to the recruiting team.")
        st.info("You may close this browser tab now.")
        st.stop()

    # ---------------- Welcome / instructions ----------------
    if not st.session_state[started_key]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Questions", len(questions))
        c2.metric("Duration", f"{duration_minutes} min")
        c3.metric("Format", "One question at a time")

        st.markdown("### Before you start")
        st.markdown(
            """
            - Read each question carefully and select the **single best answer**.
            - Questions appear **one at a time**; use **Previous** and **Next** to navigate.
            - Your question set and answer choices are randomized specifically for this candidate.
            - The timer starts only when you click **Start Assessment**.
            - You can review your answers before final submission.
            - When the timer expires, the assessment is submitted with the answers already saved.
            - Do not refresh or close the browser while the assessment is in progress.
            """
        )
        st.warning(f"⏱ You will have {duration_minutes} minutes. Make sure you have enough uninterrupted time before starting.")
        if st.button(" Start Assessment", type="primary", use_container_width=True, key=f"start_public_assessment_{token[:10]}"):
            st.session_state[started_key] = datetime.now().isoformat(timespec="seconds")
            st.session_state[current_key] = 0
            st.session_state[review_key] = False
            st.rerun()
        st.stop()

    # ---------------- Timer / expiry ----------------
    try:
        started_at = datetime.fromisoformat(st.session_state[started_key])
        deadline = started_at.timestamp() + duration_minutes * 60
        remaining = max(0, int(deadline - datetime.now().timestamp()))
    except (TypeError, ValueError):
        remaining = duration_minutes * 60
        deadline = datetime.now().timestamp() + remaining
        st.session_state[started_key] = datetime.now().isoformat(timespec="seconds")

    if remaining <= 0:
        result = assessment_result(questions, st.session_state[answers_key])
        result.update({
            "token": token,
            "candidate_id": candidate_id,
            "candidate_name": candidate.get("name", "Candidate"),
            "candidate_email": candidate.get("email", ""),
            "role": role,
            "company": company,
            "recruiter_name": recruiter_name,
            "recruiter_email": recruiter_email,
            "assessment_id": assessment.get("id", ""),
            "submission_type": "Auto-submitted on time expiry",
        })
        _save_public_assessment_result(owner_user_id, assessment, candidate_id, result)
        st.session_state[submitted_key] = True
        st.session_state["last_assessment_result"] = result
        st.rerun()

    mins, secs = divmod(remaining, 60)
    st.markdown(
        f"""
        <div style='position:sticky;top:8px;z-index:20;padding:12px 16px;border:1px solid #cbd5e1;border-radius:14px;background:#ffffff;box-shadow:0 6px 20px rgba(15,23,42,.08);margin-bottom:18px;'>
            <div style='display:flex;justify-content:space-between;align-items:center;gap:16px;'>
                <div><b>Assessment in progress</b><div style='font-size:12px;color:#64748b;'>{len(questions)} questions · one question at a time</div></div>
                <div style='font-size:20px;font-weight:800;color:#dc2626;' id='cl-timer'>{mins:02d}:{secs:02d}</div>
            </div>
            <div style='margin-top:8px;height:6px;background:#e2e8f0;border-radius:99px;overflow:hidden;'><div style='width:{min(100,max(0,remaining/(duration_minutes*60)*100)):.2f}%;height:100%;background:#2563eb;'></div></div>
        </div>
        <script>
        (function() {{
          const deadline = {deadline * 1000:.0f};
          const el = document.getElementById('cl-timer');
          function tick() {{
            const left = Math.max(0, Math.floor((deadline - Date.now()) / 1000));
            const m = Math.floor(left / 60), s = left % 60;
            if (el) el.textContent = String(m).padStart(2,'0') + ':' + String(s).padStart(2,'0');
            if (left <= 0) {{
              try {{ window.parent.location.reload(); }} catch(e) {{ window.location.reload(); }}
            }}
          }}
          tick(); setInterval(tick, 1000);
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )

    # ---------------- Review screen ----------------
    if st.session_state[review_key]:
        st.markdown("###  Review Your Answers")
        st.caption("Check your selections before final submission. Unanswered questions will be marked unanswered.")
        answered_count = sum(1 for q in questions if st.session_state[answers_key].get(q.get("id")) is not None)
        a, b, c = st.columns(3)
        a.metric("Answered", answered_count)
        b.metric("Unanswered", len(questions) - answered_count)
        c.metric("Questions", len(questions))

        for q in questions:
            selected = st.session_state[answers_key].get(q.get("id"))
            label = selected if selected is not None else "Not answered"
            st.markdown(
                f"**Q{q.get('id')}. {_escape(q.get('question', 'Question'))}**  \n"
                f"<span style='color:#64748b;'>Your answer: {_escape(label)}</span>",
                unsafe_allow_html=True,
            )

        edit_q = st.selectbox(
            "Choose a question to edit",
            options=list(range(1, len(questions) + 1)),
            format_func=lambda n: f"Question {n}",
            key=f"{state_key}_edit_question",
        )
        e1, e2 = st.columns(2)
        if e1.button("← Edit Selected Question", use_container_width=True, key=f"edit_review_{token[:10]}"):
            st.session_state[current_key] = edit_q - 1
            st.session_state[review_key] = False
            st.rerun()
        if e2.button(" Submit Assessment", type="primary", use_container_width=True, key=f"final_submit_{token[:10]}"):
            result = assessment_result(questions, st.session_state[answers_key])
            result.update({
                "token": token,
                "candidate_id": candidate_id,
                "candidate_name": candidate.get("name", "Candidate"),
                "candidate_email": candidate.get("email", ""),
                "role": role,
                "company": company,
                "recruiter_name": recruiter_name,
                "recruiter_email": recruiter_email,
                "assessment_id": assessment.get("id", ""),
                "submission_type": "Candidate submitted",
            })
            _save_public_assessment_result(owner_user_id, assessment, candidate_id, result)
            st.session_state[submitted_key] = True
            st.session_state["last_assessment_result"] = result
            st.rerun()
        st.stop()

    # ---------------- One-question-at-a-time screen ----------------
    current_idx = max(0, min(len(questions) - 1, int(st.session_state[current_key])))
    q = questions[current_idx]
    qid = q.get("id")
    current_answer = st.session_state[answers_key].get(qid)

    st.progress((current_idx + 1) / len(questions), text=f"Question {current_idx + 1} of {len(questions)}")
    st.markdown(
        f"""
        <div style='padding:26px;border:1px solid #e2e8f0;border-radius:18px;background:#ffffff;box-shadow:0 8px 30px rgba(15,23,42,.05);'>
            <div style='font-size:12px;font-weight:800;letter-spacing:.08em;color:#2563eb;text-transform:uppercase;'>{_escape(q.get('section', 'Assessment'))}</div>
            <h2 style='margin:10px 0 0;color:#0f172a;'>Question {current_idx + 1}</h2>
            <p style='font-size:20px;line-height:1.55;color:#1e293b;margin:16px 0 0;'>{_escape(q.get('question', 'Question'))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    options = q.get("options", []) or []
    default_index = options.index(current_answer) if current_answer in options else None
    selected = st.radio(
        "Select one answer",
        options,
        index=default_index,
        key=f"{state_key}_radio_{qid}",
    )

    nav_left, nav_mid, nav_right = st.columns([1, 1, 1])
    if nav_left.button("← Previous", disabled=current_idx == 0, use_container_width=True, key=f"prev_{token[:10]}_{qid}"):
        st.session_state[answers_key][qid] = selected
        st.session_state[current_key] = current_idx - 1
        st.rerun()

    if nav_mid.button("Review Answers", use_container_width=True, key=f"review_{token[:10]}_{qid}"):
        st.session_state[answers_key][qid] = selected
        st.session_state[review_key] = True
        st.rerun()

    next_label = "Next Question →" if current_idx < len(questions) - 1 else "Review & Submit →"
    if nav_right.button(next_label, type="primary", use_container_width=True, key=f"next_{token[:10]}_{qid}"):
        st.session_state[answers_key][qid] = selected
        if current_idx < len(questions) - 1:
            st.session_state[current_key] = current_idx + 1
        else:
            st.session_state[review_key] = True
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
@st.dialog(" Sign In / Register")
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
    _access_action = str(st.query_params.get("access", "") or "").strip().lower()
    if _access_action:
        try: del st.query_params["access"]
        except Exception: pass
        if _access_action == "signin": dialog_auth(default_tab=0)
        elif _access_action == "register": dialog_auth(default_tab=1)
        elif _access_action == "guest":
            st.session_state.user_id=""; st.session_state.username="Guest Explorer"; st.session_state.is_logged_in=True; st.session_state.selected_gateway=False; st.rerun()
    st.markdown("""
    <div class="landing-frame"><div class="landing-content">
      <div class="landing-nav"><div class="landing-brand"><span class="brand-mark">CL</span>CareerLens AI</div><div class="landing-links"><span class="landing-link">Career Intelligence</span><span class="landing-link">For Job Seekers</span><span class="landing-link">For Recruiters</span><span class="landing-link">Resources</span></div></div>
      <div class="landing-hero"><div><div class="landing-kicker"><span>●</span> CAREER INTELLIGENCE PLATFORM</div><div class="landing-title">Make your next career move with <span class="accent">clarity.</span></div><div class="landing-copy">CareerLens brings your resume, skills, job opportunities, interview preparation, and career planning into one practical workspace — built to help you take the next step with confidence.</div><div class="landing-note">No complicated setup. Start exploring in seconds.</div></div>
      <div class="career-panel"><div class="career-panel-head"><div class="career-panel-title">Career readiness</div><div class="career-status">On track</div></div><div class="panel-score"><strong>78</strong><span>/ 100 readiness</span></div><div class="progress-track"><div class="progress-fill"></div></div><div class="panel-row"><div class="panel-row-icon">R</div><div class="panel-row-copy"><b>Resume intelligence</b><span>Strengths and improvement areas</span></div><div class="panel-check">Done</div></div><div class="panel-row"><div class="panel-row-icon">J</div><div class="panel-row-copy"><b>Job matching</b><span>Compare roles against your skills</span></div><div class="panel-check">Ready</div></div><div class="panel-row"><div class="panel-row-icon">I</div><div class="panel-row-copy"><b>Interview practice</b><span>Prepare with role-specific questions</span></div><div class="panel-check">Next</div></div><div class="panel-row"><div class="panel-row-icon">P</div><div class="panel-row-copy"><b>Career plan</b><span>Build a focused path forward</span></div><div class="panel-check">Next</div></div></div></div>
    </div></div>
    """, unsafe_allow_html=True)
    a1,a2,a3=st.columns(3,gap="small")
    with a1:
        if st.button("Get Started",use_container_width=True,type="primary",key="landing_signin"): dialog_auth(default_tab=0)
    with a2:
        if st.button("Create Account",use_container_width=True,key="landing_register"): dialog_auth(default_tab=1)
    with a3:
        if st.button("Explore as Guest",use_container_width=True,key="landing_guest"):
            st.session_state.user_id=""; st.session_state.username="Guest Explorer"; st.session_state.is_logged_in=True; st.session_state.resume_text=""; st.session_state.resume_analysis=None; st.session_state.job_match_result=None; st.session_state.resume_builder={}; st.session_state.recruiter_data={"campaign":None,"candidates":[],"assessments":[],"submissions":[]}; st.session_state.recruiter_candidates=[]; st.session_state.recruiter_assessment_submissions={}; st.session_state.selected_gateway=False; log_event("GUEST_ACCESS","Guest","N/A","Guest entry"); st.rerun()
    st.markdown("""<div class="landing-section-title">Everything you need to move forward</div><div class="landing-section-copy">One workspace for building, preparing, exploring, and acting on your career.</div>""",unsafe_allow_html=True)
    f1,f2,f3=st.columns(3,gap="medium")
    for col,(num,title,desc) in zip((f1,f2,f3),[("01","Resume Intelligence","Understand how strong your resume is, what skills stand out, and what to improve next."),("02","Job & Career Insights","Match your profile to opportunities, estimate your fit, and build a practical career roadmap."),("03","Interview & Hiring","Practice role-specific interviews or manage candidates, assessments, and hiring workflows.")]):
        with col: st.markdown(f'<div class="landing-feature"><div class="landing-icon" style="width:36px;height:36px;border-radius:9px;background:#f2f4f7;color:#344054;display:flex;align-items:center;justify-content:center;font-size:.7rem;font-weight:800">{num}</div><div class="landing-feature-title">{title}</div><div class="landing-feature-text">{desc}</div></div>',unsafe_allow_html=True)
    st.markdown("""<div class="landing-section-title">Built for both sides of hiring</div><div class="landing-section-copy">A focused experience whether you are building your career or building a team.</div>""",unsafe_allow_html=True)
    r1,r2=st.columns(2,gap="medium")
    with r1: st.markdown('<div class="role-card"><div class="role-card-head"><div class="role-icon">JS</div><h3>Job Seeker</h3></div><p>Turn your profile into a clear career plan and make better decisions about the roles you pursue.</p><div class="role-list"><div><i></i>Resume analysis and improvement</div><div><i></i>Job matching and skill gaps</div><div><i></i>Mock interviews and assessments</div><div><i></i>Career roadmap and assistant</div></div></div>',unsafe_allow_html=True)
    with r2: st.markdown('<div class="role-card"><div class="role-card-head"><div class="role-icon">RC</div><h3>Recruiter</h3></div><p>Organize your hiring workflow from campaign setup to candidate screening, assessments, and interviews.</p><div class="role-list"><div><i></i>Hiring campaigns and candidate intake</div><div><i></i>Bulk resume screening and ranking</div><div><i></i>Assessment dispatch and score tracking</div><div><i></i>Interview pipeline management</div></div></div>',unsafe_allow_html=True)
    st.markdown('''<div class="landing-trust"><div class="trust-item"><strong>One workspace</strong><span>Career + hiring workflows</span></div><div class="trust-item"><strong>Practical insights</strong><span>Actionable recommendations</span></div><div class="trust-item"><strong>Responsive</strong><span>Phone, tablet and desktop</span></div><div class="trust-item"><strong>Secure by design</strong><span>Controlled account access</span></div></div><div class="landing-footer"><span>© 2026 CareerLens AI</span><span>Understand your career. Build your future.</span></div>''',unsafe_allow_html=True)
    st.stop()


# ============================================================
# WORKSPACE GATEWAY PORTAL
# ============================================================
if not st.session_state.selected_gateway:
    st.markdown(
        f"""
        <div class="header-banner">
          <div>
            <div class="header-title">Welcome, {html.escape(st.session_state.username)}! </div>
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
            <div class="role-icon" style="background:#ffffff;"></div>
            <div><h3 style="margin:0;font-size:1.15rem">Job Seeker Portal</h3><span class="tag-badge tag-blue">Candidate Intelligence</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Discover opportunities, improve skills, and accelerate your career with deep AI guidance.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
             Resume Intelligence &nbsp;  AI Mock Interview<br> Job Match &nbsp;  Salary Insights &nbsp;  Career Roadmap
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
            <div class="role-icon" style="background:#ffffff;"></div>
            <div><h3 style="margin:0;font-size:1.15rem">Recruiter Portal</h3><span class="tag-badge tag-purple">Talent Acquisition</span></div>
          </div>
          <p style="color:#64748b;font-size:.8rem;line-height:1.65">Streamline hiring, screen cohorts at scale, and build high-performing teams with automated assessments.</p>
          <div style="border-top:1px solid #f1f5f9;padding-top:14px;color:#475569;font-size:.76rem;line-height:1.8">
             Bulk Resume Screening &nbsp;  Hiring Campaigns<br> Assessment Dispatcher &nbsp;  Candidate Ranking &nbsp;  Interview Pipeline
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
            <div style="font-size: 26px; color: #2563eb;"></div>
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
                <div style="width:36px; height:36px; border-radius:50%; background:#ffffff; color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800;">
                    
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

    if st.button(" Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.button(" Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if is_seeker:
        st.markdown('<div class="sidebar-section-title">CAREER TOOLS</div>', unsafe_allow_html=True)
        seeker_tools = [
            (" Dashboard", "Dashboard"),
            (" Resume Intelligence", "Resume Intelligence"),
            (" Pre-Interview Assessment", "Pre-Interview Assessment"),
            (" AI Mock Interview", "AI Mock Interview"),
            (" AI Job Match", "AI Job Match"),
            (" Salary Estimation", "Salary Estimation"),
            (" Career Roadmap", "Career Roadmap"),
            (" Job Detection", "Real-Time Job Detection"),
            (" Resume Builder", "Resume Builder"),
            (" AI Assistant", "AI Career Assistant"),
        ]
        for name, key_val in seeker_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_tool_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()
    else:
        st.markdown('<div class="sidebar-section-title">RECRUITER TOOLS</div>', unsafe_allow_html=True)
        rec_tools = [
            (" Recruiter Dashboard", "Dashboard"),
            (" Hiring Campaign", "Hiring Campaign"),
            (" Bulk Resume Screening", "Bulk Screening"),
            (" Shortlisted Candidates", "Shortlisted Candidates"),
            (" Assessment Dispatcher", "Assessment Builder"),
            (" Assessment Results", "Score Vault"),
            (" Interview Pipeline", "Interview Pipeline"),
        ]
        for name, key_val in rec_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                recruiter_navigate(key_val)
                st.rerun()

    st.markdown("<hr style='border-color: rgba(0,0,0,0.06); margin: 20px 0;'>", unsafe_allow_html=True)

    if st.button(" Logout", key="sb_logout_btn", use_container_width=True):
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
        <span style="width:32px;height:32px;border-radius:50%;background:#ffffff;display:flex;align-items:center;justify-content:center;color:#2563eb;font-weight:900;font-size:12px;">●</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
#  JOB SEEKER DASHBOARD
# ============================================================
if st.session_state.active_workspace == "Job Seeker Workspace":
    analysis = st.session_state.resume_analysis
    resume_score_val = f"{analysis.get('resume_score')}%" if analysis and analysis.get("resume_score") else "--"
    readiness_val = f"{analysis.get('readiness')}%" if analysis and analysis.get("readiness") else "--"
    market_match_val = f"{st.session_state.job_match_result.get('overall')}%" if st.session_state.job_match_result else "--"
    skills_count_val = f"{len(analysis.get('skills', []))} Stack" if analysis and analysis.get("skills") else "--"

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;"></div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Resume Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{resume_score_val}</div>
                    <span class="tag-badge tag-blue">AI Evaluated</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;"></div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Readiness Index</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{readiness_val}</div>
                    <span class="tag-badge tag-purple">Domain Ready</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#f0fdf4; color:#15803d;"></div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Market Match</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{market_match_val}</div>
                    <span class="tag-badge tag-green">Job Target</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#b45309;"></div>
                <div>
                    <div style="font-size:0.74rem; font-weight:700; color:#64748b; text-transform:uppercase;">Detected Stack</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{skills_count_val}</div>
                    <span class="tag-badge tag-amber">Verified Skills</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state.active_tool == "Dashboard":
        st.markdown("<h3 style='margin-bottom:16px; font-weight:900; font-size:1.25rem; color:#0f172a;'>Career Tools Suite</h3>", unsafe_allow_html=True)
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb;"></div><div class="tool-title">Resume Intelligence</div><div class="tool-desc">Deep resume analysis, strengths and enhancements.</div></div>""", unsafe_allow_html=True)
            if st.button("Resume Intelligence", key="card_c1_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Intelligence"
                st.rerun()
        with c2:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#7c3aed;"></div><div class="tool-title">Pre-Interview Exam</div><div class="tool-desc">Standardized MCQ domain qualifying assessment.</div></div>""", unsafe_allow_html=True)
            if st.button("Pre-Interview Exam", key="card_c2_btn", use_container_width=True):
                st.session_state.active_tool = "Pre-Interview Assessment"
                st.rerun()
        with c3:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#0284c7;"></div><div class="tool-title">AI Mock Interview</div><div class="tool-desc">Sequential dynamic interview questions with scoring.</div></div>""", unsafe_allow_html=True)
            if st.button("AI Mock Interview", key="card_c3_btn", use_container_width=True):
                st.session_state.active_tool = "AI Mock Interview"
                st.rerun()
        with c4:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#f0fdf4; color:#15803d;"></div><div class="tool-title">AI Job Match</div><div class="tool-desc">Match profile with job postings to find skill gaps.</div></div>""", unsafe_allow_html=True)
            if st.button("AI Job Match", key="card_c4_btn", use_container_width=True):
                st.session_state.active_tool = "AI Job Match"
                st.rerun()

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)
        c5, c6, c7, c8 = st.columns(4)
        with c5:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fffbeb; color:#d97706;"></div><div class="tool-title">Salary Estimation</div><div class="tool-desc">Accurate market compensation benchmarks.</div></div>""", unsafe_allow_html=True)
            if st.button("Salary Estimation", key="card_c5_btn", use_container_width=True):
                st.session_state.active_tool = "Salary Estimation"
                st.rerun()
        with c6:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#f0fdf4; color:#10b981;"></div><div class="tool-title">Career Roadmap</div><div class="tool-desc">Step-by-step career progression milestones.</div></div>""", unsafe_allow_html=True)
            if st.button("Career Roadmap", key="card_c6_btn", use_container_width=True):
                st.session_state.active_tool = "Career Roadmap"
                st.rerun()
        with c7:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fef2f2; color:#ef4444;"></div><div class="tool-title">Job Detection</div><div class="tool-desc">Real-time scam and fake job offer detection.</div></div>""", unsafe_allow_html=True)
            if st.button("Job Detection", key="card_c7_btn", use_container_width=True):
                st.session_state.active_tool = "Real-Time Job Detection"
                st.rerun()
        with c8:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6;"></div><div class="tool-title">Career Assistant</div><div class="tool-desc">Ask interview preparation and career questions.</div></div>""", unsafe_allow_html=True)
            if st.button("Career Assistant", key="card_c8_btn", use_container_width=True):
                st.session_state.active_tool = "AI Career Assistant"
                st.rerun()

    # 1. RESUME INTELLIGENCE
    elif st.session_state.active_tool == "Resume Intelligence":
        if st.button("← Back to Dashboard", key="btn_back_res"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  Resume Intelligence")
        st.caption("Your score is calculated from the actual resume content. There is no fixed/demo 100% score.")
        target_role = st.text_input("Target Role (optional)", placeholder="e.g. AI Engineer, Data Analyst, HR Manager", key="resume_target_role")
        uploaded_doc = st.file_uploader("Upload Resume File", type=["pdf", "docx", "txt"], key="resume_intelligence_upload")
        if uploaded_doc and st.button(" Analyze Resume", use_container_width=True, type="primary", key="analyze_resume_btn"):
            with st.spinner("Analyzing resume content, evidence and role alignment..."):
                res = api_analyze_resume(uploaded_doc, target_role)
                st.session_state.resume_analysis = res
                st.session_state.resume_text = res.get("extracted_text", "")
                st.success("Resume analyzed successfully.")
                st.rerun()
        if st.session_state.resume_analysis:
            r = st.session_state.resume_analysis
            score = int(r.get("resume_score", 0) or 0)
            readiness = int(r.get("readiness", 0) or 0)
            market = r.get("market_match")
            c1, c2, c3 = st.columns(3)
            c1.metric("Resume Score", f"{score}%")
            c2.metric("Readiness", f"{readiness}%")
            c3.metric("Market Match", f"{market}%" if market is not None else "Not assessed")
            st.progress(score / 100, text=f"Resume quality: {score}%")

            st.markdown("#### Candidate Profile")
            st.markdown(
                f"<div class='content-box'><b>{_escape(r.get('name', 'Candidate'))}</b><br>"
                f" {_escape(r.get('email') or 'Email not detected')} &nbsp; · &nbsp; "
                f" {_escape(r.get('phone') or 'Phone not detected')} &nbsp; · &nbsp; "
                f" {_escape(r.get('experience') or 'Not detected')}</div>",
                unsafe_allow_html=True,
            )

            st.markdown("#### Detected Skills")
            skills = r.get("skills") or []
            if skills:
                st.write(", ".join(str(x) for x in skills))
            else:
                st.info("No recognized skills were detected. Add explicit skill names to improve extraction.")

            st.markdown("#### Score Breakdown")
            breakdown = r.get("score_breakdown") or {}
            labels = {
                "content_quality": "Content Quality", "section_coverage": "Section Coverage", "skills": "Skills",
                "achievement_evidence": "Achievement Evidence", "contact_completeness": "Contact Completeness",
                "target_role_alignment": "Target Role Alignment",
            }
            rows=[]
            for key, label in labels.items():
                value = breakdown.get(key)
                if value is not None:
                    rows.append({"Area": label, "Score": f"{float(value):.0f}%"})
            if rows:
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("Score details are unavailable for this analysis.")

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### Strengths")
                for item in r.get("strengths") or []:
                    st.success(str(item))
            with col_b:
                st.markdown("#### Improvement Plan")
                for item in r.get("recommendations") or []:
                    st.warning(str(item))

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back to Dashboard", key="btn_back_exam"):
            st.session_state.active_tool = "Dashboard"
            st.session_state.assessment_active = False
            st.session_state.assessment_review = False
            st.rerun()
        st.markdown("###  Pre-Interview Assessment")
        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:
            selected_assessment_role = st.text_input("Search / Enter Any Job Role", placeholder="e.g. AI Engineer, Civil Engineer, Accountant, Product Manager", key="assessment_role_input")
            question_count = st.select_slider("Number of Questions", options=list(range(10, 51, 5)), value=st.session_state.assessment_question_count, key="assessment_count_select")
            st.session_state.assessment_question_count = question_count
            if st.button(" Start Assessment", use_container_width=True, type="primary", key="start_assessment_new"):
                role = selected_assessment_role.strip()
                if len(role) < 2:
                    st.warning("Enter a job role before starting the assessment.")
                else:
                    st.session_state.assessment_questions = generate_assessment_questions(role, question_count)
                    st.session_state.assessment_role = role
                    st.session_state.assessment_answers = {}
                    st.session_state.assessment_active = True
                    st.session_state.assessment_review = False
                    st.session_state.assessment_result = None
                    st.session_state.assessment_candidate_token = f"{st.session_state.username}_{uuid.uuid4().hex[:8]}"
                    st.rerun()
        elif st.session_state.assessment_active and not st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            with st.form("exam_form"):
                temp_ans = {}
                for q in questions:
                    qid = q["id"]
                    current = st.session_state.assessment_answers.get(qid)
                    current_index = q["options"].index(current) if current in q["options"] else None
                    temp_ans[qid] = st.radio(f"Q{qid}. {q['question']}", q["options"], index=current_index, key=f"q_choice_{qid}")
                if st.form_submit_button(" Review Answers Before Submit", use_container_width=True):
                    st.session_state.assessment_answers = temp_ans
                    st.session_state.assessment_review = True
                    st.rerun()
        elif st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            st.caption(f"Reviewing {len(questions)} questions for {st.session_state.assessment_role}")
            for q in questions:
                selected = st.session_state.assessment_answers.get(q["id"])
                status = " Answered" if selected else " Unanswered"
                st.markdown(f"**Q{q['id']} — {status}**  \n{_escape(q['question'])}  \nYour answer: **{_escape(selected or 'None')}**")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("← Continue Editing", use_container_width=True, key="continue_edit_exam"):
                    st.session_state.assessment_review = False
                    st.rerun()
            with b2:
                if st.button(" Submit Assessment", type="primary", use_container_width=True, key="confirm_submit_exam"):
                    st.session_state.assessment_result = assessment_result(questions, st.session_state.assessment_answers)
                    st.session_state.assessment_active = False
                    st.session_state.assessment_review = False
                    log_event("ASSESSMENT_COMPLETED", st.session_state.username, str(st.session_state.assessment_result["percentage"]), st.session_state.assessment_role)
                    st.rerun()
        elif st.session_state.assessment_result is not None:
            result = st.session_state.assessment_result
            pct = result["percentage"]
            st.markdown(f"<div class='content-box' style='text-align:center;padding:36px;'><div style='font-size:3rem;font-weight:900;color:#2563eb;'>{pct}%</div><p style='color:#64748b;'>{_escape(st.session_state.assessment_role)} • Score: {result['score']}/{result['total']}</p></div>", unsafe_allow_html=True)
            if st.button(" Take Another Assessment", use_container_width=True, key="btn_reset_exam"):
                st.session_state.assessment_result = None
                st.session_state.assessment_answers = {}
                st.rerun()

    # 3. AI MOCK INTERVIEW
    elif st.session_state.active_tool == "AI Mock Interview":
        if st.button("← Back to Dashboard", key="btn_back_mock"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  AI Mock Interview")
        st.caption("A realistic interviewer-style conversation based on your resume. The interview continues until you press Stop Interview.")
        if not st.session_state.interview_active and not st.session_state.interview_completed:
            if not st.session_state.resume_text:
                st.info("Tip: upload your resume in Resume Intelligence first. The interview will then ask resume-specific questions.")
            target_interview_role = st.text_input("Target Role", placeholder="e.g. AI Engineer, Product Manager, Accountant", key="mock_role_input")
            company_name = st.text_input("Company (optional)", placeholder="e.g. TCS, Microsoft, Deloitte", key="mock_company_input")
            max_questions = st.select_slider("Interview question bank", options=list(range(20, 51, 5)), value=30, key="mock_count_select")
            if st.button(" Start Interview", use_container_width=True, type="primary", key="start_mock_new"):
                role = target_interview_role.strip()
                if len(role) < 2:
                    st.warning("Enter a job role before starting the interview.")
                else:
                    bank = generate_mock_interview_questions(role, max_questions, st.session_state.resume_text, company_name)
                    st.session_state.interview_questions = bank
                    st.session_state.interview_role = role
                    st.session_state.interview_company = company_name.strip()
                    st.session_state.interview_q_count = max_questions
                    st.session_state.interview_current_idx = 0
                    st.session_state.interview_transcript = []
                    st.session_state.interview_active = True
                    st.session_state.interview_completed = False
                    st.session_state.interview_report = None
                    st.rerun()
        elif st.session_state.interview_active and not st.session_state.interview_completed:
            transcript = st.session_state.interview_transcript
            if st.session_state.interview_current_idx == 0 and not transcript:
                curr_question_text = st.session_state.interview_questions[0]
            else:
                curr_question_text = generate_next_interview_question(
                    st.session_state.interview_role,
                    st.session_state.resume_text,
                    transcript,
                    st.session_state.interview_questions,
                )
            st.session_state.interview_current_question = curr_question_text
            question_no = len(transcript) + 1
            st.progress(min(1.0, question_no / max(20, st.session_state.interview_q_count)), text=f"Question {question_no} · ongoing interview")
            st.markdown(
                f"<div class='content-box'><span class='tag-badge tag-blue'>LIVE INTERVIEW · Q{question_no}</span>"
                f"<h3 style='margin-top:10px;color:#0f172a;'>{_escape(curr_question_text)}</h3>"
                f"<p style='color:#64748b;margin-bottom:0;'>Answer naturally. The next question can follow up on your previous answer.</p></div>",
                unsafe_allow_html=True,
            )
            cand_response = st.text_area("Your response", height=190, key=f"ans_text_live_{question_no}")
            next_col, stop_col = st.columns(2)
            with next_col:
                if st.button("Submit Answer & Continue ", use_container_width=True, type="primary", key=f"mock_next_live_{question_no}"):
                    if not cand_response.strip():
                        st.warning("Please answer the current question before continuing.")
                    else:
                        st.session_state.interview_transcript.append({"question": curr_question_text, "answer": cand_response.strip()})
                        st.session_state.interview_current_idx += 1
                        st.rerun()
            with stop_col:
                if st.button("⏹ Stop Interview & Show Score", use_container_width=True, key=f"mock_stop_live_{question_no}"):
                    if cand_response.strip():
                        st.session_state.interview_transcript.append({"question": curr_question_text, "answer": cand_response.strip()})
                    if not st.session_state.interview_transcript:
                        st.warning("Answer at least one question before stopping the interview.")
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        st.session_state.interview_report = score_mock_interview(st.session_state.interview_transcript, st.session_state.interview_role)
                        log_event("MOCK_INTERVIEW_COMPLETED", st.session_state.username, str(st.session_state.interview_report.get("overall", 0)), st.session_state.interview_role)
                        st.rerun()
        elif st.session_state.interview_completed:
            rep = st.session_state.interview_report or {}
            st.markdown(f"<div class='content-box' style='text-align:center;'><div class='tag-badge tag-blue'>INTERVIEW COMPLETE</div><h2>Interview Score: <span style='color:#2563eb;'>{rep.get('overall', 0)}%</span></h2><p>{_escape(st.session_state.interview_role)}{(' · ' + _escape(st.session_state.interview_company)) if st.session_state.interview_company else ''}</p></div>", unsafe_allow_html=True)
            a,b,c,d = st.columns(4)
            a.metric("Overall", f"{rep.get('overall',0)}%")
            b.metric("Communication", f"{rep.get('communication',0)}%")
            c.metric("Evidence", f"{rep.get('evidence',0)}%")
            d.metric("Relevance", f"{rep.get('relevance',0)}%")
            st.markdown("#### Interview Feedback")
            for item in rep.get("strengths", []): st.success(str(item))
            for item in rep.get("improvements", []): st.warning(str(item))
            with st.expander("View Interview Transcript"):
                for i, item in enumerate(st.session_state.interview_transcript, 1):
                    st.markdown(f"**Q{i}.** {_escape(item.get('question',''))}")
                    st.markdown(f"**Your answer:** {_escape(item.get('answer',''))}")
                    st.divider()
            if st.button(" Start Another Mock Interview", key="btn_retry_mock"):
                st.session_state.interview_completed = False
                st.session_state.interview_active = False
                st.session_state.interview_report = None
                st.session_state.interview_transcript = []
                st.rerun()

    # 4. AI JOB MATCH
    elif st.session_state.active_tool == "AI Job Match":
        if st.button("← Back to Dashboard", key="btn_back_jm"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  AI Job Match")
        st.caption("Compare your resume with any job description using semantic similarity and explicit skill evidence.")
        jd_text = st.text_area("Paste Job Description", height=220, placeholder="Paste the complete job description here…", key="job_match_jd")
        if st.button(" Analyze Job Match", use_container_width=True, type="primary", key="analyze_job_match"):
            if not st.session_state.resume_text:
                st.warning("Upload your resume in Resume Intelligence first.")
            elif not jd_text.strip():
                st.warning("Paste a job description first.")
            else:
                with st.spinner("Comparing resume evidence, skills and job requirements…"):
                    st.session_state.job_match_result = normalize_job_match(api_match_job(st.session_state.resume_text, jd_text))
                    st.rerun()
        if st.session_state.job_match_result:
            m = st.session_state.job_match_result
            score = int(m.get("overall", 0) or 0)
            st.markdown(f"<div class='content-box' style='text-align:center;'><div style='font-size:.75rem;font-weight:800;color:#64748b;text-transform:uppercase;'>Overall Job Match</div><div style='font-size:3rem;font-weight:900;color:#2563eb;'>{score}%</div><p style='color:#64748b;margin:0;'>{_escape(m.get('summary',''))}</p></div>", unsafe_allow_html=True)
            a,b,c,d = st.columns(4)
            a.metric("Match Score", f"{score}%")
            b.metric("Semantic Similarity", f"{float(m.get('semantic_similarity', 0) or 0):.1f}%")
            c.metric("Matched Skills", len(m.get("matched", [])))
            d.metric("Skill Gaps", len(m.get("missing", [])))
            t1, t2, t3 = st.columns(3)
            with t1:
                st.markdown("####  Matched Skills")
                matched = m.get("matched", []) or []
                if matched:
                    st.dataframe(pd.DataFrame({"Matched Skill": matched}), use_container_width=True, hide_index=True)
                else:
                    st.info("No explicit matching skills detected.")
            with t2:
                st.markdown("####  Skills to Upgrade")
                missing = m.get("missing", []) or []
                if missing:
                    st.dataframe(pd.DataFrame({"Skill Gap": missing}), use_container_width=True, hide_index=True)
                else:
                    st.success("No major explicit skill gaps detected.")
            with t3:
                st.markdown("####  Recommended Skills")
                recommended = m.get("recommended_skills", missing[:10]) or []
                if recommended:
                    st.dataframe(pd.DataFrame({"Recommended Skill": recommended}), use_container_width=True, hide_index=True)
                else:
                    st.success("No additional priority skills identified.")
            st.markdown(f"**Experience Alignment:** {m.get('experience_alignment', 'Unavailable')}")
            st.info("Recommendation: prioritize the missing skills that appear repeatedly in the job description, then add project or work evidence for them to your resume.")

    # 5. SALARY ESTIMATION
    elif st.session_state.active_tool == "Salary Estimation":
        if st.button("← Back to Dashboard", key="btn_back_sal"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  Salary Estimation")
        sal_role_in = st.text_input("Role Title", placeholder="e.g. AI Engineer, Accountant, Civil Engineer", key="salary_role")
        sal_exp_in = st.selectbox("Experience Level", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6-10 yrs)", "Lead / Manager (10+ yrs)"], key="salary_exp")
        sal_location = st.text_input("Location", value="India", key="salary_location")
        if st.button(" Estimate Compensation", use_container_width=True, type="primary", key="salary_btn"):
            if not sal_role_in.strip():
                st.warning("Enter a role title.")
            else:
                result = api_salary_estimate(sal_role_in.strip(), sal_exp_in, sal_location.strip() or "India")
                st.session_state.salary_result = result
        if st.session_state.get("salary_result"):
            sr = st.session_state.salary_result
            st.markdown(f"<div class='content-box'><h2 style='margin:0;color:#2563eb;'>₹{sr.get('min_lpa',0):.1f} – ₹{sr.get('max_lpa',0):.1f} LPA</h2><p style='margin:8px 0 0;color:#64748b;'>{_escape(sr.get('role',''))} · {_escape(sr.get('experience',''))} · {_escape(sr.get('location',''))}</p></div>", unsafe_allow_html=True)
            st.info(sr.get("note", "Indicative estimate; verify against current local market data before making a decision."))

    # 6. CAREER ROADMAP
    elif st.session_state.active_tool == "Career Roadmap":
        if st.button("← Back to Dashboard", key="btn_back_road"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  Career Roadmap")
        target_goal = st.text_input("Target Dream Role:", "Lead AI Architect")
        if st.button("Generate Step-by-Step Plan", use_container_width=True, type="primary"):
            with st.spinner("Generating milestones..."):
                res = api_career_roadmap(st.session_state.resume_text, target_goal)
                for step in res.get("steps", []):
                    st.markdown(f'<div class="content-box" style="padding:16px; margin-bottom:12px;">{html.escape(step)}</div>', unsafe_allow_html=True)

    # 7. REAL-TIME JOB DETECTION
    elif st.session_state.active_tool == "Real-Time Job Detection":
        if st.button("← Back to Dashboard", key="btn_back_det"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  Job Detection")
        st.caption("Provide a job/offer link, the job description, or both. One analysis runs across the combined evidence.")
        job_url = st.text_input(" Job / Offer Link", placeholder="https://example.com/jobs/…", key="fraud_url")
        description_input = st.text_area(" Job Description", height=240, placeholder="Paste the job description here…", key="fraud_description")
        if st.button(" Analyze Job", use_container_width=True, type="primary", key="analyze_job_safety_new"):
            if not job_url.strip() and not description_input.strip():
                st.warning("Provide a job link or job description before analyzing.")
            else:
                try:
                    with st.spinner("Analyzing job safety signals…"):
                        parts=[]
                        if job_url.strip(): parts.append(fetch_public_job_url(job_url.strip()))
                        if description_input.strip(): parts.append(description_input.strip())
                        st.session_state.job_detection_result = api_detect_fraud("\n".join(parts))
                        st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        if st.session_state.job_detection_result:
            res = st.session_state.job_detection_result
            st.metric("Fraud Risk Score", f"{res.get('score', 0)}/100")
            st.markdown(f"**Risk Level:** {res.get('level','UNKNOWN')}")
            for signal in res.get("signal_details", []): st.warning(str(signal))
            if not res.get("signal_details"): st.success("No obvious high-risk signals were detected by the current rule set. This is not a guarantee that a job is legitimate.")

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back to Dashboard", key="btn_back_bld"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("###  Professional Live Resume Builder")
        st.caption("Edit your content on the left. The selected template updates the preview immediately.")

        templates = [
            "Executive", "Minimal", "Modern Blue", "Modern Purple", "Emerald", "Professional",
            "Tech", "ATS Classic", "Classic Serif", "Corporate", "Clean Grid", "Modern ATS",
            "Creative", "Elegant", "Compact", "Bold Header",
        ]
        previous_template = st.session_state.get("resume_template", "Executive")
        default_index = templates.index(previous_template) if previous_template in templates else 0
        template = st.selectbox(
            "Choose Resume Template",
            templates,
            index=default_index,
            key="resume_template_select",
            help="Changing this selection changes both the live preview and the generated PDF.",
        )
        if template != previous_template:
            st.session_state.resume_template = template
            # A PDF generated for another template must never be presented as the current template.
            st.session_state.pop("resume_pdf_bytes", None)
            st.session_state.pop("resume_pdf_template", None)
        else:
            st.session_state.resume_template = template

        # Template-specific preview tokens. These are intentionally different so the
        # template selector changes the actual visual design, not only the label.
        preview_config = {
            "Executive": {"accent": "#1d4ed8", "bg": "#ffffff", "heading": "#1d4ed8", "border": "#dbeafe", "font": "Arial", "radius": "12px", "header_align": "center"},
            "Minimal": {"accent": "#111827", "bg": "#ffffff", "heading": "#111827", "border": "#e5e7eb", "font": "Arial", "radius": "0", "header_align": "left"},
            "Modern Blue": {"accent": "#2563eb", "bg": "#f8fbff", "heading": "#2563eb", "border": "#bfdbfe", "font": "Arial", "radius": "16px", "header_align": "left"},
            "Modern Purple": {"accent": "#7c3aed", "bg": "#fcfaff", "heading": "#7c3aed", "border": "#ddd6fe", "font": "Arial", "radius": "16px", "header_align": "left"},
            "Emerald": {"accent": "#059669", "bg": "#f7fffb", "heading": "#047857", "border": "#a7f3d0", "font": "Arial", "radius": "14px", "header_align": "left"},
            "Professional": {"accent": "#334155", "bg": "#ffffff", "heading": "#334155", "border": "#cbd5e1", "font": "Arial", "radius": "8px", "header_align": "center"},
            "Tech": {"accent": "#0284c7", "bg": "#f7fcff", "heading": "#0369a1", "border": "#bae6fd", "font": "Arial", "radius": "10px", "header_align": "left"},
            "ATS Classic": {"accent": "#111827", "bg": "#ffffff", "heading": "#111827", "border": "#d1d5db", "font": "Arial", "radius": "2px", "header_align": "left"},
            "Classic Serif": {"accent": "#374151", "bg": "#fffefb", "heading": "#374151", "border": "#d6d3d1", "font": "Georgia, serif", "radius": "0", "header_align": "center"},
            "Corporate": {"accent": "#0f172a", "bg": "#f8fafc", "heading": "#0f172a", "border": "#cbd5e1", "font": "Arial", "radius": "6px", "header_align": "left"},
            "Clean Grid": {"accent": "#475569", "bg": "#ffffff", "heading": "#334155", "border": "#94a3b8", "font": "Arial", "radius": "4px", "header_align": "left"},
            "Modern ATS": {"accent": "#1e293b", "bg": "#ffffff", "heading": "#1e293b", "border": "#cbd5e1", "font": "Arial", "radius": "10px", "header_align": "left"},
            "Creative": {"accent": "#db2777", "bg": "#fff8fc", "heading": "#be185d", "border": "#fbcfe8", "font": "Arial", "radius": "18px", "header_align": "center"},
            "Elegant": {"accent": "#6b21a8", "bg": "#fdfaff", "heading": "#6b21a8", "border": "#e9d5ff", "font": "Georgia, serif", "radius": "18px", "header_align": "center"},
            "Compact": {"accent": "#0f766e", "bg": "#f8fffe", "heading": "#0f766e", "border": "#99f6e4", "font": "Arial", "radius": "6px", "header_align": "left"},
            "Bold Header": {"accent": "#b45309", "bg": "#fffdf8", "heading": "#92400e", "border": "#fcd34d", "font": "Arial", "radius": "10px", "header_align": "left"},
        }
        cfg = preview_config[template].copy()
        cfg["layout"] = {
            "Executive": "centered", "Minimal": "minimal", "Modern Blue": "sidebar", "Modern Purple": "sidebar",
            "Emerald": "split", "Professional": "centered", "Tech": "terminal", "ATS Classic": "ats",
            "Classic Serif": "serif", "Corporate": "corporate", "Clean Grid": "grid", "Modern ATS": "ats-modern",
            "Creative": "creative", "Elegant": "serif", "Compact": "compact", "Bold Header": "bold",
        }.get(template, "modern")

        existing = st.session_state.get("resume_builder") or {}
        left, right = st.columns([1, 1.08], gap="large")

        with left:
            st.markdown("####  Edit Content")
            rb_name = st.text_input("Full Name", value=existing.get("name", ""), key="rb_name")
            rb_email = st.text_input("Email", value=existing.get("email", ""), key="rb_email")
            rb_phone = st.text_input("Phone", value=existing.get("phone", ""), key="rb_phone")
            rb_location = st.text_input("Location", value=existing.get("location", ""), key="rb_location")
            rb_linkedin = st.text_input("LinkedIn", value=existing.get("linkedin", ""), key="rb_linkedin")
            rb_github = st.text_input("GitHub / Portfolio", value=existing.get("github", ""), key="rb_github")
            rb_headline = st.text_input("Professional Headline", value=existing.get("headline", ""), key="rb_headline")
            rb_summary = st.text_area("Professional Summary", value=existing.get("summary", ""), height=120, key="rb_summary")
            rb_experience = st.text_area("Experience", value=existing.get("experience", ""), height=150, key="rb_experience")
            rb_education = st.text_area("Education", value=existing.get("education", ""), height=110, key="rb_education")
            rb_projects = st.text_area("Projects", value=existing.get("projects", ""), height=130, key="rb_projects")
            rb_skills = st.text_area("Skills (comma-separated)", value=existing.get("skills", ""), height=90, key="rb_skills")
            rb_cert = st.text_area("Certifications", value=existing.get("certifications", ""), height=90, key="rb_cert")
            rb_ach = st.text_area("Achievements", value=existing.get("achievements", ""), height=90, key="rb_ach")

            resume_data = {
                "name": rb_name, "email": rb_email, "phone": rb_phone, "location": rb_location,
                "linkedin": rb_linkedin, "github": rb_github, "headline": rb_headline,
                "summary": rb_summary, "experience": rb_experience, "education": rb_education,
                "projects": rb_projects, "skills": rb_skills, "certifications": rb_cert,
                "achievements": rb_ach,
            }
            st.session_state.resume_builder = resume_data

            if st.button("⬇ Generate & Download PDF", use_container_width=True, type="primary", key="download_live_resume"):
                pdf_bytes = build_resume_pdf(resume_data, template)
                st.session_state["resume_pdf_bytes"] = pdf_bytes
                st.session_state["resume_pdf_template"] = template

            if st.session_state.get("resume_pdf_bytes"):
                st.download_button(
                    "Download Resume PDF",
                    data=st.session_state["resume_pdf_bytes"],
                    file_name=f"CareerLens_Resume_{template.replace(' ', '_')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key="download_resume_file",
                )

        with right:
            st.markdown(f"####  Live Preview — {template}")
            contact = " · ".join([x for x in (rb_email, rb_phone, rb_location, rb_linkedin, rb_github) if x])
            skills_html = "".join(
                f"<span style='display:inline-block;margin:3px;padding:5px 9px;border-radius:999px;background:{cfg['border']};color:{cfg['heading']};font-size:12px;'>{_escape(x.strip())}</span>"
                for x in rb_skills.split(",") if x.strip()
            )
            name_align = cfg["header_align"]
            accent = cfg["accent"]
            heading_color = cfg["heading"]
            border = cfg["border"]
            bg = cfg["bg"]
            font = cfg["font"]
            radius = cfg["radius"]
            layout = cfg["layout"]
            section_html = ""
            for title_text, value in (("PROFILE", rb_summary), ("EXPERIENCE", rb_experience), ("EDUCATION", rb_education), ("PROJECTS", rb_projects), ("SKILLS", skills_html), ("CERTIFICATIONS", rb_cert), ("ACHIEVEMENTS", rb_ach)):
                if not value:
                    continue
                body = value if title_text == "SKILLS" else _escape(value).replace(chr(10), "<br>")
                section_html += f"<section style='margin-top:18px;'><h3 style='font-size:12px;letter-spacing:.08em;color:{heading_color};border-bottom:1px solid {border};padding-bottom:6px;margin:0 0 8px;'>{title_text}</h3><div style='color:#1f2937;line-height:1.58;font-size:13px;'>{body}</div></section>"

            if layout in {"sidebar", "split"}:
                preview = f"<div style='background:{bg};border:1px solid {border};border-radius:{radius};min-height:760px;box-shadow:0 10px 28px rgba(15,23,42,.08);font-family:{font};overflow:hidden;display:grid;grid-template-columns:30% 70%;'>"
                preview += f"<aside style='background:{accent};color:white;padding:28px 20px;'><h1 style='font-size:25px;margin:0 0 8px;color:white;'>{_escape(rb_name or 'Your Name')}</h1><div style='font-size:12px;line-height:1.7;opacity:.92;'>{_escape(contact)}</div><div style='margin-top:22px;font-size:11px;font-weight:800;letter-spacing:.1em;'>SKILLS</div><div style='margin-top:7px;color:white;'>{skills_html}</div></aside><main style='padding:28px;'>{f"<div style='font-size:15px;color:{heading_color};font-weight:700;margin-bottom:8px;'>{_escape(rb_headline)}</div>" if rb_headline else ''}{section_html}</main></div>"
            elif layout == "terminal":
                preview = f"<div style='background:#0f172a;border:1px solid {border};border-radius:{radius};min-height:760px;padding:30px;box-shadow:0 10px 28px rgba(15,23,42,.15);font-family:Consolas,monospace;color:#e2e8f0;'><div style='color:{accent};font-size:12px;'>$ careerlens resume --profile</div><h1 style='color:#f8fafc;font-size:30px;margin:8px 0;'>{_escape(rb_name or 'Your Name')}</h1><div style='color:#94a3b8;font-size:12px;'>{_escape(contact)}</div><div style='color:{accent};margin-top:8px;'>{_escape(rb_headline)}</div><div style='color:#e2e8f0;'>{section_html.replace('color:#1f2937','color:#cbd5e1')}</div></div>"
            elif layout == "serif":
                preview = f"<div style='background:{bg};border:1px solid {border};border-radius:{radius};min-height:760px;padding:42px;box-shadow:0 10px 28px rgba(15,23,42,.08);font-family:Georgia,serif;'><div style='text-align:center;border-bottom:1px solid {border};padding-bottom:18px;'><h1 style='margin:0;color:{accent};font-size:32px;'>{_escape(rb_name or 'Your Name')}</h1><div style='font-size:13px;color:#64748b;margin-top:7px;'>{_escape(contact)}</div><div style='font-style:italic;color:{heading_color};margin-top:6px;'>{_escape(rb_headline)}</div></div>{section_html}</div>"
            elif layout == "grid":
                preview = f"<div style='background:{bg};border:1px solid {border};border-radius:{radius};min-height:760px;padding:30px;box-shadow:0 10px 28px rgba(15,23,42,.08);font-family:{font};'><div style='display:grid;grid-template-columns:1fr 1fr;gap:18px;border-bottom:2px solid {accent};padding-bottom:16px;'><div><h1 style='margin:0;color:{accent};font-size:28px;'>{_escape(rb_name or 'Your Name')}</h1><div style='color:#64748b;font-size:12px;margin-top:6px;'>{_escape(contact)}</div></div><div style='text-align:right;color:{heading_color};font-weight:700;font-size:13px;'>{_escape(rb_headline)}</div></div><div style='margin-top:6px;'>{section_html}</div></div>"
            elif layout == "bold":
                preview = f"<div style='background:{bg};border:1px solid {border};border-radius:{radius};min-height:760px;box-shadow:0 10px 28px rgba(15,23,42,.08);font-family:{font};overflow:hidden;'><div style='background:{accent};padding:32px;color:white;'><h1 style='margin:0;color:white;font-size:32px;'>{_escape(rb_name or 'Your Name')}</h1><div style='margin-top:7px;font-size:13px;opacity:.9;'>{_escape(rb_headline)}</div><div style='margin-top:7px;font-size:12px;opacity:.85;'>{_escape(contact)}</div></div><div style='padding:24px;'>{section_html}</div></div>"
            elif layout == "minimal":
                preview = f"<div style='background:{bg};border-left:4px solid {accent};min-height:760px;padding:34px;box-shadow:0 10px 28px rgba(15,23,42,.06);font-family:{font};'><h1 style='margin:0;color:{accent};font-size:29px;'>{_escape(rb_name or 'Your Name')}</h1><div style='margin-top:5px;color:#64748b;font-size:12px;'>{_escape(contact)}</div><div style='margin-top:5px;color:{heading_color};'>{_escape(rb_headline)}</div>{section_html}</div>"
            else:
                preview = f"<div style='background:{bg};border:1px solid {border};border-radius:{radius};padding:30px;min-height:760px;box-shadow:0 10px 28px rgba(15,23,42,.08);font-family:{font};'><div style='text-align:{name_align};border-bottom:2px solid {accent};padding-bottom:14px;'><h1 style='margin:0;color:{accent};font-size:30px;'>{_escape(rb_name or 'Your Name')}</h1><div style='color:#475569;margin:6px 0 4px;font-size:14px;'>{_escape(rb_headline)}</div><div style='font-size:12px;color:#64748b;'>{_escape(contact)}</div></div>{section_html}</div>"
            st.markdown(preview, unsafe_allow_html=True)

    # 9. AI CAREER ASSISTANT
    elif st.session_state.active_tool == "AI Career Assistant":
        if st.button("← Back to Dashboard", key="btn_back_ast"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("###  AI Career Assistant")
        st.caption("Ask career, resume, interview, skills, salary or job-search questions in natural language.")
        if "assistant_messages" not in st.session_state:
            st.session_state.assistant_messages = []
        for msg in st.session_state.assistant_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
        prompt = st.chat_input("Ask anything about your career…", key="career_assistant_input")
        if prompt:
            st.session_state.assistant_messages.append({"role":"user","content":prompt})
            with st.spinner("CareerLens is thinking…"):
                answer = api_chat_assistant(st.session_state.assistant_messages, resume_context=st.session_state.resume_text)
            st.session_state.assistant_messages.append({"role":"assistant","content":answer})
            st.rerun()
        if st.session_state.assistant_messages and st.button("Clear Chat", key="clear_assistant_chat"):
            st.session_state.assistant_messages = []
            st.rerun()


# ============================================================
#  RECRUITER WORKSPACE
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
        if st.button(" Dashboard", use_container_width=True, key="rec_home_btn"):
            recruiter_navigate("Dashboard")
            st.rerun()

    if st.session_state.active_tool == "Dashboard":
        st.markdown("###  Recruiter Dashboard")
        company_dash = campaign.get("company") or "Company not configured"
        recruiter_dash = campaign.get("recruiter_name") or st.session_state.get("username", "Recruiter")
        recruiter_email_dash = campaign.get("recruiter_email") or "Contact email not configured"
        role_dash = campaign.get("role") or "Role not configured"
        st.markdown(f"""<div class="recruiter-command"><div class="recruiter-command-icon"></div><div><div class="recruiter-command-title">{html.escape(company_dash)}</div><div class="recruiter-command-copy"><b>Recruiter:</b> {html.escape(recruiter_dash)} &nbsp; · &nbsp; <b>Contact:</b> {html.escape(recruiter_email_dash)} &nbsp; · &nbsp; <b>Hiring:</b> {html.escape(role_dash)}</div></div></div>""", unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Candidates Screened", len(candidates))
        k2.metric("Shortlisted", sum(1 for c in candidates if c.get("status") == "Shortlisted"))
        k3.metric("Assessments Sent", sum(1 for c in candidates if c.get("assessment_status") == "Sent"))
        k4.metric("Completed Assessments", len(submissions))
        st.markdown("#### Actions")
        c1, c2, c3 = st.columns(3)
        if c1.button(" Setup Campaign", use_container_width=True, key="rec_action_campaign"):
            recruiter_navigate("Hiring Campaign")
            st.rerun()
        if c2.button(" Screen Resumes", use_container_width=True, key="rec_action_screen"):
            recruiter_navigate("Bulk Screening")
            st.rerun()
        if c3.button(" Dispatch Assessments", use_container_width=True, key="rec_action_dispatch"):
            recruiter_navigate("Assessment Builder")
            st.rerun()

    elif st.session_state.active_tool == "Hiring Campaign":
        st.markdown("###  Hiring Campaign")
        st.markdown("####  Employer & Recruiter Details")
        st.caption("These details are required. They identify who is hiring and are shown to the candidate before the assessment starts.")

        c1, c2 = st.columns(2)
        with c1:
            company_name = st.text_input(
                "Company / Organization *",
                value=str(campaign.get("company", "")),
                placeholder="e.g. Microsoft, TCS, Deloitte",
                key="campaign_company_v6",
            )
        with c2:
            recruiter_name = st.text_input(
                "Recruiter / Hiring Manager *",
                value=str(campaign.get("recruiter_name", "")),
                placeholder="e.g. Priya Sharma",
                key="campaign_recruiter_name_v6",
            )
        recruiter_email = st.text_input(
            "Recruiter Contact Email *",
            value=str(campaign.get("recruiter_email", "")),
            placeholder="recruiter@company.com",
            key="campaign_recruiter_email_v6",
        )

        st.markdown("####  Job & Assessment Details")
        role_options = IT_ROLES + NON_IT_ROLES
        saved_role = campaign.get("role", role_options[0])
        role_index = role_options.index(saved_role) if saved_role in role_options else 0
        role = st.selectbox("Target Role *", role_options, index=role_index, key="campaign_role_v6")
        job_description = st.text_area(
            "Job Description / Assessment Context *",
            value=str(campaign.get("job_description", "")),
            height=190,
            key="campaign_job_description_v6",
            placeholder="Responsibilities, required skills, experience, qualifications, and other hiring context…",
        )

        missing = []
        if not company_name.strip(): missing.append("Company / Organization")
        if not recruiter_name.strip(): missing.append("Recruiter / Hiring Manager")
        if not recruiter_email.strip(): missing.append("Recruiter Contact Email")
        if not job_description.strip(): missing.append("Job Description")

        if st.button(" Save Hiring Campaign", type="primary", use_container_width=True, key="save_campaign_v6"):
            if missing:
                st.error("Please complete: " + ", ".join(missing) + ".")
            elif not EMAIL_RE.fullmatch(recruiter_email.strip()):
                st.error("Please enter a valid recruiter contact email.")
            else:
                data["campaign"] = {
                    "role": role,
                    "company": company_name.strip(),
                    "recruiter_name": recruiter_name.strip(),
                    "recruiter_email": recruiter_email.strip().lower(),
                    "job_description": job_description.strip(),
                }
                persist_recruiter()
                st.success(f"Campaign saved: {company_name.strip()} • {role}")

    elif st.session_state.active_tool == "Bulk Screening":
        st.markdown("###  Bulk Resume Screening")
        st.caption("Upload candidates. CareerLens extracts real contact details, ranks candidates, and removes duplicate candidates.")
        files = st.file_uploader(
            "Upload candidate resumes",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="recruiter_bulk_files",
        )
        if files and st.button(" Screen All Resumes", type="primary", use_container_width=True, key="screen_all_resumes"):
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
            if a1.button(" Select All", use_container_width=True, key="select_all_candidates"):
                st.session_state.recruiter_selected_ids = [c.get("id") for c in candidates if c.get("id")]
                st.rerun()
            if a2.button(" Clear Selection", use_container_width=True, key="clear_candidate_selection"):
                st.session_state.recruiter_selected_ids = []
                st.rerun()
            if a3.button(" Shortlist Selected Candidates", type="primary", use_container_width=True, key="shortlist_selected"):
                if not selected_ids:
                    st.warning("Select at least one candidate first.")
                else:
                    for candidate in candidates:
                        if candidate.get("id") in selected_ids:
                            candidate["status"] = "Shortlisted"
                    persist_recruiter()
                    st.success(f"Shortlisted {len(selected_ids)} candidate(s).")
                    st.rerun()
            if a4.button(" Open Shortlist", use_container_width=True, key="go_shortlist"):
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
                badge = "Selected for Shortlist" if candidate.get("status") == "Shortlisted" else "Screened"
                email_label = candidate.get("email") or "Email Missing"
                st.markdown(
                    f"<div class='content-box' style='padding:12px 16px;margin-bottom:8px;'>"
                    f"<b>{html.escape(str(candidate.get('name') or 'Candidate'))}</b>"
                    f" &nbsp;·&nbsp; Match <b>{candidate.get('role_match', 0)}%</b>"
                    f" &nbsp;·&nbsp; Resume {candidate.get('resume_score', 0)}"
                    f" &nbsp;·&nbsp;  {html.escape(str(email_label))}"
                    f" &nbsp;·&nbsp; <span class='tag-badge tag-blue'>{badge}</span></div>",
                    unsafe_allow_html=True,
                )
            st.session_state.recruiter_selected_ids = list(selected_ids)

    elif st.session_state.active_tool == "Shortlisted Candidates":
        st.markdown("###  Shortlisted Candidates")
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
            if b1.button("⬅ Back to Bulk Screening", use_container_width=True, key="shortlist_back"):
                recruiter_navigate("Bulk Screening")
                st.rerun()
            if b2.button("Proceed to Assessment Dispatcher →", type="primary", use_container_width=True, key="shortlist_next"):
                recruiter_navigate("Assessment Builder")
                st.rerun()

    elif st.session_state.active_tool == "Assessment Builder":
        st.markdown("###  Assessment Dispatcher")
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
        company_target = campaign.get("company", "") or "Company"
        recruiter_target = campaign.get("recruiter_name", st.session_state.get("username", "Recruiter"))
        recruiter_email_target = campaign.get("recruiter_email", "")
        if not company_target or not campaign.get("recruiter_name") or not recruiter_email_target:
            st.error("Recruiter identity is incomplete. Go to Hiring Campaign and enter Company, Recruiter / Hiring Manager, and Recruiter Contact Email before sending an assessment.")
        st.markdown(f"**Company:** {html.escape(company_target or 'Not configured')}  ·  **Recruiter:** {html.escape(recruiter_target or 'Not configured')}" + (f"  ·  **Contact:** {html.escape(recruiter_email_target)}" if recruiter_email_target else ""), unsafe_allow_html=True)
        st.write(f"Target Role: **{role_target}**")
        q_count = st.select_slider(
            "Assessment question count",
            options=list(range(10, 51, 5)),
            value=20,
            key="recruiter_assessment_question_count",
            help="The assessment is generated from the selected hiring role. Choose 10–50 questions.",
        )
        duration_minutes = st.select_slider(
            "Assessment duration",
            options=[15, 20, 30, 45, 60, 90],
            value=30,
            format_func=lambda x: f"{x} minutes",
            key="recruiter_assessment_duration",
            help="The timer starts when the candidate clicks Start Assessment.",
        )
        st.caption(f"Role-based assessment: {q_count} questions · {duration_minutes} minutes · every candidate receives an independently randomized question and option order.")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Shortlisted", len(shortlisted))
        m2.metric("Ready to Email", len(eligible))
        m3.metric("Questions", q_count)
        m4.metric("Duration", f"{duration_minutes} min")

        if eligible and company_target and campaign.get("recruiter_name") and recruiter_email_target:
            st.dataframe(
                pd.DataFrame([{"Candidate": c.get("name"), "Email": c.get("email"), "Match": c.get("role_match", 0)} for c in eligible]),
                use_container_width=True,
                hide_index=True,
            )
            st.info(" Public assessment links are generated from: https://career-lens-ai.streamlit.app/")
            if st.button(" Send Assessment Invitations", type="primary", use_container_width=True, key="send_assessment_invitations"):
                progress = st.progress(0, text="Dispatching assessment emails…")
                rows = []
                campaign_assessment_id = uuid.uuid4().hex
                assessment_records = []
                for idx, candidate in enumerate(eligible):
                    token = _make_assessment_token({
                        "owner_user_id": st.session_state.get("user_id", ""),
                        "candidate_id": candidate.get("id", ""),
                        "assessment_id": campaign_assessment_id,
                        "candidate": {
                            "id": candidate.get("id", ""),
                            "name": candidate.get("name", "Candidate"),
                            "email": candidate.get("email", ""),
                            "phone": candidate.get("phone", ""),
                            "resume_score": candidate.get("resume_score", 0),
                            "role_match": candidate.get("role_match", 0),
                            "skills": candidate.get("skills", []),
                        },
                        "role": role_target,
                        "company": company_target,
                        "recruiter_name": recruiter_target,
                        "recruiter_email": recruiter_email_target,
                        "question_count": q_count,
                        "duration_minutes": duration_minutes,
                    })
                    # IMPORTANT: generate the question set from the candidate token so each
                    # candidate receives a different but stable exam.
                    candidate_questions = generate_assessment_questions(role_target, q_count, seed=token)
                    candidate_assessment = {
                        "id": campaign_assessment_id,
                        "role": role_target,
                        "company": company_target,
                        "recruiter_name": recruiter_target,
                        "recruiter_email": recruiter_email_target,
                        "questions": candidate_questions,
                        "question_count": q_count,
                        "duration_minutes": duration_minutes,
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "candidate_tokens": {candidate.get("id", ""): token},
                        "candidate_id": candidate.get("id", ""),
                        "used": False,
                    }
                    # Persist the candidate-specific record BEFORE sending the email.
                    _save_public_assessment_record(st.session_state.get("user_id", ""), candidate.get("id", ""), candidate_assessment, token)
                    test_link = _assessment_public_url(token)
                    sent, msg = api_send_assessment_email(
                        candidate["email"], candidate.get("name", "Candidate"), role_target, test_link,
                        company_target, recruiter_target, recruiter_email_target, duration_minutes, q_count
                    )
                    candidate["assessment_token"] = token
                    candidate["assessment_link"] = test_link
                    candidate["assessment_status"] = "Sent" if sent else "Failed"
                    candidate["assessment_company"] = company_target
                    candidate["assessment_recruiter"] = recruiter_target
                    candidate["assessment_question_count"] = q_count
                    candidate["assessment_duration_minutes"] = duration_minutes
                    if sent:
                        candidate["status"] = "Shortlisted"
                    rows.append({
                        "Candidate": candidate.get("name"),
                        "Email": candidate.get("email"),
                        "Status": "Sent" if sent else "Failed",
                        "Details": msg,
                    })
                    assessment_records.append(candidate_assessment)
                    progress.progress((idx + 1) / max(1, len(eligible)))

                # Keep campaign-level metadata for recruiter reporting, while public links
                # always resolve to their own candidate-specific record.
                data.setdefault("assessments", []).append({
                    "id": campaign_assessment_id,
                    "role": role_target,
                    "company": company_target,
                    "recruiter_name": recruiter_target,
                    "recruiter_email": recruiter_email_target,
                    "question_count": q_count,
                    "duration_minutes": duration_minutes,
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "candidate_tokens": {c.get("id", ""): c.get("assessment_token") for c in eligible},
                    "candidate_count": len(eligible),
                    "unique_candidate_question_sets": True,
                })
                persist_recruiter()
                st.success("Assessment dispatch completed — each candidate has an independent randomized question set.")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No shortlisted candidates with valid emails found.")

    elif st.session_state.active_tool == "Score Vault":
        st.markdown("###  Assessment Score Vault")
        if not submissions:
            st.info("No assessment submissions recorded yet.")
        else:
            st.dataframe(pd.DataFrame(submissions), use_container_width=True, hide_index=True)

    elif st.session_state.active_tool == "Interview Pipeline":
        st.markdown("###  Interview Pipeline")
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
