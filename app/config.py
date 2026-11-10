import os
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
AIRTABLE_PAT = os.getenv("AIRTABLE_PAT", "")
AIRTABLE_BASE_ID = os.getenv("AIRTABLE_BASE_ID", "")
TRACERFY_API_KEY = os.getenv("TRACERFY_API_KEY", "")
MY_PHONE_NUMBER = os.getenv("MY_PHONE_NUMBER", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
# Shared secret Telegram echoes back in X-Telegram-Bot-Api-Secret-Token on every
# webhook call. /telegram rejects everything while this is empty.
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
# Public origin of this deployment, e.g. https://your-app.up.railway.app (no path).
# Used to verify Twilio signatures behind a proxy and to register the Telegram webhook.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
SMTP_EMAIL = os.getenv("SMTP_EMAIL", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
REPLY_TO_EMAIL = os.getenv("REPLY_TO_EMAIL", "")
DIGEST_HOUR = int(os.getenv("DIGEST_HOUR", "8"))
DIGEST_TIMEZONE = os.getenv("DIGEST_TIMEZONE", "America/Los_Angeles")
CRON_SECRET = os.getenv("CRON_SECRET", "")
AUTO_EMAIL_ENABLED = os.getenv("AUTO_EMAIL_ENABLED", "false").lower() == "true"
YOUR_NAME = os.getenv("YOUR_NAME", "")
