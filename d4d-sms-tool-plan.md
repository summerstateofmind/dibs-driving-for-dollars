# Driving/Walking for Dollars SMS Tool — Planning Brief

> **How to use this doc:** I'm handing this to you (Claude) in a fresh session to help me design and build a personal tool. Read the whole thing first. At the end I list open decisions — please walk me through those before we start building. I'd rather decide architecture deliberately than dive into code.

---

## Who I am / context you need

- I'm a real estate investor ([Your LLC], [Your Company]), doing off-market acquisitions.
- Day job: technical PM. I'm comfortable with Python, AWS, Twilio-style APIs, and I use Claude Code daily.
- I have an existing manual outbound workflow (skip-traced list → manual click-to-dial → AI-assisted live convo → manual SMS). **This tool is separate from that.** No data sharing required.
- My other side projects ([other project], [other project]) don't intersect with this tool today. Treat this as a fully standalone personal tool.
- **I'm on iPhone for mobile, PC for desktop.** No iMessage on desktop — important for the architecture (see below).
- **TCPA / state autodialer rules:** worth noting only because **this tool only ever messages me.** Outbound to property owners is always a manual action I take outside this tool. Build accordingly — no code path should ever SMS a third party.

## What this tool is for

When I'm walking or driving the neighborhood and spot a house I want to investigate (vacant-looking, deferred maintenance, abandoned vehicles, etc.), I want a frictionless capture mechanism that:

1. Lets me text the address to a number from my phone, hands-free if possible.
2. Logs it, skip-traces the owner, and starts a default outreach campaign — all in one shot.
3. Pings me when the next action is due ("Time to mail Letter 1 to 1234 Example St NE").
4. Lets me mark actions done and modify campaigns via SMS commands.

