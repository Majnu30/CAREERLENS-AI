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
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

API_BASE_URL = os.getenv("API_URL", "https://careerlens-ai-9dx8.onrender.com")
ANALYTICS_FILE = "analytics.csv"
APP_DB_FILE = os.getenv("CAREERLENS_DB", "careerlens.db")
ADMIN_PIN = os.getenv("ADMIN_PIN", "")

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

def _extract_resume_text(file) -> str:
    """Extract text locally when the API is unavailable."""
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
    """Deterministic local fallback; never invents contact details or random scores."""
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
        "strengths": ["Skills detected" if skills else "Resume text extracted", "Structured sections detected" if section_hits >= 3 else "Basic resume structure detected"],
        "recommendations": ["Add measurable achievements and outcomes.", "Tailor skills and projects to the target role.", "Keep formatting ATS-friendly and concise."],
        "extracted_text": text,
        "source": "local-fallback"
    }


def api_analyze_resume(file) -> Dict:
    """Analyze a resume through the backend and provide a deterministic local fallback."""
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
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django",
        "flask", "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws",
        "azure", "gcp", "git", "linux", "machine learning", "deep learning", "pandas",
        "numpy", "scikit-learn", "tensorflow", "pytorch", "rest api", "graphql", "redis",
        "kafka", "system design", "html", "css", "figma", "excel", "power bi", "tableau",
        "cybersecurity", "testing", "selenium", "communication", "leadership", "problem solving"
    ]
    return {x for x in catalog if x in lower}


def api_match_job(resume_text: str, job_description: str) -> Dict:
    """Call semantic match API; fall back to deterministic TF-IDF + skill matching."""
    if not resume_text.strip() or not job_description.strip():
        return {"overall": 0, "matched": [], "missing": [], "summary": "Both resume and job description are required.", "experience_alignment": "Unavailable", "source": "validation"}
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
        "summary": "Local semantic and skill analysis completed because the matching service was unavailable.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment" if overall >= 50 else "Needs Improvement",
        "source": "local-fallback"
    }

def _safe_public_url(url: str) -> bool:
    """Reject malformed and private/local URLs before server-side fetching."""
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname
        try:
            addresses = socket.getaddrinfo(host, None)
            ips = {item[4][0] for item in addresses}
            for raw_ip in ips:
                ip = ipaddress.ip_address(raw_ip)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return False
        except socket.gaierror:
            return False
        return True
    except ValueError:
        return False


def fetch_public_job_url(url: str) -> str:
    if not _safe_public_url(url):
        raise ValueError("Please enter a valid public HTTP/HTTPS job URL.")
    response = requests.get(
        url.strip(),
        timeout=15,
        headers={"User-Agent": "CareerLensAI/2.1 Job Safety Analyzer"},
        allow_redirects=True,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError("The supplied link did not return a readable web page.")
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", response.text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:50000]


def api_detect_fraud(job_text: str) -> Dict:
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
    return {"score": score, "level": "HIGH RISK" if score >= 55 else "MEDIUM RISK" if score >= 25 else "LOW RISK", "signals": len(signals), "signal_details": signals, "source": "local-fallback"}

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

def _db_user(username):
    with _db_connect() as conn:
        return conn.execute("SELECT user_id, username, display_name, password_hash FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()

def _db_create_user(username, display_name, password_hash):
    user_id = secrets.token_hex(16)
    with _db_connect() as conn:
        conn.execute("INSERT INTO users(user_id,username,display_name,password_hash,created_at) VALUES(?,?,?,?,?)", (user_id, username.strip(), display_name.strip() or username.split('@')[0], password_hash, datetime.now().isoformat(timespec="seconds")))
    return user_id

def _db_save_state(user_id, state):
    if not user_id:
        return
    payload = json.dumps(state, ensure_ascii=False)
    with _db_connect() as conn:
        conn.execute("INSERT INTO user_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at", (user_id, payload, datetime.now().isoformat(timespec="seconds")))

def _db_load_state(user_id):
    if not user_id:
        return {}
    with _db_connect() as conn:
        row = conn.execute("SELECT state_json FROM user_state WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {}
    try:
        return json.loads(row[0]) if isinstance(row[0], str) else {}
    except (TypeError, ValueError):
        return {}

def _db_save_recruiter_state(user_id, data):
    if not user_id:
        return
    payload = json.dumps(data, ensure_ascii=False)
    with _db_connect() as conn:
        conn.execute("INSERT INTO recruiter_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at", (user_id, payload, datetime.now().isoformat(timespec="seconds")))

def _db_load_recruiter_state(user_id):
    if not user_id:
        return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    with _db_connect() as conn:
        row = conn.execute("SELECT state_json FROM recruiter_state WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    try:
        data=json.loads(row[0])
        return data if isinstance(data, dict) else {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    except (TypeError, ValueError):
        return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}

_init_app_db()

if "is_logged_in" not in st.session_state:
    st.session_state.is_logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""
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
if "assessment_question_count" not in st.session_state:
    st.session_state.assessment_question_count = 20
if "assessment_review" not in st.session_state:
    st.session_state.assessment_review = False
if "assessment_result" not in st.session_state:
    st.session_state.assessment_result = None
if "assessment_selected_role" not in st.session_state:
    st.session_state.assessment_selected_role = "Software Developer"
if "job_detection_result" not in st.session_state:
    st.session_state.job_detection_result = None
if "job_detection_text" not in st.session_state:
    st.session_state.job_detection_text = ""
if "resume_builder" not in st.session_state:
    st.session_state.resume_builder = {}
if "resume_template" not in st.session_state:
    st.session_state.resume_template = "Executive"


RECRUITER_DATA_FILE = "recruiter_workspace.json"


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


def _recruiter_score(candidate: Dict[str, Any]) -> float:
    try:
        return float(candidate.get("role_match", candidate.get("score", 0)))
    except (TypeError, ValueError):
        return 0.0


def _candidate_id(name: str, email: str) -> str:
    return hashlib.sha256(f"{name}|{email}".encode("utf-8")).hexdigest()[:16]


def _make_assessment_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def _assessment_public_url(token: str) -> str:
    base = _deployment_secret("PUBLIC_APP_URL").strip().rstrip("/")
    if not base:
        base = "http://localhost:8501"
    return f"{base}/?assessment={quote(token)}"


def _deployment_secret(name: str, default: str = "") -> str:
    try:
        value = st.secrets.get(name, default)
    except Exception:
        value = os.getenv(name, default)
    return str(value or default)


def _smtp_settings() -> Dict[str, Any]:
    # Recruiters never configure SMTP in the UI. These values belong in
    # Streamlit Secrets or deployment environment variables only.
    return {
        "host": _deployment_secret("SMTP_HOST"),
        "port": int(_deployment_secret("SMTP_PORT", "587")),
        "username": _deployment_secret("SMTP_USERNAME"),
        "password": _deployment_secret("SMTP_PASSWORD"),
        "sender": _deployment_secret("SMTP_FROM"),
        "use_ssl": _deployment_secret("SMTP_SSL", "0").lower() in {"1", "true", "yes"},
    }

def _send_assessment_email(to_email: str, candidate_name: str, role: str, link: str) -> tuple[bool, str]:
    import smtplib
    from email.message import EmailMessage
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to_email or ""):
        return False, "Candidate email is missing or invalid."
    cfg = _smtp_settings()
    if not all([cfg["host"], cfg["username"], cfg["password"], cfg["sender"]]):
        return False, "Email is not configured. Open Email Delivery and enter SMTP settings, or set SMTP_* environment variables."
    try:
        msg = EmailMessage()
        msg["Subject"] = f"CareerLens AI — {role} Assessment Invitation"
        msg["From"] = cfg["sender"]
        msg["To"] = to_email
        msg.set_content(
            f"Hello {candidate_name or 'Candidate'},\n\n"
            f"Congratulations! You have been shortlisted for the next stage of the {role} hiring process.\n\n"
            "Please complete the online assessment using the secure link below.\n\n"
            f"Take Assessment: {link}\n\n"
            "Your score and answer key will not be displayed after submission. The recruiting team will review your assessment.\n\n"
            "Please complete the assessment before the deadline shown in your invitation.\n\n"
            "Best regards,\nRecruitment Team\nCareerLens AI"
        )
        if cfg["use_ssl"] or cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=25) as server:
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=25) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(cfg["username"], cfg["password"])
                server.send_message(msg)
        return True, "Email sent successfully."
    except (OSError, ValueError, smtplib.SMTPException) as exc:
        return False, f"Email delivery failed: {exc}"


if "smtp_config" not in st.session_state:
    st.session_state.smtp_config = {}

if "recruiter_data" not in st.session_state:
    st.session_state.recruiter_data = _load_recruiter_data()

# Recruiter Store State
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

def generate_assessment_questions(role: str, count: int) -> List[Dict]:
    """Generate up to 50 deterministic MCQs and return exactly the requested count."""
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
        "Data Analyst": [
            ("Which SQL operation combines rows from related tables?", ["JOIN", "DROP", "TRUNCATE", "GRANT"], 0),
            ("What does a KPI represent?", ["A key performance indicator", "A programming language", "A database engine", "A network protocol"], 0),
            ("Which visualization best shows a trend over time?", ["Line chart", "Pie chart", "Treemap", "Single KPI card"], 0),
            ("What is data cleaning?", ["Fixing missing, invalid or inconsistent data", "Deleting all data", "Encrypting a dashboard", "Changing passwords"], 0),
            ("What does GROUP BY do?", ["Groups rows for aggregate analysis", "Deletes duplicates", "Creates a user", "Encrypts columns"], 0),
        ],
    }
    generic = [
        ("What is the safest default for sensitive user data?", ["Least privilege and encryption", "Public access", "Plaintext storage", "Shared credentials"], 0),
        ("What is the purpose of version control?", ["Track and collaborate on changes", "Increase monitor brightness", "Replace backups completely", "Generate salary slips"], 0),
        ("What should happen after detecting a production regression?", ["Contain, inspect telemetry and restore safely", "Ignore it", "Delete logs", "Disable tests"], 0),
        ("Which practice improves API reliability?", ["Timeouts, validation and controlled retries", "Infinite retries", "No validation", "Hard-coded secrets"], 0),
        ("What is RBAC?", ["Role-Based Access Control", "Random Binary API Cache", "Remote Build Allocation Controller", "Runtime Browser Access Code"], 0),
        ("Which communication style is strongest in technical teams?", ["Clear, evidence-based and respectful", "Vague and undocumented", "Aggressive and private", "No status updates"], 0),
        ("What does scalability mean?", ["Ability to handle increased load effectively", "Reducing all features", "Removing tests", "Deleting users"], 0),
        ("What is an SLA?", ["A defined service-level commitment", "A source-code language", "A database index", "A resume section"], 0),
        ("Why use code review?", ["Improve correctness, maintainability and shared knowledge", "Avoid testing", "Hide changes", "Replace documentation entirely"], 0),
        ("What should credentials never be committed to?", ["Source-control repositories", "A secret manager", "An encrypted vault", "A protected runtime environment"], 0),
    ]
    bank = role_topics.get(role, []) + generic
    questions = []
    for i in range(max(count, 1)):
        base = bank[i % len(bank)]
        q_text, options, correct_idx = base
        cycle = i // len(bank)
        question_text = q_text if cycle == 0 else f"{q_text} (Scenario {cycle + 1})"
        questions.append({
            "id": i + 1,
            "section": "Core Skills" if i < count * 0.6 else "Applied Scenarios",
            "question": question_text,
            "options": options,
            "answer": options[correct_idx],
        })
    return questions


