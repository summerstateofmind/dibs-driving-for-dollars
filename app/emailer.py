"""Email sender with template loading and field merging. Uses SendGrid API."""
import logging
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
    """Send a plain-text email via SendGrid API. Raises on failure."""
    log.info("Sending email to %s: %s", to_email, subject)
    resp = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {config.SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "personalizations": [{"to": [{"email": to_email}]}],
            "from": {"email": config.SMTP_EMAIL},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=15,
    )
    resp.raise_for_status()
