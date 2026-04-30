"""Daily digest and auto-email scheduler."""
import logging
import time
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app import config
from app.airtable_client import get_campaigning_leads, update_lead
from app.emailer import load_template, merge_fields, resolve_owner_name, send_email
from app.sms import send_sms
from app.telegram_bot import send_telegram

log = logging.getLogger(__name__)
_scheduler = None

ASAP_STEPS = {"Call / SMS", "Door Knock", "Letter 1"}


def notify_user(body: str):
    """Send a notification to the user via Telegram (preferred) or SMS."""
    if config.TELEGRAM_CHAT_ID and config.TELEGRAM_BOT_TOKEN:
        send_telegram(body, config.TELEGRAM_CHAT_ID)
    else:
        send_sms(body)


def build_digest(leads: list[dict]) -> str | None:
    """Build the daily digest message. Returns None if nothing is due."""
    now = datetime.now(timezone.utc)
    today_str = now.astimezone(ZoneInfo(config.DIGEST_TIMEZONE)).strftime("%m/%d")

    do_now = []
    coming_due = []

    for lead in leads:
        f = lead["fields"]
        step = f.get("Campaign Step", "")
        addr = f.get("Address", "?")
        owner = f.get("Owner Name") or f.get("LLC Name") or "Unknown"

        if step in ASAP_STEPS:
            if step == "Call / SMS":
                phone = f.get("Phone 1", "")
                line = f"  Call: {addr} — {owner} ({phone})" if phone else f"  Call: {addr} ({owner})"
            else:
                line = f"  {step}: {addr} ({owner})"
            do_now.append(line)

        elif step == "Letter 2":
            completed_at = f.get("Step Completed At", "")
            if completed_at:
                completed_dt = datetime.fromisoformat(completed_at)
                if now - completed_dt >= timedelta(days=30):
                    due_date = (completed_dt + timedelta(days=30)).astimezone(
                        ZoneInfo(config.DIGEST_TIMEZONE)
                    ).strftime("%m/%d")
                    coming_due.append(f"  Letter 2: {addr} (due {due_date})")
        # Email and Quarterly Drip are handled silently by process_auto_emails

    if not do_now and not coming_due:
        return None

    lines = [f"Dibs Daily — {today_str}", ""]
    if do_now:
        lines.append(f"DO NOW ({len(do_now)}):")
        lines.extend(do_now)
        lines.append("")
    if coming_due:
        lines.append(f"COMING DUE ({len(coming_due)}):")
        lines.extend(coming_due)
        lines.append("")
    lines.append(f"Total active: {len(leads)} leads")
    return "\n".join(lines)


def process_auto_emails(leads: list[dict]):
    """Send auto-emails for leads at the Email or Quarterly Drip step."""
    if not config.AUTO_EMAIL_ENABLED:
        return
    now = datetime.now(timezone.utc)

    for lead in leads:
        f = lead["fields"]
        step = f.get("Campaign Step", "")
        addr = f.get("Address", "?")
        owner_name = resolve_owner_name(f.get("Owner Name", ""), f.get("LLC Name", ""))
        email_addr = f.get("Email 1", "")
        opt_out = f.get("Email Opt Out", False)

        if step == "Email" and f.get("Emails Sent", 0) == 0:
            if opt_out:
                continue
            if not email_addr:
                log.info("No email on file for %s — skipping", addr)
                continue

            _send_template_email(
                lead, "initial_outreach", email_addr, owner_name, addr, f,
                advance_to="Letter 2",
                notification=f"Auto-emailed {owner_name} ({addr}) — step advanced to Letter 2",
            )
            time.sleep(7)

        elif step == "Quarterly Drip":
            if opt_out or not email_addr:
                continue
            anchor = f.get("Last Email Sent At") or f.get("Step Completed At", "")
            if not anchor:
                continue
            anchor_dt = datetime.fromisoformat(anchor)
            if now - anchor_dt < timedelta(days=90):
                continue

            _send_template_email(
                lead, "quarterly_drip", email_addr, owner_name, addr, f,
                advance_to=None,
                notification=f"Drip email sent to {owner_name} ({addr})",
            )
            time.sleep(7)


def _send_template_email(lead, template_name, email_addr, owner_name, addr, fields,
                         advance_to, notification):
    """Load template, merge fields, send email, update Airtable, notify user."""
    now = datetime.now(timezone.utc)
    try:
        subject_tpl, body_tpl = load_template(template_name)
        merge = {
            "owner_name": owner_name,
            "owner_first_name": owner_name.split()[0] if owner_name else "there",
            "address": addr,
            "city": fields.get("City", ""),
            "state": fields.get("State", ""),
            "your_phone": config.MY_PHONE_NUMBER,
            "your_name": config.YOUR_NAME,
        }
        subject = merge_fields(subject_tpl, merge)
        body = merge_fields(body_tpl, merge)

        send_email(email_addr, subject, body)

        update_fields = {
            "Emails Sent": (fields.get("Emails Sent", 0) or 0) + 1,
            "Last Email Sent At": now.isoformat(),
            "Notes": (
                (fields.get("Notes", "") or "")
                + f"\n[{now.strftime('%m/%d %I:%M%p')}] Auto-emailed {owner_name}"
            ).strip(),
        }
        if advance_to:
            update_fields["Campaign Step"] = advance_to
            update_fields["Step Completed At"] = now.isoformat()

        update_lead(lead["id"], update_fields)
        notify_user(notification)

    except Exception:
        log.exception("Failed to send email for %s", addr)
        notify_user(f"Email failed for {addr} — will retry tomorrow. Check SMTP credentials if this persists.")


def run_daily_job():
    """The main daily job: build digest + process auto-emails."""
    log.info("Running daily digest job")
    try:
        leads = get_campaigning_leads()
        log.info("Found %d campaigning leads", len(leads))

        digest = build_digest(leads)
        if digest:
            notify_user(digest)

        process_auto_emails(leads)
    except Exception:
        log.exception("Daily job failed")


def start_scheduler():
    """Start the background scheduler. Call once on app startup."""
    global _scheduler
    if _scheduler is not None:
        return

    tz = ZoneInfo(config.DIGEST_TIMEZONE)
    _scheduler = BackgroundScheduler(timezone=tz)
    _scheduler.add_job(
        run_daily_job,
        "cron",
        hour=config.DIGEST_HOUR,
        minute=0,
        id="daily_digest",
    )
    _scheduler.start()
    log.info("Scheduler started — daily digest at %s:00 %s", config.DIGEST_HOUR, config.DIGEST_TIMEZONE)
