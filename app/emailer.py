"""Gmail SMTP email sender with template loading and field merging."""
import logging
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

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
    """Send a plain-text email via Gmail SMTP. Raises on failure."""
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = config.SMTP_EMAIL
    msg["To"] = to_email

    log.info("Sending email to %s: %s", to_email, subject)
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(config.SMTP_EMAIL, config.SMTP_PASSWORD)
        server.send_message(msg)
