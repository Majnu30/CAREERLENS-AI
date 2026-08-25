
"""SendGrid email service for CareerLens AI.

Secrets are read only from environment variables through config.py.
No credentials are stored in source code.
"""

from __future__ import annotations

import html
import re
from typing import Tuple

from config import SENDGRID_API_KEY, SENDGRID_FROM_EMAIL

EMAIL_RE = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)


def _valid_email(email: str) -> bool:
    value = (email or "").strip().lower()
    return bool(
        value
        and len(value) <= 254
        and EMAIL_RE.fullmatch(value)
    )


def _send(
    to_email: str,
    subject: str,
    html_content: str,
) -> Tuple[bool, str]:

    # Validate recipient
    if not _valid_email(to_email):
        return False, "Candidate email is invalid or missing."

    # Check SendGrid API key
    if not SENDGRID_API_KEY:
        return False, "SendGrid API key is not configured."

    # Check sender email
    if not _valid_email(SENDGRID_FROM_EMAIL):
        return False, "SendGrid sender email is not configured correctly."

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=SENDGRID_FROM_EMAIL,
            to_emails=to_email.strip().lower(),
            subject=subject[:200],
            html_content=html_content,
        )

        response = SendGridAPIClient(SENDGRID_API_KEY).send(message)

        print(
            f"SendGrid response: "
            f"status_code={response.status_code}"
        )

        if response.status_code in (200, 201, 202):
            return True, "Email accepted by SendGrid."

        # Print response body for debugging.
        # This does not print the API key.
        try:
            body = response.body.decode("utf-8")
        except Exception:
            body = str(response.body)

        print(f"SendGrid response body: {body}")

        return (
            False,
            f"SendGrid returned status code {response.status_code}."
        )

    except Exception as exc:
        # Print the real provider error to Render logs.
        # IMPORTANT: Never print SENDGRID_API_KEY.
        print(
            f"SendGrid error: "
            f"{type(exc).__name__}: {exc}"
        )

        return (
            False,
            "Email delivery failed. Check the server logs."
        )


def send_html_email(
    to_email: str,
    subject: str,
    html_content: str,
) -> Tuple[bool, str]:
    """Send caller-supplied HTML content after validating the destination."""

    return _send(
        to_email,
        subject,
        html_content,
    )


def send_assessment_email(
    to_email: str,
    candidate_name: str,
    role: str,
    test_link: str,
) -> Tuple[bool, str]:
    """Send a safe, consistent assessment invitation."""

    safe_name = html.escape(
        (candidate_name or "Candidate").strip()[:120]
    )

    safe_role = html.escape(
        (role or "Open Position").strip()[:160]
    )

    safe_link = html.escape(
        (test_link or "").strip(),
        quote=True,
    )

    if not safe_link.startswith(("http://", "https://")):
        return False, "Assessment link is invalid."

    subject = (
        f"CareerLens AI — Assessment Invitation for {safe_role}"
    )

    content = f"""
    <div style="
        font-family:Arial,sans-serif;
        max-width:620px;
        margin:auto;
        padding:24px;
        border:1px solid #e2e8f0;
        border-radius:14px;
        background:#ffffff;
    ">

      <h2 style="
        color:#2563eb;
        margin-top:0;
      ">
        CareerLens AI Assessment
      </h2>

      <p>
        Hello <strong>{safe_name}</strong>,
      </p>

      <p>
        You have been shortlisted for the
        <strong>{safe_role}</strong> role.
      </p>

      <p>
        Please complete your online pre-interview
        assessment using the secure link below.
      </p>

      <p style="
        text-align:center;
        margin:28px 0;
      ">

        <a
          href="{safe_link}"
          style="
            background:#2563eb;
            color:#ffffff;
            padding:13px 24px;
            text-decoration:none;
            border-radius:8px;
            font-weight:700;
            display:inline-block;
          "
        >
          Start Assessment
        </a>

      </p>

      <p style="
        color:#64748b;
        font-size:13px;
      ">

        If the button does not work,
        copy this link into your browser:

        <br>

        {safe_link}

      </p>

      <hr style="
        border:0;
        border-top:1px solid #e2e8f0;
        margin:24px 0;
      ">

      <p style="
        color:#94a3b8;
        font-size:12px;
      ">
        CareerLens AI Recruitment Intelligence.
        This is an automated message.
      </p>

    </div>
    """

    return _send(
        to_email,
        subject,
        content,
    )
