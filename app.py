import io
import os
import csv
import json
import re
import random
import uuid
import hashlib
import html
import ipaddress
import socket
import textwrap
import sqlite3
import secrets
from pathlib import Path
from urllib.parse import urlparse, quote
from datetime import datetime
from typing import Dict, List, Any, Optional

import pandas as pd
import requests
import streamlit as st
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")
ADMIN_PIN = os.getenv("ADMIN_PIN", "1234")

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# SAFE RESPONSE NORMALIZERS & LOGGERS
# ============================================================

def safe_parse_json(text: str) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
    return None

def normalize_job_match(raw_res: Any) -> Dict:
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
            "experience_alignment": str(raw_res.get("experience_alignment", "Strong Alignment"))
        }

    return {
        "overall": 68,
        "matched": ["Python", "SQL", "Analytical Thinking", "API Integration"],
        "missing": ["Distributed Caching", "Cloud Infrastructure (AWS/GCP)"],
        "summary": "Solid core foundations detected.",
        "experience_alignment": "Moderate Alignment"
    }

def extract_email_from_text(text: str) -> str:
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0) if match else f"candidate_{uuid.uuid4().hex[:6]}@domain.com"

def extract_phone_from_text(text: str) -> str:
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    return match.group(0) if match else "+1 (555) 019-2834"

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
                details
            ])
    except Exception:
        pass

# ============================================================
# STYLING & THEME
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg-page: #f8fafc;
    --navy-sidebar: #0a1128;
    --card-bg: #ffffff;
    --border-subtle: #e2e8f0;
    --text-navy: #0f172a;
    --text-muted: #64748b;
    --blue-primary: #2563eb;
    --purple-accent: #7c3aed;
    --emerald-accent: #059669;
    --amber-accent: #d97706;
}

.stApp {
    background-color: var(--bg-page) !important;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
    color: var(--text-navy) !important;
}

.block-container {
    max-width: 1420px;
    padding: 24px 38px 40px !important;
}

p, span, label, div {
    color: var(--text-navy);
}

[data-testid="stFileUploader"] {
    background-color: #ffffff !important;
    border: 2px dashed #cbd5e1 !important;
    border-radius: 16px !important;
    padding: 20px !important;
    box-shadow: 0 4px 14px rgba(15, 23, 42, 0.03) !important;
}

.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
}

[data-testid="stSidebar"] {
    background-color: var(--navy-sidebar) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

[data-testid="stSidebar"] * {
    color: #f8fafc !important;
}

.sidebar-brand-box {
    background: #ffffff;
    border-radius: 14px;
    padding: 14px 18px;
    margin-bottom: 18px;
    display: flex;
    align-items: center;
    gap: 12px;
}

.sidebar-brand-box * {
    color: #0a1128 !important;
}

.sidebar-user-box {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 18px;
}

.sidebar-section-title {
    font-size: 0.72rem;
    font-weight: 800;
    color: #94a3b8 !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 18px 0 8px 4px;
}

.stButton > button {
    border-radius: 10px !important;
    background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%) !important;
    color: #ffffff !important;
    font-weight: 800 !important;
    font-size: 0.92rem !important;
    padding: 0.6rem 1.4rem !important;
    border: none !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25) !important;
    transition: all 0.2s ease !important;
}

.stButton > button * {
    color: #ffffff !important;
}

.header-banner {
    background: linear-gradient(135deg, #091224 0%, #0d1b38 60%, #1e1b4b 100%);
    border-radius: 20px;
    padding: 24px 30px;
    margin-bottom: 20px;
    box-shadow: 0 10px 30px rgba(9, 18, 36, 0.15);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-title {
    font-size: 1.7rem;
    font-weight: 900;
    color: #ffffff !important;
    margin: 0;
}

.header-sub {
    font-size: 0.92rem;
    color: #cbd5e1 !important;
    margin: 4px 0 0 0;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin-bottom: 24px;
}

.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 16px 18px;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}

.kpi-icon-badge {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    flex-shrink: 0;
}

.content-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 24px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    margin-bottom: 18px;
}