This tool replaces the role of a Driving-for-Dollars SaaS (DealMachine, PropStream's D4D, etc.) and the lightweight CRM piece for these specific spontaneous leads. It is **not** trying to replace skip-trace tools, dialers, or my outbound calling rig.

## Phone + desktop split

This is a hybrid two-surface tool, not a chat tool:

- **Phone (SMS via Twilio):** the only write path. All state changes — capture, skip trace toggles, campaign edits, action completions, kills — happen through SMS commands.
- **Desktop (web UI = Airtable):** read-only workspace. Where I review leads, draft mail-merge letters, look at enrichment data, and take outbound actions. I can hand-edit notes and photos in Airtable too, but state transitions go through SMS.

We considered WhatsApp for cross-device. **Rejected** — still a chat thread, no sortable views, no filters.

**Why SMS-as-only-write-path:** I'm on PC, so no iMessage on desktop. But this constraint actually produces a cleaner architecture. The backend never has to detect Airtable field changes (which the free plan makes annoying — see Airtable section). Every state transition has one entry point. Years from now this is still trivial to maintain.

## View layer: Airtable-as-UI for v1

Use Airtable as the entire view layer for v1.

- Airtable Free fits: 1,000 records per base (I'll be at a few hundred), 5 editors, 1 GB attachments, mobile + web apps included.
- **Watch-out: Free plan caps at 1,000 API calls per workspace per month.** Since SMS is the only write path, write volume is naturally bounded by my message volume. Keep reads frugal too.
- **Watch-out: Free plan caps automation runs at 100/month.** All scheduling and notification logic lives in our own backend, not Airtable Automations.
- Migrate to a custom React/Next.js frontend later only if Airtable's UX or limits start to bite. Schema stays portable either way.

Airtable interface views to build:
- **Lead inbox** — sorted by recency, filter by status (New, Pursuing, Active Campaign, Dead, Contacted, Under Contract).
- **Today's actions** — every action due today across all leads.
- **Lead detail** — single record with all enrichment, contact info, action history, notes, photo.

## Core user flow (happy path)

```
Me (walking past house): SMS → "1234 Example St NE Anytown. Vacant, plywood on
                                  one window, lawn knee-high, no car."

Tool: 1. Parses address + condition notes (LLM)
      2. Geocodes / validates address
      3. Creates Lead in Airtable, status = Active Campaign
      4. Fires REISkip → writes owner, phones, emails to lead
      5. Initializes default campaign (action records with due dates)
      6. SMS reply: "Logged 1234 Example St NE. Owner: Jane Smith.
                     2 phones, 1 email. First action (Letter 1) due Day 7."

Me (later, at PC): Reviews lead in Airtable. Drafts and mails Letter 1 on Day 7.
SMS → "done letter 1 1234 Example"

Tool: Marks Action 1 complete, schedules Action 2.

Tool (3 weeks later): SMS → "Door knock due today: 1234 Example St NE.
                              Owner: Jane Smith. Last touch: Letter 1 mailed Nov 2."
```

**Default behavior on capture: skip trace + start campaign immediately.** At ~$0.10–0.25 per trace × ~30 leads/month, the cost (~$3–7/mo) is rounding error against having owner info ready the moment I sit down at my desk. Use SMS flags (below) to opt out per-lead.

**PII note:** auto-skip-on-capture means owner names hit Airtable immediately on every captured address. That's a third-party system holding more PII than a "log only" approach would. REISkip already has this data; the marginal exposure is low. Flagging for awareness, not blocking.

## SMS command spec (v1 starter set)

Plain text → default behavior (capture, skip trace, start campaign).

Flag suffix on a capture message modifies behavior:

| Command | Effect |
|---------|--------|
| `<address>` | Default: log + skip trace + start campaign |
| `<address> -ns` | No skip trace. Just log it, decide later. |
| `<address> -nc` | No campaign. Log + skip trace, but don't start cadence. Useful for leads I want info on but am not committed to. |
| `<address> -hot` | Skip the 0–3 day decision window, start campaign immediately at Day 7 action |

Standalone commands (no address parsing, just keywords):

| Command | Effect |
|---------|--------|
| `done <action> <addr-fragment>` | Mark current action complete, advance campaign. e.g. `done letter 1 1234 Example` |
| `skip <addr-fragment>` | Run skip trace on a previously `-ns` lead |
| `start <addr-fragment>` | Start campaign on a previously `-nc` lead |
| `kill <addr-fragment>` | Mark lead dead, stop all reminders |
| `status <addr-fragment>` | Reply with current status, owner info, next action |
| `note <addr-fragment> <text>` | Append to lead notes |
| `help` | Reply with command list |

Address fragment matching: LLM-assisted fuzzy match against active leads. If ambiguous, reply with numbered list and ask me to pick.

## Default campaign cadence (starting point — adjust to taste)

| Day | Action | Channel | Notes |
|-----|--------|---------|-------|
| 0 | Log + skip trace + reply | Auto | Owner info in confirmation SMS |
| 7 | Letter 1 (handwritten yellow letter) | Me, mailed | Tool prompts and shows merge fields |
| 21 | Letter 2 (postcard or typed) | Me, mailed | Different format than #1 |
| 35 | Door knock | Me, in person | Tool gives owner name + script reminder |
| 50 | Door hanger / flyer | Me, in person | Only if no contact yet |
| 70 | Letter 3 | Me, mailed | "Final" letter framing |
| 100 | Quarterly drip begins | Me, mailed | Until lead is dispositioned |

Treat this as a config (YAML or DB rows), not as code-level constants. I want to tweak per-lead and per-cohort.

## Skip trace integration

**Provisional provider: REISkip.** Why:
- Has a real API (most competitors are CSV-only or have $500/mo minimums).
- Real-estate-focused, decent LLC resolution.
- Pay-per-record, no monthly minimum.
- BatchData (formerly BatchSkipTracing) was the obvious pick but moved to a $500/mo subscription floor — dead for my volume.
- Tracerfy is cheaper ($0.02/lead) but bulk minimum is 1,000 records; need to confirm whether per-call API has a minimum too. Worth a 10-min discovery call before committing.

**Expected cost:** $3–7/mo at ~30 captures/mo with auto-skip default.

**Build size:** small. Single HTTP call on capture, ~50 lines. Real work is decision logic for edge cases.

**Failure handling:**
- No match → flag lead for manual lookup, don't block campaign start.
- LLC owner → flag for manual entity research, surface LLC name + state.
- Multiple phones → store all, no preference logic in v1.

## Key design decisions (already made)

1. **SMS provider:** Twilio. ~$1/mo number + $0.0079/msg.
2. **AI parser:** Claude Haiku 4.5. Friction-free capture is the whole point. Cost is rounding-error.
3. **Storage + UI:** Airtable Free. Backend (FastAPI) talks to Airtable's REST API. Schema lives in Airtable; backend is stateless.
4. **Notifications:** outbound SMS to me via Twilio. Apple Reminders via Shortcuts as optional secondary layer.
5. **Hands-free capture:** iOS Shortcut grabs current location, reverse-geocodes, SMS-sends to the tool. One-tap or Siri ("log this house").
6. **Write path:** SMS only. Airtable is read-mostly (hand-editable notes/photos OK, but state machine lives in the backend, triggered by SMS).
7. **Skip trace default:** auto-on-capture. Use `-ns` flag to opt out per-lead.

## Architecture sketch

```
[My phone] ──SMS──> [Twilio number]
                        │
                        ▼ webhook
              [FastAPI app on Lambda or small VPS]
                        │
            ┌───────────┼─────────────┬────────────────┐
            ▼           ▼             ▼                ▼
      [LLM parser]  [Geocode]   [REISkip API]  [Airtable REST]
       (Haiku)                    (default                │
                                   on capture)            ▼
                                                  [Airtable Interfaces:
                                                   web + mobile UI,
                                                   read-mostly]

  [Scheduler: APScheduler or cron] ──fires due actions──> [Outbound SMS via Twilio]
```

**Architectural rules:**
- All writes to Airtable are SMS-driven or scheduler-driven. No polling Airtable for changes.
- Stay under 1,000 Airtable API calls/month.
- All campaign state transitions flow through one entry point (the SMS webhook handler).

## MVP scope

**Weekend 1 — capture + skip trace:**
1. Twilio number + webhook receiver (FastAPI).
2. Inbound SMS → AI parse → write Lead to Airtable → fire REISkip → reply with owner info.
3. `-ns` flag handling.
4. Manual review via Airtable interface I build.

**Weekend 2 — campaign loop:**
1. Define campaign-as-config (cadence table above).
2. On capture (default) or `start` command, instantiate action records with due dates.
3. Scheduler emits SMS reminders at action due dates.
4. `done`, `kill`, `status`, `note` commands.
5. Fuzzy address matching for command targets.

**Weekend 3+ — polish:**
1. iOS Shortcut for hands-free capture.
2. Daily digest SMS at 8am with all due actions.
3. Letter draft generation (LLM fills template with merge fields, I print and mail).
4. MMS support for capture (photo of the house).
5. `-hot` and `-nc` flag handling.

## Stretch / phase 2

- Photo intake via MMS — store in Airtable + run a vision model to flag distress signals.
- Disposition tracking: outcome codes (contacted / dead-end / under-contract / closed).
- Custom React/Next.js frontend if Airtable starts to feel limiting.
- Letter mail-merge → service like Lob for actual mailing automation (still a manual go/no-go).

## Constraints / non-negotiables

- **No SaaS dependency for the core flow.** Twilio + Airtable Free + REISkip pay-per-use are all OK; I own the keys, no vendor can lock me in or jack monthly pricing on me.
- **TCPA / state law:** Tool only messages me. Never a third party. Outbound to leads is always a manual action I take outside this tool.
- **Single-user for v1.** I'm the only operator.
- **Simple > clever.** I want this to run for years with minimal maintenance.
- **Cost ceiling: ~$25/mo total at low volume.** Twilio (~$2) + REISkip (~$5–7) + LLM calls (~$1) + hosting (~$5) + Airtable ($0). Should fit comfortably.

## Open questions I want you to push me on before we start building

1. **Hosting:** Lambda + EventBridge vs a $5 VPS with FastAPI + cron. Pros/cons for *this specific* workload at my scale (probably <50 leads/month).
2. **Schema:** what does the Lead record look like? What does an Action record look like? Sketch the minimum useful Airtable schema (tables, fields, links, status enums).
3. **Address-fragment fuzzy matching:** what's the simplest reliable approach? LLM call on every command? Local string match against active leads? Hybrid (local first, LLM fallback)?
4. **Failure modes:** what happens if I text a junk address, a duplicate, or an address with a typo? How should the tool clarify without being annoying?
5. **Skip trace provider:** is REISkip actually the right starting bet, or should we burn 30 minutes vetting Tracerfy and one other option first?
6. **Anything I'm missing.** I've been thinking about this for a couple of hours. You're fresh. What did I not consider?

Once we've worked through those, propose a concrete v1 Airtable schema + a one-page build plan and we'll start coding.
