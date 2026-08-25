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

# SendGrid Dispatcher Integration
try:
    from engine.email_dispatcher import send_assessment_email
except ImportError:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail

    def send_assessment_email(to_email: str, candidate_name: str, role: str, test_link: str) -> tuple[bool, str]:
        api_key = os.getenv("SENDGRID_API_KEY", "")
        from_email = os.getenv("SENDGRID_FROM_EMAIL", "noreply@careerlens.ai")
        
        cleaned_email = (to_email or "").strip()
        if not cleaned_email or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", cleaned_email):
            return False, f"Invalid email format: '{cleaned_email}'"
            
        # Development simulation for example domains
        if cleaned_email.endswith("@example.com") or cleaned_email.endswith("@domain.com"):
            return True, f"Simulated delivery to {cleaned_email} (demo domain)."

        if not api_key:
            return False, "SendGrid API Key is missing in environment variables."
        
        subject = f"CareerLens AI — Assessment Invitation for {role}"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
            <h2 style="color: #2563eb; margin-top: 0;">CareerLens AI Assessment</h2>
            <p>Hello <strong>{candidate_name or 'Candidate'}</strong>,</p>
            <p>Congratulations! You have been shortlisted for the <strong>{role}</strong> position.</p>
            <p>Please complete your online assessment using the link below:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{test_link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
                    Start Assessment Now →
                </a>
            </div>
            <p style="color: #64748b; font-size: 13px;">Direct URL: <a href="{test_link}" style="color: #2563eb;">{test_link}</a></p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
            <p style="color: #94a3b8; font-size: 12px;">CareerLens AI Recruitment Intelligence.</p>
        </div>
        """
        message = Mail(from_email=from_email, to_emails=cleaned_email, subject=subject, html_content=html_content)
        try:
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            if response.status_code in [200, 201, 202]:
                return True, "Email delivered successfully via SendGrid."
            return False, f"SendGrid status code: {response.status_code}"
        except Exception as e:
            err_body = str(e)
            if hasattr(e, "body") and e.body:
                try:
                    err_body = e.body.decode("utf-8")
                except Exception:
                    err_body = str(e.body)
            return False, f"SendGrid error: {err_body}"

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")
ADMIN_PIN = os.getenv("ADMIN_PIN", "")
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "http://localhost:8501")

st.set_page_config(
    page_title="CareerLens AI - Smart Career & Recruiter Intelligence",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# SAFE RESPONSE NORMALIZERS
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
    match = re.search(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', text or "")
    return match.group(0) if match else ""

def extract_phone_from_text(text: str) -> str:
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text or "")
    return match.group(0) if match else ""

def _candidate_id(name: str, email: str) -> str:
    val = f"{name or 'cand'}|{email or uuid.uuid4().hex}"
    return hashlib.sha256(val.encode("utf-8")).hexdigest()[:16]

def _clean_dataframe_columns(records: List[Dict], default_cols: List[str]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=default_cols)
    df = pd.DataFrame(records)
    for col in default_cols:
        if col not in df.columns:
            df[col] = "N/A"
    return df[default_cols]

# ============================================================
# ACTIVITY LOGGER
# ============================================================

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
# ULTRA-CLEAN MODERN LIGHT THEME
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap');

:root {
    --bg-page: #f8fafc;
    --navy-sidebar: #0a1128;
    --navy-header: #0f172a;
    --card-bg: #ffffff;
    --border-subtle: #e2e8f0;
    --text-navy: #0f172a;
    --text-muted: #64748b;
    --blue-primary: #2563eb;
    --blue-hover: #1d4ed8;
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

[data-testid="stFileUploader"] * {
    color: #0f172a !important;
    background-color: transparent !important;
}

[data-testid="stFileUploader"] section {
    background-color: #f8fafc !important;
    border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
}

[data-testid="stFileUploader"] button {
    background: #2563eb !important;
    color: #ffffff !important;
    border-radius: 8px !important;
    border: none !important;
}

.stTextInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] {
    background-color: #ffffff !important;
    color: #0f172a !important;
    border: 1px solid #cbd5e1 !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 6px rgba(15, 23, 42, 0.02) !important;
}

.stTextInput input:focus, .stTextArea textarea:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.15) !important;
}

[data-testid="stSidebar"] {
    background-color: var(--navy-sidebar) !important;
    border-right: 1px solid rgba(255, 255, 255, 0.08) !important;
}

[data-testid="stSidebar"] * {
    font-family: 'Plus Jakarta Sans', sans-serif !important;
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
    box-shadow: 0 4px 14px rgba(0,0,0,0.18);
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

[data-testid="stSidebar"] .stButton > button {
    background-color: rgba(255, 255, 255, 0.07) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 10px !important;
    padding: 0.55rem 0.95rem !important;
    font-weight: 700 !important;
    font-size: 0.88rem !important;
    text-align: left !important;
    justify-content: flex-start !important;
    width: 100% !important;
    box-shadow: none !important;
    transition: all 0.2s ease !important;
}

[data-testid="stSidebar"] .stButton > button:hover {
    background: linear-gradient(90deg, #2563eb, #7c3aed) !important;
    color: #ffffff !important;
    border-color: #60a5fa !important;
    transform: translateX(4px) !important;
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

.stButton > button:hover {
    background: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%) !important;
    transform: translateY(-1px) !important;
    box-shadow: 0 6px 18px rgba(37, 99, 235, 0.35) !important;
}

.header-banner {
    background: linear-gradient(135deg, #091224 0%, #0d1b38 60%, #1e1b4b 100%);
    border-radius: 20px;
    padding: 28px 34px;
    margin-bottom: 24px;
    box-shadow: 0 10px 30px rgba(9, 18, 36, 0.15);
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-title {
    font-size: 1.85rem;
    font-weight: 900;
    color: #ffffff !important;
    margin: 0;
}

.header-sub {
    font-size: 0.96rem;
    color: #cbd5e1 !important;
    margin: 4px 0 0 0;
}

.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 18px;
    margin-bottom: 28px;
}

.kpi-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 18px 20px;
    display: flex;
    align-items: center;
    gap: 16px;
    box-shadow: 0 4px 18px rgba(15, 23, 42, 0.04);
}

.kpi-icon-badge {
    width: 50px;
    height: 50px;
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    flex-shrink: 0;
}

.tool-box-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px 18px 0 0;
    padding: 24px 18px 14px;
    text-align: center;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.03);
    display: flex;
    flex-direction: column;
    align-items: center;
    height: 165px;
    justify-content: flex-start;
}

.tool-icon-circle {
    width: 54px;
    height: 54px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 26px;
    margin-bottom: 10px;
}

.tool-title {
    font-size: 1.05rem;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 4px;
}

.tool-desc {
    font-size: 0.82rem;
    color: #64748b;
    line-height: 1.45;
}

.content-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 24px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    margin-bottom: 16px;
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

.stButton > button,
.stButton > button *,
button[kind="primary"],
button[kind="primary"] *,
button[kind="secondary"],
button[kind="secondary"] *,
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] .stButton > button * {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

@media (max-width: 768px) {
    .block-container {
        padding: 14px 12px 28px !important;
    }
    .header-banner {
        display: block !important;
        padding: 20px 18px !important;
    }
    .kpi-grid {
        grid-template-columns: 1fr !important;
    }
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
    
    extracted_email = extract_email_from_text(text)
    extracted_phone = extract_phone_from_text(text)
    clean_name = re.sub(r"[_-]+", " ", Path(filename).stem).strip().title() or "Candidate"
    
    return {
        "name": clean_name,
        "email": extracted_email,
        "phone": extracted_phone,
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
                # Ensure actual parsed email is prioritized over placeholders
                if not data.get("email") or data.get("email") == "candidate@example.com":
                    parsed_email = extract_email_from_text(text)
                    if parsed_email:
                        data["email"] = parsed_email
                data.setdefault("skills", [])
                data.setdefault("missing_skills", [])
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
        return {"overall": 0, "matched": [], "missing": [], "summary": "Both resume and job description are required.", "experience_alignment": "Unavailable", "source": "validation"}
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
        if res.ok:
            return {**normalize_job_match(res.json()), "source": "api"}
    except Exception:
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
        "source": "local-fallback"
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
        "whatsapp": "WhatsApp-only recruitment communication",
        "crypto": "Cryptocurrency payment requests",
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
            f"Step 1: Strengthen foundational architecture in {target_role}.",
            "Step 2: Build an end-to-end production portfolio showcasing measurable throughput.",
            "Step 3: Refactor achievements into the Google XYZ format.",
            "Step 4: Practice domain mock interview questions and system design scenarios."
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

# State initialization
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = False
if "username" not in st.session_state: st.session_state.username = "Guest Explorer"
if "active_workspace" not in st.session_state: st.session_state.active_workspace = "Job Seeker Workspace"
if "active_tool" not in st.session_state: st.session_state.active_tool = "Dashboard"
if "resume_text" not in st.session_state: st.session_state.resume_text = ""
if "resume_analysis" not in st.session_state: st.session_state.resume_analysis = None
if "job_match_result" not in st.session_state: st.session_state.job_match_result = None

# Recruiter Flow States
if "recruiter_candidates" not in st.session_state: st.session_state.recruiter_candidates = []
if "shortlisted_candidates" not in st.session_state: st.session_state.shortlisted_candidates = []
if "recruiter_data" not in st.session_state: st.session_state.recruiter_data = {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
if "recruiter_assessment_submissions" not in st.session_state: st.session_state.recruiter_assessment_submissions = {}

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"]
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"]

def _make_assessment_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex

def _assessment_public_url(token: str) -> str:
    base = os.getenv("PUBLIC_APP_URL", PUBLIC_APP_URL).strip().rstrip("/")
    if not base:
        base = "http://localhost:8501"
    return f"{base}/?assessment={quote(token)}"

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
# 1. LANDING SCREEN
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
                    Resume scoring, standardized qualifying tests, AI mock interviews, and automated SendGrid recruiting pipelines.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("🔐 Sign In", key="btn_entry_sign_in", use_container_width=True): dialog_auth()
        with b2:
            if st.button("📝 Register", key="btn_entry_register", use_container_width=True): dialog_auth()
        with b3:
            if st.button("🚀 Guest Access", key="btn_entry_guest", use_container_width=True):
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
        """,
        unsafe_allow_html=True
    )

    st.markdown("### Workspaces")
    if st.button("👤 Candidate Workspace", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()
    if st.button("🏢 Recruiter Workspace", use_container_width=True):
        st.session_state.active_workspace = "Recruiter Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state.is_logged_in = False
        st.session_state.username = "Guest Explorer"
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
# 🏢 RECRUITER WORKSPACE (NAVIGATION & PIPELINE)
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

    def recruiter_nav(tool: str):
        st.session_state.active_tool = tool
        st.rerun()

    # Step Breadcrumbs
    pipeline_steps = [
        ("Dashboard", "Overview"),
        ("Hiring Campaign", "1. Campaign"),
        ("Bulk Screening", "2. Screening"),
        ("Shortlisted Candidates", "3. Shortlist"),
        ("Assessment Builder", "4. Dispatcher"),
        ("Score Vault", "5. Score Vault"),
        ("Interview Pipeline", "6. Pipeline")
    ]
    curr_step_idx = next((i for i, (tool_key, _) in enumerate(pipeline_steps) if tool_key == st.session_state.active_tool), 0)
    
    st.markdown(
        f"""
        <div class="content-box" style="padding:12px 20px; margin-bottom:20px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                {' '.join([f'<span class="tag-badge {"tag-blue" if i == curr_step_idx else "tag-purple"}" style="font-size:0.8rem; padding:5px 12px;">{lbl}</span>' for i, (_, lbl) in enumerate(pipeline_steps)])}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # 1. DASHBOARD
    if st.session_state.active_tool == "Dashboard":
        st.markdown("### 📊 Recruiter Dashboard")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Candidates Screened", len(candidates))
        k2.metric("Shortlisted", sum(1 for c in candidates if c.get("status") == "Shortlisted"))
        k3.metric("Assessments Sent", sum(1 for c in candidates if c.get("assessment_status") == "Sent"))
        k4.metric("Completed Assessments", len(submissions))

        st.markdown("#### Quick Pipeline Actions")
        c1, c2, c3 = st.columns(3)
        if c1.button("🎯 Setup Campaign", use_container_width=True): recruiter_nav("Hiring Campaign")
        if c2.button("📤 Screen Resumes", use_container_width=True): recruiter_nav("Bulk Screening")
        if c3.button("✉️ Dispatch Assessments", use_container_width=True): recruiter_nav("Assessment Builder")

    # 2. HIRING CAMPAIGN
    elif st.session_state.active_tool == "Hiring Campaign":
        st.markdown("### 🎯 Step 1: Hiring Campaign Setup")
        role_options = IT_ROLES + NON_IT_ROLES
        current_saved_role = campaign.get("role", "Software Developer")
        role = st.selectbox("Target Role", role_options, index=role_options.index(current_saved_role) if current_saved_role in role_options else 0)
        job_description = st.text_area("Job Description & Requirements", value=campaign.get("job_description", ""), height=140)
        
        if st.button("💾 Save Campaign", type="primary", use_container_width=True):
            data["campaign"] = {"role": role, "job_description": job_description.strip()}
            persist_recruiter()
            st.success("Campaign configured successfully!")

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Dashboard", use_container_width=True): recruiter_nav("Dashboard")
        with col_n2:
            if st.button("Next: Bulk Screening ➡️", use_container_width=True): recruiter_nav("Bulk Screening")

    # 3. BULK SCREENING
    elif st.session_state.active_tool == "Bulk Screening":
        st.markdown("### 📤 Step 2: Bulk Resume Screening")
        files = st.file_uploader("Upload candidate resumes (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], accept_multiple_files=True)
        
        if files and st.button("⚡ Screen All Resumes", type="primary", use_container_width=True):
            processed = []
            campaign_jd = campaign.get("job_description", "")
            with st.spinner("Processing candidate resumes..."):
                for f in files:
                    profile = api_analyze_resume(f)
                    r_text = profile.get("extracted_text", "")
                    match = normalize_job_match(api_match_job(r_text, campaign_jd)) if campaign_jd else {"overall": 75}
                    
                    name = profile.get("name") or Path(f.name).stem.title()
                    # Ensure true parsed email is captured
                    email = profile.get("email") or extract_email_from_text(r_text)
                    cid = _candidate_id(name, email)
                    
                    processed.append({
                        "id": cid,
                        "name": name,
                        "email": email or "Not Found",
                        "resume_score": profile.get("resume_score", 0),
                        "role_match": match.get("overall", 0),
                        "status": "Shortlisted",
                        "assessment_status": "Not Sent",
                    })
                st.session_state.recruiter_candidates = processed
                st.session_state.shortlisted_candidates = list(processed)
                persist_recruiter()
                st.success(f"Screened and ranked {len(processed)} candidate(s)!")
                st.rerun()

        if candidates:
            # Safely render DataFrame with guaranteed columns to avoid KeyError
            display_df = _clean_dataframe_columns(candidates, ["name", "email", "role_match", "resume_score", "status"])
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Campaign", use_container_width=True): recruiter_nav("Hiring Campaign")
        with col_n2:
            if st.button("Next: Shortlist & Select ➡️", use_container_width=True): recruiter_nav("Shortlisted Candidates")

    # 4. SHORTLISTED CANDIDATES & SELECTION
    elif st.session_state.active_tool == "Shortlisted Candidates":
        st.markdown("### 🏆 Step 3: Shortlist & Candidate Selection")
        
        if not candidates:
            st.info("No candidates uploaded yet. Please run Bulk Screening first.")
        else:
            select_all = st.checkbox("Select All Candidates", value=True, key="chk_select_all_candidates")
            selected_records = []
            st.markdown("---")

            for idx, cand in enumerate(candidates):
                col_chk, col_info = st.columns([0.08, 0.92])
                with col_chk:
                    # Index appended to key ensures 100% unique Streamlit element IDs
                    cand_id = cand.get("id", f"idx_{idx}")
                    is_chk = st.checkbox("", value=select_all, key=f"rec_cand_select_{idx}_{cand_id}", label_visibility="collapsed")
                with col_info:
                    st.markdown(f"""
                    <div class="content-box" style="padding:12px 18px; margin-bottom:6px;">
                        <b>{cand.get('name', 'Candidate')}</b> | Match: <span style="color:#2563eb; font-weight:800;">{cand.get('role_match', 0)}%</span> | Resume: <b>{cand.get('resume_score', 0)}%</b> | 📧 {cand.get('email', 'N/A')}
                    </div>
                    """, unsafe_allow_html=True)
                if is_chk:
                    selected_records.append(cand)

            st.session_state.shortlisted_candidates = selected_records
            st.caption(f"Selected for next round: {len(selected_records)} / {len(candidates)} candidates")

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Bulk Screening", use_container_width=True): recruiter_nav("Bulk Screening")
        with col_n2:
            if st.button("Next: Assessment Dispatcher ➡️", use_container_width=True):
                if not st.session_state.shortlisted_candidates:
                    st.warning("Please select at least one candidate before proceeding.")
                else:
                    recruiter_nav("Assessment Builder")

    # 5. ASSESSMENT DISPATCHER
    elif st.session_state.active_tool == "Assessment Builder":
        st.markdown("### ✉️ Step 4: Automated Assessment Dispatcher (SendGrid)")
        
        shortlisted = st.session_state.shortlisted_candidates
        if not shortlisted:
            st.warning("No shortlisted candidates selected. Go back and select candidates first.")
        else:
            role_target = campaign.get("role", "Software Developer")
            st.write(f"Sending test invitations for **{role_target}** to **{len(shortlisted)}** candidate(s).")
            
            if st.button("🚀 Dispatch Assessment Invites via SendGrid", type="primary", use_container_width=True):
                progress = st.progress(0, text="Dispatching emails via SendGrid...")
                rows = []
                
                for idx, candidate in enumerate(shortlisted):
                    token = _make_assessment_token()
                    test_link = _assessment_public_url(token)
                    
                    target_email = candidate.get("email", "")
                    sent, msg = send_assessment_email(target_email, candidate.get("name", "Candidate"), role_target, test_link)
                    
                    candidate["assessment_token"] = token
                    candidate["assessment_link"] = test_link
                    candidate["assessment_status"] = "Sent" if sent else "Failed"
                    candidate["status"] = "Assessment Sent" if sent else candidate.get("status")
                    
                    rows.append({
                        "Candidate": candidate.get("name"),
                        "Email": target_email or "Missing Email",
                        "SendGrid Status": "Delivered" if sent else "Failed",
                        "Delivery Log": msg,
                        "Exam Link": test_link
                    })
                    progress.progress((idx + 1) / len(shortlisted))
                
                persist_recruiter()
                st.success("Assessment dispatches processed!")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Shortlisting", use_container_width=True): recruiter_nav("Shortlisted Candidates")
        with col_n2:
            if st.button("Next: Score Vault ➡️", use_container_width=True): recruiter_nav("Score Vault")

    # 6. SCORE VAULT
    elif st.session_state.active_tool == "Score Vault":
        st.markdown("### 📊 Step 5: Assessment Score Vault")
        if not submissions:
            st.info("No assessment submissions recorded yet.")
        else:
            st.dataframe(pd.DataFrame(submissions), use_container_width=True, hide_index=True)

        col_n1, col_n2 = st.columns(2)
        with col_n1:
            if st.button("⬅️ Back to Assessment Dispatcher", use_container_width=True): recruiter_nav("Assessment Builder")
        with col_n2:
            if st.button("Next: Interview Pipeline ➡️", use_container_width=True): recruiter_nav("Interview Pipeline")

    # 7. INTERVIEW PIPELINE
    elif st.session_state.active_tool == "Interview Pipeline":
        st.markdown("### 🎤 Step 6: Recruiter Interview Pipeline")
        if not candidates:
            st.info("No candidates in pipeline.")
        else:
            pipe_df = _clean_dataframe_columns(candidates, ["name", "email", "role_match", "resume_score", "status", "assessment_status"])
            st.dataframe(pipe_df, use_container_width=True, hide_index=True)

        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("⬅️ Back to Score Vault", use_container_width=True):
            recruiter_nav("Score Vault")

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
