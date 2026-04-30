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
