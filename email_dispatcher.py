import os
import re
from typing import Tuple
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from config import SENDGRID_API_KEY, SENDGRID_FROM_EMAIL

def send_assessment_email(to_email: str, candidate_name: str, role: str, test_link: str) -> Tuple[bool, str]:
    """
    Sends automated candidate assessment invitations using SendGrid API.
    """
    if not to_email or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", to_email.strip()):
        return False, "Candidate email is invalid or missing."

    if not SENDGRID_API_KEY:
        return False, "SendGrid API Key is not configured."

    subject = f"CareerLens AI — Assessment Invitation for {role}"
    
    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 12px;">
        <h2 style="color: #2563eb; margin-top: 0;">CareerLens AI Assessment</h2>
        <p>Hello <strong>{candidate_name or 'Candidate'}</strong>,</p>
        <p>Congratulations! You have been shortlisted for the <strong>{role}</strong> role.</p>
        <p>Please complete your online pre-interview qualifying assessment by clicking the link below:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{test_link}" style="background-color: #2563eb; color: #ffffff; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
                Start Assessment Now →
            </a>
        </div>
        <p style="color: #64748b; font-size: 13px;">If the button doesn't work, copy and paste this URL into your browser:<br>
        <a href="{test_link}" style="color: #2563eb;">{test_link}</a></p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;">
        <p style="color: #94a3b8; font-size: 12px;">CareerLens AI Recruitment Intelligence. Please do not reply directly to this automated email.</p>
    </div>
    """

    message = Mail(
        from_email=SENDGRID_FROM_EMAIL,
        to_emails=to_email.strip(),
        subject=subject,
        html_content=html_content
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        if response.status_code in [200, 201, 202]:
            return True, "Email delivered successfully via SendGrid."
        return False, f"SendGrid returned status code: {response.status_code}"
    except Exception as e:
        return False, f"Delivery failed: {str(e)}"
