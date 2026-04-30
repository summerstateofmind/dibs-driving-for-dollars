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