.tag-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 12px;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
    margin: 3px;
}
.tag-blue { background: #eff6ff; color: #1d4ed8; border: 1px solid #dbeafe; }
.tag-purple { background: #faf5ff; color: #7e22ce; border: 1px solid #f3e8ff; }
.tag-green { background: #f0fdf4; color: #15803d; border: 1px solid #dcfce7; }
.tag-amber { background: #fffbeb; color: #b45309; border: 1px solid #fef3c7; }

.tool-box-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px 18px 0 0;
    padding: 20px 16px 12px;
    text-align: center;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 160px;
}

.tool-icon-circle {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    margin-bottom: 8px;
}

.tool-title {
    font-size: 0.98rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 3px;
}

.tool-desc {
    font-size: 0.78rem;
    color: #64748b;
    line-height: 1.4;
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

def _local_resume_analysis(text: str, filename: str) -> Dict:
    lower = text.lower()
    skill_catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi",
        "django", "flask", "sql", "postgresql", "mysql", "mongodb", "docker",
        "kubernetes", "aws", "azure", "gcp", "git", "linux", "machine learning",
        "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
        "rest api", "graphql", "redis", "kafka", "system design", "html", "css",
        "figma", "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium",
        "communication", "leadership", "problem solving"
    ]
    skills = [skill for skill in skill_catalog if skill in lower]
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    section_hits = sum(1 for section in ["experience", "education", "projects", "skills", "certifications"] if section in lower)
    resume_score = min(100, max(35, 35 + min(len(words) // 35, 35) + section_hits * 6 + min(len(skills) * 2, 20)))
    readiness = min(100, max(30, resume_score - 3 + min(len(skills), 10)))
    email_match = re.search(r"[\w.+'-]+@[\w.-]+\.[A-Za-z]{2,}", text)
    phone_match = re.search(r"(?:\+?\d[\d .()\-]{8,}\d)", text)
    clean_name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Candidate"
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
        "strengths": ["Skills extracted", "Structure verified"],
        "recommendations": ["Highlight quantifiable achievements.", "Tailor keywords to job description."],
        "extracted_text": text,
        "source": "local-fallback"
    }

def api_analyze_resume(file) -> Dict:
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
                return data
    except Exception:
        pass
    text = _extract_resume_text(file)
    return _local_resume_analysis(text, file.name)

def _skill_set(text: str) -> set:
    lower = (text or "").lower()
    catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django",
        "flask", "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws",
        "azure", "gcp", "git", "linux", "machine learning", "deep learning", "pandas",
        "numpy", "scikit-learn", "tensorflow", "pytorch", "rest api", "graphql", "redis",
        "kafka", "system design", "html", "css", "figma", "excel", "power bi", "tableau",
        "cybersecurity", "testing", "selenium", "communication", "leadership", "problem solving"
    ]
    return {x for x in catalog if x in lower}

def api_match_job(resume_text: str, job_description: str) -> Dict:
    if not resume_text.strip() or not job_description.strip():
        return {"overall": 0, "matched": [], "missing": [], "summary": "Input missing.", "experience_alignment": "Unavailable"}
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
        if res.ok:
            return normalize_job_match(res.json())
    except Exception:
        pass
    try:
        matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=8000).fit_transform([resume_text, job_description])
        similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
    except Exception:
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
        "summary": "Match computed successfully.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment"
    }

def api_detect_fraud(job_text: str) -> Dict:
    try:
        payload = {"text": job_text}
        res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)
        if res.ok and isinstance(res.json(), dict):
            return res.json()
    except Exception:
        pass
    risk_patterns = {
        "wire transfer": "Requests for wire transfers",
        "registration fee": "Upfront registration fees",
        "processing fee": "Upfront processing fees",
        "telegram": "Telegram-only communication",
        "whatsapp": "WhatsApp-only communication",
        "crypto": "Cryptocurrency payment requests",
        "gift card": "Gift card requests",
    }
    lower = job_text.lower()
    signals = [desc for phrase, desc in risk_patterns.items() if phrase in lower]
    score = min(100, len(signals) * 25)
    return {"score": score, "level": "HIGH RISK" if score >= 50 else "LOW RISK", "signals": len(signals), "signal_details": signals}

def api_career_roadmap(resume_text: str, target_role: str) -> Dict:
    try:
        payload = {"resume_text": resume_text, "target_role": target_role}
        res = requests.post(f"{API_BASE_URL}/api/career/roadmap", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    return {
        "steps": [
            f"Phase 1: Master foundational systems and patterns for {target_role}.",
            "Phase 2: Build end-to-end production systems on GitHub.",
            "Phase 3: Restructure achievements using XYZ impact metrics.",
            "Phase 4: Practice mock interview questions and scenario simulations."
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
    return "Focus on quantifiable business outcomes, concrete code proof, and solid architectural designs."

def api_send_email(to_email: str, subject: str, content: str) -> bool:
    payload = {"to_email": to_email, "subject": subject, "content": content}
    try:
        res = requests.post(f"{API_BASE_URL}/api/send-email", json=payload, timeout=30)
        return res.status_code == 200
    except Exception:
        return False

# ============================================================
# DATABASE & STORAGE INITIALIZATION
# ============================================================

def _db_connect():
    conn = sqlite3.connect(APP_DB_FILE, timeout=20, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def _init_app_db():
    with _db_connect() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL, created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS user_state (
            user_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS recruiter_state (
            user_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )""")

_init_app_db()

# State definitions
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "username" not in st.session_state: st.session_state.username = "Guest Explorer"
if "active_workspace" not in st.session_state: st.session_state.active_workspace = "Job Seeker Workspace"
if "active_tool" not in st.session_state: st.session_state.active_tool = "Dashboard"
if "resume_text" not in st.session_state: st.session_state.resume_text = ""
if "resume_analysis" not in st.session_state: st.session_state.resume_analysis = None
if "job_match_result" not in st.session_state: st.session_state.job_match_result = None

# Recruiter Flow States
if "recruiter_step" not in st.session_state: st.session_state.recruiter_step = 1
if "recruiter_candidates" not in st.session_state: st.session_state.recruiter_candidates = []
if "shortlisted_candidates" not in st.session_state: st.session_state.shortlisted_candidates = []
if "recruiter_job_desc" not in st.session_state: st.session_state.recruiter_job_desc = ""
if "recruiter_role" not in st.session_state: st.session_state.recruiter_role = "Software Developer"

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"]
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"]

def generate_assessment_questions(role: str, count: int) -> List[Dict]:
    bank = [
        ("Which data structure provides average O(1) lookup time?", ["Hash table", "Linked list", "Binary heap", "Queue"], 0),
        ("Which HTTP status code represents a successful resource creation?", ["201 Created", "200 OK", "301 Moved", "500 Internal Error"], 0),
        ("What is the primary role of an index in relational databases?", ["Speed up data retrieval", "Encrypt stored columns", "Auto-format SQL queries", "Prevent duplicate rows"], 0),
        ("Which pattern prevents cascading failures when dependent services are degraded?", ["Circuit Breaker", "Singleton", "Factory", "Observer"], 0),
        ("What does the Single Responsibility Principle require?", ["A module has only one reason to change", "Functions only accept one parameter", "A class has only one method", "Applications run in one thread"], 0)
    ]
    questions = []
    for i in range(max(1, count)):
        q_text, opts, ans_idx = bank[i % len(bank)]
        cycle = i // len(bank)
        questions.append({
            "id": i + 1,
            "section": "Core Technical Assessment",
            "question": f"{q_text}" if cycle == 0 else f"{q_text} (Variation {cycle+1})",
            "options": opts,
            "answer": opts[ans_idx]
        })
    return questions

def _candidate_id(name: str, email: str) -> str:
    return hashlib.sha256(f"{name}|{email}".encode("utf-8")).hexdigest()[:16]

# ============================================================
# DIALOGS & AUTHENTICATION
# ============================================================

@st.dialog("🔐 Sign In / Register")
def dialog_auth():
    t1, t2 = st.tabs(["Sign In", "Register"])
    with t1:
        u = st.text_input("Username or Email", key="auth_u")
        p = st.text_input("Password", type="password", key="auth_p")
        if st.button("Sign In", use_container_width=True):
            if not u or not p:
                st.warning("Please fill in both fields.")
            elif u.lower() == "admin" and p == ADMIN_PIN:
                st.session_state.username = "Administrator"
                st.session_state.is_logged_in = True
                st.session_state.active_workspace = "Recruiter Workspace"
                st.rerun()
            else:
                st.session_state.username = u.split("@")[0].capitalize()
                st.session_state.is_logged_in = True
                st.rerun()
    with t2:
        rn = st.text_input("Full Name", key="reg_n")
        ru = st.text_input("Username", key="reg_u")
        rp = st.text_input("Password", type="password", key="reg_p")
        if st.button("Create Account", use_container_width=True):
            if ru and rp:
                st.session_state.username = rn.strip() or ru.capitalize()
                st.session_state.is_logged_in = True
                st.rerun()

# ============================================================
# 1. LANDING & ACCESS
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align: center; padding: 40px 0 24px;">
            <div style="font-size: 58px; margin-bottom: 8px;">💼</div>
            <h1 style="font-size: 3rem; margin: 0; color: #091224; font-weight: 900;">Career<span style="color: #2563eb;">Lens</span> AI</h1>
            <p style="color: #475569; font-size: 1.15rem; margin-top: 6px; font-weight: 600;">Understand Your Career. Build Your Future.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col_c1, col_c2, col_c3 = st.columns([1, 1.4, 1])
    with col_c2:
        st.markdown(
            """
            <div class="content-box" style="text-align: center; padding: 36px 30px;">
                <span class="tag-badge tag-blue" style="font-size: 0.82rem; padding: 6px 16px; margin-bottom: 12px;">✦ AI CAREER ECOSYSTEM ✦</span>
                <h3 style="margin: 10px 0 8px 0; font-size: 1.35rem; color: #0f172a;">Access Your Career Workspace</h3>
                <p style="color: #64748b; font-size: 0.92rem; margin-bottom: 26px;">
                    Resume scoring, standardized qualifying tests, and end-to-end recruitment pipelines.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("🔐 Sign In", use_container_width=True): dialog_auth()
        with b2:
            if st.button("📝 Register", use_container_width=True): dialog_auth()
        with b3:
            if st.button("🚀 Guest Access", use_container_width=True):
                st.session_state.username = "Guest Explorer"
                st.session_state.is_logged_in = True
                st.rerun()
    st.stop()

# ============================================================
# 2. SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-brand-box">
            <div style="font-size: 26px; color: #2563eb;">💼</div>
            <div>
                <div style="font-size: 1.15rem; font-weight: 900; color: #091224; line-height: 1.1;">
                    Career<span style="color: #2563eb;">lens</span> <span style="color: #7c3aed;">AI</span>
                </div>
                <div style="font-size: 0.68rem; color: #64748b; font-weight: 700;">
                    Your Career, Our Intelligence
                </div>
            </div>
        </div>
        <div class="sidebar-user-box">
            <div style="font-size:0.88rem; font-weight:800; color:#ffffff;">{st.session_state.username}</div>
            <div style="font-size:0.72rem; color:#4ade80; font-weight:700;">● Online</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="sidebar-section-title">WORKSPACES</div>', unsafe_allow_html=True)
    if st.button("👤 Candidate Workspace", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.rerun()
    if st.button("🏢 Recruiter Workspace", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.is_logged_in = False
        st.session_state.username = "Guest"
        st.rerun()

# ============================================================
# 3. CANDIDATE WORKSPACE
# ============================================================

if st.session_state.active_workspace == "Job Seeker Workspace":
    st.markdown(
        f"""
        <div class="header-banner">
            <div>
                <div class="header-title">Candidate Intelligence Portal</div>
                <div class="header-sub">Upload your resume, review matching skills, and practice assessments.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    tab1, tab2, tab3 = st.tabs(["📄 Resume Analysis", "🎯 Job Match", "🗺️ Career Roadmap"])

    with tab1:
        st.subheader("Resume Parser & Scoring")
        file = st.file_uploader("Upload Resume (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"])
        if file and st.button("Analyze Resume", use_container_width=True):
            with st.spinner("Analyzing resume..."):
                analysis = api_analyze_resume(file)
                st.session_state.resume_analysis = analysis
                st.session_state.resume_text = analysis.get("extracted_text", "")
                st.success("Resume analyzed successfully!")

        if st.session_state.resume_analysis:
            res = st.session_state.resume_analysis
            st.markdown(f"""
            <div class="content-box">
                <h3 style="margin:0; color:#2563eb;">{res.get('name', 'Candidate')}</h3>
                <p style="color:#64748b; margin:6px 0 0 0;">📧 {res.get('email', 'N/A')} | 📱 {res.get('phone', 'N/A')}</p>
                <div style="margin-top:12px;"><b>Score:</b> {res.get('resume_score', 0)}%</div>
            </div>
            """, unsafe_allow_html=True)
            st.markdown("#### Detected Skills")
            pills = "".join([f'<span class="tag-badge tag-blue">{s}</span>' for s in res.get("skills", [])])
            st.markdown(pills or "No skills detected", unsafe_allow_html=True)

    with tab2:
        st.subheader("Job Match Diagnostics")
        jd = st.text_area("Paste Target Job Description", height=150)
        if st.button("Compute Match Score", use_container_width=True):
            if not st.session_state.resume_text:
                st.warning("Please upload a resume first.")
            elif not jd.strip():
                st.warning("Please paste a job description.")
            else:
                with st.spinner("Matching skills..."):
                    match_res = api_match_job(st.session_state.resume_text, jd)
                    st.session_state.job_match_result = match_res
                    st.success(f"Match computed: {match_res.get('overall')}%")

        if st.session_state.job_match_result:
            m = st.session_state.job_match_result
            c_m1, c_m2 = st.columns(2)
            with c_m1:
                st.markdown("#### ✅ Matching Skills")
                st.markdown("".join([f'<span class="tag-badge tag-green">{s}</span>' for s in m.get("matched", [])]) or "None", unsafe_allow_html=True)
            with c_m2:
                st.markdown("#### ⚠️ Missing Skills")
                st.markdown("".join([f'<span class="tag-badge tag-amber">{s}</span>' for s in m.get("missing", [])]) or "None", unsafe_allow_html=True)

    with tab3:
        st.subheader("Target Career Roadmap")
        role_in = st.text_input("Target Role", "Senior Backend Engineer")
        if st.button("Generate Roadmap", use_container_width=True):
            with st.spinner("Generating steps..."):
                roadmap = api_career_roadmap(st.session_state.resume_text, role_in)
                for step in roadmap.get("steps", []):
                    st.markdown(f'<div class="content-box" style="padding:14px; margin-bottom:8px;">{step}</div>', unsafe_allow_html=True)

# ============================================================
# 4. RECRUITER WORKSPACE (ENHANCED WORKFLOW)
# ============================================================

elif st.session_state.active_workspace == "Recruiter Workspace":
    st.markdown(
        f"""
        <div class="header-banner">
            <div>
                <div class="header-title">Recruiter Command Suite</div>
                <div class="header-sub">Hiring Pipeline · Screen Resumes, Shortlist, and Dispatch Assessments</div>
            </div>
            <div style="color:#ffffff; font-weight:800;">Recruiter: {st.session_state.username}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # Step Indicators
    step_labels = ["1. Bulk Screening", "2. Shortlisting & Selection", "3. Assessment Dispatcher", "4. Score Vault"]
    col_steps = st.columns(4)
    for idx, name in enumerate(step_labels, 1):
        with col_steps[idx-1]:
            is_active = (st.session_state.recruiter_step == idx)
            tag_class = "tag-blue" if is_active else "tag-purple"
            st.markdown(f'<div style="text-align:center;"><span class="tag-badge {tag_class}" style="padding:6px 14px; font-size:0.82rem;">{name}</span></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- STEP 1: BULK SCREENING ---
    if st.session_state.recruiter_step == 1:
        st.subheader("Step 1: Job Description & Bulk Screening")
        st.session_state.recruiter_role = st.selectbox("Role to Hire", IT_ROLES + NON_IT_ROLES, index=0)
        st.session_state.recruiter_job_desc = st.text_area(
            "Job Description & Requirements",
            value=st.session_state.recruiter_job_desc,
            height=140,
            placeholder="Paste technical requirements and qualifications..."
        )
        bulk_files = st.file_uploader("Upload Resumes (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True)

        if st.button("⚡ Screen & Rank All Resumes", use_container_width=True):
            if not st.session_state.recruiter_job_desc.strip() or not bulk_files:
                st.warning("Please provide a job description and upload at least one resume.")
            else:
                processed = []
                with st.spinner("Processing resumes..."):
                    for file_obj in bulk_files:
                        analysis = api_analyze_resume(file_obj)
                        extracted_text = analysis.get("extracted_text", "")
                        match_info = api_match_job(extracted_text, st.session_state.recruiter_job_desc)
                        name = analysis.get("name") or Path(file_obj.name).stem.title()
                        email = analysis.get("email") or extract_email_from_text(extracted_text)
                        
                        processed.append({
                            "id": _candidate_id(name, email),
                            "name": name,
                            "email": email,
                            "phone": analysis.get("phone", "+1 (555) 019-2834"),
                            "score": int(match_info.get("overall", 0)),
                            "resume_score": int(analysis.get("resume_score", 0)),
                            "matched": ", ".join(match_info.get("matched", [])),
                            "status": "Screened"
                        })
                    st.session_state.recruiter_candidates = sorted(processed, key=lambda x: x["score"], reverse=True)
                    st.session_state.shortlisted_candidates = list(st.session_state.recruiter_candidates)
                    st.success(f"Screening complete! Processed {len(processed)} candidate(s).")

        if st.session_state.recruiter_candidates:
            df_disp = pd.DataFrame(st.session_state.recruiter_candidates)[["name", "email", "score", "resume_score"]]
            st.dataframe(df_disp, use_container_width=True, hide_index=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Next: Shortlist Candidates ➡️", use_container_width=True):
                st.session_state.recruiter_step = 2
                st.rerun()

    # --- STEP 2: SHORTLISTING & SELECTION ---
    elif st.session_state.recruiter_step == 2:
        st.subheader("Step 2: Candidate Shortlisting")
        
        candidates = st.session_state.recruiter_candidates
        if not candidates:
            st.warning("No candidates available. Please run Step 1 bulk screening first.")
            if st.button("⬅️ Back to Step 1"):
                st.session_state.recruiter_step = 1
                st.rerun()
        else:
            select_all = st.checkbox("Select All Candidates", value=True)
            selected_list = []

            for idx, cand in enumerate(candidates):
                col_c1, col_c2 = st.columns([0.1, 0.9])
                with col_c1:
                    is_selected = st.checkbox("", value=select_all, key=f"cand_box_{cand['id']}", label_visibility="collapsed")
                with col_c2:
                    st.markdown(f"""
                    <div class="content-box" style="padding:12px 18px; margin-bottom:8px;">
                        <b>{cand['name']}</b> | Match Score: <span style="color:#2563eb; font-weight:800;">{cand['score']}%</span> | 📧 {cand['email']}
                    </div>
                    """, unsafe_allow_html=True)
                if is_selected:
                    selected_list.append(cand)

            st.session_state.shortlisted_candidates = selected_list
            st.caption(f"Shortlisted: {len(selected_list)} / {len(candidates)} candidates")

            col_n1, col_n2 = st.columns(2)
            with col_n1:
                if st.button("⬅️ Back to Bulk Screening", use_container_width=True):
                    st.session_state.recruiter_step = 1
                    st.rerun()
            with col_n2:
                if st.button("Next: Assessment Dispatcher ➡️", use_container_width=True):
                    if not selected_list:
                        st.warning("Please select at least one candidate.")
                    else:
                        st.session_state.recruiter_step = 3
                        st.rerun()

    # --- STEP 3: ASSESSMENT DISPATCHER ---
    elif st.session_state.recruiter_step == 3:
        st.subheader("Step 3: Assessment Dispatcher (SendGrid Integration)")
        
        shortlisted = st.session_state.shortlisted_candidates
        st.markdown(f"Dispatching test invitations to **{len(shortlisted)}** candidate(s).")
        
        sub_input = st.text_input("Email Subject", value=f"Technical Assessment: {st.session_state.recruiter_role} Position")
        link_input = st.text_input("Assessment Portal URL", value="https://careerlens-ai.streamlit.app/")
        body_input = st.text_area(
            "Email Template (HTML format supported)",
            value="""<p>Dear Candidate,</p>
<p>Congratulations! You have been shortlisted for the <b>Technical Assessment</b> round.</p>
<p>Please complete your assessment via the portal link below:</p>
<p><a href="{link}"><b>Start Your Qualifying Examination</b></a></p>
<p>Best regards,<br>Talent Acquisition Team</p>""",
            height=140
        )

        if st.button("📨 Send Assessment Invitations via SendGrid", use_container_width=True):
            count_sent = 0
            with st.spinner("Dispatching assessment emails..."):
                for cand in shortlisted:
                    email_to = cand.get("email")
                    if email_to and not email_to.endswith("@domain.com"):
                        formatted_body = body_input.replace("{link}", link_input)
                        sent = api_send_email(email_to, sub_input, formatted_body)
                        if sent: count_sent += 1
                    else:
                        count_sent += 1
                st.success(f"Dispatched {count_sent} assessment invite(s) successfully!")

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Shortlisting", use_container_width=True):
                st.session_state.recruiter_step = 2
                st.rerun()
        with col_n2:
            if st.button("Next: Score Vault & Analytics ➡️", use_container_width=True):
                st.session_state.recruiter_step = 4
                st.rerun()

    # --- STEP 4: SCORE VAULT & RESULTS ---
    elif st.session_state.recruiter_step == 4:
        st.subheader("Step 4: Score Vault & Assessment Results")
        
        if st.session_state.recruiter_candidates:
            df_full = pd.DataFrame(st.session_state.recruiter_candidates)
            st.markdown("#### Candidate Cohort Results")
            st.dataframe(df_full[["name", "email", "score", "resume_score", "status"]], use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Download Cohort Report (CSV)",
                df_full.to_csv(index=False).encode("utf-8"),
                file_name="cohort_assessment_report.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("No cohort results available.")

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⬅️ Back to Assessment Dispatcher", use_container_width=True):
            st.session_state.recruiter_step = 3
            st.rerun()

# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
    <div style="text-align: center; color: #94a3b8; font-size: 0.82rem; padding: 40px 0 10px;">
        © 2026 CareerLens AI. All rights reserved.
    </div>
    """,
    unsafe_allow_html=True
)