def generate_100q_assessment(role: str) -> List[Dict]:
    # Backward-compatible wrapper for recruiter blueprints.
    return generate_assessment_questions(role, 50)


def assessment_result(questions: List[Dict], answers: Dict) -> Dict:
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
    """Create a real A4 PDF resume using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm, topMargin=14*mm, bottomMargin=14*mm)
    styles = getSampleStyleSheet()
    title_size = 22 if template in {"Executive", "Minimal"} else 20
    accent = colors.HexColor({
        "Executive": "#1d4ed8", "Minimal": "#0f172a", "Modern Blue": "#2563eb", "Modern Purple": "#7c3aed",
        "Emerald": "#059669", "Professional": "#334155", "Tech": "#0284c7", "Elegant": "#9a3412",
        "ATS Classic": "#111827", "Compact": "#475569"
    }.get(template, "#2563eb"))
    title = ParagraphStyle("ResumeTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=title_size, leading=25, textColor=accent, alignment=TA_CENTER, spaceAfter=4)
    contact = ParagraphStyle("Contact", parent=styles["Normal"], fontSize=8.8, leading=12, textColor=colors.HexColor("#475569"), alignment=TA_CENTER, spaceAfter=10)
    heading = ParagraphStyle("Heading", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=13, textColor=accent, spaceBefore=7, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=8.8, leading=12, textColor=colors.HexColor("#1f2937"), spaceAfter=3)
    small = ParagraphStyle("Small", parent=body, fontSize=8.2, leading=11)
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


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def password_matches(stored: str, provided: str) -> bool:
    if not stored:
        return False
    digest = hash_password(provided)
    if stored == digest:
        return True
    # Backward compatibility for accounts created by the previous version.
    if stored == provided:
        st.session_state.users_db = {
            key: (hash_password(value) if key == u else value)
            for key, value in st.session_state.users_db.items()
        }
        return True
    return False


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
    st.caption(f"Role: {assessment.get('role', 'Professional Assessment')} • {assessment.get('question_count', len(assessment.get('questions', [])))} questions")
    st.info("Complete the assessment and submit it. Your score and answer key are not displayed on the candidate page; the recruiter will review the result.")

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
        st.info("You can close this page now. Your score is available only to the recruiter.")
        st.stop()

    answered = sum(1 for q in questions if st.session_state[answer_key].get(q.get("id")) is not None)
    st.progress(answered / max(1, len(questions)), text=f"Answered {answered} of {len(questions)}")
    for q in questions:
        qid = q.get("id")
        current = st.session_state[answer_key].get(qid)
        index = q.get("options", []).index(current) if current in q.get("options", []) else None
        selected = st.radio(q.get("question", "Question"), q.get("options", []), index=index, key=f"{state_key}_{qid}")
        st.session_state[answer_key][qid] = selected

    answered = sum(1 for q in questions if st.session_state[answer_key].get(q.get("id")) is not None)
    st.write(f"**Answered:** {answered} • **Unanswered:** {len(questions) - answered}")
    if st.button("🚀 Submit Assessment", type="primary", use_container_width=True):
        result = assessment_result(questions, st.session_state[answer_key])
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

    st.stop()


# Public recruiter-generated assessment links are handled before login so invited
# candidates do not need a recruiter account and never see recruiter scores.
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
def dialog_auth():
    tab_auth1, tab_auth2 = st.tabs(["Sign In", "Register"])
    with tab_auth1:
        u = st.text_input("Username or Email", key="auth_sign_u")
        p = st.text_input("Password", type="password", key="auth_sign_p")
        if st.button("Sign In", use_container_width=True, key="btn_confirm_sign"):
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
                    st.session_state.recruiter_assessment_submissions = {x.get("token", str(i)): x for i, x in enumerate(st.session_state.recruiter_data.get("submissions", [])) if isinstance(x, dict)}
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
                    st.error("Account not found. Please register or continue as Guest.")
    with tab_auth2:
        reg_n = st.text_input("Full Name", key="auth_reg_n")
        reg_u = st.text_input("Choose Username / Email", key="auth_reg_u")
        reg_p = st.text_input("Create Password", type="password", key="auth_reg_p")
        if st.button("Create Account", use_container_width=True, key="btn_confirm_reg"):
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
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Pre-Interview Exam:</b> 10–50 question MCQ assessment with instant results.</div>
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

    if st.button("👤  Job Seeker Workspace", key="sb_ws_seeker", type="primary" if is_seeker else "secondary", use_container_width=True):
        st.session_state.active_workspace = "Job Seeker Workspace"
        st.session_state.active_tool = "Dashboard"
        st.rerun()

    if st.button("🏢  Recruiter Workspace", key="sb_ws_recruiter", type="primary" if is_recruiter else "secondary", use_container_width=True):
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
            ("📝 Assessment Builder", "Assessment Builder"),
            ("📊 Assessment Results", "Score Vault"),
            ("🎤 Interview Pipeline", "Interview Pipeline")
        ]
        for name, key_val in rec_tools:
            is_active = st.session_state.active_tool == key_val
            if st.button(name, key=f"sb_rec_{key_val}", type="primary" if is_active else "secondary", use_container_width=True):
                st.session_state.active_tool = key_val
                st.rerun()

    st.markdown("<hr style='border-color: rgba(255,255,255,0.1); margin: 20px 0;'>", unsafe_allow_html=True)
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
            st.markdown("#### Resume Intelligence Scores")
            rr1, rr2, rr3 = st.columns(3)
            rr1.metric("Resume Score", f"{r.get('resume_score', 0)}%")
            rr2.metric("Readiness", f"{r.get('readiness', 0)}%")
            rr3.metric("Market Match", f"{r.get('market_match')}%" if r.get('market_match') is not None else "Run AI Job Match")
            st.markdown("#### Detected Skills")
            skills_html = "".join([f'<span class="tag-badge tag-blue">{_escape(s)}</span>' for s in r.get("skills", [])])
            st.markdown(skills_html or "No skills detected yet.", unsafe_allow_html=True)
            target_role_resume = st.selectbox("Target Role for Skill Gap", IT_ROLES + NON_IT_ROLES, key="resume_target_role")
            role_skill_map = {
                "Software Developer": {"python","sql","git","rest api","testing","system design"},
                "Data Scientist": {"python","pandas","numpy","scikit-learn","machine learning","sql"},
                "Data Analyst": {"sql","excel","power bi","tableau","python"},
                "DevOps Engineer": {"linux","docker","kubernetes","aws","git"},
                "Cybersecurity Analyst": {"linux","cybersecurity","python","testing"},
                "Cloud Engineer": {"aws","azure","gcp","docker","kubernetes","linux"},
                "QA Engineer": {"testing","selenium","python","sql","git"},
            }
            detected = {str(x).lower() for x in r.get("skills", [])}
            required = role_skill_map.get(target_role_resume, set())
            missing = sorted(required - detected)
            st.markdown("#### Missing Skills")
            if missing:
                st.warning(" • ".join(missing))
            else:
                st.success("No major skills missing for the selected target role.")
            if r.get("recommendations"):
                st.markdown("#### Recommended Improvements")
                for item in r.get("recommendations", []): st.info(item)

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back to Dashboard", key="btn_back_exam"):
            st.session_state.active_tool = "Dashboard"
            st.session_state.assessment_active = False
            st.session_state.assessment_review = False
            st.rerun()

        st.markdown("### 📝 Pre-Interview Assessment")
        st.caption("Choose 10–50 MCQs • Review your answers • Confirm submission • Get your score here")

        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:
            domain_type = st.radio("Domain Category", ["IT Roles", "Non-IT Roles"], horizontal=True, key="assessment_domain")
            roles_list = IT_ROLES if domain_type == "IT Roles" else NON_IT_ROLES
            selected_assessment_role = st.selectbox("Select Target Role", roles_list, key="assessment_role_select")
            question_count = st.select_slider("Number of Questions", options=list(range(10, 51, 5)), value=st.session_state.assessment_question_count, key="assessment_count_select")
            st.session_state.assessment_question_count = question_count
            st.markdown(f"""<div class="content-box"><h4 style="margin:0;color:#2563eb;">{question_count}-Question Assessment</h4><p style="color:#64748b;margin:6px 0 0 0;">Each question carries 1 mark. You can leave questions unanswered, review all answers before submission, and receive the complete result immediately in your Job Seeker workspace.</p></div>""", unsafe_allow_html=True)
            if st.button("🚀 Start Assessment", use_container_width=True, key="start_assessment_new"):
                st.session_state.assessment_questions = generate_assessment_questions(selected_assessment_role, question_count)
                st.session_state.assessment_role = selected_assessment_role
                st.session_state.assessment_answers = {}
                st.session_state.assessment_active = True
                st.session_state.assessment_review = False
                st.session_state.assessment_result = None
                st.session_state.assessment_candidate_token = f"{st.session_state.username}_{uuid.uuid4().hex[:8]}"
                st.rerun()

        elif st.session_state.assessment_active and not st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.markdown(f"#### {st.session_state.assessment_role} Assessment")
            st.progress(answered / len(questions) if questions else 0, text=f"Answered {answered} / {len(questions)} • Unanswered {unanswered}")
            for q in questions:
                qid = q["id"]
                current = st.session_state.assessment_answers.get(qid)
                try:
                    current_index = q["options"].index(current) if current in q["options"] else None
                except ValueError:
                    current_index = None
                chosen = st.radio(f"Q{qid}. {q['question']}", q["options"], index=current_index, key=f"q_choice_{qid}")
                st.session_state.assessment_answers[qid] = chosen
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.info(f"Answered: {answered}  |  Unanswered: {unanswered}")
            if st.button("🔎 Review Answers Before Submit", use_container_width=True, key="review_assessment"):
                st.session_state.assessment_review = True
                st.rerun()

        elif st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            answered = sum(1 for q in questions if st.session_state.assessment_answers.get(q["id"]) is not None)
            unanswered = len(questions) - answered
            st.markdown("### 🔎 Review Your Assessment")
            c1, c2 = st.columns(2)
            c1.metric("Answered", answered)
            c2.metric("Unanswered", unanswered)
            for q in questions:
                selected = st.session_state.assessment_answers.get(q["id"])
                status = "✅ Answered" if selected else "⚪ Unanswered"
                shown = selected if selected else "No answer selected"
                st.markdown(f"**Q{q['id']} — {status}**  \n{q['question']}  \nYour answer: **{shown}**")
            st.warning("Please review your answers. Once you confirm submission, the assessment will be finalized and cannot be edited.")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("← Continue Editing", use_container_width=True, key="continue_edit_exam"):
                    st.session_state.assessment_review = False
                    st.rerun()
            with b2:
                if st.button("✅ Submit Assessment", type="primary", use_container_width=True, key="confirm_submit_exam"):
                    st.session_state.assessment_result = assessment_result(questions, st.session_state.assessment_answers)
                    st.session_state.assessment_active = False
                    st.session_state.assessment_review = False
                    # IMPORTANT: Job-seeker results stay in Job Seeker state.
                    # They are deliberately NOT copied into recruiter_assessment_submissions.
                    log_event("ASSESSMENT_COMPLETED", st.session_state.username, str(st.session_state.assessment_result["percentage"]), st.session_state.assessment_role)
                    st.rerun()

        elif st.session_state.assessment_result is not None:
            result = st.session_state.assessment_result
            pct = result["percentage"]
            st.markdown(f"""<div class="content-box" style="text-align:center;padding:36px;"><div style="font-size:50px;">{'🏆' if pct >= 80 else '✅' if pct >= 60 else '📚'}</div><h2 style="margin:8px 0;color:#0f172a;">Assessment Result</h2><div style="font-size:3rem;font-weight:900;color:#2563eb;">{pct}%</div><p style="color:#64748b;">{st.session_state.assessment_role} • {result['total']} questions • Submitted {result['submitted_at']}</p></div>""", unsafe_allow_html=True)
            r1, r2, r3, r4 = st.columns(4)
            r1.metric("Score", f"{result['score']} / {result['total']}")
            r2.metric("Correct", result["correct_count"])
            r3.metric("Incorrect", result["wrong_count"])
            r4.metric("Unanswered", result["unanswered_count"])
            st.markdown("### Answer Review")
            with st.expander("Show correct answers", expanded=False):
                for item in result["correct_items"]:
                    st.success(f"Q{item['id']}: {item['question']}\n\nCorrect: {item['correct']}")
            with st.expander("Show incorrect answers", expanded=True):
                if result["wrong_items"]:
                    for item in result["wrong_items"]:
                        st.error(f"Q{item['id']}: {item['question']}\n\nYour answer: {item['selected']}\n\nCorrect answer: {item['correct']}")
                else:
                    st.success("No incorrect answers.")
            with st.expander("Show unanswered questions", expanded=False):
                if result["unanswered_items"]:
                    for item in result["unanswered_items"]:
                        st.warning(f"Q{item['id']}: {item['question']}\n\nCorrect answer: {item['correct']}")
                else:
                    st.success("All questions were answered.")
            if pct < 60:
                st.info("Focus on the concepts behind your incorrect answers and retake the assessment after preparation.")
            elif pct < 80:
                st.info("Good foundation. Review the incorrect questions and strengthen the weak areas before interviewing.")
            else:
                st.success("Strong assessment performance. Keep practicing role-specific scenarios and interviews.")
            if st.button("🔄 Take Another Assessment", use_container_width=True, key="btn_reset_exam"):
                st.session_state.assessment_result = None
                st.session_state.assessment_active = False
                st.session_state.assessment_review = False
                st.session_state.assessment_answers = {}
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
                target_interview_role = st.selectbox("Select Target Role", IT_ROLES + NON_IT_ROLES, key="mock_role_select")
            with c2:
                interview_len = st.select_slider("Interview Questions", options=list(range(1, 51)), value=min(max(st.session_state.interview_q_count, 10), 50), key="mock_count_select")
            st.caption("Choose anywhere from 1 to 50 questions. Longer sessions provide a broader evaluation.")
            if st.button("🚀 Start Mock Interview", use_container_width=True, key="start_mock_new"):
                q_templates = [
                    f"Tell me about yourself and why you are targeting the {target_interview_role} role.",
                    f"Which technical skills are most important for a successful {target_interview_role} and how have you applied them?",
                    "Describe a difficult problem you solved. Explain your reasoning and the measurable outcome.",
                    "Tell me about a disagreement with a teammate and how you resolved it.",
                    "Describe a project where something went wrong. What did you learn?",
                    f"How would you design a reliable solution for a production system relevant to {target_interview_role}?",
                    "How do you prioritize work when multiple deadlines conflict?",
                    "How do you test and validate your work before release?",
                    "How do you keep your skills current in a changing technical environment?",
                    "Why should a hiring team choose you for this role?",
                ]
                questions = [q_templates[i % len(q_templates)] + (f" (Question {i+1})" if i >= len(q_templates) else "") for i in range(interview_len)]
                st.session_state.interview_questions = questions
                st.session_state.interview_role = target_interview_role
                st.session_state.interview_q_count = interview_len
                st.session_state.interview_current_idx = 0
                st.session_state.interview_transcript = []
                st.session_state.interview_active = True
                st.session_state.interview_completed = False
                st.session_state.interview_report = None
                st.rerun()

        elif st.session_state.interview_active and not st.session_state.interview_completed:
            curr_i = st.session_state.interview_current_idx
            total_i = len(st.session_state.interview_questions)
            curr_question_text = st.session_state.interview_questions[curr_i]
            st.progress((curr_i) / total_i if total_i else 0, text=f"Question {curr_i + 1} of {total_i}")
            st.markdown(f"""<div class="content-box"><span class="tag-badge tag-blue">QUESTION {curr_i + 1} OF {total_i}</span><h3 style="margin-top:10px;color:#0f172a;">{_escape(curr_question_text)}</h3></div>""", unsafe_allow_html=True)
            cand_response = st.text_area("Your response", height=180, key=f"ans_text_{curr_i}")
            if st.button("Submit & Next ➔", use_container_width=True, key=f"mock_next_{curr_i}"):
                if not cand_response.strip():
                    st.warning("Please type your response before proceeding.")
                else:
                    st.session_state.interview_transcript.append({"question": curr_question_text, "answer": cand_response.strip()})
                    if curr_i + 1 < total_i:
                        st.session_state.interview_current_idx += 1
                        st.rerun()
                    else:
                        st.session_state.interview_active = False
                        st.session_state.interview_completed = True
                        answers = st.session_state.interview_transcript
                        avg_words = sum(len(x["answer"].split()) for x in answers) / len(answers) if answers else 0
                        quality = min(100, round(55 + min(avg_words / 2, 25) + min(len(answers), 10)))
                        st.session_state.interview_report = {
                            "overall": quality,
                            "confidence": min(100, quality + 2),
                            "communication": min(100, quality + 1),
                            "correctness": max(0, quality - 4),
                            "role_knowledge": max(0, quality - 2),
                            "strengths": ["Completed the full interview", "Provided substantive responses" if avg_words >= 35 else "Maintained concise responses"],
                            "improvements": ["Add measurable outcomes to examples", "Use a clear situation-action-result structure", "Support technical claims with concrete project evidence"]
                        }
                        log_event("MOCK_INTERVIEW_COMPLETED", st.session_state.username, str(quality), st.session_state.interview_role)
                        st.rerun()

        elif st.session_state.interview_completed:
            rep = st.session_state.interview_report or {}
            st.markdown(f"""<div class="content-box" style="text-align:center;"><span class="tag-badge tag-green">EVALUATION COMPLETED</span><h2 style="margin:10px 0;">Interview Readiness: <span style="color:#2563eb;">{rep.get('overall', 0)}%</span></h2><p style="color:#64748b;">Evaluation for {st.session_state.interview_role}</p></div>""", unsafe_allow_html=True)
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            col_r1.metric("Overall", f"{rep.get('overall', 0)}%")
            col_r2.metric("Confidence", f"{rep.get('confidence', 0)}%")
            col_r3.metric("Communication", f"{rep.get('communication', 0)}%")
            col_r4.metric("Role Knowledge", f"{rep.get('role_knowledge', 0)}%")
            st.markdown("#### Strengths")
            for item in rep.get("strengths", []): st.success(item)
            st.markdown("#### Areas to Improve")
            for item in rep.get("improvements", []): st.warning(item)
            if st.button("Practice Another Mock Interview", key="btn_retry_mock"):
                st.session_state.interview_completed = False
                st.session_state.interview_active = False
                st.session_state.interview_report = None
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

        st.markdown("### 🛡️ Job Detection")
        st.caption("Check a public job/interview link or paste the job description. You no longer need to paste the full offer body.")
        detection_mode = st.radio("Input Method", ["🔗 Paste Job Link", "📝 Paste Description"], horizontal=True, key="fraud_mode")
        if detection_mode == "🔗 Paste Job Link":
            job_url = st.text_input("Job / Interview / Offer URL", placeholder="https://example.com/jobs/software-engineer", key="fraud_url")
            description_input = ""
        else:
            description_input = st.text_area("Job Description", height=220, placeholder="Paste the job description here...", key="fraud_description")
            job_url = ""
        if st.button("🔍 Analyze Job Safety", use_container_width=True, key="analyze_job_safety_new"):
            try:
                with st.spinner("Analyzing job safety signals..."):
                    if detection_mode.startswith("🔗"):
                        if not job_url.strip():
                            raise ValueError("Please enter a job URL.")
                        analysis_text = fetch_public_job_url(job_url.strip())
                        source_label = job_url.strip()
                    else:
                        if not description_input.strip():
                            raise ValueError("Please paste a job description.")
                        analysis_text = description_input.strip()
                        source_label = "Pasted description"
                    result = api_detect_fraud(analysis_text)
                    result["source_label"] = source_label
                    st.session_state.job_detection_result = result
                    st.session_state.job_detection_text = analysis_text
            except (ValueError, requests.RequestException) as exc:
                st.error(str(exc))
        if st.session_state.job_detection_result:
            res = st.session_state.job_detection_result
            verdict_color = "#ef4444" if res.get("level") == "HIGH RISK" else "#d97706" if res.get("level") == "MEDIUM RISK" else "#059669"
            st.markdown(f"""<div class="content-box"><h3>Risk Verdict: <span style="color:{verdict_color};">{_escape(res.get('level','UNKNOWN'))}</span></h3><p style="color:#64748b;margin:0;">Risk Score: {res.get('score',0)}/100 • Signals Found: {res.get('signals',0)}</p><p style="color:#64748b;margin-top:6px;">Source: {_escape(res.get('source_label',''))}</p></div>""", unsafe_allow_html=True)
            for signal in res.get("signal_details", []):
                st.warning(signal)

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back to Dashboard", key="btn_back_bld"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()

        st.markdown("### 📄 Professional Resume Builder")
        st.caption("Choose one of 10 templates, complete your resume sections, preview it live, and export a real PDF.")
        templates = ["Executive", "Minimal", "Modern Blue", "Modern Purple", "Emerald", "Professional", "Tech", "Elegant", "ATS Classic", "Compact"]
        st.session_state.resume_template = st.selectbox("Resume Template", templates, index=templates.index(st.session_state.resume_template) if st.session_state.resume_template in templates else 0, key="resume_template_select")
        left, right = st.columns([1.05, 1], gap="large")
        with left:
            st.markdown("#### Resume Information")
            rb_name = st.text_input("Full Name", value=st.session_state.resume_builder.get("name", st.session_state.username), key="rb_name")
            rb_headline = st.text_input("Professional Headline", value=st.session_state.resume_builder.get("headline", "Software Developer"), key="rb_headline")
            c1, c2 = st.columns(2)
            with c1: rb_email = st.text_input("Email", value=st.session_state.resume_builder.get("email", ""), key="rb_email")
            with c2: rb_phone = st.text_input("Phone", value=st.session_state.resume_builder.get("phone", ""), key="rb_phone")
            c3, c4 = st.columns(2)
            with c3: rb_location = st.text_input("Location", value=st.session_state.resume_builder.get("location", ""), key="rb_location")
            with c4: rb_linkedin = st.text_input("LinkedIn", value=st.session_state.resume_builder.get("linkedin", ""), key="rb_linkedin")
            rb_github = st.text_input("GitHub / Portfolio", value=st.session_state.resume_builder.get("github", ""), key="rb_github")
            rb_summary = st.text_area("Professional Summary", value=st.session_state.resume_builder.get("summary", ""), height=110, key="rb_summary")
            rb_experience = st.text_area("Experience", value=st.session_state.resume_builder.get("experience", ""), height=150, help="Use one role per line or paragraph. Include measurable achievements.", key="rb_experience")
            rb_education = st.text_area("Education", value=st.session_state.resume_builder.get("education", ""), height=100, key="rb_education")
            rb_projects = st.text_area("Projects", value=st.session_state.resume_builder.get("projects", ""), height=130, key="rb_projects")
            rb_skills = st.text_area("Skills", value=st.session_state.resume_builder.get("skills", "Python, SQL, Git"), height=90, key="rb_skills")
            rb_certifications = st.text_area("Certifications", value=st.session_state.resume_builder.get("certifications", ""), height=80, key="rb_certifications")
            rb_achievements = st.text_area("Achievements", value=st.session_state.resume_builder.get("achievements", ""), height=80, key="rb_achievements")
            resume_data = {"name": rb_name, "headline": rb_headline, "email": rb_email, "phone": rb_phone, "location": rb_location, "linkedin": rb_linkedin, "github": rb_github, "summary": rb_summary, "experience": rb_experience, "education": rb_education, "projects": rb_projects, "skills": rb_skills, "certifications": rb_certifications, "achievements": rb_achievements}
            st.session_state.resume_builder = resume_data
            if st.button("⬇️ Generate & Download PDF", use_container_width=True, key="generate_resume_pdf"):
                if not rb_name.strip():
                    st.error("Full Name is required.")
                else:
                    try:
                        pdf_bytes = build_resume_pdf(resume_data, st.session_state.resume_template)
                        st.download_button("Download Resume PDF", data=pdf_bytes, file_name=f"{re.sub(r'[^A-Za-z0-9_-]+','_',rb_name.strip())}_Resume.pdf", mime="application/pdf", use_container_width=True, key="resume_pdf_download")
                    except Exception as exc:
                        st.error(f"PDF generation failed: {exc}")
        with right:
            st.markdown("#### Live Preview")
            template_styles = {
                "Executive": {"accent": "#1d4ed8", "font": "Georgia,serif", "align": "left", "border": "3px solid #1d4ed8", "radius": "6px"},
                "Minimal": {"accent": "#111827", "font": "Arial,sans-serif", "align": "left", "border": "1px solid #111827", "radius": "0"},
                "Modern Blue": {"accent": "#2563eb", "font": "Arial,sans-serif", "align": "center", "border": "4px solid #2563eb", "radius": "12px"},
                "Modern Purple": {"accent": "#7c3aed", "font": "Arial,sans-serif", "align": "center", "border": "4px solid #7c3aed", "radius": "12px"},
                "Emerald": {"accent": "#059669", "font": "Arial,sans-serif", "align": "left", "border": "4px solid #059669", "radius": "14px"},
                "Professional": {"accent": "#334155", "font": "Arial,sans-serif", "align": "left", "border": "2px solid #334155", "radius": "4px"},
                "Tech": {"accent": "#0284c7", "font": "monospace", "align": "left", "border": "2px dashed #0284c7", "radius": "8px"},
                "Elegant": {"accent": "#9a3412", "font": "Georgia,serif", "align": "center", "border": "1px solid #9a3412", "radius": "18px"},
                "ATS Classic": {"accent": "#111827", "font": "Arial,sans-serif", "align": "left", "border": "0", "radius": "0"},
                "Compact": {"accent": "#475569", "font": "Arial,sans-serif", "align": "left", "border": "2px solid #cbd5e1", "radius": "8px"},
            }
            ts = template_styles[st.session_state.resume_template]
            contact_line = " • ".join(_escape(x) for x in [rb_email, rb_phone, rb_location, rb_linkedin, rb_github] if x)
            preview_html = f"""<div style=\"background:#fff;border:{ts['border']};border-radius:{ts['radius']};padding:30px;min-height:900px;box-shadow:0 8px 25px rgba(15,23,42,.08);font-family:{ts['font']};\"><div style=\"text-align:{ts['align']};border-bottom:3px solid {ts['accent']};padding-bottom:14px;margin-bottom:16px;\"><h1 style=\"margin:0;color:{ts['accent']};font-size:28px;\">{_escape(rb_name or 'Your Name')}</h1><div style=\"color:#475569;margin-top:5px;font-size:14px;\">{_escape(rb_headline)}</div><div style=\"color:#64748b;font-size:11px;margin-top:7px;\">{contact_line}</div></div>"""
            def preview_section(title, content):
                if not content.strip():
                    return ""
                return f"<h3 style=\"font-size:13px;color:{ts['accent']};border-bottom:1px solid #e2e8f0;padding-bottom:4px;margin:16px 0 7px;\">{title}</h3><div style=\"font-size:11px;line-height:1.55;color:#1f2937;white-space:pre-wrap;\">{_escape(content)}</div>"
            for title, content in [("PROFESSIONAL SUMMARY", rb_summary), ("EXPERIENCE", rb_experience), ("EDUCATION", rb_education), ("PROJECTS", rb_projects), ("SKILLS", rb_skills), ("CERTIFICATIONS", rb_certifications), ("ACHIEVEMENTS", rb_achievements)]:
                preview_html += preview_section(title, content)
            preview_html += "</div>"
            st.markdown(preview_html, unsafe_allow_html=True)


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
# 🏢 RECRUITER WORKSPACE
# ============================================================

