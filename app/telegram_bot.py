import logging
import httpx
from app import config

log = logging.getLogger(__name__)


def send_telegram(body: str, chat_id: str = ""):
    """Send a Telegram message to the user."""
    chat_id = chat_id or config.TELEGRAM_CHAT_ID
    if not config.TELEGRAM_BOT_TOKEN or not chat_id:
        log.warning("Telegram not configured — skipping send")
        return

    log.info("Sending Telegram: %s", body[:80])
    resp = httpx.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": body},
        timeout=10,
    )
    if not resp.is_success:
        log.error("Telegram send failed: %s", resp.text)


def set_webhook(url: str):
    """Register a webhook URL with Telegram, including the shared secret.

    Telegram sends TELEGRAM_WEBHOOK_SECRET back in the
    X-Telegram-Bot-Api-Secret-Token header of every update, which /telegram
    requires. Refuses to register a webhook without a secret.
    """
    if not config.TELEGRAM_WEBHOOK_SECRET:
        raise RuntimeError(
            "TELEGRAM_WEBHOOK_SECRET is not set; refusing to register an unauthenticated webhook"
        )
    resp = httpx.post(
        f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/setWebhook",
        json={
            "url": url,
            "secret_token": config.TELEGRAM_WEBHOOK_SECRET,
            "allowed_updates": ["message"],
        },
        timeout=10,
    )
    return resp.json()
