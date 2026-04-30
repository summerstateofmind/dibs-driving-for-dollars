# Daily Digest + Auto-Email Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily 8am PT scheduler that texts the user a digest of due campaign actions and auto-sends templated emails to property owners at the Email and Quarterly Drip steps.

**Architecture:** APScheduler runs in-process with FastAPI. A single daily job fetches Campaigning leads from Airtable, builds a digest message, auto-sends emails for eligible leads, and notifies the user via SMS or Telegram. A `notify_user()` helper bypasses the thread-local `send_reply` system since the scheduler runs in its own thread.

**Tech Stack:** APScheduler, smtplib (stdlib), zoneinfo (stdlib), existing FastAPI + pyairtable + httpx stack.

**Spec:** `docs/superpowers/specs/2026-04-29-scheduler-auto-email-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `app/config.py` | Modify | Add SMTP, digest, and cron secret config vars |
| `app/airtable_client.py` | Modify | Add `get_campaigning_leads()` filtered fetch |
| `app/emailer.py` | Create | Gmail SMTP send, template loading, field merging |
| `app/scheduler.py` | Create | APScheduler setup, daily job, digest builder, auto-email orchestration, `notify_user()` |
| `app/main.py` | Modify | Start scheduler on startup, add `/cron/daily` endpoint, update `handle_done` to write `Step Completed At` |
| `templates/initial_outreach.txt` | Create | Initial outreach email template |
| `templates/quarterly_drip.txt` | Create | Quarterly drip email template |
| `requirements.txt` | Modify | Add `apscheduler` |
| `.env.example` | Modify | Add SMTP, digest, cron secret placeholders |
| `tests/test_emailer.py` | Create | Tests for template loading, merging, owner name fallback |
| `tests/test_scheduler.py` | Create | Tests for digest building, auto-email logic, notify_user |
| `tests/test_airtable_filter.py` | Create | Test for filtered Airtable fetch |

---

### Task 1: Config + Dependencies

**Files:**
- Modify: `app/config.py`
- Modify: `requirements.txt`
- Modify: `.env.example`

- [ ] **Step 1: Add config vars to `app/config.py`**

Add after the `TELEGRAM_CHAT_ID` line:

```python
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "8"))
DIGEST_TIMEZONE = os.getenv("DIGEST_TIMEZONE", "America/Los_Angeles")
CRON_SECRET = os.getenv("CRON_SECRET", "")
```

- [ ] **Step 2: Add `apscheduler` to `requirements.txt`**

Add to end of file:

```
apscheduler>=3.10.0,<4
```

- [ ] **Step 3: Update `.env.example`**

Add after the Telegram section:

```
# Auto-email (for campaign email step)
SMTP_EMAIL=your.email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx

# Scheduler
DIGEST_HOUR=8
DIGEST_TIMEZONE=America/Los_Angeles
CRON_SECRET=some-random-secret
```

- [ ] **Step 4: Add CRON_SECRET and DIGEST vars to local `.env`**

Generate a random secret and add to `.env`:

```
DIGEST_HOUR=8
DIGEST_TIMEZONE=America/Los_Angeles
CRON_SECRET=<generate a random string>
```

- [ ] **Step 5: Commit**

```bash
git add app/config.py requirements.txt .env.example
git commit -m "feat: add SMTP, digest, and cron secret config"
```

---

### Task 2: Filtered Airtable Fetch

**Files:**
- Modify: `app/airtable_client.py`
- Test: `tests/test_airtable_filter.py`

- [ ] **Step 1: Write the test**

Create `tests/test_airtable_filter.py`:

```python
"""Test that get_campaigning_leads uses a filtered Airtable formula."""
from unittest.mock import patch, MagicMock


