# Dibs — Driving for Dollars

Personal text-driven lead capture for real estate investors doing Driving for Dollars. Spot a house, text it to a bot, get the owner back in seconds.

---

## What It Does

You spot a distressed property while driving or walking. You text the address to your Dibs bot. The tool does the rest:

1. **Capture** — AI parses the address and any condition notes from your text.
2. **Skip trace** — Automatically looks up the property owner, phone numbers, emails, and mailing address via Tracerfy.
3. **Campaign** — Starts a multi-step outreach cadence (call, door knock, letters) and texts you reminders when each step is due.
4. **Manage** — Mark steps done, add notes, kill dead leads, check status — all via text commands.

Desktop review happens in Airtable. The chat channel is the only write path. The tool only ever messages you — never a property owner or third party.

---

## Architecture

```
  YOU (iPhone)
    |
    |  Telegram message (or SMS via Twilio)
    v
+----------------------+
|  Telegram / Twilio   |  (inbound webhook)
+----------------------+
            |
            v
+------------------+       +------------------+
|   FastAPI app    | ----> | Claude Haiku 4.5 |
|  (stateless)     |       | (parse address   |
+------------------+       |  + commands)     |
    |          |            +------------------+
    |          |
    v          v
+----------+  +------------------+
| Tracerfy |  |  Airtable        |
| skip     |  |  (Leads table,   |
| trace    |  |   desktop UI)    |
+----------+  +------------------+
    |
    +---> Owner name, phones,
          emails, mailing address
          written back to Airtable

  Reply sent back to you via the same
  channel with confirmation + owner summary
```

All processing is stateless. Airtable is the database. The chat channel (Telegram or SMS) is the only write path.

---

## Features

- **One-text capture** — text an address, get owner info back in seconds
- **AI parsing** — natural language input, no rigid format required
- **Auto skip trace** — owner lookup fires on capture by default (opt out with `-ns`)
- **Owner-occupied detection** — compares property address to owner mailing address
- **Daily digest** — morning notification listing leads that need action today
- **Auto-email** — sends templated emails to owners at the Email and Quarterly Drip campaign steps
- **Campaign tracking** — multi-step outreach cadence per lead
- **Duplicate detection** — won't re-add an address you're already tracking
- **Fuzzy address matching** — commands work with partial addresses ("1234 Main")
- **Telegram-first** — free messaging, no carrier registration required
- **Twilio SMS optional** — works with Siri, CarPlay, and iOS Shortcuts if you want full SMS
- **Airtable UI** — sortable, filterable lead views on desktop and mobile
- **iOS Shortcut** — one-tap or "Hey Siri, log this house" hands-free capture

---

## Why Telegram (and why Twilio is optional)

This started as an SMS tool. In practice, **Telegram is the better default**:

- **Free.** No per-message cost, no $1.15/mo phone number, no monthly minimums.
- **No brand verification.** Twilio (and every other US SMS provider) now enforces A2P 10DLC registration. Your webhook domain must match the LLC name you register with — if it doesn't, you'll get rejected. Telegram has no equivalent gate.
- **Same UX.** Send a message, get a reply. Works hands-free from iPhone via Siri Shortcuts the same way SMS does.

Twilio support is still in the codebase for anyone whose business name and domain happen to align (or who already has a registered campaign). Treat it as the advanced path.

---

## Command Reference

### Capture (text an address)

| Message | What happens |
|---------|-------------|
| `1234 Main St Seattle` | Log + skip trace + start campaign |
| `1234 Main St -ns` | Log only, no skip trace |
| `1234 Main St -nc` | Log + skip trace, no campaign |
| `1234 Main St. Vacant, boarded windows` | Log with condition notes |

### Commands

| Command | Example | What it does |
|---------|---------|-------------|
| `done <addr>` | `done 1234 Main` | Mark current campaign step complete, advance to next |
| `status <addr>` | `status 1234 Main` | Get lead details: owner, phones, status, next step |
| `note <addr> <text>` | `note 1234 Main called owner no answer` | Append a timestamped note |
| `kill <addr>` | `kill 1234 Main` | Mark lead dead, stop campaign |
| `list` | `list` | Count of all leads by status |
| `help` | `help` | Show command list |

Address fragments work for all commands. If multiple leads match, you get a numbered list to disambiguate.

---

## Setup

### Prerequisites

