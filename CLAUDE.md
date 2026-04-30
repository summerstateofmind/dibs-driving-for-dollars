# D4D SMS Tool — Driving for Dollars

## Project overview
Personal SMS-driven tool for capturing real estate leads while walking/driving neighborhoods. Text an address to a Twilio number → AI parses it → skip traces the owner → starts an outreach campaign → reminders via SMS. Desktop view via Airtable (read-mostly). Single-user tool, built for a solo real estate investor.

## Architecture
- **Backend:** FastAPI (Python), stateless — deployed on VPS or Lambda (TBD)
- **SMS:** Twilio (inbound webhook + outbound notifications)
- **AI parser:** Claude Haiku 4.5 for address/command parsing
- **Skip trace:** REISkip API (pay-per-record, auto-on-capture by default)
- **Storage + UI:** Airtable Free tier (REST API, 1,000 records, 1,000 API calls/mo)
- **Scheduler:** APScheduler or cron for due-date reminders

## Key constraints
- SMS is the ONLY write path — all state transitions flow through the SMS webhook handler
- Tool only messages the user, NEVER a third party (TCPA compliance)
- Stay under 1,000 Airtable API calls/month
- Cost ceiling ~$25/mo total
- Simple > clever — must run for years with minimal maintenance
- Campaign cadence is config (YAML/DB rows), not code constants

## Tech stack
- Python 3.12+
- FastAPI
- Twilio SDK
- Anthropic SDK (Haiku 4.5)
- pyairtable
- httpx (for REISkip API)

## Development practices
- Incremental builds: plan first, build piece by piece, test each piece
- Feature branches for major work (`feat/*`), keep `main` stable
- Always ask user to test before committing — never auto-commit
- Review code for bugs before every commit
- Keep code succinct and elegant — no bloat, no unnecessary abstractions
- User is a semi-technical PM, not an engineer — clear inline docs help

## Project phases
1. **Weekend 1:** Twilio + webhook + AI parse + Airtable write + REISkip + reply
2. **Weekend 2:** Campaign engine, scheduler, SMS commands (done/kill/status/note)
3. **Weekend 3+:** iOS Shortcut, daily digest, letter drafts, MMS photo support

## Planning doc
See `d4d-sms-tool-plan.md` for the full planning brief with architecture, SMS command spec, campaign cadence, and open questions.