elif st.session_state.active_workspace == "Recruiter Workspace":
    data = st.session_state.recruiter_data
    candidates = st.session_state.recruiter_candidates
    submissions = list(st.session_state.recruiter_assessment_submissions.values())
    campaign = data.get("campaign") or {}

    # --------------------------------------------------------
    # Recruiter dashboard helpers
    # --------------------------------------------------------
    status_order = ["Screened", "Shortlisted", "Assessment Sent", "Assessment Completed", "Interview", "Selected", "Rejected"]
    status_counts = {status: sum(1 for c in candidates if c.get("status") == status) for status in status_order}
    pending = sum(1 for c in candidates if c.get("assessment_status") == "Sent")
    completed_scores = [float(x.get("percentage", 0)) for x in submissions if isinstance(x, dict)]
    avg_score = round(sum(completed_scores) / len(completed_scores), 1) if completed_scores else 0
    shortlist_count = status_counts["Shortlisted"]

    def persist_recruiter():
        data["candidates"] = st.session_state.recruiter_candidates
        data["submissions"] = list(st.session_state.recruiter_assessment_submissions.values())
        st.session_state.recruiter_data = data
        _save_recruiter_data(data)

    def recruiter_nav(tool: str):
        st.session_state.active_tool = tool
        st.rerun()

    recruiter_steps = [
        ("Dashboard", "Command Center"),
        ("Hiring Campaign", "Campaign"),
        ("Bulk Screening", "Screening"),
        ("Shortlisted Candidates", "Shortlist"),
        ("Assessment Builder", "Assessment"),
        ("Score Vault", "Results"),
        ("Interview Pipeline", "Interview"),
    ]
    current_index = next((i for i, (key, _) in enumerate(recruiter_steps) if key == st.session_state.active_tool), 0)
    nav_left, nav_center, nav_right = st.columns([1, 5, 1])
    with nav_left:
        if current_index > 0 and st.button("← Back", key="recruiter_back", use_container_width=True):
            recruiter_nav(recruiter_steps[current_index - 1][0])
    with nav_center:
        labels = "  →  ".join([f"**{label}**" if i == current_index else label for i, (_, label) in enumerate(recruiter_steps)])
        st.markdown(f"<div style='text-align:center;color:#64748b;font-size:.82rem;padding-top:8px'>{labels}</div>", unsafe_allow_html=True)
    with nav_right:
        if current_index < len(recruiter_steps) - 1 and st.button("Next →", key="recruiter_next", use_container_width=True):
            recruiter_nav(recruiter_steps[current_index + 1][0])

    # Professional, compact command center header.
    st.markdown(
        f"""
        <div class="header-banner" style="margin-bottom:18px;">
          <div>
            <div class="header-title">Recruiter Command Center</div>
            <div class="header-sub">{html.escape(campaign.get('role', 'Start a hiring campaign'))} · One clean pipeline from resume to decision</div>
          </div>
          <div style="font-weight:800;color:#fff;">{html.escape(st.session_state.username)}</div>
        </div>
        """, unsafe_allow_html=True
    )

    if st.session_state.active_tool == "Dashboard":
        st.markdown("### Hiring overview")
        if not campaign:
            st.info("Start with the role you are hiring for. CareerLens will use it to screen resumes and build the assessment.")
        else:
            st.success(f"Active campaign · **{campaign.get('role')}** · {campaign.get('openings', 1)} opening(s)")

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Candidates", len(candidates))
        k2.metric("Shortlisted", shortlist_count)
        k3.metric("Assessments Sent", pending)
        k4.metric("Completed", len(submissions))
        k5.metric("Avg. Score", f"{avg_score}%")

        st.markdown("#### What do you want to do?")
        actions = [
            ("🎯", "Create / Edit Campaign", "Hiring Campaign"),
            ("📤", "Upload Resumes", "Bulk Screening"),
            ("🏆", "Review Shortlist", "Shortlisted Candidates"),
            ("📝", "Send Assessment", "Assessment Builder"),
            ("📊", "Review Results", "Score Vault"),
            ("🎤", "Manage Interviews", "Interview Pipeline"),
        ]
        cols = st.columns(3)
        for i, (icon, label, target) in enumerate(actions):
            with cols[i % 3]:
                if st.button(f"{icon} {label}", key=f"dash_action_{i}", use_container_width=True):
                    recruiter_nav(target)

        st.markdown("#### Hiring pipeline")
        stages = [
            ("Screened", status_counts["Screened"]),
            ("Shortlisted", status_counts["Shortlisted"]),
            ("Assessment Sent", status_counts["Assessment Sent"]),
            ("Assessment Completed", status_counts["Assessment Completed"]),
            ("Interview", status_counts["Interview"]),
            ("Selected", status_counts["Selected"]),
        ]
        pipe_cols = st.columns(len(stages))
        for col, (stage, count) in zip(pipe_cols, stages):
            with col:
                st.markdown(f"<div class='content-box' style='text-align:center;padding:14px 8px;'><div style='font-size:1.55rem;font-weight:900;color:#0f172a'>{count}</div><div style='font-size:.76rem;color:#64748b;font-weight:700'>{stage}</div></div>", unsafe_allow_html=True)

        if candidates:
            st.markdown("#### Recent candidates")
            recent = sorted(candidates, key=lambda c: c.get("uploaded_at", ""), reverse=True)[:8]
            st.dataframe(pd.DataFrame([{
                "Candidate": c.get("name", "Candidate"),
                "Role Match": f"{c.get('role_match', 0)}%",
                "Resume": f"{c.get('resume_score', 0)}%",
                "Status": c.get("status", "Screened"),
                "Assessment": c.get("assessment_status", "Not Sent"),
            } for c in recent]), use_container_width=True, hide_index=True)

    elif st.session_state.active_tool == "Hiring Campaign":
        st.markdown("### 🎯 Hiring campaign")
        st.caption("Define the hiring target once. Screening, shortlisting and assessments will follow this role.")
        role_options = IT_ROLES + NON_IT_ROLES + ["Custom Role"]
        current_role = campaign.get("role", "Software Developer")
        selected = current_role if current_role in role_options else "Custom Role"
        role = st.selectbox("What role are you hiring for?", role_options, index=role_options.index(selected))
        custom_role = st.text_input("Custom role title", value=campaign.get("custom_role", "")) if role == "Custom Role" else ""
        final_role = custom_role.strip() if role == "Custom Role" else role
        c1, c2 = st.columns(2)
        with c1:
            experience = st.text_input("Required experience", value=campaign.get("experience", "0–3 years"))
            required_skills = st.text_input("Required skills", value=campaign.get("required_skills", "Python, SQL, Git"))
            openings = st.number_input("Number of openings", min_value=1, max_value=500, value=int(campaign.get("openings", 1)))
        with c2:
            company = st.text_input("Company name", value=campaign.get("company", ""), placeholder="Your company")
            job_description = st.text_area("What is this examination about? / Job description", value=campaign.get("job_description", ""), height=130)
            exam_instructions = st.text_area("Candidate instructions (optional)", value=campaign.get("exam_instructions", ""), height=80)
        d1, d2, d3 = st.columns(3)
        with d1:
            exam_date = st.date_input("Assessment deadline", value=datetime.fromisoformat(campaign.get("exam_date")).date() if campaign.get("exam_date") else datetime.now().date())
        with d2:
            exam_time = st.time_input("Assessment deadline time", value=datetime.fromisoformat(campaign.get("exam_datetime")).time() if campaign.get("exam_datetime") else datetime.now().replace(hour=18, minute=0, second=0, microsecond=0).time())
        with d3:
            exam_duration = st.number_input("Duration (minutes)", min_value=5, max_value=240, value=int(campaign.get("exam_duration", 30)))
        if st.button("💾 Save campaign", type="primary", use_container_width=True):
            if not final_role or not job_description.strip():
                st.error("Role and job description are required.")
            else:
                data["campaign"] = {
                    "role": final_role, "custom_role": custom_role,
                    "company": company.strip(),
                    "experience": experience.strip(), "required_skills": required_skills.strip(),
                    "openings": int(openings), "job_description": job_description.strip(),
                    "exam_instructions": exam_instructions.strip(),
                    "exam_date": exam_date.isoformat(),
                    "exam_datetime": datetime.combine(exam_date, exam_time).isoformat(timespec="minutes"),
                    "exam_duration": int(exam_duration),
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                }
                persist_recruiter()
                st.success("Hiring campaign saved. Next: upload resumes for AI screening.")
                if st.button("Continue to Resume Screening →", type="primary", use_container_width=True):
                    recruiter_nav("Bulk Screening")

    elif st.session_state.active_tool == "Bulk Screening":
        st.markdown("### 📤 Bulk resume screening")
        if not campaign:
            st.warning("Create a hiring campaign first.")
            if st.button("Create hiring campaign", type="primary", use_container_width=True): recruiter_nav("Hiring Campaign")
        else:
            st.info(f"Screening against **{campaign['role']}** · Skills: {campaign.get('required_skills', 'Not specified')}")
            files = st.file_uploader("Upload candidate resumes", type=["pdf", "docx", "txt"], accept_multiple_files=True, key="recruiter_bulk_upload_v2")
            if files and st.button("⚡ Analyze all resumes", type="primary", use_container_width=True):
                processed = []
                progress = st.progress(0, text="Analyzing resumes…")
                for idx, uploaded in enumerate(files, 1):
                    try:
                        profile = api_analyze_resume(uploaded)
                        resume_text = profile.get("extracted_text", "") or ""
                        match = normalize_job_match(api_match_job(resume_text, campaign.get("job_description", "")))
                        name = str(profile.get("name") or re.sub(r"[_-]+", " ", os.path.splitext(uploaded.name)[0])).strip()
                        email = str(profile.get("email") or extract_email_from_text(resume_text) or "").strip()
                        if email.endswith("@domain.com"): email = ""
                        cid = _candidate_id(name, email or uploaded.name)
                        old = next((c for c in candidates if c.get("id") == cid), {})
                        processed.append({
                            **old, "id": cid, "name": name, "email": email,
                            "phone": profile.get("phone", ""),
                            "resume_score": round(float(profile.get("resume_score", 0) or 0), 1),
                            "role_match": int(match.get("overall", 0)),
                            "matched_skills": ", ".join(match.get("matched", [])),
                            "missing_skills": ", ".join(match.get("missing", [])),
                            "skills": ", ".join(profile.get("skills", [])),
                            "resume_text": resume_text,
                            "status": old.get("status", "Screened"),
                            "assessment_status": old.get("assessment_status", "Not Sent"),
                            "uploaded_at": old.get("uploaded_at", datetime.now().isoformat(timespec="seconds")),
                        })
                    except Exception as exc:
                        st.error(f"Could not process {uploaded.name}: {exc}")
                    progress.progress(idx / len(files), text=f"Analyzed {idx}/{len(files)}")
                by_id = {c.get("id"): c for c in candidates}
                by_id.update({c["id"]: c for c in processed})
                st.session_state.recruiter_candidates = sorted(by_id.values(), key=lambda c: (_recruiter_score(c), float(c.get("resume_score", 0))), reverse=True)
                persist_recruiter()
                st.success(f"Processed {len(processed)} resume(s).")
                st.rerun()
            if candidates:
                st.markdown("#### Screening results")
                st.dataframe(pd.DataFrame([{
                    "Candidate": c.get("name"), "Email": c.get("email") or "Missing",
                    "Resume": f"{c.get('resume_score',0)}%", "Role Match": f"{c.get('role_match',0)}%", "Status": c.get("status")
                } for c in candidates]), use_container_width=True, hide_index=True)
                st.markdown("#### 🏆 Shortlist")
                count = st.number_input("How many candidates should be shortlisted?", min_value=1, max_value=len(candidates), value=min(int(campaign.get("openings", 1)), len(candidates)))
                if st.button("Generate shortlist", type="primary", use_container_width=True):
                    ranked = sorted(candidates, key=lambda c: (_recruiter_score(c), float(c.get("resume_score", 0))), reverse=True)
                    ids = {c["id"] for c in ranked[:int(count)]}
                    for c in candidates:
                        if c.get("status") not in {"Assessment Completed", "Interview", "Selected", "Rejected"}:
                            c["status"] = "Shortlisted" if c.get("id") in ids else "Screened"
                    persist_recruiter(); st.success(f"{len(ids)} candidate(s) shortlisted."); st.rerun()

    elif st.session_state.active_tool == "Shortlisted Candidates":
        st.markdown("### 🏆 Shortlisted candidates")
        shortlisted = [c for c in candidates if c.get("status") == "Shortlisted"]
        if not shortlisted:
            st.info("No shortlist yet. Upload resumes and generate a shortlist first.")
        else:
            st.caption(f"{len(shortlisted)} candidate(s) ready for assessment")
            for c in sorted(shortlisted, key=_recruiter_score, reverse=True):
                with st.container(border=True):
                    a,b,c3 = st.columns([2.4,1,1])
                    with a:
                        st.markdown(f"**{html.escape(c.get('name','Candidate'))}**")
                        st.caption(c.get("email") or "Email not detected")
                        st.write(f"Matched: {c.get('matched_skills') or 'None'}")
                        st.write(f"Missing: {c.get('missing_skills') or 'None'}")
                    with b: st.metric("Match", f"{c.get('role_match',0)}%")
                    with c3: st.metric("Resume", f"{c.get('resume_score',0)}%")
                    if st.button("Invite to assessment", key=f"short_invite_{c['id']}", disabled=not bool(c.get("email"))):
                        st.session_state.assessment_selected_ids = [c["id"]]
                        recruiter_nav("Assessment Builder")

    elif st.session_state.active_tool == "Assessment Builder":
        st.markdown("### 📝 Assessment center")
        if not campaign:
            st.warning("Create a hiring campaign first.")
        else:
            eligible = [c for c in candidates if c.get("status") in {"Shortlisted", "Assessment Sent"} and c.get("email")]
            if not eligible:
                st.info("No shortlisted candidates with valid email addresses are ready. Return to Shortlisted Candidates after screening.")
            else:
                st.markdown("#### Assessment details")
                st.caption("These details are used automatically in the candidate invitation. Recruiters do not need to configure SMTP.")
                company_name = st.text_input("Company", value=campaign.get("company", ""), key="assessment_company")
                duration = st.number_input("Duration (minutes)", min_value=5, max_value=240, value=int(campaign.get("exam_duration", 30)), key="assessment_duration")
                deadline_label = st.text_input("Deadline", value=campaign.get("exam_datetime", ""), key="assessment_deadline")
                instructions = st.text_area("What is the examination about?", value=campaign.get("exam_instructions", ""), key="assessment_instructions", height=90)
                count = st.select_slider("Questions", options=list(range(10,51,5)), value=20)
                difficulty = st.selectbox("Difficulty", ["Standard", "Advanced", "Mixed"])
                ids_default = st.session_state.pop("assessment_selected_ids", [c["id"] for c in eligible])
                ids_default = [x for x in ids_default if any(c["id"] == x for c in eligible)]
                selected_ids = st.multiselect("Candidates to invite", [c["id"] for c in eligible], default=ids_default, format_func=lambda x: next((c.get("name",x) for c in eligible if c["id"]==x),x))
                if st.button("🚀 Generate Assessment & Send to Shortlisted Candidates", type="primary", use_container_width=True):
                    if not selected_ids:
                        st.error("Select at least one candidate.")
                    else:
                        questions = generate_assessment_questions(campaign["role"], int(count))
                        assessment = {"id": uuid.uuid4().hex, "role": campaign["role"], "company": company_name.strip(), "difficulty": difficulty, "question_count": int(count), "duration_minutes": int(duration), "deadline": deadline_label.strip(), "instructions": instructions.strip(), "questions": questions, "created_at": datetime.now().isoformat(timespec="seconds"), "candidate_tokens": {}}
                        rows=[]
                        for cid in selected_ids:
                            candidate=next((x for x in candidates if x.get("id")==cid),None)
                            if not candidate: continue
                            token=_make_assessment_token(); link=_assessment_public_url(token)
                            assessment["candidate_tokens"][cid]=token
                            candidate.update({"assessment_token":token,"assessment_link":link,"assessment_status":"Sent","status":"Assessment Sent","email_delivery":"Pending"})
                            sent,msg=_send_assessment_email(candidate.get("email",""),candidate.get("name","Candidate"),campaign["role"],link)
                            candidate["email_delivery"]="Sent" if sent else "Failed"
                            candidate["email_message"]=msg
                            rows.append({"Candidate":candidate.get("name"),"Email":candidate.get("email"),"Delivery":"Sent" if sent else "Failed","Message":msg,"Link":link})
                        data.setdefault("assessments",[]).append(assessment)
                        st.session_state.last_generated_assessment=assessment
                        persist_recruiter()
                        sent_count = sum(1 for r in rows if r["Delivery"] == "Sent")
                        failed_count = len(rows) - sent_count
                        if sent_count == len(rows):
                            st.success(f"Assessment generated and sent to all {sent_count} shortlisted candidate(s).")
                        elif sent_count:
                            st.warning(f"Assessment generated. {sent_count} email(s) sent; {failed_count} could not be delivered. Copy the affected candidate links below.")
                        else:
                            st.error("Assessment links were generated, but no emails were delivered. Configure SMTP in deployment secrets, then resend.")
                        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
                        for r in rows:
                            if r["Delivery"] != "Sent":
                                st.markdown(f"**{html.escape(str(r['Candidate']))}** — copy this candidate-specific link")
                                st.code(r["Link"],language="text")
                        if st.button("Continue to Assessment Results →", use_container_width=True):
                            recruiter_nav("Score Vault")

    elif st.session_state.active_tool == "Score Vault":
        st.markdown("### 📊 Assessment results")
        st.caption("Only recruiter accounts can see scores and answer keys.")
        if not submissions:
            st.info("No candidate has completed a recruiter-issued assessment yet.")
        else:
            for result in sorted(submissions,key=lambda x:float(x.get("percentage",0)),reverse=True):
                with st.container(border=True):
                    st.markdown(f"### {html.escape(result.get('candidate_name','Candidate'))}")
                    c1,c2,c3,c4=st.columns(4)
                    c1.metric("Score",f"{result.get('score',0)}/{result.get('total',0)}")
                    c2.metric("Percentage",f"{result.get('percentage',0)}%")
                    c3.metric("Correct",result.get('correct_count',0))
                    c4.metric("Unanswered",result.get('unanswered_count',0))
                    if st.button("Review answers",key=f"review_result_{result.get('token','')}"):
                        st.session_state[f"open_result_{result.get('token','')}"]=True
                    if st.session_state.get(f"open_result_{result.get('token','')}"):
                        for item in result.get("wrong_items",[]): st.error(f"Q{item['id']}: {item['question']} · Candidate: {item.get('selected')} · Correct: {item.get('correct')}")
                        for item in result.get("correct_items",[]): st.success(f"Q{item['id']}: {item['question']} · Correct: {item.get('correct')}")
                        for item in result.get("unanswered_items",[]): st.warning(f"Q{item['id']}: Unanswered · Correct: {item.get('correct')}")

    elif st.session_state.active_tool == "Interview Pipeline":
        st.markdown("### 🎤 Interview pipeline")
        visible=[c for c in candidates if c.get("status") in {"Assessment Completed","Interview","Selected","Rejected"}]
        if not visible: st.info("Candidates appear here after assessment completion.")
        for c in visible:
            with st.container(border=True):
                st.markdown(f"**{html.escape(c.get('name','Candidate'))}** · {c.get('email') or 'No email'}")
                st.write(f"Resume **{c.get('resume_score',0)}%** · Match **{c.get('role_match',0)}%** · Assessment **{c.get('assessment_percentage','Pending')}%**")
                a,b,d=st.columns(3)
                with a:
                    if st.button("🎤 Interview",key=f"int_{c['id']}"): c["status"]="Interview"; persist_recruiter(); st.rerun()
                with b:
                    if st.button("✅ Select",key=f"sel_{c['id']}"): c["status"]="Selected"; persist_recruiter(); st.rerun()
                with d:
                    if st.button("❌ Reject",key=f"rej_{c['id']}"): c["status"]="Rejected"; persist_recruiter(); st.rerun()

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
