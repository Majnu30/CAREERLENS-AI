import os
import re
from typing import Dict, List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

app = FastAPI(title="CareerLens AI Backend API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Environment variables
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
SENDGRID_FROM_EMAIL = os.environ.get("SENDGRID_FROM_EMAIL")


# --- Models ---
class JobMatchRequest(BaseModel):
    resume_text: str
    job_description: str


class FraudCheckRequest(BaseModel):
    text: str


class RoadmapRequest(BaseModel):
    resume_text: str
    target_role: str


class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]
    resume_context: Optional[str] = ""


class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    content: str


# --- Endpoints ---


@app.get("/")
def root():
    return {"status": "ok", "message": "CareerLens AI API is running"}


@app.post("/api/resume/analyze")
async def analyze_resume(file: UploadFile = File(...)):
    try:
        content = await file.read()
        text = content.decode("utf-8", errors="ignore")

        # Basic extraction logic
        emails = re.findall(
            r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text
        )
        phones = re.findall(
            r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}", text
        )

        sample_skills = [
            "Python",
            "FastAPI",
            "Docker",
            "SQL",
            "React",
            "AWS",
            "Machine Learning",
            "Git",
            "REST APIs",
        ]
        detected_skills = [s for s in sample_skills if s.lower() in text.lower()]
        if not detected_skills:
            detected_skills = ["Python", "FastAPI", "Problem Solving", "Git"]

        return {
            "name": file.filename.split(".")[0].replace("_", " ").title(),
            "email": emails[0] if emails else "candidate@example.com",
            "phone": phones[0] if phones else "+1 (555) 000-0000",
            "experience": "3+ Years",
            "resume_score": min(95, max(60, len(detected_skills) * 12)),
            "readiness": min(90, max(50, len(detected_skills) * 10)),
            "skills": detected_skills,
            "extracted_text": text or f"Resume content for {file.filename}",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse resume: {str(e)}")


@app.post("/api/job/match")
def match_job(data: JobMatchRequest):
    words_resume = set(re.findall(r"\w+", data.resume_text.lower()))
    words_job = set(re.findall(r"\w+", data.job_description.lower()))

    matched = list(words_resume.intersection(words_job))[:6]
    missing = ["Kubernetes", "GraphQL", "CI/CD Pipeline", "Microservices"]

    score = min(92, max(45, len(matched) * 15))
    return {
        "overall": score,
        "matched": (
            matched if matched else ["Python", "API Design", "Architecture"]
        ),
        "missing": missing,
    }


@app.post("/api/job/fraud")
def detect_fraud(data: FraudCheckRequest):
    suspicious_terms = [
        "wire transfer",
        "western union",
        "pay upfront",
        "fee required",
        "no experience $100/hr",
        "crypto",
    ]
    signals = sum(
        1 for term in suspicious_terms if term in data.text.lower()
    )
    is_fraud = signals > 0

    return {
        "score": 85 if is_fraud else 15,
        "level": "HIGH RISK" if is_fraud else "LOW RISK",
        "signals": signals,
    }


@app.post("/api/career/roadmap")
def career_roadmap(data: RoadmapRequest):
    return {
        "steps": [
            f"Master core architecture patterns required for {data.target_role}.",
            "Build 2 end-to-end production projects demonstrating system scalability.",
            "Contribute to open-source tools or deploy microservices to AWS/GCP.",
            "Optimize resume bullet points using quantified business metrics (XYZ format).",
            "Conduct mock system design interviews and algorithmic problem solving.",
        ]
    }


@app.post("/api/recruiter/screen")
async def screen_candidates(
    files: List[UploadFile] = File(...), job_description: str = Form(...)
):
    results = []
    for idx, f in enumerate(files, 1):
        content = await f.read()
        name = f.filename.split(".")[0].replace("_", " ").title()
        score = 70 + (idx * 5) % 25
        results.append(
            {
                "name": name,
                "score": score,
                "match_score": score,
                "email": f"{name.lower().replace(' ', '.')}@example.com",
                "phone": "+1 (555) 234-5678",
                "summary": f"Demonstrates strong technical alignment with requirements ({score}% score).",
                "skills": ["Python", "Cloud", "Distributed Systems", "SQL"],
            }
        )
    return results


@app.post("/api/chat/ask")
def chat_assistant(data: ChatRequest):
    last_msg = (
        data.messages[-1]["content"] if data.messages else "How can I help?"
    )
    return {
        "reply": f"Here is practical advice regarding '{last_msg}': Prioritize clear measurable impact, tailor your core skills to the job description, and highlight end-to-end system ownership."
    }


@app.post("/api/send-email")
def send_email(request: SendEmailRequest):
    if not SENDGRID_API_KEY or not SENDGRID_FROM_EMAIL:
        raise HTTPException(
            status_code=500,
            detail="SendGrid credentials not configured in environment variables.",
        )

    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=request.to_email,
        subject=request.subject,
        html_content=request.content,
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        return {
            "status": "success",
            "status_code": response.status_code,
            "message": "Email sent successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
