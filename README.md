# D4D SMS Tool

Personal SMS-driven lead capture for real estate investors doing Driving for Dollars.

---

## What It Does

You spot a distressed property while driving or walking. You text the address to your D4D number. The tool does the rest:

1. **Capture** -- AI parses the address and any condition notes from your text.
2. **Skip trace** -- Automatically looks up the property owner, phone numbers, emails, and mailing address via Tracerfy.
3. **Campaign** -- Starts a multi-step outreach cadence (call, door knock, letters) and texts you reminders when each step is due.
4. **Manage** -- Mark steps done, add notes, kill dead leads, check status -- all via text commands.

Desktop review happens in Airtable. SMS is the only write path. The tool only ever messages you -- never a property owner or third party.

---

## Architecture

```
  YOU (iPhone)
    |
    |  SMS or Telegram message
    v
+------------------+
|  Twilio / Telegram|  (inbound webhook)
+------------------+
         |
         v
+------------------+       +------------------+
|   FastAPI app    | ----> | Claude Haiku 4.5 |
|  (stateless)     |       | (parse address   |
+------------------+       |  + commands)      |
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

  Reply SMS/Telegram sent back to you
  with confirmation + owner summary
```

All processing is stateless. Airtable is the database. SMS (or Telegram) is the only write path.

---

## Features

- **One-text capture** -- text an address, get owner info back in seconds
- **AI parsing** -- natural language input, no rigid format required
- **Auto skip trace** -- owner lookup fires on capture by default (opt out with `-ns`)
- **Owner-occupied detection** -- compares property address to owner mailing address
- **Daily digest** -- morning notification listing leads that need action today
- **Auto-email** -- sends templated emails to owners at the Email and Quarterly Drip campaign steps
- **Campaign tracking** -- multi-step outreach cadence per lead
- **Duplicate detection** -- won't re-add an address you're already tracking
- **Fuzzy address matching** -- commands work with partial addresses ("4823 32nd")
- **Telegram support** -- use Telegram instead of Twilio for zero-cost messaging
- **Airtable UI** -- sortable, filterable lead views on desktop and mobile
- **iOS Shortcut** -- one-tap or "Hey Siri, log this house" hands-free capture

---

## Command Reference

### Capture (text an address)

| Message | What happens |
|---------|-------------|
| `4823 32nd Ave NE Seattle` | Log + skip trace + start campaign |
| `4823 32nd Ave NE -ns` | Log only, no skip trace |
| `4823 32nd Ave NE -nc` | Log + skip trace, no campaign |
| `4823 32nd Ave NE. Vacant, boarded windows` | Log with condition notes |

### Commands

| Command | Example | What it does |
|---------|---------|-------------|
| `done <addr>` | `done 4823 32nd` | Mark current campaign step complete, advance to next |
| `status <addr>` | `status 4823 32nd` | Get lead details: owner, phones, status, next step |
| `note <addr> <text>` | `note 4823 32nd called owner no answer` | Append a timestamped note |
| `kill <addr>` | `kill 4823 32nd` | Mark lead dead, stop campaign |
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
- Either a Twilio account OR a Telegram bot (see paths below)

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USER/d4d-app.git
cd d4d-app
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
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

Copy `.env.example` or create `.env`:

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...
AIRTABLE_PAT=pat...
AIRTABLE_BASE_ID=appXXXXXXXX
MY_PHONE_NUMBER=+1XXXXXXXXXX

# Twilio (for SMS path)
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX

# Tracerfy (for skip tracing)
TRACERFY_API_KEY=...

# Telegram (alternative to Twilio)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 4a. Easy Setup (Telegram)

No phone number purchase required. Free messaging.