def test_get_campaigning_leads_uses_formula():
    mock_table = MagicMock()
    mock_table.all.return_value = [
        {"id": "rec1", "fields": {"Address": "123 Main St", "Status": "Campaigning"}},
    ]
    with patch("app.airtable_client._get_table", return_value=mock_table):
        from app.airtable_client import get_campaigning_leads
        result = get_campaigning_leads()
        mock_table.all.assert_called_once_with(formula="{Status} = 'Campaigning'")
        assert len(result) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_airtable_filter.py -v`
Expected: FAIL — `get_campaigning_leads` not defined

- [ ] **Step 3: Add `get_campaigning_leads` to `app/airtable_client.py`**

Add after `get_all_leads()`:

```python
def get_campaigning_leads():
    """Return leads where Status = Campaigning (filtered server-side to save API calls)."""
    return _get_table().all(formula="{Status} = 'Campaigning'")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_airtable_filter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/airtable_client.py tests/test_airtable_filter.py
git commit -m "feat: add get_campaigning_leads with server-side filter"
```

---

### Task 3: Email Templates

**Files:**
- Create: `templates/initial_outreach.txt`
- Create: `templates/quarterly_drip.txt`

- [ ] **Step 1: Create `templates/initial_outreach.txt`**

```
Subject: Your property at {address}

Hi {owner_name},

My name is Skyler with Three Willows Capital. I'm reaching out about your property at {address}, {city}, {state}.

If you've ever considered selling, I'd love to have a quick conversation. I buy properties in any condition and can close on your timeline.

Feel free to call or text me at {your_phone}.

If you'd rather not hear from me, just reply "stop" and I won't reach out again.

Best,
Skyler
```

- [ ] **Step 2: Create `templates/quarterly_drip.txt`**

```
Subject: Still interested in {address}

Hi {owner_name},

I reached out a while back about your property at {address}. Just wanted to check in — if you're considering selling, my offer still stands.

Call or text anytime: {your_phone}.

If you'd rather not hear from me, just reply "stop" and I won't reach out again.

Best,
Skyler
```

- [ ] **Step 3: Commit**

```bash
git add templates/
git commit -m "feat: add email templates for initial outreach and quarterly drip"
```

---

### Task 4: Emailer Module

**Files:**
- Create: `app/emailer.py`
- Create: `tests/test_emailer.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_emailer.py`:

```python
"""Tests for emailer — template loading, field merging, owner name fallback."""
import os
import pytest
from unittest.mock import patch, MagicMock

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def test_load_template_returns_subject_and_body():
    from app.emailer import load_template
    subject, body = load_template("initial_outreach")
    assert "property at {address}" in subject
    assert "{owner_name}" in body
    assert "{your_phone}" in body


def test_load_template_quarterly_drip():
    from app.emailer import load_template
    subject, body = load_template("quarterly_drip")
    assert "Still interested" in subject
    assert "{address}" in body


def test_merge_fields_basic():
    from app.emailer import merge_fields
    template = "Hi {owner_name}, your property at {address}, {city}, {state}. Call {your_phone}."
    result = merge_fields(template, {
        "owner_name": "Jane Smith",
        "address": "123 Main St",
        "city": "Seattle",
        "state": "WA",
        "your_phone": "+12065551234",
    })
    assert result == "Hi Jane Smith, your property at 123 Main St, Seattle, WA. Call +12065551234."


def test_resolve_owner_name_prefers_owner_name():
    from app.emailer import resolve_owner_name
    assert resolve_owner_name("Jane Smith", "Acme LLC") == "Jane Smith"


def test_resolve_owner_name_falls_back_to_llc():
    from app.emailer import resolve_owner_name
    assert resolve_owner_name("", "Acme LLC") == "Acme LLC"


def test_resolve_owner_name_falls_back_to_default():
    from app.emailer import resolve_owner_name
    assert resolve_owner_name("", "") == "Property Owner"