- Python 3.12+
- An [Airtable](https://airtable.com) account (free tier works)
- An [Anthropic](https://console.anthropic.com) API key
- A [Tracerfy](https://tracerfy.com) API key (for skip tracing)
- A Telegram account (default path) — or a Twilio account (optional)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USER/dibs-driving-for-dollars.git
cd dibs-driving-for-dollars
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` is a fully pinned lockfile generated from `requirements.in`. To update dependencies, edit `requirements.in` and regenerate:

```bash
uv pip compile requirements.in --universal --python-version 3.11 --no-header --no-annotate -o requirements.txt
```

### 2. Set up Airtable

Create a base with a table called **Leads** and these fields:

| Field | Type |
|-------|------|
| Address | Single line text |
| City | Single line text |
| State | Single line text |
| Zip | Single line text |
| Status | Single select: `New`, `Campaigning`, `Contacted`, `Under Contract`, `Dead` |
| Campaign Step | Single select: `Not Started`, `Call / SMS`, `Door Knock`, `Letter 1`, `Email`, `Letter 2`, `Quarterly Drip` |
| Skip Trace Status | Single select: `Pending`, `Complete`, `Failed`, `Skipped` |
| Condition Notes | Long text |
| Notes | Long text |
| Owner Name | Single line text |
| LLC Name | Single line text |
| Owner Address | Single line text |
| Owner Occupied? | Single select: `Yes`, `No`, `Unknown` |
| Phone 1 / Phone 2 / Phone 3 | Single line text |
| Phone Type 1 / Phone Type 2 / Phone Type 3 | Single line text |
| Email 1 / Email 2 | Single line text |
| Captured At | Single line text |
| Step Completed At | Single line text |
| Emails Sent | Number |
| Last Email Sent At | Single line text |
| Email Opt Out | Checkbox |

Then generate a [Personal Access Token](https://airtable.com/create/tokens) with read/write access to your base. Grab the Base ID from the Airtable URL (`https://airtable.com/appXXXXXXXX/...`).

### 3. Configure environment

Copy `.env.example` to `.env`:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
AIRTABLE_PAT=pat...
AIRTABLE_BASE_ID=appXXXXXXXX
MY_PHONE_NUMBER=+1XXXXXXXXXX    # used by SMS path and for outbound digest fallback

# Tracerfy (for skip tracing)
TRACERFY_API_KEY=...

# Telegram (default messaging path)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TELEGRAM_WEBHOOK_SECRET=...     # random string; see step 4

# Public URL of your deployment (no trailing path)
PUBLIC_BASE_URL=https://your-app.up.railway.app

# Twilio (optional SMS path — only if you've completed A2P 10DLC registration)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX
```

### 4. Set up Telegram (recommended)

Free, no phone-number purchase, no brand verification.

1. Message [@BotFather](https://t.me/BotFather) on Telegram. Send `/newbot`, follow the prompts, copy the bot token.
2. Start a chat with your new bot. Send it any message so it can see you.
3. Get your chat ID: visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find `"chat":{"id":XXXXXXX}`.
4. Generate a webhook secret (letters, digits, `_` and `-` only):
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
5. Set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_WEBHOOK_SECRET`, and `PUBLIC_BASE_URL` in your `.env` (and in your host's environment variables).
6. Deploy the app (see below), then register the webhook with the secret:
   ```bash
   python scripts/set_telegram_webhook.py https://your-app.up.railway.app
   ```
   Or by hand:
   ```bash
   curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook"      -d "url=https://your-app.up.railway.app/telegram"      -d "secret_token=<YOUR_TELEGRAM_WEBHOOK_SECRET>"
   ```

The `/telegram` endpoint only accepts requests that carry this secret in the `X-Telegram-Bot-Api-Secret-Token` header and come from your `TELEGRAM_CHAT_ID`. If either variable is unset, every request is rejected. Re-run the registration whenever you change the secret or the URL.

### 4b. Set up Twilio SMS (optional / advanced)

> Heads up: as of 2024+, US SMS through Twilio requires **A2P 10DLC** brand registration. Your registered LLC name has to match the domain/brand on file. If they don't line up, your campaign will be rejected and your messages won't deliver. Telegram avoids this entirely.

If you're set up for it:

1. Create a [Twilio](https://www.twilio.com) account and buy a phone number.
2. Complete A2P 10DLC brand + campaign registration.
3. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` in your `.env`.
4. Deploy the app, then in the Twilio console set the **Messaging webhook** on your number to:
   ```
   https://your-app.up.railway.app/sms
   ```
   Method: POST.
5. Set `PUBLIC_BASE_URL` to the same origin (`https://your-app.up.railway.app`).

The `/sms` endpoint verifies Twilio's `X-Twilio-Signature` on every request using `TWILIO_AUTH_TOKEN`. The signature covers the exact public URL, so the webhook URL in the Twilio console must match `PUBLIC_BASE_URL` + `/sms`. If `TWILIO_AUTH_TOKEN` or `MY_PHONE_NUMBER` is unset, every request is rejected.

### 5. Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

For local testing of the webhook, expose your local server with [ngrok](https://ngrok.com):

```bash
ngrok http 8000
```

Then point your Telegram (or Twilio) webhook at the ngrok URL.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for address/command parsing |
| `AIRTABLE_PAT` | Yes | Airtable Personal Access Token |
| `AIRTABLE_BASE_ID` | Yes | Airtable base ID (starts with `app`) |
| `MY_PHONE_NUMBER` | Yes | Your phone number in E.164 format (`+1XXXXXXXXXX`) |
| `TELEGRAM_BOT_TOKEN` | Telegram path | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Telegram path | Your Telegram chat ID |
| `TELEGRAM_WEBHOOK_SECRET` | Telegram path | Random string (1-256 chars: letters, digits, `_`, `-`) registered with `setWebhook`. `/telegram` rejects all requests without it. |
| `PUBLIC_BASE_URL` | Recommended | Public https origin of the deployment, e.g. `https://your-app.up.railway.app`. Used for Twilio signature checks and webhook registration. |
| `TWILIO_ACCOUNT_SID` | SMS path | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | SMS path | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | SMS path | Your Twilio phone number |
| `TRACERFY_API_KEY` | No | Tracerfy API key. Without it, skip trace is disabled. |
| `RESEND_API_KEY` | Resend path | Resend API key (starts with `re_`) |
| `SMTP_EMAIL` | Auto-email | Sender email address (your verified domain for Resend, or Gmail for SMTP) |
| `SMTP_PASSWORD` | SMTP path | Gmail app password (not needed if using Resend) |
| `YOUR_NAME` | Auto-email | Your name for email templates |
| `AUTO_EMAIL_ENABLED` | No | Set to `true` to enable auto-email. Defaults to `false`. |
| `DIGEST_HOUR` | No | Hour (0-23) to send daily digest. Default: `8` |
| `DIGEST_TIMEZONE` | No | Timezone for digest. Default: `America/Los_Angeles` |
| `CRON_SECRET` | No | Secret for the manual `/cron/daily` trigger, sent in an `X-Cron-Secret` header. The endpoint is disabled while unset. |

---

## Daily Digest & Auto-Email

The scheduler runs inside the app process (APScheduler). Every morning at `DIGEST_HOUR` (default 8am Pacific), it:

1. **Sends you a digest** — lists leads that need manual action today (calls, door knocks, letters coming due). Delivered via Telegram if configured, otherwise SMS.
2. **Auto-sends emails** — for leads on the Email or Quarterly Drip step, sends a templated email to the owner and advances the campaign. Only runs when `AUTO_EMAIL_ENABLED=true`.

### Enabling auto-email

Auto-email is **off by default**. To enable:

1. Edit the email templates in `templates/` (see below).
2. Set up an email backend — Resend (for Railway/PaaS) or Gmail SMTP (for VPS). See below.
3. Set `AUTO_EMAIL_ENABLED=true` in your environment (Railway dashboard or `.env`).

### Email templates

Templates live in `templates/`. Each file has a `Subject:` line followed by the body:

```
Subject: Your property at {address}

Hi {owner_name},

...body...
```

Available merge fields: `{address}`, `{city}`, `{state}`, `{owner_name}`, `{owner_first_name}`, `{your_name}`, `{your_phone}`.

| Template | When it sends | File |
|----------|---------------|------|
| Initial outreach | Email campaign step | `templates/initial_outreach.txt` |
| Quarterly drip | Quarterly Drip step (90+ days since last email) | `templates/quarterly_drip.txt` |

Edit these templates to match your voice before enabling auto-email. Set `YOUR_NAME` in your environment so `{your_name}` fills in automatically.

### Email backend: Resend (Railway / PaaS)

Railway and most PaaS hosts block outbound SMTP. Use Resend's API instead (free tier = 3,000 emails/month):

1. Sign up at [resend.com](https://resend.com).
2. Add and verify your domain (Domains > Add Domain — add the DNS records they provide).
3. Create an API key (API Keys > Create API Key).
4. Set `RESEND_API_KEY` and `SMTP_EMAIL` (e.g., `hello@yourdomain.com`) in your environment.

When `RESEND_API_KEY` is set, emails go through Resend's HTTPS API.

### Email backend: Gmail SMTP (VPS)

If you're hosting on a VPS (DigitalOcean, Linode, Hetzner, etc.) where SMTP isn't blocked, you can send directly through Gmail with no third-party service:

1. Enable 2-Step Verification on your Google account.
2. Go to [App Passwords](https://myaccount.google.com/apppasswords).
3. Create a new app password (select "Mail" and your device).
4. Copy the 16-character password (e.g., `xxxx xxxx xxxx xxxx`).
5. Set `SMTP_EMAIL` and `SMTP_PASSWORD` in your environment. Leave `RESEND_API_KEY` unset.

When `RESEND_API_KEY` is not set, the app falls back to Gmail SMTP automatically.

### Opt-out handling

Each email includes "reply stop" language. If an owner replies stop, check the **Email Opt Out** checkbox in Airtable — the scheduler will skip them going forward.

### Manual trigger

You can trigger the daily job on demand:

```bash
curl -H "X-Cron-Secret: YOUR_CRON_SECRET" https://your-app.up.railway.app/cron/daily
```

`Authorization: Bearer YOUR_CRON_SECRET` works too. The old `?secret=` query parameter is deprecated (it leaks into logs) and will be removed.

---

## Deploy to Railway

The app is configured for [Railway](https://railway.app) out of the box.

1. Push your repo to GitHub.
2. Go to [railway.app](https://railway.app), create a new project, and connect your repo.
3. Add all environment variables in Railway's dashboard (Settings > Variables).
4. Railway reads the `Procfile` and deploys automatically:
   ```
   web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
   ```
5. Grab your deployment URL, set it as `PUBLIC_BASE_URL`, and register it as your Telegram webhook with `python scripts/set_telegram_webhook.py` (or set it as the Twilio webhook).

---

## iOS Shortcut

One-tap or "Hey Siri, log this house" capture. The shortcut grabs your GPS location, reverse-geocodes it to a street address, and sends it as a message to your Dibs bot.

Setup takes 2 minutes. See [docs/ios-shortcut-setup.md](docs/ios-shortcut-setup.md) for step-by-step instructions.

---

## Cost Breakdown

Estimated monthly cost at ~30 leads/month:

| Service | Cost | Notes |
|---------|------|-------|
| Telegram | $0 | Default messaging path. Free, no carrier registration. |
| Twilio | ~$2/mo | Optional. $1.15/mo number + $0.0079/msg. Requires A2P 10DLC. |
| Tracerfy | ~$3-7/mo | ~$0.10-0.25 per skip trace. 0 credits on a miss. |
| Anthropic (Haiku) | ~$0.50/mo | One parse call per inbound message. Haiku is cheap. |
| Resend | $0 | Free tier covers 3,000 emails/mo. |
| Railway | $5/mo | Hobby plan. Sleeps when idle. |
| Airtable | $0 | Free tier: 1,000 records, 1,000 API calls/mo. |
| **Total (Telegram path)** | **~$8-12/mo** | Well under the $25/mo ceiling. |

---

## Campaign Step Sequence

Each captured lead progresses through these steps. Use `done <addr>` to advance.

| Step | Channel | What you do |
|------|---------|-------------|
| 1. Call / SMS | Phone | Call or text the owner directly |
| 2. Door Knock | In person | Visit the property, talk to owner or neighbor |
| 3. Letter 1 | Mail | Handwritten yellow letter |
| 4. Email | Email | Direct email to owner |
| 5. Letter 2 | Mail | Typed letter or postcard, different format |
| 6. Quarterly Drip | Mail | Recurring mailer until lead is dispositioned |

The sequence is defined in code (`CAMPAIGN_SEQUENCE` in `app/main.py`) and can be modified.

---

## Project Structure

```
dibs-driving-for-dollars/
  app/
    main.py            # FastAPI app, webhook handler, command routing
    parser.py          # Claude Haiku message parser
    sms.py             # Twilio outbound SMS
    telegram_bot.py    # Telegram outbound messages + webhook setup
    reply.py           # Channel-aware reply routing (Telegram or SMS)
    airtable_client.py # Airtable read/write operations
    skip_trace.py      # Tracerfy skip trace integration
    scheduler.py       # Daily digest + auto-email orchestration
    emailer.py         # Resend / Gmail SMTP sender + template engine
    config.py          # Environment variable loading
  templates/
    initial_outreach.txt   # Email template for Email campaign step
    quarterly_drip.txt     # Email template for Quarterly Drip step
  tests/
    test_scheduler.py
    test_emailer.py
    test_airtable_filter.py
    test_webhook_security.py
  docs/
    ios-shortcut-setup.md
  .env.example           # Template for environment variables
  Procfile               # Railway/Heroku deploy command
  requirements.in        # Loose dependency ranges (edit this)
  requirements.txt       # Pinned lockfile generated from requirements.in
  PLAN.md                # Original planning brief / design notes
```

---

## License

MIT
