"""Security tests for the HTTP endpoints: webhook authentication, cron secret, hidden docs.

All secrets, phone numbers, and chat IDs here are made-up test values.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app import config, main

TG_SECRET = "test-telegram-webhook-secret"
TG_CHAT = "1000001"
TW_TOKEN = "test-twilio-auth-token"
OPERATOR = "+15555550100"
BASE_URL = "https://dibs.example.test"
CRON = "test-cron-secret"


@pytest.fixture
def client():
    # No context manager: startup events (the scheduler) must not run in tests.
    return TestClient(main.app)


@pytest.fixture
def processed():
    """Replace the message processor so no test reaches Claude/Airtable/Telegram."""
    with patch.object(main, "process_message") as mock:
        yield mock


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", TG_SECRET)
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", TG_CHAT)
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", TW_TOKEN)
    monkeypatch.setattr(config, "MY_PHONE_NUMBER", OPERATOR)
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", BASE_URL)
    monkeypatch.setattr(config, "CRON_SECRET", CRON)


def _tg_update(chat_id=TG_CHAT, text="1234 Main St"):
    return {"message": {"chat": {"id": int(chat_id)}, "text": text}}


TG_HEADER = "X-Telegram-Bot-Api-Secret-Token"


# --- /telegram ---


def test_telegram_without_secret_header_rejected(client, configured, processed):
    resp = client.post("/telegram", json=_tg_update())
    assert resp.status_code == 403
    processed.assert_not_called()


def test_telegram_wrong_secret_rejected(client, configured, processed):
    resp = client.post("/telegram", json=_tg_update(), headers={TG_HEADER: "wrong"})
    assert resp.status_code == 403
    processed.assert_not_called()


def test_telegram_correct_secret_and_chat_accepted(client, configured, processed):
    resp = client.post("/telegram", json=_tg_update(), headers={TG_HEADER: TG_SECRET})
    assert resp.status_code == 200
    processed.assert_called_once_with("1234 Main St", "telegram", chat_id=TG_CHAT)


def test_telegram_correct_secret_wrong_chat_ignored(client, configured, processed):
    resp = client.post(
        "/telegram", json=_tg_update(chat_id="2000002"), headers={TG_HEADER: TG_SECRET}
    )
    assert resp.status_code == 200
    processed.assert_not_called()


def test_telegram_unset_secret_rejects_everything(client, configured, processed, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", "")
    for headers in ({}, {TG_HEADER: ""}, {TG_HEADER: TG_SECRET}):
        resp = client.post("/telegram", json=_tg_update(), headers=headers)
        assert resp.status_code == 403
    processed.assert_not_called()


def test_telegram_unset_chat_id_rejects_everything(client, configured, processed, monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    resp = client.post("/telegram", json=_tg_update(), headers={TG_HEADER: TG_SECRET})
    assert resp.status_code == 403
    # An update with no chat at all must not slip through as "" == "".
    resp = client.post("/telegram", json={}, headers={TG_HEADER: TG_SECRET})
    assert resp.status_code == 403
    processed.assert_not_called()


def test_telegram_malformed_body_does_not_crash(client, configured, processed):
    for body in ("not json", "[]", '{"message": "x"}', '{"message": {"chat": 5}}'):
        resp = client.post(
            "/telegram",
            content=body,
            headers={TG_HEADER: TG_SECRET, "Content-Type": "application/json"},
        )
        assert resp.status_code in (200, 400)
    processed.assert_not_called()


def test_set_webhook_sends_secret_token(monkeypatch):
    from app import telegram_bot

    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "test-bot-token")
    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", TG_SECRET)
    with patch.object(telegram_bot.httpx, "post") as post:
        telegram_bot.set_webhook(f"{BASE_URL}/telegram")
    payload = post.call_args.kwargs["json"]
    assert payload["url"] == f"{BASE_URL}/telegram"
    assert payload["secret_token"] == TG_SECRET


def test_set_webhook_refuses_without_secret(monkeypatch):
    from app import telegram_bot

    monkeypatch.setattr(config, "TELEGRAM_WEBHOOK_SECRET", "")
    with patch.object(telegram_bot.httpx, "post") as post:
        with pytest.raises(RuntimeError):
            telegram_bot.set_webhook(f"{BASE_URL}/telegram")
    post.assert_not_called()


# --- /sms ---


def _sms_form(sender=OPERATOR, body="1234 Main St"):
    return {"From": sender, "To": "+15555550199", "Body": body, "MessageSid": "SMtest"}


def _sign(form, url=f"{BASE_URL}/sms", token=TW_TOKEN):
    return RequestValidator(token).compute_signature(url, form)


def test_sms_missing_signature_rejected(client, configured, processed):
    resp = client.post("/sms", data=_sms_form())
    assert resp.status_code == 403
    processed.assert_not_called()


def test_sms_bad_signature_rejected(client, configured, processed):
    form = _sms_form()
    for sig in ("AAAA", _sign(form, token="some-other-token"), _sign(_sms_form(body="other"))):
        resp = client.post("/sms", data=form, headers={"X-Twilio-Signature": sig})
        assert resp.status_code == 403
    processed.assert_not_called()


def test_sms_valid_signature_accepted(client, configured, processed):
    form = _sms_form()
    resp = client.post("/sms", data=form, headers={"X-Twilio-Signature": _sign(form)})
    assert resp.status_code == 200
    processed.assert_called_once_with("1234 Main St", "sms")


def test_sms_valid_signature_via_forwarded_headers(client, configured, processed, monkeypatch):
    """Without PUBLIC_BASE_URL the public URL is rebuilt from the proxy headers."""
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "")
    form = _sms_form()
    resp = client.post(
        "/sms",
        data=form,
        headers={
            "X-Twilio-Signature": _sign(form),
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "dibs.example.test",
        },
    )
    assert resp.status_code == 200
    processed.assert_called_once()


def test_sms_valid_signature_wrong_sender_ignored(client, configured, processed):
    form = _sms_form(sender="+15555550123")
    resp = client.post("/sms", data=form, headers={"X-Twilio-Signature": _sign(form)})
    assert resp.status_code == 200
    processed.assert_not_called()


@pytest.mark.parametrize("unset", ["TWILIO_AUTH_TOKEN", "MY_PHONE_NUMBER"])
def test_sms_unconfigured_rejects_everything(client, configured, processed, monkeypatch, unset):
    form = _sms_form(sender="" if unset == "MY_PHONE_NUMBER" else OPERATOR)
    signature = _sign(form)
    monkeypatch.setattr(config, unset, "")
    resp = client.post("/sms", data=form, headers={"X-Twilio-Signature": signature})
    assert resp.status_code == 403
    # A signature computed with an empty token must not validate either.
    resp = client.post(
        "/sms", data=form, headers={"X-Twilio-Signature": _sign(form, token="")}
    )
    assert resp.status_code == 403
    processed.assert_not_called()


# --- API docs ---


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_not_exposed(client, path):
    assert client.get(path).status_code == 404


def test_health_still_public(client):
    assert client.get("/health").status_code == 200


# --- /cron/daily ---


@pytest.fixture
def daily_job():
    with patch.object(main, "run_daily_job") as mock:
        yield mock


def test_cron_missing_secret_rejected(client, configured, daily_job):
    assert client.get("/cron/daily").status_code == 403
    daily_job.assert_not_called()


def test_cron_wrong_secret_rejected(client, configured, daily_job):
    attempts = [
        {"headers": {"X-Cron-Secret": "wrong"}},
        {"headers": {"Authorization": "Bearer wrong"}},
        {"headers": {"Authorization": f"Basic {CRON}"}},
        {"params": {"secret": "wrong"}},
    ]
    for kwargs in attempts:
        assert client.get("/cron/daily", **kwargs).status_code == 403
    daily_job.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"headers": {"X-Cron-Secret": CRON}},
        {"headers": {"Authorization": f"Bearer {CRON}"}},
        {"params": {"secret": CRON}},  # deprecated fallback, still accepted for now
    ],
)
def test_cron_correct_secret_accepted(client, configured, daily_job, kwargs):
    assert client.get("/cron/daily", **kwargs).status_code == 200
    daily_job.assert_called_once()


def test_cron_unset_secret_rejects_everything(client, configured, daily_job, monkeypatch):
    monkeypatch.setattr(config, "CRON_SECRET", "")
    attempts = [
        {},
        {"headers": {"X-Cron-Secret": ""}},
        {"headers": {"Authorization": "Bearer "}},
        {"params": {"secret": ""}},
        {"headers": {"X-Cron-Secret": CRON}},
    ]
    for kwargs in attempts:
        assert client.get("/cron/daily", **kwargs).status_code == 403
    daily_job.assert_not_called()
