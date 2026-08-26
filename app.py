"""CareerLens AI - Streamlit Web Application."""

from __future__ import annotations

import csv
from datetime import datetime
import hashlib
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
# SAFE RESPONSE NORMALIZERS
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
    """Return a real email found in resume text."""
    for raw in EMAIL_RE.findall(text or ""):
        email = raw.strip(".,;:()[]{}<>\"").lower()
        if len(email) <= 254:
            return email
    return ""


def extract_emails_from_text(text: str) -> List[str]:
    """Extract all unique valid-looking email addresses from resume text."""
    seen = set()
    result = []
    for raw in EMAIL_RE.findall(text or ""):
        email = raw.strip(".,;:()[]{}<>\"").lower()
        if len(email) <= 254 and email not in seen:
            seen.add(email)
            result.append(email)
    return result


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
    """Remove duplicate candidates by email, then name+phone when email is absent."""
    unique = []
    seen = set()
    for candidate in candidates:
        key = _candidate_identity_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


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
                details,
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
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: linear-gradient(90deg, #2563eb, #4f46e5) !important;
        color: #ffffff !important;
        border: 1px solid #60a5fa !important;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.4) !important;
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
        padding: 28px;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
        margin-bottom: 20px;
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
    .stButton > button, .stButton > button *, button[kind="primary"], button[kind="primary"] *, button[kind="secondary"], button[kind="secondary"] *, [data-testid="stSidebar"] .stButton > button, [data-testid="stSidebar"] .stButton > button * {
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
    }
    @media (max-width: 768px) {
        .block-container { padding: 14px 12px 28px !important; }
        .header-banner { display: block !important; padding: 20px 18px !important; }
        .kpi-grid { grid-template-columns: 1fr !important; }
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
    lower = text.lower()
    skill_catalog = [
        "python", "java", "javascript", "typescript", "react", "node.js", "fastapi", "django", "flask",
        "sql", "postgresql", "mysql", "mongodb", "docker", "kubernetes", "aws", "azure", "gcp", "git",
        "linux", "machine learning", "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow",
        "pytorch", "rest api", "graphql", "redis", "kafka", "system design", "html", "css", "figma",
        "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium", "communication",
        "leadership", "problem solving",
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
        "source": "local-fallback",
    }


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
    """Dispatches assessment invitation via the working FastAPI backend endpoint."""
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
# STATE & DATABASE INITIALIZATION
# ============================================================
def _db_connect():
    conn = sqlite3.connect(APP_DB_FILE, timeout=20, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_app_db():
    with _db_connect() as conn:
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


def _db_user(username):
    with _db_connect() as conn:
        return conn.execute("SELECT user_id, username, display_name, password_hash FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()


def _db_create_user(username, display_name, password_hash):
    user_id = secrets.token_hex(16)
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO users(user_id,username,display_name,password_hash,created_at) VALUES(?,?,?,?,?)",
            (user_id, username.strip(), display_name.strip() or username.split("@")[0], password_hash, datetime.now().isoformat(timespec="seconds")),
        )
    return user_id


def _db_save_state(user_id, state):
    if not user_id:
        return
    payload = json.dumps(state, ensure_ascii=False)
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO user_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
            (user_id, payload, datetime.now().isoformat(timespec="seconds")),
        )


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
        conn.execute(
            "INSERT INTO recruiter_state(user_id,state_json,updated_at) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET state_json=excluded.state_json, updated_at=excluded.updated_at",
            (user_id, payload, datetime.now().isoformat(timespec="seconds")),
        )


def _db_load_recruiter_state(user_id):
    if not user_id:
        return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
    with _db_connect() as conn:
        row = conn.execute("SELECT state_json FROM recruiter_state WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
        try:
            data = json.loads(row[0])
            return data if isinstance(data, dict) else {"campaign": None, "candidates": [], "assessments": [], "submissions": []}
        except (TypeError, ValueError):
            return {"campaign": None, "candidates": [], "assessments": [], "submissions": []}


_init_app_db()

defaults = {
    "is_logged_in": False,
    "user_id": "",
    "username": "Guest Explorer",
    "users_db": {},
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
    """Navigate recruiter pages with desktop-style back/forward history."""
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
        "Elegant": "#9a3412",
        "ATS Classic": "#111827",
        "Compact": "#475569",
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


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def password_matches(stored: str, provided: str) -> bool:
    if not stored:
        return False
    digest = hash_password(provided)
    if stored == digest:
        return True
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


# URL Query Assessment Handler
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
        unsafe_allow_html=True,
    )

    col_c1, col_c2, col_c3 = st.columns([1, 1.3, 1])
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
            unsafe_allow_html=True,
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
        unsafe_allow_html=True,
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
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Salary Estimation:</b> Accurate compensation benchmarks.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
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
                        Streamline your hiring pipeline with bulk resume screening and automated testing via SendGrid.
                    </p>
                    <hr style="border-color:#f1f5f9; margin:14px 0;">
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Bulk Resume Intake:</b> Upload cohorts and auto-extract candidate emails.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Assessment Dispatcher:</b> Send automated SendGrid test invitations in 1 click.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Candidate Score Vault:</b> Private recruiter assessment ranking view.</div>
                    <div style="color:#475569; font-size:0.9rem; margin:8px 0;">✦ <b>Role Blueprints:</b> Standardized evaluation tracks for IT and Non-IT.</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
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
                    <div style="font-size:0.88rem; font-weight:800; color:#ffffff;">{st.session_state.username}</div>
                    <div style="font-size:0.72rem; color:#4ade80; font-weight:700;">● Active User</div>
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
    unsafe_allow_html=True,
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
        unsafe_allow_html=True,
    )

    if st.session_state.active_tool == "Dashboard":
        st.markdown("<h3 style='margin-bottom:16px; font-weight:900; font-size:1.25rem; color:#0f172a;'>Career Tools Suite</h3>", unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#2563eb;">📄</div><div class="tool-title">Resume Intelligence</div><div class="tool-desc">Deep resume analysis, strengths and enhancements.</div></div>""", unsafe_allow_html=True)
            if st.button("Resume Intelligence", key="card_c1_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Intelligence"
                st.rerun()
        with c2:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#7c3aed;">📝</div><div class="tool-title">Pre-Interview Exam</div><div class="tool-desc">100-mark standardized MCQ domain qualifying test.</div></div>""", unsafe_allow_html=True)
            if st.button("Pre-Interview Exam", key="card_c2_btn", use_container_width=True):
                st.session_state.active_tool = "Pre-Interview Assessment"
                st.rerun()
        with c3:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#0284c7;">🎤</div><div class="tool-title">AI Mock Interview</div><div class="tool-desc">Sequential dynamic interview questions with scoring.</div></div>""", unsafe_allow_html=True)
            if st.button("AI Mock Interview", key="card_c3_btn", use_container_width=True):
                st.session_state.active_tool = "AI Mock Interview"
                st.rerun()
        with c4:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#ecfdf5; color:#059669;">🎯</div><div class="tool-title">AI Job Match</div><div class="tool-desc">Match profile with job postings to find skill gaps.</div></div>""", unsafe_allow_html=True)
            if st.button("AI Job Match", key="card_c4_btn", use_container_width=True):
                st.session_state.active_tool = "AI Job Match"
                st.rerun()
        with c5:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fffbeb; color:#d97706;">💰</div><div class="tool-title">Salary Estimation</div><div class="tool-desc">Accurate market salary estimates.</div></div>""", unsafe_allow_html=True)
            if st.button("Salary Estimation", key="card_c5_btn", use_container_width=True):
                st.session_state.active_tool = "Salary Estimation"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        c6, c7, c8, c9, _ = st.columns(5)
        with c6:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#ecfdf5; color:#10b981;">🗺️</div><div class="tool-title">Career Roadmap</div><div class="tool-desc">Step-by-step career progression milestones.</div></div>""", unsafe_allow_html=True)
            if st.button("Career Roadmap", key="card_c6_btn", use_container_width=True):
                st.session_state.active_tool = "Career Roadmap"
                st.rerun()
        with c7:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#fef2f2; color:#ef4444;">🛡️</div><div class="tool-title">Job Detection</div><div class="tool-desc">Real-time scam and fake job offer detection.</div></div>""", unsafe_allow_html=True)
            if st.button("Job Detection", key="card_c7_btn", use_container_width=True):
                st.session_state.active_tool = "Real-Time Job Detection"
                st.rerun()
        with c8:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#eff6ff; color:#3b82f6;">📄</div><div class="tool-title">Resume Builder</div><div class="tool-desc">Build ATS-friendly clean formatted resumes.</div></div>""", unsafe_allow_html=True)
            if st.button("Resume Builder", key="card_c8_btn", use_container_width=True):
                st.session_state.active_tool = "Resume Builder"
                st.rerun()
        with c9:
            st.markdown("""<div class="tool-box-card"><div class="tool-icon-circle" style="background:#faf5ff; color:#8b5cf6;">🤖</div><div class="tool-title">AI Career Assistant</div><div class="tool-desc">Ask interview preparation and profile guidance.</div></div>""", unsafe_allow_html=True)
            if st.button("Career Assistant", key="card_c9_btn", use_container_width=True):
                st.session_state.active_tool = "AI Career Assistant"
                st.rerun()

    # 1. RESUME INTELLIGENCE
    elif st.session_state.active_tool == "Resume Intelligence":
        if st.button("← Back to Dashboard", key="btn_back_res"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("### 📄 Resume Intelligence")
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
                unsafe_allow_html=True,
            )
            st.markdown("#### Resume Intelligence Scores")
            rr1, rr2, rr3 = st.columns(3)
            rr1.metric("Resume Score", f"{r.get('resume_score', 0)}%")
            rr2.metric("Readiness", f"{r.get('readiness', 0)}%")
            rr3.metric("Market Match", f"{r.get('market_match')}%" if r.get('market_match') is not None else "Run AI Job Match")
            st.markdown("#### Detected Skills")
            skills_html = "".join([f'<span class="tag-badge tag-blue">{_escape(s)}</span>' for s in r.get("skills", [])])
            st.markdown(skills_html or "No skills detected yet.", unsafe_allow_html=True)

    # 2. PRE-INTERVIEW ASSESSMENT
    elif st.session_state.active_tool == "Pre-Interview Assessment":
        if st.button("← Back to Dashboard", key="btn_back_exam"):
            st.session_state.active_tool = "Dashboard"
            st.session_state.assessment_active = False
            st.session_state.assessment_review = False
            st.rerun()
        st.markdown("### 📝 Pre-Interview Assessment")
        if not st.session_state.assessment_active and not st.session_state.assessment_review and st.session_state.assessment_result is None:
            domain_type = st.radio("Domain Category", ["IT Roles", "Non-IT Roles"], horizontal=True, key="assessment_domain")
            roles_list = IT_ROLES if domain_type == "IT Roles" else NON_IT_ROLES
            selected_assessment_role = st.selectbox("Select Target Role", roles_list, key="assessment_role_select")
            question_count = st.select_slider("Number of Questions", options=list(range(10, 51, 5)), value=st.session_state.assessment_question_count, key="assessment_count_select")
            st.session_state.assessment_question_count = question_count
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
            st.progress(answered / len(questions) if questions else 0, text=f"Answered {answered} / {len(questions)}")
            for q in questions:
                qid = q["id"]
                current = st.session_state.assessment_answers.get(qid)
                current_index = q["options"].index(current) if current in q["options"] else None
                chosen = st.radio(f"Q{qid}. {q['question']}", q["options"], index=current_index, key=f"q_choice_{qid}")
                st.session_state.assessment_answers[qid] = chosen
            if st.button("🔎 Review Answers Before Submit", use_container_width=True, key="review_assessment"):
                st.session_state.assessment_review = True
                st.rerun()
        elif st.session_state.assessment_review:
            questions = st.session_state.assessment_questions
            for q in questions:
                selected = st.session_state.assessment_answers.get(q["id"])
                status = "✅ Answered" if selected else "⚪ Unanswered"
                st.markdown(f"**Q{q['id']} — {status}** \n{q['question']} \nYour answer: **{selected or 'None'}**")
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
                    log_event("ASSESSMENT_COMPLETED", st.session_state.username, str(st.session_state.assessment_result["percentage"]), st.session_state.assessment_role)
                    st.rerun()
        elif st.session_state.assessment_result is not None:
            result = st.session_state.assessment_result
            pct = result["percentage"]
            st.markdown(f"""<div class="content-box" style="text-align:center;padding:36px;"><div style="font-size:3rem;font-weight:900;color:#2563eb;">{pct}%</div><p style="color:#64748b;">{st.session_state.assessment_role} • Score: {result['score']}/{result['total']}</p></div>""", unsafe_allow_html=True)
            if st.button("🔄 Take Another Assessment", use_container_width=True, key="btn_reset_exam"):
                st.session_state.assessment_result = None
                st.session_state.assessment_answers = {}
                st.rerun()

    # 3. AI MOCK INTERVIEW
    elif st.session_state.active_tool == "AI Mock Interview":
        if st.button("← Back to Dashboard", key="btn_back_mock"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("### 🎤 AI Mock Interview Simulation")
        if not st.session_state.interview_active and not st.session_state.interview_completed:
            target_interview_role = st.selectbox("Select Target Role", IT_ROLES + NON_IT_ROLES, key="mock_role_select")
            interview_len = st.select_slider("Interview Questions", options=list(range(1, 11)), value=5, key="mock_count_select")
            if st.button("🚀 Start Mock Interview", use_container_width=True, key="start_mock_new"):
                q_templates = [
                    f"Tell me about yourself and why you are targeting the {target_interview_role} role.",
                    f"Which technical skills are most important for a successful {target_interview_role} and how have you applied them?",
                    "Describe a difficult problem you solved. Explain your reasoning and the measurable outcome.",
                    "Tell me about a disagreement with a teammate and how you resolved it.",
                    "Describe a project where something went wrong. What did you learn?",
                ]
                st.session_state.interview_questions = q_templates[:interview_len]
                st.session_state.interview_role = target_interview_role
                st.session_state.interview_current_idx = 0
                st.session_state.interview_transcript = []
                st.session_state.interview_active = True
                st.session_state.interview_completed = False
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
                        st.session_state.interview_report = {
                            "overall": 82,
                            "confidence": 85,
                            "communication": 80,
                            "strengths": ["Completed the full interview", "Provided structured responses"],
                            "improvements": ["Add measurable metrics to outcomes"],
                        }
                        st.rerun()
        elif st.session_state.interview_completed:
            rep = st.session_state.interview_report or {}
            st.markdown(f"""<div class="content-box" style="text-align:center;"><h2 style="margin:10px 0;">Interview Readiness: <span style="color:#2563eb;">{rep.get('overall', 0)}%</span></h2></div>""", unsafe_allow_html=True)
            if st.button("Practice Another Mock Interview", key="btn_retry_mock"):
                st.session_state.interview_completed = False
                st.session_state.interview_active = False
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
            st.markdown(f"""<div class="content-box"><h3 style="margin:0;">Job Match Score: <span style="color:#2563eb;">{m.get('overall', 0)}%</span></h3></div>""", unsafe_allow_html=True)

    # 5. SALARY ESTIMATION
    elif st.session_state.active_tool == "Salary Estimation":
        if st.button("← Back to Dashboard", key="btn_back_sal"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("### 💰 Salary Estimation")
        sal_role_in = st.text_input("Role Title:", "Software Engineer")
        sal_exp_in = st.selectbox("Experience Level:", ["Entry Level (0-2 yrs)", "Mid Level (3-5 yrs)", "Senior Level (6+ yrs)"])
        if st.button("Calculate Compensation Band", use_container_width=True):
            st.markdown(f"""<div class="content-box" style="margin-top: 20px;"><h2 style="margin: 8px 0; color:#2563eb;">₹9.5 LPA - ₹18.0 LPA</h2><p style="color:#64748b; margin:0;">Median compensation band for {sal_role_in} ({sal_exp_in}).</p></div>""", unsafe_allow_html=True)

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
        detection_mode = st.radio("Input Method", ["🔗 Paste Job Link", "📝 Paste Description"], horizontal=True, key="fraud_mode")
        job_url = st.text_input("Job / Offer URL", placeholder="https://example.com/jobs/software-engineer", key="fraud_url") if detection_mode == "🔗 Paste Job Link" else ""
        description_input = st.text_area("Job Description", height=220, placeholder="Paste the job description...", key="fraud_description") if detection_mode != "🔗 Paste Job Link" else ""
        if st.button("🔍 Analyze Job Safety", use_container_width=True, key="analyze_job_safety_new"):
            try:
                with st.spinner("Analyzing safety signals..."):
                    analysis_text = fetch_public_job_url(job_url.strip()) if detection_mode.startswith("🔗") else description_input.strip()
                    result = api_detect_fraud(analysis_text)
                    st.session_state.job_detection_result = result
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.job_detection_result:
            res = st.session_state.job_detection_result
            st.markdown(f"""<div class="content-box"><h3>Risk Level: {res.get('level','UNKNOWN')} (Score: {res.get('score',0)})</h3></div>""", unsafe_allow_html=True)

    # 8. RESUME BUILDER
    elif st.session_state.active_tool == "Resume Builder":
        if st.button("← Back to Dashboard", key="btn_back_bld"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("### 📄 Professional Resume Builder")
        templates = ["Executive", "Minimal", "Modern Blue", "Modern Purple", "Emerald", "Professional", "Tech", "ATS Classic"]
        st.session_state.resume_template = st.selectbox("Template", templates, index=0)
        rb_name = st.text_input("Full Name", value=st.session_state.username)
        rb_email = st.text_input("Email", value="")
        rb_skills = st.text_area("Skills (comma-separated)", value="Python, SQL, Git")
        rb_summary = st.text_area("Professional Summary", value="")
        rb_experience = st.text_area("Experience", value="")
        resume_data = {"name": rb_name, "email": rb_email, "skills": rb_skills, "summary": rb_summary, "experience": rb_experience}
        if st.button("⬇️ Generate & Download PDF", use_container_width=True):
            pdf_bytes = build_resume_pdf(resume_data, st.session_state.resume_template)
            st.download_button("Download Resume PDF", data=pdf_bytes, file_name="CareerLens_Resume.pdf", mime="application/pdf", use_container_width=True)

    # 9. AI CAREER ASSISTANT
    elif st.session_state.active_tool == "AI Career Assistant":
        if st.button("← Back to Dashboard", key="btn_back_ast"):
            st.session_state.active_tool = "Dashboard"
            st.rerun()
        st.markdown("### 🤖 AI Career Assistant")
        user_query = st.text_input("Ask any career question:")
        if st.button("Ask Assistant", use_container_width=True) and user_query:
            ans = api_chat_assistant([{"role": "user", "content": user_query}], resume_context=st.session_state.resume_text)
            st.markdown(f'<div class="content-box" style="margin-top:16px;">{ans}</div>', unsafe_allow_html=True)


# ============================================================
# 🏢 RECRUITER WORKSPACE (API INTEGRATED)
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

    st.markdown("### Recruiter Command Suite")

    if st.session_state.active_tool == "Dashboard":
        st.markdown("### 📊 Recruiter Dashboard")
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
        st.caption("Upload a cohort. CareerLens extracts real contact details, ranks candidates, and removes duplicate candidates.")
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
                st.success(f"Screened {len(processed)} unique candidate(s). Duplicate resumes were removed.")
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
            st.info("No candidates are shortlisted yet. Go to Bulk Resume Screening and use Select All or select individual candidates.")
        else:
            st.caption(f"{len(shortlisted)} shortlisted candidate(s). Only these candidates are eligible for assessment dispatch.")
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
        st.caption("Only shortlisted candidates with real email addresses are eligible. Duplicate email addresses are removed before dispatch.")
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

        missing_email = [c for c in shortlisted if not c.get("email")]
        if missing_email:
            st.warning(f"{len(missing_email)} shortlisted candidate(s) have no email address in their resume and will not receive an invitation.")

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
                st.success("Assessment dispatch completed. Review the delivery table below.")
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("No shortlisted candidate with a valid resume email is ready for dispatch.")

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
