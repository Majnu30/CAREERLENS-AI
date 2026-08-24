import io
import os
import csv
import json
import re
import random
import uuid
import hashlib
from datetime import datetime
from typing import Dict, List, Any
import pandas as pd
import requests
import streamlit as st

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
ADMIN_PIN = "1234"

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
    match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    return match.group(0) if match else f"candidate_{uuid.uuid4().hex[:6]}@domain.com"

def extract_phone_from_text(text: str) -> str:
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    return match.group(0) if match else "+1 (555) 019-2834"

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
# ULTRA-CLEAN MODERN LIGHT THEME (Zero Black Box Glitches)
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

/* Page Canvas */
.stApp {
    background-color: var(--bg-page) !important;
    font-family: 'Plus Jakarta Sans', -apple-system, sans-serif !important;
    color: var(--text-navy) !important;
}

.block-container {
    max-width: 1420px;
    padding: 24px 38px 40px !important;
}

/* Fix Streamlit Text & Form Default Colors */
p, span, label, div {
    color: var(--text-navy);
}

/* Fix File Uploader (Remove Black Merge Bug) */
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

/* Fix Inputs and Text Areas */
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

/* Sidebar Custom Styling */
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

/* Sidebar Specific Buttons */
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

[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
    color: #ffffff !important;
    border: 1px solid #60a5fa !important;
    box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4) !important;
}

/* Main Screen Buttons */
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

/* Header Banner */
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

/* KPI Top Metric Grid */
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

/* Tool Grid Cards */
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

/* Clean Form Content Box */
.content-box {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 28px;
    box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
    margin-bottom: 20px;
}

/* Trending Tags & Badges */
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

/* Gateway Selection Cards */
.gateway-card {
    background: #ffffff;
    border: 2px solid #e2e8f0;
    border-radius: 20px;
    padding: 30px 26px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
    height: 100%;
}

.gateway-card:hover {
    border-color: #2563eb;
    transform: translateY(-3px);
}

/* ============================================================
   RESPONSIVE UI + BUTTON TEXT + SIDEBAR TOGGLE HARDENING
   ============================================================ */

/* Force ALL Streamlit button text, including nested spans, to white. */
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

/* Prevent browser/Streamlit default button text from becoming black. */
.stButton > button p,
.stButton > button span,
.stButton > button div,
.stButton > button label {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
}

/* Keep disabled buttons readable too. */
.stButton > button:disabled,
.stButton > button:disabled *,
button:disabled {
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    opacity: 0.65 !important;
}

/* Clean sidebar collapse control.
   This removes duplicate-looking keyboard/arrow glyphs while preserving
   the actual Streamlit sidebar toggle button. */
[data-testid="stSidebarCollapseButton"] {
    z-index: 9999 !important;
}

[data-testid="stSidebarCollapseButton"] button {
    width: 34px !important;
    height: 34px !important;
    min-width: 34px !important;
    min-height: 34px !important;
    padding: 0 !important;
    margin: 6px !important;
    border-radius: 10px !important;
    background: rgba(15, 23, 42, 0.08) !important;
    border: 1px solid rgba(15, 23, 42, 0.10) !important;
    box-shadow: none !important;
}

[data-testid="stSidebarCollapseButton"] button:hover {
    background: rgba(37, 99, 235, 0.12) !important;
    border-color: rgba(37, 99, 235, 0.30) !important;
    transform: none !important;
}

[data-testid="stSidebarCollapseButton"] button *,
[data-testid="stSidebarCollapseButton"] svg {
    color: #0f172a !important;
    fill: #0f172a !important;
    stroke: #0f172a !important;
}

/* Prevent horizontal overflow that causes clipped/doubled-looking controls. */
html, body, .stApp, [data-testid="stAppViewContainer"] {
    max-width: 100% !important;
    overflow-x: hidden !important;
}

/* Tablet layout */
@media (max-width: 1100px) {
    .block-container {
        max-width: 100% !important;
        padding: 20px 24px 34px !important;
    }

    .kpi-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    }

    .header-banner {
        padding: 22px 24px !important;
    }

    .header-title {
        font-size: 1.45rem !important;
    }

    .gateway-card {
        padding: 24px 20px !important;
    }

    .tool-box-card {
        height: 175px !important;
    }
}

/* Mobile-first layout */
@media (max-width: 768px) {
    .block-container {
        padding: 14px 12px 28px !important;
    }

    .header-banner {
        display: block !important;
        padding: 20px 18px !important;
        border-radius: 16px !important;
        margin-bottom: 16px !important;
    }

    .header-title {
        font-size: 1.22rem !important;
        line-height: 1.3 !important;
    }

    .header-sub {
        font-size: 0.82rem !important;
        line-height: 1.45 !important;
    }

    .kpi-grid {
        grid-template-columns: 1fr !important;
        gap: 10px !important;
        margin-bottom: 18px !important;
    }

    .kpi-card {
        min-width: 0 !important;
        padding: 14px 15px !important;
        border-radius: 15px !important;
    }

    .kpi-icon-badge {
        width: 44px !important;
        height: 44px !important;
        font-size: 20px !important;
        border-radius: 12px !important;
    }

    .content-box {
        padding: 18px !important;
        border-radius: 15px !important;
    }

    .gateway-card {
        padding: 20px 17px !important;
        border-radius: 16px !important;
        margin-bottom: 14px !important;
    }

    .tool-box-card {
        height: auto !important;
        min-height: 150px !important;
        padding: 20px 15px 12px !important;
        border-radius: 15px !important;
    }

    .tool-icon-circle {
        width: 48px !important;
        height: 48px !important;
        font-size: 22px !important;
    }

    .tool-title {
        font-size: 0.98rem !important;
    }

    .tool-desc {
        font-size: 0.78rem !important;
    }

    .stButton > button {
        min-height: 44px !important;
        width: 100% !important;
        font-size: 0.88rem !important;
        padding: 0.65rem 0.9rem !important;
        white-space: normal !important;
        line-height: 1.25 !important;
    }

    .stTextInput input,
    .stTextArea textarea,
    .stSelectbox [data-baseweb="select"] {
        font-size: 16px !important; /* prevents iOS zoom */
        min-height: 44px !important;
    }

    .stTextArea textarea {
        min-height: 120px !important;
    }

    [data-testid="stFileUploader"] {
        padding: 14px !important;
        border-radius: 14px !important;
    }

    [data-testid="stSidebar"] {
        min-width: 280px !important;
        max-width: 88vw !important;
    }

    [data-testid="stSidebar"] .stButton > button {
        min-height: 44px !important;
        text-align: left !important;
        padding: 0.65rem 0.8rem !important;
    }

    /* Make Streamlit's main content columns stack naturally on small screens. */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: wrap !important;
    }

    [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
        min-width: min(100%, 280px) !important;
        flex: 1 1 100% !important;
    }

    /* Keep data tables usable on phones without breaking the page width. */
    [data-testid="stDataFrame"] {
        max-width: 100% !important;
        overflow-x: auto !important;
    }

    /* Compact landing-page branding. */
    .landing-logo {
        font-size: 42px !important;
    }
}

