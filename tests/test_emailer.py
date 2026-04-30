"""Tests for emailer — template loading, field merging, owner name fallback, send backends."""
import os
import pytest
from unittest.mock import patch, MagicMock

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates")


def test_load_template_returns_subject_and_body():
    from app.emailer import load_template
    subject, body = load_template("initial_outreach")
    assert "property at {address}" in subject
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


@patch("app.emailer.httpx.post")
def test_send_email_uses_sendgrid_when_key_set(mock_post):
    mock_post.return_value = MagicMock(status_code=202)

    from app.emailer import send_email
    with patch("app.config.SMTP_EMAIL", "test@gmail.com"), \
         patch("app.config.SENDGRID_API_KEY", "SG.test"):
        send_email("owner@example.com", "Test Subject", "Test body")
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.kwargs["json"]["personalizations"][0]["to"][0]["email"] == "owner@example.com"


@patch("app.emailer.smtplib.SMTP")
def test_send_email_uses_smtp_when_no_sendgrid_key(mock_smtp_class):
    mock_smtp = MagicMock()
    mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_smtp)
    mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

    from app.emailer import send_email
    with patch("app.config.SMTP_EMAIL", "test@gmail.com"), \
         patch("app.config.SMTP_PASSWORD", "pass"), \
         patch("app.config.SENDGRID_API_KEY", ""):
        send_email("owner@example.com", "Test Subject", "Test body")
    mock_smtp.send_message.assert_called_once()


@patch("app.emailer.httpx.post")
def test_send_email_raises_on_sendgrid_failure(mock_post):
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("SendGrid error")
    mock_post.return_value = mock_response

    from app.emailer import send_email
    with patch("app.config.SMTP_EMAIL", "test@gmail.com"), \
         patch("app.config.SENDGRID_API_KEY", "SG.test"):
        with pytest.raises(Exception, match="SendGrid error"):
            send_email("owner@example.com", "Test Subject", "Test body")
