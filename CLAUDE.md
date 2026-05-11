# Dibs — Driving for Dollars

## Project overview
Personal text-driven tool for capturing real estate leads while walking/driving neighborhoods. Send an address to a Telegram bot (or Twilio SMS number) → AI parses it → skip traces the owner → starts an outreach campaign → reminders via Telegram/SMS. Desktop view via Airtable (read-mostly). Single-user tool, built for a solo real estate investor.

## Architecture
- **Backend:** FastAPI (Python), stateless — deployed on Railway (or any PaaS / VPS)
- **Messaging:** Telegram bot (primary, zero cost) or Twilio SMS (optional, requires A2P 10DLC brand registration in the US)
- **AI parser:** Claude Haiku 4.5 for address/command parsing
- **Skip trace:** Tracerfy API (pay-per-record, auto-on-capture by default)
- **Storage + UI:** Airtable Free tier (REST API, 1,000 records, 1,000 API calls/mo)
- **Email:** Resend API (Railway/PaaS) or Gmail SMTP (VPS) for auto-email campaign steps
- **Scheduler:** APScheduler in-process for daily digest + auto-email

## Key constraints
- The chat channel (Telegram or SMS) is the ONLY write path — all state transitions flow through the webhook handler
- Tool only messages the operator, NEVER a third party for SMS (TCPA compliance). Email outreach to owners is opt-in via `AUTO_EMAIL_ENABLED`.
- Stay under 1,000 Airtable API calls/month
- Cost ceiling ~$25/mo total (Telegram path is closer to $5–10/mo)
- Simple > clever — must run for years with minimal maintenance
- Campaign cadence is config (template files / DB rows), not code constants

## Tech stack
- Python 3.12+
- FastAPI
- python-telegram-bot (or Twilio SDK for SMS path)
- Anthropic SDK (Haiku 4.5)
- pyairtable
- httpx (for Tracerfy + Resend APIs)
- APScheduler

## Development practices
- Incremental builds: plan first, build piece by piece, test each piece
- Feature branches for major work (`feat/*`), keep `master` stable
- Always ask user to test before committing — never auto-commit
- Review code for bugs before every commit
- Keep code succinct and elegant — no bloat, no unnecessary abstractions
- User is a semi-technical PM, not an engineer — clear inline docs help

## Channel notes
- **Telegram is the default** because it's free and avoids Twilio's A2P 10DLC brand-verification process, which rejects any project whose webhook domain doesn't match a registered LLC name.
- **Twilio SMS** is still supported (works with iMessage, Siri, CarPlay, and iOS Shortcuts) but requires US carrier brand registration. Treat it as optional / advanced.

## Planning doc
See `PLAN.md` for the full planning brief with architecture, command spec, campaign cadence, and historical open questions.