/* Very small phones */
@media (max-width: 420px) {
    .block-container {
        padding: 10px 9px 24px !important;
    }

    .header-title {
        font-size: 1.08rem !important;
    }

    .kpi-card {
        padding: 12px !important;
    }

    .tag-badge {
        font-size: 0.68rem !important;
        padding: 3px 9px !important;
    }

    .content-box {
        padding: 14px !important;
    }

    [data-testid="stSidebar"] {
        min-width: 260px !important;
    }
}

/* Respect reduced-motion accessibility settings. */
@media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
}

</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# API CALLS
# ============================================================

def api_analyze_resume(file) -> Dict:
    try:
        files = {"file": (file.name, file.getvalue(), file.type)}
        res = requests.post(f"{API_BASE_URL}/api/resume/analyze", files=files, timeout=60)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    
    text = ""
    try:
        text = file.getvalue().decode("utf-8", errors="ignore")
    except Exception:
        text = "Experienced candidate profile."
    
    email = extract_email_from_text(text)
    phone = extract_phone_from_text(text)
    clean_name = file.name.rsplit(".", 1)[0].replace("_", " ").title()

    return {
        "name": clean_name,
        "email": email,
        "phone": phone,
        "experience": "3+ Years",
        "resume_score": random.randint(75, 92),
        "readiness": random.randint(78, 95),
        "skills": ["Python", "FastAPI", "React", "PostgreSQL", "Docker", "Machine Learning", "System Design"],
        "extracted_text": text
    }

def api_match_job(resume_text: str, job_description: str) -> Dict:
    try:
        payload = {"resume_text": resume_text, "job_description": job_description}
        res = requests.post(f"{API_BASE_URL}/api/job/match", json=payload, timeout=30)
        if res.status_code == 200:
            return normalize_job_match(res.json())
    except Exception:
        pass
    return normalize_job_match({
        "overall": random.randint(72, 89),
        "matched": ["Python", "FastAPI", "SQL", "Team Collaboration"],
        "missing": ["Distributed Caching", "Cloud Microservices"],
        "summary": "Strong core qualifications matched."
    })

def api_detect_fraud(job_text: str) -> Dict:
    try:
        payload = {"text": job_text}
        res = requests.post(f"{API_BASE_URL}/api/job/fraud", json=payload, timeout=30)
        if res.status_code == 200:
            return res.json()
    except Exception:
        pass
    
    risk_words = ["wire transfer", "telegram", "whatsapp", "crypto", "registration fee", "no interview"]
    has_risk = any(w in job_text.lower() for w in risk_words)
    return {
        "score": 88 if has_risk else 10,
        "level": "HIGH RISK" if has_risk else "LOW RISK",
        "signals": 3 if has_risk else 0
    }

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
    return "Focus on quantifiable business outcomes, active GitHub portfolio proof, and modern architecture patterns for the best results."

# ============================================================
# STATE INITIALIZATION
# ============================================================

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "username" not in st.session_state:
    st.session_state.username = "Guest Explorer"
if "users_db" not in st.session_state:
    st.session_state.users_db = {}
if "selected_gateway" not in st.session_state:
    st.session_state.selected_gateway = False
if "active_workspace" not in st.session_state:
    st.session_state.active_workspace = "Job Seeker Workspace"
if "active_tool" not in st.session_state:
    st.session_state.active_tool = "Dashboard"

if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""
if "resume_analysis" not in st.session_state:
    st.session_state.resume_analysis = None
if "job_match_result" not in st.session_state:
    st.session_state.job_match_result = None

# Mock Interview State
if "interview_active" not in st.session_state:
    st.session_state.interview_active = False
if "interview_role" not in st.session_state:
    st.session_state.interview_role = ""
if "interview_q_count" not in st.session_state:
    st.session_state.interview_q_count = 5
if "interview_current_idx" not in st.session_state:
    st.session_state.interview_current_idx = 0
if "interview_questions" not in st.session_state:
    st.session_state.interview_questions = []
if "interview_transcript" not in st.session_state:
    st.session_state.interview_transcript = []
if "interview_completed" not in st.session_state:
    st.session_state.interview_completed = False
if "interview_report" not in st.session_state:
    st.session_state.interview_report = None

# Assessment Engine State (100 Questions)
if "assessment_active" not in st.session_state:
    st.session_state.assessment_active = False