@patch("app.emailer.smtplib.SMTP_SSL")
def test_send_email_calls_smtp(mock_smtp_class):
    mock_smtp = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    from app.emailer import send_email
    with patch("app.config.SMTP_EMAIL", "test@gmail.com"), \
         patch("app.config.SMTP_PASSWORD", "pass"):
        send_email("owner@example.com", "Test Subject", "Test body")
    mock_smtp.send_message.assert_called_once()


@patch("app.emailer.smtplib.SMTP_SSL")
def test_send_email_raises_on_failure(mock_smtp_class):
    mock_smtp = MagicMock()
    mock_smtp.send_message.side_effect = Exception("SMTP error")
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    from app.emailer import send_email
    with patch("app.config.SMTP_EMAIL", "test@gmail.com"), \
         patch("app.config.SMTP_PASSWORD", "pass"):
        with pytest.raises(Exception, match="SMTP error"):
            send_email("owner@example.com", "Test Subject", "Test body")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_emailer.py -v`
Expected: FAIL — `app.emailer` not found

- [ ] **Step 3: Implement `app/emailer.py`**

```python
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
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(config.SMTP_EMAIL, config.SMTP_PASSWORD)
        server.send_message(msg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_emailer.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/emailer.py tests/test_emailer.py
git commit -m "feat: add emailer module with SMTP send, templates, field merging"
```

---

### Task 5: Update `handle_done` to Write `Step Completed At`

**Files:**
- Modify: `app/main.py:268-293`

- [ ] **Step 1: Update `handle_done` in `app/main.py`**

Change the `update_lead` call in `handle_done` (around line 289) from:

```python
    update_lead(lead["id"], {
        "Campaign Step": next_step,
        "Notes": updated_notes,
    })
```

To:

```python
    update_lead(lead["id"], {
        "Campaign Step": next_step,
        "Step Completed At": datetime.now(timezone.utc).isoformat(),
        "Notes": updated_notes,
    })
```

- [ ] **Step 2: Verify app still starts**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: handle_done writes Step Completed At on every step advance"
```

---

### Task 6: Scheduler Module

**Files:**
- Create: `app/scheduler.py`
- Create: `tests/test_scheduler.py`

- [ ] **Step 1: Write the tests**

Create `tests/test_scheduler.py`:

```python
"""Tests for scheduler — notify_user, digest building, auto-email orchestration."""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, call


def _make_lead(address, step, owner="Jane Smith", phone1="206-555-1234",
               email1="", emails_sent=0, last_email_at="",
               step_completed_at="", opt_out=False, llc=""):
    return {
        "id": f"rec_{address.replace(' ', '')}",
        "fields": {
            "Address": address,
            "Campaign Step": step,
            "Owner Name": owner,
            "LLC Name": llc,
            "Phone 1": phone1,
            "Email 1": email1,
            "Emails Sent": emails_sent,
            "Last Email Sent At": last_email_at,
            "Step Completed At": step_completed_at,
            "Email Opt Out": opt_out,
            "Status": "Campaigning",
            "Notes": "",
        },
    }


def test_notify_user_prefers_telegram():
    with patch("app.config.TELEGRAM_CHAT_ID", "12345"), \
         patch("app.config.TELEGRAM_BOT_TOKEN", "tok"), \
         patch("app.scheduler.send_telegram") as mock_tg, \
         patch("app.scheduler.send_sms") as mock_sms:
        from app.scheduler import notify_user
        notify_user("Hello")
        mock_tg.assert_called_once_with("Hello", "12345")
        mock_sms.assert_not_called()


def test_notify_user_falls_back_to_sms():
    with patch("app.config.TELEGRAM_CHAT_ID", ""), \
         patch("app.config.TELEGRAM_BOT_TOKEN", ""), \
         patch("app.scheduler.send_sms") as mock_sms:
        from app.scheduler import notify_user
        notify_user("Hello")
        mock_sms.assert_called_once_with("Hello")


def test_build_digest_do_now_with_phone():
    leads = [_make_lead("123 Main St", "Call / SMS", phone1="206-555-1234")]
    from app.scheduler import build_digest
    msg = build_digest(leads)
    assert "Call: 123 Main St" in msg
    assert "206-555-1234" in msg
    assert "DO NOW (1)" in msg


def test_build_digest_door_knock_no_phone_inline():
    leads = [_make_lead("456 Oak Ave", "Door Knock", owner="Bob Jones")]
    from app.scheduler import build_digest
    msg = build_digest(leads)
    assert "Door Knock: 456 Oak Ave (Bob Jones)" in msg
    # Phone number should NOT appear inline for non-Call steps
    assert "206-555-1234" not in msg


def test_build_digest_letter2_coming_due():
    old_ts = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
    leads = [_make_lead("789 Elm St", "Letter 2", step_completed_at=old_ts)]
    from app.scheduler import build_digest
    msg = build_digest(leads)
    assert "COMING DUE" in msg
    assert "789 Elm St" in msg


def test_build_digest_letter2_not_yet_due():
    recent_ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    leads = [_make_lead("789 Elm St", "Letter 2", step_completed_at=recent_ts)]
    from app.scheduler import build_digest
    msg = build_digest(leads)
    assert msg is None  # Nothing due


def test_build_digest_skips_email_and_drip_steps():
    leads = [
        _make_lead("100 Email St", "Email", email1="a@b.com"),
        _make_lead("200 Drip St", "Quarterly Drip", email1="c@d.com"),
    ]
    from app.scheduler import build_digest
    msg = build_digest(leads)
    assert msg is None  # Email and drip are handled silently, not in digest


def test_build_digest_empty_returns_none():
    from app.scheduler import build_digest
    msg = build_digest([])
    assert msg is None


@patch("app.scheduler.update_lead")
@patch("app.scheduler.send_email")
@patch("app.scheduler.notify_user")
def test_process_auto_emails_sends_initial_email(mock_notify, mock_send, mock_update):
    leads = [_make_lead("100 Email St", "Email", email1="owner@example.com", owner="Jane Smith")]
    from app.scheduler import process_auto_emails
    process_auto_emails(leads)
    mock_send.assert_called_once()
    mock_update.assert_called_once()
    # Verify step advanced to Letter 2
    update_fields = mock_update.call_args[0][1]
    assert update_fields["Campaign Step"] == "Letter 2"
    assert update_fields["Emails Sent"] == 1
    mock_notify.assert_called_once()
    assert "Auto-emailed" in mock_notify.call_args[0][0]


@patch("app.scheduler.notify_user")
def test_process_auto_emails_missing_email_notifies_user(mock_notify):
    leads = [_make_lead("200 No Email St", "Email", email1="", owner="Bob Jones")]
    from app.scheduler import process_auto_emails
    process_auto_emails(leads)
    mock_notify.assert_called_once()
    assert "No email for" in mock_notify.call_args[0][0]
    assert "manual outreach needed" in mock_notify.call_args[0][0]


@patch("app.scheduler.update_lead")
@patch("app.scheduler.send_email", side_effect=Exception("SMTP error"))
@patch("app.scheduler.notify_user")
def test_process_auto_emails_smtp_failure_no_state_update(mock_notify, mock_send, mock_update):
    leads = [_make_lead("300 Fail St", "Email", email1="owner@example.com")]
    from app.scheduler import process_auto_emails
    process_auto_emails(leads)
    mock_update.assert_not_called()  # No Airtable update on failure
    mock_notify.assert_called_once()
    assert "Email failed" in mock_notify.call_args[0][0]
    assert "retry tomorrow" in mock_notify.call_args[0][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: FAIL — `app.scheduler` not found

- [ ] **Step 3: Implement `app/scheduler.py`**

```python
"""Daily digest and auto-email scheduler."""
import logging
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
    today_str = now.astimezone(ZoneInfo(config.DIGEST_TIMEZONE)).strftime("%-m/%d")

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
                    ).strftime("%-m/%d")
                    coming_due.append(f"  Letter 2: {addr} (due {due_date})")
        # Email and Quarterly Drip are handled silently by process_auto_emails

    if not do_now and not coming_due:
        return None

    lines = [f"Dibs 🚙 Daily — {today_str}", ""]
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
                notify_user(f"No email for {addr} — skipping auto-email, manual outreach needed")
                continue

            _send_template_email(
                lead, "initial_outreach", email_addr, owner_name, addr, f,
                advance_to="Letter 2",
                notification=f"Auto-emailed {owner_name} ({addr}) — step advanced to Letter 2",
            )

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


