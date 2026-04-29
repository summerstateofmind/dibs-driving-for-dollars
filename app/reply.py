"""Channel-aware reply routing. Supports SMS (Twilio) and Telegram."""

import threading
import logging

log = logging.getLogger(__name__)
_ctx = threading.local()


def set_reply_channel(channel: str, **kwargs):
    """Set the reply channel for the current thread. Call before processing."""
    _ctx.channel = channel
    _ctx.kwargs = kwargs


def send_reply(body: str):
    """Send a reply via whatever channel the current message came from."""
    channel = getattr(_ctx, "channel", "sms")
    kwargs = getattr(_ctx, "kwargs", {})

    if channel == "telegram":
        from app.telegram_bot import send_telegram
        send_telegram(body, kwargs.get("chat_id", ""))
    else:
        from app.sms import send_sms
        send_sms(body)