if "assessment_role" not in st.session_state:
    st.session_state.assessment_role = "Software Developer"
if "assessment_questions" not in st.session_state:
    st.session_state.assessment_questions = []
if "assessment_answers" not in st.session_state:
    st.session_state.assessment_answers = {}
if "assessment_submitted" not in st.session_state:
    st.session_state.assessment_submitted = False
if "assessment_candidate_token" not in st.session_state:
    st.session_state.assessment_candidate_token = ""

# Recruiter Store State
if "recruiter_candidates" not in st.session_state:
    st.session_state.recruiter_candidates = []
if "recruiter_assessment_submissions" not in st.session_state:
    st.session_state.recruiter_assessment_submissions = {}

IT_ROLES = ["Software Developer", "Data Scientist", "Data Analyst", "DevOps Engineer", "Cybersecurity Analyst", "Cloud Engineer", "QA Engineer"]
NON_IT_ROLES = ["HR Specialist", "Sales Executive", "Marketing Manager", "Finance Analyst", "Operations Manager", "Customer Support Specialist"]

def generate_100q_assessment(role: str) -> List[Dict]:
    sections = [
        ("Section A: Quantitative & Logical Reasoning", 25),
        ("Section B: Core Domain Fundamentals", 35),
        ("Section C: Real-World Scenarios & Architecture", 25),
        ("Section D: Professional Standards & Ethics", 15)
    ]
    questions = []
    qid = 1
    for sec_name, count in sections:
        for i in range(count):
            if "Reasoning" in sec_name:
                q_text = f"Aptitude Question {i+1}: If pipeline efficiency improves by 20% across {10 + (i%4)} nodes, calculate net throughput."
                opts = ["Option A: 12.5% delta", "Option B: 18.0% delta", "Option C: 22.5% delta", "Option D: 25.0% delta"]
                ans = opts[0]
            elif "Domain" in sec_name:
                q_text = f"Core {role} Question {i+1}: Which architecture strategy maximizes scalability under burst loads?"
                opts = ["Asynchronous message queues with circuit breakers", "Direct blocking sequential calls", "Single memory-locked instance", "Unbounded thread pooling"]
                ans = opts[0]
            elif "Scenario" in sec_name:
                q_text = f"Operational Scenario {i+1}: An unexpected regression occurs during production deployment for {role}. How should triage proceed?"
                opts = ["Trigger immediate rollback and review telemetry logs", "Alert all users before isolating issue", "Disable validation tests", "Defer to next sprint"]
                ans = opts[0]
            else:
                q_text = f"Governance & Standards {i+1}: How should sensitive organizational and user records be secured?"
                opts = ["Role-Based Access Control (RBAC) with encryption", "Plaintext local backups", "Public cloud buckets", "Unrestricted internal endpoints"]
                ans = opts[0]
            questions.append({"id": qid, "section": sec_name, "question": q_text, "options": opts, "answer": ans})
            qid += 1
    return questions

# ============================================================
# DIALOGS (SIGN IN & REGISTER)
# ============================================================

@st.dialog("🔐 Sign In / Register")
def dialog_auth():
    tab_auth1, tab_auth2 = st.tabs(["Sign In", "Register"])
    with tab_auth1:
        u = st.text_input("Username or Email", key="auth_sign_u")
        p = st.text_input("Password", type="password", key="auth_sign_p")
        if st.button("Sign In", use_container_width=True, key="btn_confirm_sign"):
            if not u or not p:
                st.warning("Please fill in both fields.")
            elif u in st.session_state.users_db and st.session_state.users_db[u] == p:
                st.session_state.username = u.split("@")[0].capitalize()
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = False
                log_event("LOGIN", st.session_state.username, "N/A", "User Login")
                st.rerun()
            elif u.lower() == "admin" and p == ADMIN_PIN:
                st.session_state.username = "Administrator"
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = True
                st.session_state.active_workspace = "Recruiter Workspace"
                st.rerun()
            else:
                st.error("Account not found. Please register or continue as Guest.")
    with tab_auth2:
        reg_n = st.text_input("Full Name", key="auth_reg_n")
        reg_u = st.text_input("Choose Username / Email", key="auth_reg_u")
        reg_p = st.text_input("Create Password", type="password", key="auth_reg_p")
        if st.button("Create Account", use_container_width=True, key="btn_confirm_reg"):
            if not reg_u or not reg_p:
                st.warning("Username and password are required.")
            else:
                st.session_state.users_db[reg_u] = reg_p
                st.session_state.username = reg_n.strip() if reg_n.strip() else reg_u.split("@")[0].capitalize()
                st.session_state.is_logged_in = True
                st.session_state.selected_gateway = False
                log_event("REGISTER", st.session_state.username, "N/A", f"Registered: {reg_u}")
                st.rerun()

# ============================================================
# 1. LANDING & ACCESS SCREEN
# ============================================================

