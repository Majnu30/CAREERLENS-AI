"""CareerLens AI FastAPI backend.

This module intentionally contains API routes only. The Streamlit UI belongs in app.py.
Run with: uvicorn api:app --host 0.0.0.0 --port 8000
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
    lower=text.lower(); words=re.findall(r"\b[a-zA-Z]{2,}\b",text); word_count=len(words); skills=sorted(_skill_set(text))
    sections=["experience","education","projects","skills","certifications","summary"]
    section_hits=sum(1 for x in sections if re.search(r"\b"+re.escape(x)+r"\b",lower))
    measurable=len(re.findall(r"(?:\b\d+%|\b\d+[kKmM]?\+?|\$\d+|₹\s?\d+|reduced|increased|improved|saved|grew|delivered)",lower))
    action=len(re.findall(r"\b(led|built|developed|designed|implemented|created|optimized|managed|automated|analyzed|delivered|improved|launched|deployed|engineered)\b",lower))
    email=_extract_email(text); phone=_extract_phone(text); contact=(2 if email else 0)+(1 if phone else 0)
    content=min(100,round(min(word_count/700,1)*20)); section=round(section_hits/len(sections)*20); skill=min(20,len(skills)*2); evidence=min(20,measurable*5); action_score=min(10,round(action*1.5)); contact_score=round(contact/3*10)
    score=max(10,min(100,content+section+skill+evidence+action_score+contact_score)); readiness=max(10,min(100,round(score*.55+min(len(skills)*4,20)+min(section_hits*4,24)+min(measurable*3,12))))
    strengths=[]; recs=[]
    if skills: strengths.append(f"Detected {len(skills)} relevant skills.")
    if section_hits>=4: strengths.append("Good coverage of standard resume sections.")
    if measurable>=2: strengths.append("Includes measurable achievement evidence.")
    if not strengths: strengths.append("Resume text was successfully extracted, but evidence is limited.")
    if not email: recs.append("Add a professional email address.")
    if not phone: recs.append("Add a reachable phone number.")
    if section_hits<4: recs.append("Add or strengthen standard resume sections.")
    if len(skills)<6: recs.append("Add more role-relevant skills you can substantiate.")
    if measurable<2: recs.append("Add measurable achievements and outcomes.")
    if action<4: recs.append("Use stronger action verbs and ownership language.")
    if word_count<250: recs.append("Add enough evidence to demonstrate experience without filler.")
    return {"name":_extract_name(text,filename),"email":email,"phone":phone,"experience":"Detected from resume" if "experience" in lower else "Not detected","resume_score":score,"readiness":readiness,"market_match":None,"skills":skills,"missing_skills":[],"score_breakdown":{"content_quality":content,"section_coverage":section,"skills":skill,"achievement_evidence":evidence,"action_language":action_score,"contact_completeness":contact_score},"strengths":strengths,"recommendations":recs,"extracted_text":text,"source":"local-api"}

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
    skills=sorted(_skill_set(payload.resume_text)); role=payload.target_role.strip(); lower=role.lower()
    steps=[f"Clarify the responsibilities, entry requirements and success metrics for {role}.",f"Build the core competency stack for {role} and close the largest gaps in your current profile.",f"Create 2–3 portfolio projects that demonstrate real {role} work with measurable outcomes.",f"Gain practical experience through internships, freelance work, volunteering or production projects related to {role}.",f"Tailor your resume, LinkedIn profile and portfolio around {role} keywords and evidence.",f"Practice role-specific technical, behavioral and scenario-based interviews for {role}.",f"Track applications and feedback, then iterate your skill plan every 2–4 weeks."]
    return {"steps":steps,"current_skills":skills,"target_role":role,"source":"local-api","note":"Roadmap is dynamically generated from the requested role and detected resume skills."}


@app.post("/api/chat/ask")
def chat_assistant(payload: ChatRequest) -> Dict[str, str]:
    latest=""
    for message in reversed(payload.messages):
        if isinstance(message,dict) and message.get("role")=="user": latest=str(message.get("content","")).strip(); break
    if not latest: return {"reply":"Ask me about careers, roles, resumes, interviews, job matching, salary or learning plans.","source":"local-api"}
    q=latest.lower(); resume=payload.resume_context.lower(); skills=sorted(_skill_set(payload.resume_context))
    if "how to become" in q or "roadmap" in q or "career path" in q:
        role=latest.split("how to become",1)[-1].strip(" ?:") if "how to become" in q else latest
        reply=(f"To become strong in {role}, use this path:\n\n1. Learn the core fundamentals for the role.\n2. Build 2–3 practical projects that prove those skills.\n3. Get hands-on experience and document measurable outcomes.\n4. Tailor your resume and portfolio to the role.\n5. Practice role-specific technical and behavioral interviews.\n6. Apply, collect feedback and close the biggest skill gaps.\n\n")
        if skills: reply+=f"Your resume already shows: {', '.join(skills[:12])}. Use those as your starting point and identify the missing competencies next."
    elif "resume" in q:
        reply="For your resume, focus on evidence: quantified achievements, role-relevant skills, projects, clear experience bullets, and ATS-readable structure."
        if skills: reply+=f" I can see these detected skills in your current context: {', '.join(skills[:10])}."
    elif "interview" in q:
        reply="For interview preparation, practice role fundamentals, realistic scenarios, behavioral stories using Situation–Action–Result, and questions about your projects. Aim to explain decisions and measurable outcomes, not just definitions."
    elif "salary" in q or "pay" in q or "compensation" in q:
        reply="Salary depends on role, experience, location, company, skills and market conditions. Use a verified salary dataset for current figures; I can help you compare offers once you provide the role, experience and location."
    else:
        reply=f"Here is a practical way to approach that career question: define the target outcome, identify the skills and evidence required, build a small project or experience that proves the skill, and measure the result. Your question was: {latest[:500]}"
    return {"reply":reply,"source":"local-api"}


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
