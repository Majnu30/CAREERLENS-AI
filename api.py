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
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
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
APP_VERSION = "4.0.0"
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

ROLE_SKILL_HINTS = {
    "ai": ["python", "machine learning", "deep learning", "pytorch", "tensorflow", "statistics", "sql"],
    "machine learning": ["python", "machine learning", "statistics", "pandas", "numpy", "scikit-learn"],
    "data scientist": ["python", "statistics", "sql", "pandas", "numpy", "machine learning"],
    "data analyst": ["sql", "excel", "power bi", "tableau", "statistics", "data analysis"],
    "software": ["python", "java", "javascript", "git", "sql", "rest api", "testing"],
    "developer": ["python", "git", "sql", "testing", "rest api"],
    "devops": ["linux", "docker", "kubernetes", "aws", "git", "ci/cd"],
    "cloud": ["aws", "azure", "gcp", "docker", "kubernetes", "linux"],
    "cyber": ["cybersecurity", "linux", "networking", "python"],
    "qa": ["testing", "selenium", "automation", "api testing", "git"],
    "hr": ["recruitment", "employee relations", "communication", "hr analytics"],
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


class SalaryRequest(BaseModel):
    role: str = Field(..., min_length=2, max_length=120)
    experience: str = Field(..., min_length=1, max_length=80)
    location: str = Field("India", min_length=1, max_length=120)


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


def _role_hints(role: str) -> List[str]:
    role_l=(role or "").lower()
    result=[]
    for key, values in ROLE_SKILL_HINTS.items():
        if key in role_l:
            result.extend(values)
    return list(dict.fromkeys(result))


def _resume_analysis(text: str, filename: str, target_role: str = "") -> Dict[str, Any]:
    text=(text or "").strip()
    lower=text.lower()
    words=re.findall(r"\b[a-zA-Z]{2,}\b", text)
    skills=sorted(_skill_set(text))
    section_names={
        "summary": ("summary","professional summary","profile","objective"),
        "experience": ("experience","work experience","professional experience","employment"),
        "education": ("education","academic background"),
        "projects": ("projects","personal projects","academic projects"),
        "skills": ("skills","technical skills","core skills"),
        "certifications": ("certifications","certificates","licenses"),
        "achievements": ("achievements","accomplishments","awards"),
    }
    lines=[re.sub(r"\s+"," ",x).strip().lower() for x in text.splitlines() if x.strip()]
    found={k for k, variants in section_names.items() if any(line.strip(" :") in variants for line in lines)}
    quantified=len(re.findall(r"(?:\b\d+%|\b\d+[+]?(?:\s*years?|\s*users?|\s*clients?)|\b(?:increased|reduced|improved|saved|grew|generated)\b[^.]{0,60}\b\d+)", lower))
    action_verbs=len(re.findall(r"\b(led|built|developed|designed|implemented|improved|optimized|automated|created|managed|analyzed|delivered|launched|reduced|increased|deployed|tested|trained)\b", lower))
    bullets=len(re.findall(r"(?:^|\n)\s*[•▪●*-]\s+", text))
    email=bool(_extract_email(text)); phone=bool(_extract_phone(text))
    content=min(100,25+min(len(words),700)/700*45+min(bullets,18)/18*15+min(action_verbs,12)/12*15)
    section_score=len(found)/7*100
    skill_score=min(100,len(skills)/12*100)
    achievement_score=min(100,quantified/5*70+min(action_verbs,10)/10*30)
    contact_score=(50 if email else 0)+(50 if phone else 0)
    hints=_role_hints(target_role)
    role_match=(sum(1 for h in hints if h in lower)/len(hints)*100) if hints else None
    score=content*.25+section_score*.20+skill_score*.20+achievement_score*.15+contact_score*.10+(role_match*.10 if role_match is not None else 5)
    score=int(round(max(5,min(98,score))))
    experience_signals=len(re.findall(r"\b(experience|intern|internship|employment|work history|years?)\b",lower))
    readiness=int(round(max(5,min(97,score*.55+min(len(skills),10)*3+min(quantified,5)*2+min(experience_signals,3)*2))))
    missing_sections=[x.title() for x in section_names if x not in found]
    missing_skills=[x for x in hints if x not in lower][:8]
    recommendations=[]
    if "Experience" in missing_sections: recommendations.append("Add relevant experience, internships, or substantial project work.")
    if "Projects" in missing_sections: recommendations.append("Add 2–3 relevant projects with tools, contribution, and outcomes.")
    if quantified<2: recommendations.append("Add measurable results such as percentages, time saved, users, revenue, accuracy, or scale.")
    if action_verbs<4: recommendations.append("Use stronger action verbs and show what you personally delivered.")
    if not email or not phone: recommendations.append("Complete your contact details with a professional email and phone number.")
    if len(skills)<6: recommendations.append("Add more skills that are supported by evidence in your projects or experience.")
    if target_role and role_match is not None and role_match<50: recommendations.append(f"Tailor the resume toward {target_role} and add evidence for the missing role skills.")
    if not recommendations: recommendations.append("Maintain the structure and tailor achievements to each target job.")
    strengths=[]
    if len(skills)>=6: strengths.append(f"Detected {len(skills)} relevant skills.")
    if len(found)>=5: strengths.append("Good coverage of standard resume sections.")
    if quantified>=2: strengths.append("Includes measurable achievement evidence.")
    if email and phone: strengths.append("Complete contact information detected.")
    if not strengths: strengths.append("Resume text extracted successfully; add more evidence to strengthen the profile.")
    return {
        "name":_extract_name(text,filename),"email":_extract_email(text),"phone":_extract_phone(text),
        "experience":"Experience evidence detected" if experience_signals else "Experience not clearly detected",
        "resume_score":score,"readiness":readiness,"market_match":None,"skills":skills,"missing_skills":missing_skills,
        "strengths":strengths,"recommendations":recommendations,
        "score_breakdown":{"content_quality":round(content,1),"section_coverage":round(section_score,1),"skills":round(skill_score,1),"achievement_evidence":round(achievement_score,1),"contact_completeness":round(contact_score,1),"target_role_alignment":round(role_match,1) if role_match is not None else None},
        "extracted_text":text,"source":"api-analysis-v4","analysis_version":4,"target_role":target_role,
    }

def _match(resume_text: str, job_description: str) -> Dict[str, Any]:
    resume_text=resume_text.strip(); job_description=job_description.strip()
    if not resume_text or not job_description:
        raise ValueError("Both resume and job description are required.")
    try:
        matrix=TfidfVectorizer(stop_words="english",ngram_range=(1,2),max_features=8000).fit_transform([resume_text,job_description])
        similarity=float(cosine_similarity(matrix[0:1],matrix[1:2])[0][0])
    except ValueError:
        similarity=0.0
    resume_skills=_skill_set(resume_text); job_skills=_skill_set(job_description)
    matched=sorted(resume_skills & job_skills); missing=sorted(job_skills-resume_skills)
    skill_score=(len(matched)/len(job_skills)*100) if job_skills else 0
    semantic_score=similarity*100
    if job_skills:
        overall=round(semantic_score*.55+skill_score*.45)
    else:
        overall=round(semantic_score)
    recommended=missing[:10]
    return {
        "overall":max(0,min(100,overall)),"matched":matched,"missing":missing,"recommended_skills":recommended,
        "semantic_similarity":round(semantic_score,1),
        "summary":f"Matched {len(matched)} explicit skills and identified {len(missing)} skill gap(s).",
        "experience_alignment":"Strong Alignment" if overall>=75 else "Moderate Alignment" if overall>=50 else "Needs Improvement",
        "source":"local-api-v4","analysis_version":4,
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
async def analyze_resume(
    file: UploadFile = File(...),
    target_role: str = Form("", max_length=120),
) -> Dict[str, Any]:
    data = await file.read()
    text = _extract_text(file.filename or "resume.txt", data)
    return _resume_analysis(text, file.filename or "resume.txt", target_role.strip())


@app.post("/api/job/match")
def match_job(payload: JobMatchRequest) -> Dict[str, Any]:
    try:
        return _match(payload.resume_text, payload.job_description)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unable to calculate the job match from the supplied text.") from exc


@app.post("/api/salary/estimate")
def salary_estimate(payload: SalaryRequest) -> Dict[str, Any]:
    role=payload.role.strip(); role_l=role.lower(); exp=payload.experience; base=4.5
    if any(x in role_l for x in ("ai", "machine learning", "data scientist", "cloud", "cyber")): base=7.0
    elif any(x in role_l for x in ("software", "developer", "devops", "qa")): base=5.5
    elif any(x in role_l for x in ("product", "project manager", "manager")): base=6.0
    elif any(x in role_l for x in ("finance", "account")): base=4.0
    elif any(x in role_l for x in ("sales", "marketing", "hr", "human resource")): base=4.2
    elif any(x in role_l for x in ("civil", "mechanical", "electrical")): base=4.3
    if "Mid" in exp: base*=1.45
    elif "Senior" in exp: base*=2.0
    elif "Lead" in exp: base*=2.6
    return {"role":role,"experience":exp,"location":payload.location.strip(),"min_lpa":round(base*.85,1),"max_lpa":round(base*1.8,1),"note":"Indicative estimate based on role family and experience; it is not a live market feed. Verify against current local job listings before making decisions.","source":"local-estimate-v4"}


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
    skills=sorted(_skill_set(payload.resume_text)); hints=_role_hints(payload.target_role); missing=[x for x in hints if x not in (payload.resume_text or "").lower()]
    return {
        "steps":[
            f"Clarify the responsibilities and core competencies expected for {payload.target_role}.",
            f"Build evidence for these priority skills: {', '.join(missing[:6]) if missing else 'role-specific fundamentals and practical tools'}.",
            "Build 2–3 portfolio projects with measurable outcomes and document your decisions.",
            "Tailor your resume and LinkedIn profile around role-relevant evidence and impact.",
            "Practice role-specific technical, behavioral and scenario-based interview questions.",
        ],"current_skills":skills,"missing_skills":missing[:10],"target_role":payload.target_role,"source":"local-api-v4","analysis_version":4
    }


@app.post("/api/chat/ask")
def chat_assistant(payload: ChatRequest) -> Dict[str, str]:
    latest=""
    for message in reversed(payload.messages):
        if isinstance(message,dict) and message.get("role")=="user": latest=str(message.get("content","")).strip(); break
    if not latest: return {"reply":"Tell me what career, resume, job-match, interview, salary or job-search problem you want to solve.","source":"local-api-v4"}
    q=latest.lower(); skills=sorted(_skill_set(payload.resume_context))
    if "how to become" in q or "become an" in q or "become a" in q:
        role=re.sub(r".*?how to become\s+(?:an?\s+)?", "", latest, flags=re.I).strip(" ?.") or "your target role"
        reply=(f"### Roadmap to become a {role}\n\n"
               "**1. Learn the foundations** — understand the core concepts and tools used in the role.\n\n"
               "**2. Build practical skills** — follow structured projects instead of only watching tutorials.\n\n"
               "**3. Build a portfolio** — create 2–3 projects that demonstrate real problem solving and measurable outcomes.\n\n"
               "**4. Strengthen your resume** — quantify impact, highlight relevant skills, and tailor it to the role.\n\n"
               "**5. Prepare for interviews** — practice technical, behavioral and scenario questions.\n\n"
               "**6. Apply strategically** — target roles where your strongest evidence matches the requirements.")
        if skills: reply += f"\n\n**Your detected resume skills:** {', '.join(skills[:15])}."
    elif "resume" in q:
        reply="Focus your resume on role relevance, measurable achievements, strong action verbs, clear sections, and evidence for the skills requested by the job."
    elif "interview" in q:
        reply="For interviews, prepare a concise introduction, 5–8 STAR stories, role-specific fundamentals, project deep dives, and questions for the interviewer. Practice answers with concrete outcomes."
    elif "salary" in q or "pay" in q or "ctc" in q:
        reply="Salary depends on role, experience, location, company and skills. Use CareerLens Salary Estimation for an indicative band, then compare it with current job listings before negotiating."
    elif "skill" in q:
        reply=f"Start with the skills explicitly required by your target role. Your resume currently exposes: {', '.join(skills[:15]) if skills else 'no recognized skills yet'}. Build evidence for each priority gap through projects or work."
    else:
        reply=(f"For your question — **{latest}** — break the goal into: target role, required skills, evidence/portfolio, resume positioning, interview preparation, and a practical application plan. "
               "If you give me your target role and experience level, I can turn that into a step-by-step plan.")
    return {"reply":reply,"source":"local-api-v4"}


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