def _send_template_email(lead, template_name, email_addr, owner_name, addr, fields,
                         advance_to, notification):
    """Load template, merge fields, send email, update Airtable, notify user."""
    now = datetime.now(timezone.utc)
    try:
        subject_tpl, body_tpl = load_template(template_name)
        merge = {
            "owner_name": owner_name,
            "address": addr,
            "city": fields.get("City", ""),
            "state": fields.get("State", ""),
            "your_phone": config.MY_PHONE_NUMBER,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scheduler.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add app/scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler with daily digest and auto-email processing"
```

---

### Task 7: Wire Scheduler into FastAPI + Add Cron Endpoint

**Files:**
- Modify: `app/main.py:1-18` (imports and app setup)
- Modify: `app/main.py:65-67` (after health endpoint)

- [ ] **Step 1: Add startup event and cron endpoint to `app/main.py`**

Add import at top of file (with other imports):

```python
from app.scheduler import start_scheduler, run_daily_job
```

Add startup event after the `app = FastAPI(...)` line:

```python
@app.on_event("startup")
def on_startup():
    start_scheduler()
```

Add the cron endpoint after the `/health` endpoint:

```python
@app.get("/cron/daily")
def cron_daily(secret: str = ""):
    """Manual trigger for the daily digest job. Protected by CRON_SECRET."""
    if not config.CRON_SECRET or secret != config.CRON_SECRET:
        return Response(status_code=403, content="Forbidden")
    run_daily_job()
    return {"status": "ok", "message": "Daily job triggered"}
```

- [ ] **Step 2: Verify app starts and scheduler logs**

Run: `python -c "from app.main import app; print('OK')"`
Expected: `OK` (plus scheduler log line)

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: wire scheduler into FastAPI startup, add /cron/daily endpoint"
```

---

### Task 8: Set Railway Env Vars + Deploy + Test

**Files:** None (operational)

- [ ] **Step 1: Generate a cron secret and set Railway vars**

```bash
CRON_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
railway variables set CRON_SECRET=$CRON_SECRET SMTP_EMAIL=bissell.skyler@gmail.com SMTP_PASSWORD="REDACTED-APP-PASSWORD" DIGEST_HOUR=8 DIGEST_TIMEZONE=America/Los_Angeles
```

- [ ] **Step 2: Deploy to Railway**

```bash
railway up --detach
```

- [ ] **Step 3: Test the cron endpoint manually**

```bash
curl "https://d4d-sms-tool-production.up.railway.app/cron/daily?secret=$CRON_SECRET"
```

Expected: `{"status":"ok","message":"Daily job triggered"}` and a digest message arrives via Telegram/SMS.

- [ ] **Step 4: Test auth rejection**

```bash
curl "https://d4d-sms-tool-production.up.railway.app/cron/daily"
```

Expected: 403 Forbidden

- [ ] **Step 5: Check Railway logs for scheduler startup**

```bash
railway logs | grep -i scheduler
```

Expected: `Scheduler started — daily digest at 8:00 America/Los_Angeles`

- [ ] **Step 6: Commit everything and push**

```bash
git add -A
git commit -m "feat: daily digest + auto-email scheduler complete"
git push
```
