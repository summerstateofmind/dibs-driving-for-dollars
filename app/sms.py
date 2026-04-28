import logging
from twilio.rest import Client
from app import config

log = logging.getLogger(__name__)
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client


def send_sms(body: str):
    """Send an SMS to the user's phone."""
    log.info("Sending SMS: %s", body[:80])
    _get_client().messages.create(
        body=body,
        from_=config.TWILIO_PHONE_NUMBER,
        to=config.MY_PHONE_NUMBER,
    )
