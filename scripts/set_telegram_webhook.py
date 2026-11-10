"""Register (or re-register) the Telegram webhook with the shared secret.

Run this after every deploy that changes TELEGRAM_WEBHOOK_SECRET or the public URL:

    python scripts/set_telegram_webhook.py
    python scripts/set_telegram_webhook.py https://your-app.up.railway.app

Reads TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET and (if no URL is passed)
PUBLIC_BASE_URL from the environment / .env. Never prints the token or secret.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.telegram_bot import set_webhook


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else config.PUBLIC_BASE_URL).rstrip("/")
    if not base.startswith("https://"):
        sys.exit("Pass your public https:// base URL as an argument or set PUBLIC_BASE_URL.")
    if not config.TELEGRAM_BOT_TOKEN:
        sys.exit("TELEGRAM_BOT_TOKEN is not set.")
    if not config.TELEGRAM_WEBHOOK_SECRET:
        sys.exit("TELEGRAM_WEBHOOK_SECRET is not set.")

    result = set_webhook(f"{base}/telegram")
    print(f"setWebhook -> {base}/telegram: {result}")
    if not result.get("ok"):
        sys.exit(1)


if __name__ == "__main__":
    main()