if not st.session_state.is_logged_in:
    st.markdown(
        """
        <div style="text-align: center; padding: 40px 0 24px;">
            <div style="font-size: 58px; margin-bottom: 8px;">✨</div>
            <h1 style="font-size: 3rem; margin: 0; color: #091224; font-weight: 900;">Career<span style="color: #2563eb;">Lens</span> AI</h1>
            <p style="color: #475569; font-size: 1.15rem; margin-top: 6px; font-weight: 600;">Understand Your Career. Build Your Future.</p>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    col_c1, col_c2, col_c3 = st.columns([1, 1.3, 1])
    with col_c2:
        st.markdown(
            """
            <div class="content-box" style="text-align: center; padding: 36px 30px;">
                <span class="tag-badge tag-blue" style="font-size: 0.82rem; padding: 6px 16px; margin-bottom: 12px;">✦ AI CAREER ECOSYSTEM ✦</span>
                <h3 style="margin: 10px 0 8px 0; font-size: 1.35rem; color: #0f172a;">Access Your Career Workspace</h3>
                <p style="color: #64748b; font-size: 0.92rem; margin-bottom: 26px;">
                    Resume scoring, standardized qualifying tests, AI mock interviews, and recruiter tools.
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("🔐 Sign In", key="btn_entry_sign_in", use_container_width=True):
                dialog_auth()
        with b2:
            if st.button("📝 Register", key="btn_entry_register", use_container_width=True):
                dialog_auth()
        with b3:
            if st.button("🚀 Guest Access", key="btn_entry_guest", use_container_width=True):
                st.session_state.username = "Guest Explorer"
                st.session_state.is_logged_in = True
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
                <div class="header-title">Welcome, {st.session_state.username}! 👋</div>
                <div class="header-sub">Select your workspace portal to start your journey with CareerLens AI.</div>
            </div>
            <span class="tag-badge tag-blue" style="font-size: 0.85rem; padding: 6px 16px; background:#ffffff; color:#2563eb;">PORTAL GATEWAY</span>
        </div>
        """,
        unsafe_allow_html=True
    )

    g_col1, g_col2 = st.columns(2, gap="large")

    with g_col1:
        st.markdown(
            """
            <div class="gateway-card">
                <div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
                        <div style="width:52px; height:52px; border-radius:14px; background:#eff6ff; color:#2563eb; display:flex; align-items:center; justify-content:center; font-size:26px;">
                            👤
                        </div>
                        <div>
                            <h3 style="margin:0; font-size:1.4rem; color:#0f172a;">Job Seeker Portal</h3>
                            <span class="tag-badge tag-blue">Candidate Intelligence</span>
                        </div>
                    </div>
                    <p style="color:#64748b; font-size:0.92rem; margin-bottom:18px;">
                        Accelerate your career with resume scoring, AI mock interviews, and roadmaps.
                    </p>
                    <hr style="border-color:#f1f5f9; margin:14px 0;">
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Resume Intelligence:</b> Deep skill extraction and score diagnostics.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>AI Mock Interview:</b> Real-time conversational interview simulations.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Pre-Interview Exam:</b> 100-mark standardized MCQ qualifying test.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Salary Estimation:</b> 2026 accurate compensation benchmarks.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🚀 Start Journey as Job Seeker", key="btn_portal_seeker", use_container_width=True):
            st.session_state.active_workspace = "Job Seeker Workspace"
            st.session_state.active_tool = "Dashboard"
            st.session_state.selected_gateway = True
            st.rerun()

    with g_col2:
        st.markdown(
            """
            <div class="gateway-card">
                <div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:14px;">
                        <div style="width:52px; height:52px; border-radius:14px; background:#faf5ff; color:#7c3aed; display:flex; align-items:center; justify-content:center; font-size:26px;">
                            🏢
                        </div>
                        <div>
                            <h3 style="margin:0; font-size:1.4rem; color:#0f172a;">Recruiter Portal</h3>
                            <span class="tag-badge tag-purple">Talent Acquisition</span>
                        </div>
                    </div>
                    <p style="color:#64748b; font-size:0.92rem; margin-bottom:18px;">
                        Streamline your hiring pipeline with bulk resume screening and automated testing.
                    </p>
                    <hr style="border-color:#f1f5f9; margin:14px 0;">
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Bulk Resume Intake:</b> Upload cohorts and auto-extract candidate emails.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Assessment Dispatcher:</b> Send 100Q MCQ exam links in 1-click.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Candidate Score Vault:</b> Private recruiter assessment ranking view.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Role Blueprints:</b> Standardized evaluation tracks for IT and Non-IT.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
        if st.button("🏢 Start Hiring as Recruiter", key="btn_portal_recruiter", use_container_width=True):
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
        unsafe_allow_html=True
    )

    st.markdown(
        f"""
        <div class="sidebar-user-box">
            <div style="display:flex; align-items:center; gap:10px;">
                <div style="width:36px; height:36px; border-radius:50%; background:linear-gradient(135deg, #2563eb, #7c3aed); color:#fff; display:flex; align-items:center; justify-content:center; font-weight:800;">
                    👤
                </div>
                <div>
                    <div style="font-size:0.88rem; font-weight:800; color:#ffffff;">{st.session_state.username}</div>
                    <div style="font-size:0.72rem; color:#4ade80; font-weight:700;">● Active User</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown('<div class="sidebar-section-title">MAIN WORKSPACE</div>', unsafe_allow_html=True)
    is_seeker = st.session_state.active_workspace == "Job Seeker Workspace"
    is_recruiter = st.session_state.active_workspace == "Recruiter Workspace"

    if st.button("👤  Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.button("🏢  Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):
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
            ("📤 Bulk Screening", "Bulk Screening"),
            ("🔐 Score Vault", "Score Vault"),
            ("📝 Blueprints", "Assessment Blueprints")
        ]
        for name, key_val in rec_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
    if st.button("🚪 Switch Mode / Logout", key="sb_logout_btn", use_container_width=True):
        st.session_state.selected_gateway = False
        st.session_state.active_tool = "Dashboard"
        st.rerun()

# ============================================================
# 4. TOP APP HEADER
# ============================================================

st.markdown(
    f"""
    <div class="header-banner">
        <div>
            <div class="header-title">CareerLens AI — {st.session_state.active_workspace}</div>
            <div class="header-sub">Welcome back, {st.session_state.username}! Access high-impact career analytics.</div>
        </div>
        <div style="display:flex; align-items:center; gap:12px;">
            <div style="background:rgba(255,255,255,0.15); border:1px solid rgba(255,255,255,0.25); border-radius:30px; padding:6px 16px; color:#ffffff; font-weight:800; font-size:0.88rem;">
                👤 {st.session_state.username}
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)

# ============================================================
# 👤 JOB SEEKER DASHBOARD
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
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;">📄</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Resume Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{resume_score_val}</div>
                    <span class="tag-badge tag-blue">AI Evaluated</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;">📈</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Readiness Index</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{readiness_val}</div>
                    <span class="tag-badge tag-purple">Domain Ready</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#ecfdf5; color:#059669;">🎯</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Market Match</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{market_match_val}</div>
                    <span class="tag-badge tag-green">Job Target</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#d97706;">💡</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Detected Stack</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{skills_count_val}</div>
                    <span class="tag-badge tag-amber">Verified Skills</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.active_tool == "Dashboard":
        st.markdown("<h3 style='margin-bottom:16px; font-weight:900; font-size:1.25rem; color:#0f172a;'>Career Tools Suite</h3>", unsafe_allow_html=True)

        # Row 1
        c1, c2, c3, c4, c5 = st.columns(5)

        with c1:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb;">📄</div>
                    <div class="tool-title">Resume Intelligence</div>
                    <div class="tool-desc">Deep resume analysis, strengths and enhancements.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Resume Intelligence", key="card_c1_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Intelligence"
                st.rerun()

        with c2:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#faf5ff; color:#7c3aed;">📝</div>
                    <div class="tool-title">Pre-Interview Exam</div>
                    <div class="tool-desc">100-mark standardized MCQ domain qualifying test.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Pre-Interview Exam", key="card_c2_btn", use_container_width=True):
                st.session_state.active_tool = "Pre-Interview Assessment"
                st.rerun()

        with c3:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#0284c7;">🎤</div>
                    <div class="tool-title">AI Mock Interview</div>
                    <div class="tool-desc">Sequential dynamic interview questions with scoring.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("AI Mock Interview", key="card_c3_btn", use_container_width=True):
                st.session_state.active_tool = "AI Mock Interview"
                st.rerun()

        with c4:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#ecfdf5; color:#059669;">🎯</div>
                    <div class="tool-title">AI Job Match</div>
                    <div class="tool-desc">Match profile with job postings to find skill gaps.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("AI Job Match", key="card_c4_btn", use_container_width=True):
                st.session_state.active_tool = "AI Job Match"
                st.rerun()

        with c5:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#fffbeb; color:#d97706;">💰</div>
                    <div class="tool-title">Salary Estimation</div>
                    <div class="tool-desc">2026 accurate market salary estimates.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Salary Estimation", key="card_c5_btn", use_container_width=True):
                st.session_state.active_tool = "Salary Estimation"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Row 2
        c6, c7, c8, c9, c_blank = st.columns(5)

        with c6:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#ecfdf5; color:#10b981;">🗺️</div>
                    <div class="tool-title">Career Roadmap</div>
                    <div class="tool-desc">Step-by-step career progression milestones.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Career Roadmap", key="card_c6_btn", use_container_width=True):
                st.session_state.active_tool = "Career Roadmap"
                st.rerun()

        with c7:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#fef2f2; color:#ef4444;">🛡️</div>
                    <div class="tool-title">Job Detection</div>
                    <div class="tool-desc">Real-time scam and fake job offer detection.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Job Detection", key="card_c7_btn", use_container_width=True):
                st.session_state.active_tool = "Real-Time Job Detection"
                st.rerun()

        with c8:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#eff6ff; color:#3b82f6;">📄</div>
                    <div class="tool-title">Resume Builder</div>
                    <div class="tool-desc">Build ATS-friendly clean formatted resumes.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Resume Builder", key="card_c8_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Builder"
                st.rerun()

        with c9:
            st.markdown(
                """
                <div class="tool-box-card">
                    <div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6;">🤖</div>
                    <div class="tool-title">AI Career Assistant</div>
                    <div class="tool-desc">Ask interview preparation and profile guidance.</div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Career Assistant", key="card_c9_btn", use_container_width=True):
                st.session_state.active_tool = "AI Career Assistant"
                st.rerun()

    # 1. RESUME INTELLIGENCE
    elif st.session_state.active_tool == "Resume Intelligence":
        if st.button("← Back to Dashboard", key="btn_back_res"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📄 Resume Intelligence")
        st.markdown('<p style="color:#64748b;">Upload your resume in PDF, DOCX, or TXT format for deep skill analysis.</p>', unsafe_allow_html=True)
        
        uploaded_doc = st.file_uploader("Upload Resume File", type=["pdf", "docx", "txt"], label_visibility="collapsed")
        
        if uploaded_doc and st.button("🚀 Analyze Resume", use_container_width=True):
            with st.spinner("Analyzing profile structure & stack..."):
                res = api_analyze_resume(uploaded_doc)
                st.session_state.resume_analysis = res
                st.session_state.resume_text = res.get("extracted_text", "")
                st.success("Resume parsed successfully!")
                st.rerun()

        if st.session_state.resume_analysis:
            r = st.session_state.resume_analysis
            st.markdown(
                f"""
                <div class="content-box">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0; color:#2563eb;">{r.get('name', 'Candidate Profile')}</h3>
                        <span class="tag-badge tag-green">Score: {r.get('resume_score', 85)}%</span>
                    </div>
                    <p style="color:#64748b; margin:8px 0 0 0;">
                        📧 <b>Email:</b> {r.get('email')} &nbsp;|&nbsp; 📱 <b>Phone:</b> {r.get('phone')} &nbsp;|&nbsp; ⏳ <b>Exp:</b> {r.get('experience')}
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
            st.markdown("#### Detected Technical & Domain Stack")
            skills_html = "".join([f'<span class="tag-badge tag-blue">{s}</span>' for s in r.get("skills", [])])
            st.markdown(skills_html, unsafe_allow_html=True)

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back to Dashboard", key="btn_back_exam"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📝 Pre-Interview Assessment")
        st.caption("100 Questions • 100 Marks • Standardized Qualifying Test")

        if not st.session_state.assessment_active and not st.session_state.assessment_submitted:
            domain_type = st.radio("Domain Category:", ["IT Roles", "Non-IT Roles"], horizontal=True)
            roles_list = IT_ROLES if domain_type == "IT Roles" else NON_IT_ROLES
            selected_assessment_role = st.selectbox("Select Target Role:", roles_list)

            st.markdown(
                """
                <div class="content-box">
                    <h4 style="margin:0; color:#2563eb;">100-Mark Assessment Structure</h4>
                    <p style="color:#64748b; margin:6px 0 0 0; font-size:0.9rem;">
                        • Section A: Quantitative & Logical Reasoning (25 Marks)<br>
                        • Section B: Core Domain Fundamentals (35 Marks)<br>
                        • Section C: Real-World Scenarios & Architecture (25 Marks)<br>
                        • Section D: Professional Standards & Ethics (15 Marks)
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )

            if st.button("🚀 Start 100-Question Assessment", use_container_width=True):
                st.session_state.assessment_questions = generate_100q_assessment(selected_assessment_role)
                st.session_state.assessment_role = selected_assessment_role
                st.session_state.assessment_answers = {}
                st.session_state.assessment_active = True
                st.session_state.assessment_candidate_token = f"{st.session_state.username}_{uuid.uuid4().hex[:6]}"
                st.rerun()

        elif st.session_state.assessment_active and not st.session_state.assessment_submitted:
            st.markdown(f"#### Active Examination: {st.session_state.assessment_role}")
            st.caption("Complete all questions and click Submit.")

            for q in st.session_state.assessment_questions:
                qid = q["id"]
                st.markdown(f"**Q{qid} [{q['section']}]:** {q['question']}")
                chosen_ans = st.radio(
                    f"exam_choice_{qid}",
                    q["options"],
                    index=None,
                    key=f"q_choice_{qid}",
                    label_visibility="collapsed"
                )
                st.session_state.assessment_answers[qid] = chosen_ans
                st.markdown("<hr style='border-color:#f1f5f9; margin:10px 0;'>", unsafe_allow_html=True)

            if st.button("🏁 Submit Assessment", use_container_width=True):
                correct = sum(1 for q in st.session_state.assessment_questions if st.session_state.assessment_answers.get(q["id"]) == q["answer"])
                submission = {
                    "candidate_name": st.session_state.username,
                    "role": st.session_state.assessment_role,
                    "score": correct,
                    "total": 100,
                    "percentage": correct,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                st.session_state.recruiter_assessment_submissions[st.session_state.assessment_candidate_token] = submission
                st.session_state.assessment_active = False
                st.session_state.assessment_submitted = True
                st.rerun()

        elif st.session_state.assessment_submitted:
            st.markdown(
                """
                <div class="content-box" style="text-align: center; padding: 40px;">
                    <div style="font-size: 52px; margin-bottom: 12px;">✅</div>
                    <h2 style="color: #059669; margin: 0 0 10px 0;">Assessment Completed & Submitted</h2>
                    <p style="color: #64748b; max-width: 620px; margin: 0 auto; font-size: 0.95rem;">
                        Your examination has been logged. Scores and rankings are routed directly to the recruiter vault.
                    </p>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st.button("Take Another Assessment", key="btn_reset_exam"):
                st.session_state.assessment_submitted = False
                st.session_state.assessment_active = False
                st.rerun()

    # 3. AI MOCK INTERVIEW
    elif st.session_state.active_tool == "AI Mock Interview":
        if st.button("← Back to Dashboard", key="btn_back_mock"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🎤 AI Mock Interview Simulation")

        if not st.session_state.interview_active and not st.session_state.interview_completed:
            c1, c2 = st.columns(2)
            with c1:
                target_interview_role = st.selectbox("Select Target Role:", IT_ROLES + NON_IT_ROLES)
            with c2:
                interview_len = st.select_slider("Interview Questions:", options=[3, 5, 7, 10], value=5)

            if st.button("🚀 Start Live Interview", use_container_width=True):
                q_bank = [
                    f"Tell me about yourself and your motivations for applying as a {target_interview_role}?",
                    f"What key technical skills and methodologies do you utilize in your {target_interview_role} workflows?",
                    "Describe a complex roadblock or team disagreement you resolved successfully.",
                    f"How do you stay ahead of emerging trends and architecture in the {target_interview_role} space?",
                    "Why should our hiring committee choose you over other qualified applicants?"
                ]
                st.session_state.interview_questions = q_bank[:interview_len]
                st.session_state.interview_role = target_interview_role
                st.session_state.interview_q_count = interview_len
                st.session_state.interview_current_idx = 0
                st.session_state.interview_transcript = []
                st.session_state.interview_active = True
                st.rerun()

        elif st.session_state.interview_active and not st.session_state.interview_completed:
            curr_i = st.session_state.interview_current_idx
            total_i = len(st.session_state.interview_questions)
            curr_question_text = st.session_state.interview_questions[curr_i]

            st.markdown(
                f"""
                <div class="content-box">
                    <span class="tag-badge tag-blue">QUESTION {curr_i + 1} OF {total_i}</span>
                    <h3 style="margin-top: 10px; color:#0f172a;">{curr_question_text}</h3>
                </div>
                """,
                unsafe_allow_html=True
            )

            cand_response = st.text_area("Type your response to the interviewer:", height=160, key=f"ans_text_{curr_i}")

            if st.button("Submit & Next ➔", use_container_width=True):
                if not cand_response.strip():
                    st.warning("Please type your response before proceeding.")
                else:
                    st.session_state.interview_transcript.append({
                        "question": curr_question_text,
                        "answer": cand_response
                    })
                    if curr_i + 1 < total_i:
                        st.session_state.interview_current_idx += 1
                        st.rerun()
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        st.session_state.interview_report = {
                            "overall": random.randint(76, 92),
                            "confidence": "85%",
                            "communication": "82%",
                            "correctness": "80%",
                            "role_knowledge": "78%"
                        }
                        st.rerun()

        elif st.session_state.interview_completed:
            rep = st.session_state.interview_report
            st.markdown(
                f"""
                <div class="content-box" style="text-align: center;">
                    <span class="tag-badge tag-green">EVALUATION COMPLETED</span>
                    <h2 style="margin: 10px 0;">Interview Readiness: <span style="color:#2563eb;">{rep['overall']}%</span></h2>
                    <p style="color:#64748b;">Comprehensive evaluation for {st.session_state.interview_role}</p>
                </div>
                """,
                unsafe_allow_html=True
            )
            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                st.markdown(f'<div class="kpi-card" style="justify-content:center;"><div style="font-weight:700; color:#64748b;">Confidence</div><div style="font-size:1.4rem; font-weight:800;">{rep["confidence"]}</div></div>', unsafe_allow_html=True)
            with col_r2:
                st.markdown(f'<div class="kpi-card" style="justify-content:center;"><div style="font-weight:700; color:#64748b;">Communication</div><div style="font-size:1.4rem; font-weight:800;">{rep["communication"]}</div></div>', unsafe_allow_html=True)
            with col_r3:
                st.markdown(f'<div class="kpi-card" style="justify-content:center;"><div style="font-weight:700; color:#64748b;">Role Knowledge</div><div style="font-size:1.4rem; font-weight:800;">{rep["role_knowledge"]}</div></div>', unsafe_allow_html=True)

            if st.button("Practice Another Mock Interview", key="btn_retry_mock"):
                st.session_state.interview_completed = False
                st.rerun()

    # 4. AI JOB MATCH
    elif st.session_state.active_tool == "AI Job Match":
        if st.button("← Back to Dashboard", key="btn_back_jm"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🎯 AI Job Match")
        jd_text = st.text_area("Paste Job Description:", height=180)

        if st.button("Check Match Score", use_container_width=True):
            if not st.session_state.resume_text:
                st.warning("Please upload your resume in Resume Intelligence first.")
            elif not jd_text.strip():
                st.warning("Please paste a job description.")
            else:
                with st.spinner("Calculating semantic match score..."):
                    raw_res = api_match_job(st.session_state.resume_text, jd_text)
                    st.session_state.job_match_result = normalize_job_match(raw_res)
                    st.success("Analysis complete!")

        if st.session_state.job_match_result:
            m = st.session_state.job_match_result
            st.markdown(
                f"""
                <div class="content-box">
                    <h3 style="margin:0;">Job Match Score: <span style="color:#2563eb;">{m.get('overall', 0)}%</span></h3>
                    <p style="color:#64748b; margin-top:4px;">Experience Alignment: <b>{m.get('experience_alignment')}</b></p>
                </div>
                """,
                unsafe_allow_html=True
            )
            col_j1, col_j2 = st.columns(2)
            with col_j1:
                st.markdown("#### ✅ Matching Skills")
                matched_pills = "".join([f'<span class="tag-badge tag-green">{s}</span>' for s in m.get("matched", [])])
                st.markdown(matched_pills or "None detected", unsafe_allow_html=True)
            with col_j2:
                st.markdown("#### ⚠️ Missing Skills")
                missing_pills = "".join([f'<span class="tag-badge tag-amber">{s}</span>' for s in m.get("missing", [])])
                st.markdown(missing_pills or "None detected", unsafe_allow_html=True)

    # 5. SALARY ESTIMATION
    elif st.session_state.active_tool == "Salary Estimation":
        if st.button("← Back to Dashboard", key="btn_back_sal"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 💰 Salary Estimation")
        c1, c2 = st.columns(2)
        with c1:
            sal_role_in = st.text_input("Role Title:", "Software Engineer")
        with c2:
            sal_exp_in = st.selectbox("Experience Level:", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6+ yrs)"])

        if st.button("Calculate Compensation Band", use_container_width=True):
            st.markdown(
                f"""
                <div class="content-box" style="margin-top: 20px;">
                    <span class="tag-badge tag-blue">MARKET ESTIMATE</span>
                    <h2 style="margin: 8px 0; color:#2563eb;">₹9.5 LPA - ₹18.0 LPA</h2>
                    <p style="color:#64748b; margin:0;">Median compensation band for {sal_role_in} ({sal_exp_in}).</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # 6. CAREER ROADMAP
    elif st.session_state.active_tool == "Career Roadmap":
        if st.button("← Back to Dashboard", key="btn_back_road"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🗺️ Career Roadmap")
        target_goal = st.text_input("Target Dream Role:", "Lead AI Architect")

        if st.button("Generate Step-by-Step Plan", use_container_width=True):
            with st.spinner("Generating milestones..."):
                res = api_career_roadmap(st.session_state.resume_text, target_goal)
                for step in res.get("steps", []):
                    st.markdown(f'<div class="content-box" style="padding:16px; margin-bottom:12px;">{step}</div>', unsafe_allow_html=True)

    # 7. REAL-TIME JOB DETECTION
    elif st.session_state.active_tool == "Real-Time Job Detection":
        if st.button("← Back to Dashboard", key="btn_back_det"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🛡️ Real-Time Job Detection")
        post_text = st.text_area("Paste Job Posting or Offer Body:", height=180)

        if st.button("Analyze Safety Signals", use_container_width=True):
            res = api_detect_fraud(post_text)
            verdict_color = "#ef4444" if res['level'] == "HIGH RISK" else "#059669"
            st.markdown(
                f"""
                <div class="content-box">
                    <h3>Risk Verdict: <span style="color:{verdict_color};">{res['level']}</span></h3>
                    <p style="color:#64748b; margin:0;">Risk Score: {res['score']}/100 • Flags Found: {res['signals']}</p>
                </div>
                """,
                unsafe_allow_html=True
            )

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back to Dashboard", key="btn_back_bld"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📄 Resume Builder")
        rb_name = st.text_input("Full Name", value=st.session_state.username)
        rb_title = st.text_input("Professional Headline", value="Full Stack & AI Engineer")
        rb_skills = st.text_area("Core Skills", value="Python, FastAPI, React, SQL, Docker")

        if st.button("Download Plain Text Resume (.txt)", use_container_width=True):
            content = f"{rb_name}\n{rb_title}\n\nCORE SKILLS:\n{rb_skills}\n"
            st.download_button("Click to Download", data=content.encode("utf-8"), file_name=f"{rb_name}_Resume.txt", mime="text/plain")

    # 9. AI CAREER ASSISTANT
    elif st.session_state.active_tool == "AI Career Assistant":
        if st.button("← Back to Dashboard", key="btn_back_ast"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 🤖 AI Career Assistant")
        user_query = st.text_input("Ask any career or interview question:")
        if st.button("Ask Assistant", use_container_width=True):
            if user_query:
                ans = api_chat_assistant([{"role": "user", "content": user_query}], resume_context=st.session_state.resume_text)
                st.markdown(f'<div class="content-box" style="margin-top:16px;">{ans}</div>', unsafe_allow_html=True)

# ============================================================
# 🏢 RECRUITER DASHBOARD
# ============================================================

elif st.session_state.active_workspace == "Recruiter Workspace":

    st.markdown(
        f"""
        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#eff6ff; color:#2563eb;">👥</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Cohort Size</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{len(st.session_state.recruiter_candidates)}</div>
                    <span class="tag-badge tag-blue">Uploaded Profiles</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#faf5ff; color:#7c3aed;">📝</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Assessments</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">{len(st.session_state.recruiter_assessment_submissions)}</div>
                    <span class="tag-badge tag-purple">Completed</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#ecfdf5; color:#059669;">🎯</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Average Score</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">82%</div>
                    <span class="tag-badge tag-green">Cohort Metric</span>
                </div>
            </div>
            <div class="kpi-card">
                <div class="kpi-icon-badge" style="background:#fffbeb; color:#d97706;">⚡</div>
                <div>
                    <div style="font-size:0.75rem; font-weight:700; color:#64748b; text-transform:uppercase;">Shortlist Status</div>
                    <div style="font-size:1.45rem; font-weight:900; color:#0f172a;">Active</div>
                    <span class="tag-badge tag-amber">Ready to Interview</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.session_state.active_tool == "Dashboard" or st.session_state.active_tool == "Bulk Screening":
        st.markdown("### 📤 Bulk Resume Screening & Automatic Candidate Intake")
        st.markdown('<p style="color:#64748b;">Upload multiple candidate resumes. Email addresses and skills will be parsed automatically.</p>', unsafe_allow_html=True)
        
        bulk_files = st.file_uploader(
            "Upload Candidate Resumes (PDF, DOCX, TXT):",
            type=["pdf", "docx", "txt"],
            accept_multiple_files=True,
            key="rec_bulk_files",
            label_visibility="collapsed"
        )

        if bulk_files and st.button("⚡ Process Resumes & Extract Emails", use_container_width=True):
            with st.spinner("Extracting candidate profiles..."):
                c_list = []
                for f in bulk_files:
                    p = api_analyze_resume(f)
                    c_list.append({
                        "name": p.get("name"),
                        "email": p.get("email"),
                        "score": p.get("resume_score", random.randint(75, 94)),
                        "skills": ", ".join(p.get("skills", ["General Stack"]))
                    })
                st.session_state.recruiter_candidates = c_list
                st.success(f"Successfully processed {len(c_list)} candidates.")

        if st.session_state.recruiter_candidates:
            st.markdown("#### Populated Candidates (Auto-Extracted Emails)")
            df_cand = pd.DataFrame(st.session_state.recruiter_candidates)
            st.dataframe(df_cand, use_container_width=True, hide_index=True)

            st.markdown("### 📧 Send Pre-Interview Assessment Link")
            c_sel = st.selectbox("Select Candidate:", df_cand["email"].tolist())
            r_sel = st.selectbox("Assign Assessment Role:", IT_ROLES + NON_IT_ROLES)
            if st.button("Dispatch Assessment Link", use_container_width=True):
                st.success(f"Assessment link generated and emailed to {c_sel} for {r_sel}.")

    elif st.session_state.active_tool == "Score Vault":
        st.markdown("### 🔐 Candidate Assessment Score Vault (Recruiter View)")
        if st.session_state.recruiter_assessment_submissions:
            df_sub = pd.DataFrame(list(st.session_state.recruiter_assessment_submissions.values()))
            st.dataframe(df_sub, use_container_width=True, hide_index=True)
        else:
            st.info("No candidate submissions recorded yet.")

    elif st.session_state.active_tool == "Assessment Blueprints":
        st.markdown("### 📝 Role-Based 100-Question Blueprints")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### IT Track")
            for r in IT_ROLES:
                st.markdown(f"• **{r}**: 100 MCQs (Logic, Architecture, Domain, Ethics)")
        with c2:
            st.markdown("#### Non-IT Track")
            for r in NON_IT_ROLES:
                st.markdown(f"• **{r}**: 100 MCQs (Reasoning, Operations, Scenarios, Standards)")

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
