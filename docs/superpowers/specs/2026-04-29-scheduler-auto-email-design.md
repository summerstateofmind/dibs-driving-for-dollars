# Dibs — Daily Digest + Auto-Email Design Spec

**Date:** 2026-04-29
**Status:** Draft
**Scope:** Add a daily scheduler that sends a morning digest of due campaign actions, and auto-sends templated emails to property owners when leads reach the Email and Quarterly Drip steps.

---

## Problem

The tool captures leads and tracks campaign steps, but the user has to manually check Airtable to know what's due. There's no proactive nudge. The Email campaign step also requires manual effort despite being easily automatable with a template.

## Solution

1. **Daily digest** — An 8am PT text message summarizing all leads with pending actions.
2. **Auto-email** — Templated emails sent automatically when a lead reaches the Email or Quarterly Drip campaign step.

Both run from a single APScheduler job inside the existing FastAPI app.

---

## Airtable Schema Changes

Three new fields on the Leads table:

| Field | Type | Purpose |
|-------|------|---------|
| `Step Completed At` | Single line text | ISO timestamp of last step completion via `done` command |
| `Emails Sent` | Number (default 0) | Count of auto-emails sent to this lead |
| `Last Email Sent At` | Single line text | ISO timestamp of last auto-email. Used to space drip emails. |
| `Email Opt Out` | Checkbox | If checked, no auto-emails sent to this lead |

No changes to existing fields.

---

## Campaign Step Timing

| Step | Timing | Action |
|------|--------|--------|
| Call / SMS | ASAP | Manual — appears in digest daily until done |
| Door Knock | ASAP | Manual — appears in digest daily until done |
| Letter 1 | ASAP | Manual — appears in digest daily until done |
| Email | ASAP | **Auto-send** on first daily run after reaching this step |
| Letter 2 | 30 days after Email step completed | Manual — appears in digest when due |
| Quarterly Drip | Every 90 days after last email | **Auto-send** drip email, stays in this step |

---

## Daily Digest

### Trigger
APScheduler job runs daily at 8:00 AM Pacific.

### Logic
1. Fetch all leads where Status = "Campaigning"
2. Bucket each lead:
   - **DO NOW**: Campaign Step is Call/SMS, Door Knock, or Letter 1
   - **COMING DUE**: Campaign Step is Letter 2, and 30+ days since `Step Completed At`
   - Auto-email and drip leads are handled silently (see Auto-Email section)
3. Build and send digest message

### Message Format
```
Dibs 🚙 Daily — 4/30

DO NOW (3):
  Call: 1234 Example St — Jane Smith (206-555-1234)
  Door Knock: 5678 Oak Ave (Bob Jones)
  Letter 1: 910 Pine St (LLC Holdings)

COMING DUE (1):
  Letter 2: 222 Elm St (due 5/3)

Total active: 12 leads
```

- Phone number included inline for Call / SMS step only (Phone 1 field)
- Owner name in parentheses for all steps
- If nothing is due, no message sent (don't spam)

### Delivery
Uses `send_reply` with a default channel. If `TELEGRAM_CHAT_ID` is set, sends via Telegram. Otherwise falls back to SMS.

---

## Auto-Email

### Trigger
Same daily scheduler job. After building the digest, processes auto-email leads.

### Email Step Logic
For leads where Campaign Step = "Email":
1. Check `Emails Sent` == 0 (hasn't been sent yet)
2. Check `Email Opt Out` is not checked
3. Check lead has at least one email address (Email 1 field)
4. Send initial outreach email via Gmail SMTP
5. Update Airtable: increment `Emails Sent`, set `Last Email Sent At`, advance Campaign Step to "Letter 2", set `Step Completed At`, append to Notes
6. Text user: "Auto-emailed Jane Smith (1234 Example St) — step advanced to Letter 2"

If no email address on the lead:
- Text user: "No email for 1234 Example St — skipping auto-email, manual outreach needed"
- Do NOT advance the step

### Quarterly Drip Logic
For leads where Campaign Step = "Quarterly Drip":
1. Check 90+ days since `Last Email Sent At`
2. Check `Email Opt Out` is not checked
3. Check lead has at least one email address
4. Send quarterly drip email via Gmail SMTP
5. Update Airtable: increment `Emails Sent`, set `Last Email Sent At`, append to Notes
6. Text user: "Drip email sent to Jane Smith (1234 Example St)"

Lead stays in Quarterly Drip step indefinitely until manually killed.

### Email Provider
Gmail SMTP with app password. Emails come from the user's real Gmail address.

**Config:**
```
SMTP_EMAIL=your.email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

### Templates
Plain text, field merges only. No AI generation. Stored as files in `templates/` directory.

**`templates/initial_outreach.txt`:**
```
Subject: Your property at {address}

Hi {owner_name},

My name is Skyler with Three Willows Capital. I'm reaching out about your property at {address}, {city}, {state}.

If you've ever considered selling, I'd love to have a quick conversation. I buy properties in any condition and can close on your timeline.

Feel free to call or text me at {your_phone}.

If you'd rather not hear from me, just reply "stop" and I won't reach out again.

Best,
Skyler
```

**`templates/quarterly_drip.txt`:**
```
Subject: Still interested in {address}

Hi {owner_name},

I reached out a while back about your property at {address}. Just wanted to check in — if you're considering selling, my offer still stands.

Call or text anytime: {your_phone}.

If you'd rather not hear from me, just reply "stop" and I won't reach out again.

Best,
Skyler
```

**Merge fields** (pulled from Airtable):
- `{owner_name}` — Owner Name
- `{address}` — Address
- `{city}` — City
- `{state}` — State
- `{your_phone}` — from `MY_PHONE_NUMBER` env var

---

## New Files

| File | Purpose |
|------|---------|
| `app/scheduler.py` | APScheduler setup, daily job, digest builder, auto-email logic |
| `app/emailer.py` | Gmail SMTP send function, template loading and field merging |
| `templates/initial_outreach.txt` | Initial email template |
| `templates/quarterly_drip.txt` | Quarterly drip email template |

## Modified Files

| File | Change |
|------|--------|
| `app/main.py` | Start scheduler on app startup, add `GET /cron/daily` fallback endpoint |
| `app/config.py` | Add `SMTP_EMAIL`, `SMTP_PASSWORD`, `DIGEST_HOUR`, `DIGEST_TIMEZONE` |
| `requirements.txt` | Add `apscheduler` |
| `.env.example` | Add SMTP and digest config placeholders |

---

## Fallback Endpoint

`GET /cron/daily` — triggers the daily digest + auto-email job manually. Useful for testing and as a backup if the scheduler misses a run.

---

## Config

| Variable | Default | Purpose |
|----------|---------|---------|
| `SMTP_EMAIL` | (required for auto-email) | Gmail address to send from |
| `SMTP_PASSWORD` | (required for auto-email) | Gmail app password |
| `DIGEST_HOUR` | 8 | Hour to send daily digest (24hr) |
| `DIGEST_TIMEZONE` | America/Los_Angeles | Timezone for digest schedule |

---

## What This Does NOT Include

- Web dashboard or UI beyond Airtable
- AI-generated email copy (templates only)
- Data enrichment (public records, tax liens, comps) — future work, likely in FlaggedLeads
- Multi-user support
- Batch capture or MMS photo support
