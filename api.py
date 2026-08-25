"""CareerLens AI FastAPI backend.

This module intentionally contains API routes only. The Streamlit UI belongs in app.py.
Run with: uvicorn api:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import io
import ipaddress
import os
import re
import socket
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from email_dispatcher import send_html_email

try:
    from PyPDF2 import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None

try:
    from docx import Document
except ImportError:  # pragma: no cover
    Document = None

APP_NAME = "CareerLens AI API"
APP_VERSION = "3.0.0"
MAX_FILE_BYTES = int(os.getenv("MAX_RESUME_BYTES", str(10 * 1024 * 1024)))
MAX_BULK_FILES = int(os.getenv("MAX_BULK_FILES", "50"))

SKILLS = [
    "python", "java", "javascript", "typescript", "react", "node.js", "fastapi",
    "django", "flask", "sql", "postgresql", "mysql", "mongodb", "docker",
    "kubernetes", "aws", "azure", "gcp", "git", "linux", "machine learning",
    "deep learning", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
    "rest api", "graphql", "redis", "kafka", "system design", "html", "css",
    "figma", "excel", "power bi", "tableau", "cybersecurity", "testing", "selenium",
    "communication", "leadership", "problem solving", "data analysis", "statistics",
]

RISK_PATTERNS = {
    "wire transfer": "Requests for wire transfers or direct money movement.",
    "registration fee": "Upfront registration or application fees.",
    "processing fee": "Upfront processing fees.",
    "telegram": "Telegram-only recruitment communication.",
    "whatsapp": "WhatsApp-only recruitment communication.",
    "crypto": "Cryptocurrency payment/request.",
    "gift card": "Gift-card payment request.",
    "no interview": "No-interview hiring claim.",
    "pay to apply": "Payment required to apply.",
    "urgent payment": "Urgent payment pressure.",
}

EMAIL_RE = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
PHONE_RE = re.compile(r"(?:\+?\d[\d .()\-]{8,}\d)")
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _cors_origins() -> List[str]:
    raw = os.getenv("CORS_ORIGINS", "*").strip()
    return [item.strip() for item in raw.split(",") if item.strip()] or ["*"]


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="CareerLens AI career intelligence and recruiter API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class JobMatchRequest(BaseModel):
    resume_text: str = Field(..., min_length=1, max_length=200_000)
    job_description: str = Field(..., min_length=1, max_length=200_000)


class FraudRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200_000)


class RoadmapRequest(BaseModel):
    resume_text: str = Field("", max_length=200_000)
    target_role: str = Field(..., min_length=1, max_length=200)


class ChatRequest(BaseModel):
    messages: List[Dict[str, Any]] = Field(default_factory=list, max_length=50)
    resume_context: str = Field("", max_length=100_000)


class EmailRequest(BaseModel):
    to_email: str = Field(..., min_length=3, max_length=254)
    subject: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=100_000)


def _extract_text(filename: str, data: bytes) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Unsupported resume type. Use PDF, DOCX, or TXT.")

    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail=f"Resume exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.")

    try:
        if extension == ".pdf":
            if PdfReader is None:
                raise HTTPException(status_code=500, detail="PDF support is not installed on the server.")
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        elif extension == ".docx":
            if Document is None:
                raise HTTPException(status_code=500, detail="DOCX support is not installed on the server.")
            document = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in document.paragraphs)
        else:
            text = data.decode("utf-8", errors="ignore")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The uploaded resume could not be read.") from exc

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise HTTPException(status_code=422, detail="The uploaded resume contains no readable text.")
    return text[:200_000]


def _extract_email(text: str) -> str:
    for match in EMAIL_RE.findall(text or ""):
        email = match.strip(".,;:()[]{}<>\"").lower()
        if len(email) <= 254:
            return email
    return ""


def _extract_phone(text: str) -> str:
    match = PHONE_RE.search(text or "")
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else ""


def _extract_name(text: str, filename: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    for line in lines[:12]:
        if not line or "@" in line or PHONE_RE.search(line):
            continue
        if len(line) > 70 or any(token in line.lower() for token in ("resume", "curriculum vitae", "objective", "summary", "skills")):
            continue
        words = line.split()
        if 2 <= len(words) <= 5 and all(re.fullmatch(r"[A-Za-z.'-]+", word) for word in words):
            return line.title()
    fallback = re.sub(r"[_-]+", " ", Path(filename or "Candidate").stem).strip()
    return fallback.title() if fallback else "Candidate"


def _skill_set(text: str) -> set[str]:
    lower = (text or "").lower()
    return {skill for skill in SKILLS if skill in lower}


def _resume_analysis(text: str, filename: str) -> Dict[str, Any]:
    lower = text.lower()
    skills = sorted(_skill_set(text))
    words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
    sections = ["experience", "education", "projects", "skills", "certifications"]
    section_hits = sum(1 for section in sections if section in lower)
    score = min(100, max(35, 35 + min(len(words) // 35, 35) + section_hits * 6 + min(len(skills) * 2, 20)))
    readiness = min(100, max(30, score - 3 + min(len(skills), 10)))
    return {
        "name": _extract_name(text, filename),
        "email": _extract_email(text),
        "phone": _extract_phone(text),
        "experience": "Detected from resume" if "experience" in lower else "Not detected",
        "resume_score": score,
        "readiness": readiness,
        "market_match": None,
        "skills": skills,
        "missing_skills": [],
        "strengths": [
            "Skills detected" if skills else "Resume text extracted",
            "Structured sections detected" if section_hits >= 3 else "Basic resume structure detected",
        ],
        "recommendations": [
            "Add measurable achievements and outcomes.",
            "Tailor skills and projects to the target role.",
            "Keep formatting ATS-friendly and concise.",
        ],
        "extracted_text": text,
        "source": "local-api",
    }


def _match(resume_text: str, job_description: str) -> Dict[str, Any]:
    matrix = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), max_features=8000).fit_transform(
        [resume_text, job_description]
    )
    similarity = float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0])
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
        "summary": "Semantic and skill analysis completed.",
        "experience_alignment": "Strong Alignment" if overall >= 75 else "Moderate Alignment" if overall >= 50 else "Needs Improvement",
        "source": "local-api",
    }


def _safe_public_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        for item in socket.getaddrinfo(parsed.hostname, None):
            ip = ipaddress.ip_address(item[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except (ValueError, socket.gaierror):
        return False


def _candidate_key(candidate: Dict[str, Any]) -> str:
    email = (candidate.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    name = re.sub(r"\W+", "", (candidate.get("name") or "").lower())
    phone = re.sub(r"\D+", "", (candidate.get("phone") or ""))
    return f"identity:{name}|{phone}"


def _dedupe_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    unique: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": APP_NAME, "version": APP_VERSION}


@app.get("/")
def root() -> Dict[str, str]:
    return {"service": APP_NAME, "status": "running", "docs": "/docs"}


@app.post("/api/resume/analyze")
async def analyze_resume(file: UploadFile = File(...)) -> Dict[str, Any]:
    data = await file.read()
    text = _extract_text(file.filename or "resume.txt", data)
    return _resume_analysis(text, file.filename or "resume.txt")


@app.post("/api/job/match")
def match_job(payload: JobMatchRequest) -> Dict[str, Any]:
    try:
        return _match(payload.resume_text, payload.job_description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unable to calculate the job match from the supplied text.") from exc


@app.post("/api/job/fraud")
def detect_fraud(payload: FraudRequest) -> Dict[str, Any]:
    lower = payload.text.lower()
    matched = [description for phrase, description in RISK_PATTERNS.items() if phrase in lower]
    score = min(100, len(matched) * 22)
    return {
        "score": score,
        "level": "HIGH RISK" if score >= 55 else "MEDIUM RISK" if score >= 25 else "LOW RISK",
        "signals": len(matched),
        "signal_details": matched,
        "source": "local-api",
    }


@app.post("/api/career/roadmap")
def career_roadmap(payload: RoadmapRequest) -> Dict[str, Any]:
    skills = sorted(_skill_set(payload.resume_text))
    return {
        "steps": [
            f"Strengthen the core technical foundations expected for {payload.target_role}.",
            "Build an end-to-end portfolio project with measurable outcomes.",
            "Rewrite resume achievements around impact, metrics, and ownership.",
            "Practice role-specific technical, behavioral, and system-design questions.",
        ],
        "current_skills": skills,
        "target_role": payload.target_role,
        "source": "local-api",
    }


@app.post("/api/chat/ask")
def chat_assistant(payload: ChatRequest) -> Dict[str, str]:
    latest = ""
    for message in reversed(payload.messages):
        if isinstance(message, dict) and message.get("role") == "user":
            latest = str(message.get("content", "")).strip()
            break
    if latest:
        reply = (
            "CareerLens AI recommends focusing on measurable outcomes, role-relevant skills, "
            "portfolio evidence, and targeted interview preparation. "
            f"For your question, start by breaking the problem into clear actions: {latest[:400]}"
        )
    else:
        reply = "Tell me what career, resume, job-match, or interview problem you want to solve."
    return {"reply": reply, "source": "local-api"}


@app.post("/api/recruiter/screen")
async def recruiter_screen(
    job_description: str = "",
    files: List[UploadFile] = File(...),
) -> List[Dict[str, Any]]:
    if len(files) > MAX_BULK_FILES:
        raise HTTPException(status_code=413, detail=f"A maximum of {MAX_BULK_FILES} resumes can be processed per batch.")
    if not job_description.strip():
        raise HTTPException(status_code=422, detail="Job description is required for bulk screening.")

    candidates: List[Dict[str, Any]] = []
    for upload in files:
        data = await upload.read()
        text = _extract_text(upload.filename or "resume.txt", data)
        profile = _resume_analysis(text, upload.filename or "resume.txt")
        match = _match(text, job_description)
        candidates.append({
            "id": os.urandom(8).hex(),
            "name": profile["name"],
            "email": profile["email"],
            "phone": profile["phone"],
            "resume_score": profile["resume_score"],
            "role_match": match["overall"],
            "status": "Screened",
            "assessment_status": "Not Sent",
            "email_status": "Found" if profile["email"] else "Missing",
            "skills": profile["skills"],
            "missing_skills": match["missing"],
        })

    unique = _dedupe_candidates(candidates)
    unique.sort(key=lambda item: float(item.get("role_match", 0)), reverse=True)
    return unique


@app.post("/api/send-email")
def send_email(payload: EmailRequest) -> Dict[str, Any]:
    success, message = send_html_email(payload.to_email, payload.subject, payload.content)
    if not success:
        raise HTTPException(status_code=502, detail=message)
    return {"status": "sent", "message": message}
