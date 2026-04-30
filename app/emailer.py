"""Email sender with template loading and field merging.

Supports two backends:
- Resend API (set RESEND_API_KEY) — required on Railway/PaaS that block SMTP
- Gmail SMTP (set SMTP_EMAIL + SMTP_PASSWORD) — works on any VPS
Resend is used when RESEND_API_KEY is set; otherwise falls back to SMTP.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import httpx

from app import config

log = logging.getLogger(__name__)
TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def load_template(name: str) -> tuple[str, str]:
    """Load a template file. Returns (subject, body). First line must be 'Subject: ...'."""
    path = TEMPLATES_DIR / f"{name}.txt"
    text = path.read_text().strip()
    subject_line, body = text.split("\n", 1)
    subject = subject_line.removeprefix("Subject:").strip()
    return subject, body.strip()


def merge_fields(template: str, fields: dict[str, str]) -> str:
    """Replace {field_name} placeholders with values."""
    result = template
    for key, value in fields.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def resolve_owner_name(owner_name: str, llc_name: str) -> str:
    """Owner Name > LLC Name > 'Property Owner'."""
    return owner_name.strip() or llc_name.strip() or "Property Owner"


def send_email(to_email: str, subject: str, body: str):
    """Send a plain-text email. Uses Resend if configured, otherwise Gmail SMTP."""
    log.info("Sending email to %s: %s", to_email, subject)
    if config.RESEND_API_KEY:
        _send_via_resend(to_email, subject, body)
    else:
        _send_via_smtp(to_email, subject, body)


def _send_via_resend(to_email: str, subject: str, body: str):
    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {config.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": config.SMTP_EMAIL,
            "to": [to_email],
            "subject": subject,
            "text": body,
        },
        timeout=15,
    )
    resp.raise_for_status()


def _send_via_smtp(to_email: str, subject: str, body: str):
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.SMTP_EMAIL
    msg["To"] = to_email

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(config.SMTP_EMAIL, config.SMTP_PASSWORD)
        server.send_message(msg)