1. Message [@BotFather](https://t.me/BotFather) on Telegram. Send `/newbot`, follow the prompts, and copy the bot token.
2. Start a chat with your new bot. Send it any message.
3. Get your chat ID: visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` and find `"chat":{"id":XXXXXXX}`.
4. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in your `.env`.
5. Deploy the app (see below), then set the webhook:
   ```
   curl -X POST "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://your-app.railway.app/telegram"
   ```

### 4b. Full Setup (Twilio SMS)

Real SMS -- works with Siri, CarPlay, and iOS Shortcuts.

1. Create a [Twilio](https://www.twilio.com) account. Buy a phone number (~$1.15/mo).
2. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` in your `.env`.
3. Deploy the app (see below).
4. In Twilio console, go to your phone number's settings. Set the **Messaging webhook** to:
   ```
   https://your-app.railway.app/sms
   ```
   Method: POST.

### 5. Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

For local testing with Twilio, use [ngrok](https://ngrok.com) to expose your local server:

```bash
ngrok http 8000
```

Then set the ngrok URL as your Twilio webhook.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key for address/command parsing |
| `AIRTABLE_PAT` | Yes | Airtable Personal Access Token |
| `AIRTABLE_BASE_ID` | Yes | Airtable base ID (starts with `app`) |
| `MY_PHONE_NUMBER` | Yes | Your phone number in E.164 format (`+1XXXXXXXXXX`) |
| `TWILIO_ACCOUNT_SID` | SMS path | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | SMS path | Twilio auth token |
| `TWILIO_PHONE_NUMBER` | SMS path | Your Twilio phone number |
| `TRACERFY_API_KEY` | No | Tracerfy API key. Without it, skip trace is disabled. |
| `TELEGRAM_BOT_TOKEN` | Telegram path | Telegram bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Telegram path | Your Telegram chat ID |
| `SENDGRID_API_KEY` | SendGrid path | SendGrid API key (starts with `SG.`) |
| `SMTP_EMAIL` | Auto-email | Sender email address (Gmail or verified SendGrid sender) |
| `SMTP_PASSWORD` | SMTP path | Gmail app password (not needed if using SendGrid) |
| `YOUR_NAME` | Auto-email | Your name for email templates |
| `AUTO_EMAIL_ENABLED` | No | Set to `true` to enable auto-email. Defaults to `false`. |
| `DIGEST_HOUR` | No | Hour (0-23) to send daily digest. Default: `8` |
| `DIGEST_TIMEZONE` | No | Timezone for digest. Default: `America/Los_Angeles` |
| `CRON_SECRET` | No | Secret for manual `/cron/daily?secret=...` trigger |

---

## Daily Digest & Auto-Email

The scheduler runs inside the app process (APScheduler). Every morning at `DIGEST_HOUR` (default 8am Pacific), it:

1. **Sends you a digest** -- lists leads that need manual action today (calls, door knocks, letters coming due). Delivered via Telegram if configured, otherwise SMS.
2. **Auto-sends emails** -- for leads on the Email or Quarterly Drip step, sends a templated email to the owner and advances the campaign. Only runs when `AUTO_EMAIL_ENABLED=true`.

### Enabling auto-email

Auto-email is **off by default**. To enable:

1. Edit the email templates in `templates/` (see below).
2. Set up an email backend — SendGrid (for Railway/PaaS) or Gmail SMTP (for VPS). See below.
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

### Email backend: SendGrid (Railway / PaaS)

Railway and most PaaS hosts block outbound SMTP. Use SendGrid's API instead (free tier = 100 emails/day):

1. Sign up at [sendgrid.com](https://sendgrid.com).
2. Authenticate your sending domain (Settings > Sender Authentication).
3. Create an API key (Settings > API Keys > Full Access).
4. Set `SENDGRID_API_KEY` and `SMTP_EMAIL` (your verified sender address) in your environment.

When `SENDGRID_API_KEY` is set, emails go through SendGrid's HTTPS API.

### Email backend: Gmail SMTP (VPS)

If you're hosting on a VPS (DigitalOcean, Linode, Hetzner, etc.) where SMTP isn't blocked, you can send directly through Gmail with no third-party service:

1. Enable 2-Step Verification on your Google account.
2. Go to [App Passwords](https://myaccount.google.com/apppasswords).
3. Create a new app password (select "Mail" and your device).
4. Copy the 16-character password (e.g., `xxxx xxxx xxxx xxxx`).
5. Set `SMTP_EMAIL` and `SMTP_PASSWORD` in your environment. Leave `SENDGRID_API_KEY` unset.

When `SENDGRID_API_KEY` is not set, the app falls back to Gmail SMTP automatically.

### Opt-out handling

Each email includes "reply stop" language. If an owner replies stop, check the **Email Opt Out** checkbox in Airtable -- the scheduler will skip them going forward.

### Manual trigger

You can trigger the daily job on demand:

```
GET /cron/daily?secret=YOUR_CRON_SECRET
```

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
5. Grab your deployment URL and set it as your Twilio or Telegram webhook.

---

## iOS Shortcut

One-tap or "Hey Siri, log this house" capture. The shortcut grabs your GPS location, reverse-geocodes it to a street address, and sends it as an SMS to your D4D number.

Setup takes 2 minutes. See [docs/ios-shortcut-setup.md](docs/ios-shortcut-setup.md) for step-by-step instructions.

---

## Cost Breakdown

Estimated monthly cost at ~30 leads/month:

| Service | Cost | Notes |
|---------|------|-------|
| Twilio | ~$2/mo | $1.15/mo number + $0.0079/msg. Skip if using Telegram. |
| Tracerfy | ~$3-7/mo | ~$0.10-0.25 per skip trace. 0 credits on a miss. |
| Anthropic (Haiku) | ~$0.50/mo | One parse call per inbound message. Haiku is cheap. |
| Railway | $5/mo | Hobby plan. Sleeps when idle. |
| Airtable | $0 | Free tier: 1,000 records, 1,000 API calls/mo. |
| **Total** | **~$10-15/mo** | Well under the $25/mo ceiling. |

Using Telegram instead of Twilio drops the total by ~$2/mo.

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
d4d-app/
  app/
    main.py            # FastAPI app, webhook handler, command routing
    parser.py          # Claude Haiku SMS parser
    sms.py             # Twilio outbound SMS
    telegram_bot.py    # Telegram outbound messages + webhook setup
    reply.py           # Channel-aware reply routing (SMS or Telegram)
    airtable_client.py # Airtable read/write operations
    skip_trace.py      # Tracerfy skip trace integration
    scheduler.py       # Daily digest + auto-email orchestration
    emailer.py         # Gmail SMTP sender + template engine
    config.py          # Environment variable loading
  templates/
    initial_outreach.txt   # Email template for Email campaign step
    quarterly_drip.txt     # Email template for Quarterly Drip step
  tests/
    test_scheduler.py
    test_emailer.py
    test_airtable_filter.py
  docs/
    ios-shortcut-setup.md
  .env.example           # Template for environment variables
  Procfile               # Railway/Heroku deploy command
  requirements.txt
```

---

## License

MIT
