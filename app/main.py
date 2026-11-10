import hmac
import logging
import re
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import Response
from twilio.request_validator import RequestValidator

from app import config
from app.airtable_client import create_lead, find_leads_by_address, update_lead, get_all_leads
from app.parser import parse_sms
from app.reply import send_reply, set_reply_channel
from app.scheduler import start_scheduler, run_daily_job
from app.skip_trace import skip_trace

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# Interactive docs and the OpenAPI schema are disabled: this is a private,
# single-user webhook service and should not advertise its routes.
app = FastAPI(
    title="Dibs — Driving for Dollars",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


@app.on_event("startup")
def on_startup():
    start_scheduler()


# --- Request authentication helpers ---


def _secrets_match(provided: str, expected: str) -> bool:
    """Constant-time comparison. An empty expected secret never matches (fail closed)."""
    if not expected or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def _forbidden() -> Response:
    return Response(status_code=403, content="Forbidden")


def _public_url(request: Request) -> str:
    """The URL the outside world used to reach this request.

    Twilio signs the public URL, but behind Railway's proxy the app sees plain
    http and an internal host. Prefer PUBLIC_BASE_URL; otherwise rebuild the
    URL from the proxy's forwarded headers.
    """
    path = request.url.path
    if request.url.query:
        path += f"?{request.url.query}"
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL + path
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).split(",")[0].strip()
    host = (
        request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    ).split(",")[0].strip()
    return f"{proto}://{host}{path}"


# --- Webhook endpoints ---


@app.post("/sms")
async def handle_sms(request: Request, background_tasks: BackgroundTasks):
    """Twilio inbound SMS webhook. Returns immediately, processes in background.

    Every request must carry a valid X-Twilio-Signature. While the SMS path is
    not configured (no auth token or no operator number) all requests are rejected.
    """
    if not config.TWILIO_AUTH_TOKEN or not config.MY_PHONE_NUMBER:
        log.warning("Rejected SMS webhook: SMS path is not configured")
        return _forbidden()

    form = await request.form()
    params = {k: v for k, v in form.items() if isinstance(v, str)}
    signature = request.headers.get("x-twilio-signature", "")
    validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
    if not signature or not validator.validate(_public_url(request), params, signature):
        log.warning("Rejected SMS webhook: missing or invalid Twilio signature")
        return _forbidden()

    from_number = params.get("From", "")
    body = params.get("Body", "").strip()

    if from_number != config.MY_PHONE_NUMBER:
        log.warning("Ignored SMS from an unexpected sender")
        return Response(content=EMPTY_TWIML, media_type="text/xml")

    if not body:
        return Response(content=EMPTY_TWIML, media_type="text/xml")

    log.info("Received SMS: %s", body)
    background_tasks.add_task(process_message, body, "sms")
    return Response(content=EMPTY_TWIML, media_type="text/xml")


@app.post("/telegram")
async def handle_telegram(request: Request, background_tasks: BackgroundTasks):
    """Telegram Bot webhook. Returns 200 immediately, processes in background.

    Telegram sends the secret registered via setWebhook in the
    X-Telegram-Bot-Api-Secret-Token header. Requests without the right secret
    are rejected, and so is everything while TELEGRAM_WEBHOOK_SECRET or
    TELEGRAM_CHAT_ID is unset.
    """
    if not config.TELEGRAM_WEBHOOK_SECRET or not config.TELEGRAM_CHAT_ID:
        log.warning("Rejected Telegram webhook: secret or chat ID is not configured")
        return _forbidden()

    provided = request.headers.get("x-telegram-bot-api-secret-token", "")
    if not _secrets_match(provided, config.TELEGRAM_WEBHOOK_SECRET):
        log.warning("Rejected Telegram webhook: missing or wrong secret token")
        return _forbidden()

    try:
        data = await request.json()
    except ValueError:
        return Response(status_code=400, content="Bad Request")
    if not isinstance(data, dict):
        return Response(status_code=400, content="Bad Request")

    message = data.get("message") or {}
    chat = message.get("chat") if isinstance(message, dict) else None
    chat_id = str((chat or {}).get("id", "")) if isinstance(chat or {}, dict) else ""
    text = (message.get("text") or "").strip() if isinstance(message, dict) else ""
    if not isinstance(text, str):
        text = ""

    if chat_id != config.TELEGRAM_CHAT_ID:
        log.warning("Ignored Telegram message from an unexpected chat")
        return {"ok": True}

    if not text:
        return {"ok": True}

    log.info("Received Telegram: %s", text)
    background_tasks.add_task(process_message, text, "telegram", chat_id=chat_id)
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/cron/daily")
def cron_daily(request: Request, secret: str = ""):
    """Manual trigger for the daily digest job. Protected by CRON_SECRET.

    Send the secret in an `X-Cron-Secret` header or as `Authorization: Bearer <secret>`.
    Rejects everything while CRON_SECRET is unset.
    """
    provided = request.headers.get("x-cron-secret", "")
    if not provided:
        scheme, _, token = request.headers.get("authorization", "").partition(" ")
        if scheme.lower() == "bearer":
            provided = token.strip()
    if not provided and secret:
        # DEPRECATED: a secret in the query string ends up in access logs and
        # browser history. Kept only so existing callers keep working; remove
        # once they send a header instead.
        log.warning("/cron/daily called with the deprecated ?secret= query parameter")
        provided = secret

    if not _secrets_match(provided, config.CRON_SECRET):
        return _forbidden()
    run_daily_job()
    return {"status": "ok", "message": "Daily job triggered"}


# --- Processing ---


def process_message(body: str, channel: str = "sms", **kwargs):
    """Route an inbound message to the right handler."""
    set_reply_channel(channel, **kwargs)
    try:
        parsed = parse_sms(body)
        log.info("Parsed: %s", parsed)

        msg_type = parsed.get("type")
        if msg_type == "capture":
            handle_capture(parsed)
        elif msg_type == "command":
            handle_command(parsed)
        else:
            send_reply("Couldn't parse that. Text HELP for commands.")
    except Exception:
        log.exception("Error processing: %s", body)
        send_reply("Something went wrong. Try again?")


# --- Capture flow ---


def handle_capture(parsed: dict):
    address = parsed["address"]
    city = parsed.get("city", "Seattle")
    state = parsed.get("state", "WA")
    zip_code = parsed.get("zip", "")
    notes = parsed.get("notes", "")
    flags = parsed.get("flags", [])

    # Duplicate check
    existing = find_leads_by_address(address)
    if existing:
        lead = existing[0]["fields"]
        send_reply(
            f"Dupe — already tracking {lead.get('Address', address)}. "
            f"Status: {lead.get('Status', '?')}. "
            f"Text 'status {address.split()[0]}' for details."
        )
        return

    skip_enabled = "-ns" not in flags
    campaign_enabled = "-nc" not in flags
    status = "Campaigning" if campaign_enabled else "New"
    campaign_step = "Call / SMS" if campaign_enabled else "Not Started"

    # Create lead in Airtable
    record = create_lead(
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        notes=notes,
        status=status,
        skip_trace_status="Pending" if skip_enabled else "Skipped",
        campaign_step=campaign_step,
    )

    # Skip trace
    owner_info = None
    if skip_enabled:
        owner_info = skip_trace(address, city, state, zip_code)
        if owner_info:
            phones = owner_info.get("phones", [])
            emails = owner_info.get("emails", [])
            mailing = owner_info.get("mailing_address", "")
            owner_occupied = check_owner_occupied(address, mailing)

            fields = {
                "Owner Name": owner_info["owner_name"],
                "LLC Name": owner_info.get("llc_name") or "",
                "Skip Trace Status": "Complete",
                "Owner Address": mailing,
                "Owner Occupied?": owner_occupied,
            }
            for i, p in enumerate(phones[:3], 1):
                fields[f"Phone {i}"] = p["number"]
                fields[f"Phone Type {i}"] = p.get("type", "")
            for i, e in enumerate(emails[:2], 1):
                fields[f"Email {i}"] = e
            update_lead(record["id"], fields)
        else:
            update_lead(record["id"], {"Skip Trace Status": "Failed"})

    # Reply
    if owner_info:
        phones = owner_info.get("phones", [])
        ph1 = phones[0]["number"] if phones else "none"
        occ_label = "Owner-occupied" if owner_occupied == "Yes" else "NOT owner-occupied" if owner_occupied == "No" else "Occupancy unknown"
        reply = (
            f"Tracked {address}.\n"
            f"{occ_label}\n"
            f"Owner: {owner_info['owner_name']}\n"
            f"Ph1: {ph1}\n"
            f"Step: {campaign_step}"
        )
    elif skip_enabled:
        reply = f"Tracked {address}.\nSkip trace miss — manual lookup needed.\nStep: {campaign_step}"
    else:
        reply = f"Tracked {address} (no skip trace).\nStep: {campaign_step}"

    send_reply(reply)


# --- Command handlers ---


def handle_command(parsed: dict):
    cmd = parsed.get("command", "")

    if cmd == "help":
        send_reply(
            "Dibs 🚙 Commands:\n"
            "<address> = Log + skip + campaign\n"
            "<address> -ns = No skip trace\n"
            "<address> -nc = No campaign\n"
            "done <addr> = Advance campaign step\n"
            "status <addr> = Get lead info\n"
            "note <addr> <text> = Add note\n"
            "kill <addr> = Mark dead\n"
            "list = Active lead count\n"
            "help = This message"
        )
        return

    if cmd == "list":
        handle_list()
        return

    fragment = parsed.get("address_fragment", "")
    if not fragment:
        send_reply(f"Need an address. E.g.: {cmd} 1234 Main")
        return

    leads = find_leads_by_address(fragment)

    if not leads:
        send_reply(f"No lead matching '{fragment}'.")
        return

    if len(leads) > 1:
        options = "\n".join(
            f"{i + 1}. {l['fields'].get('Address', '?')}"
            for i, l in enumerate(leads[:5])
        )
        send_reply(f"Multiple matches:\n{options}")
        return

    lead = leads[0]
    fields = lead["fields"]
    addr = fields.get("Address", "?")

    if cmd == "status":
        lines = [addr]
        lines.append(f"Status: {fields.get('Status', '?')} | Step: {fields.get('Campaign Step', '?')}")
        if fields.get("Owner Name"):
            lines.append(f"Owner: {fields['Owner Name']}")
        for i in range(1, 4):
            num = fields.get(f"Phone {i}")
            if num:
                ptype = fields.get(f"Phone Type {i}", "")
                pstatus = fields.get(f"Phone {i} Status", "")
                label_parts = [p for p in [ptype, pstatus] if p]
                label = f" ({', '.join(label_parts)})" if label_parts else ""
                lines.append(f"Ph{i}: {num}{label}")
        for i in range(1, 3):
            email = fields.get(f"Email {i}")
            if email:
                lines.append(f"Email: {email}")
        if fields.get("Condition Notes"):
            lines.append(f"Notes: {fields['Condition Notes']}")
        send_reply("\n".join(lines))

    elif cmd == "kill":
        update_lead(lead["id"], {"Status": "Dead"})
        send_reply(f"Killed {addr}. RIP.")

    elif cmd == "note":
        note_text = parsed.get("note_text", "")
        existing_notes = fields.get("Notes", "") or ""
        ts = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
        updated = f"{existing_notes}\n[{ts}] {note_text}".strip()
        update_lead(lead["id"], {"Notes": updated})
        send_reply(f"Note added to {addr}.")

    elif cmd == "done":
        handle_done(lead)

    elif cmd in ("skip", "start"):
        send_reply(f"'{cmd}' coming soon.")

    else:
        send_reply(f"Unknown command: {cmd}. Text HELP.")


CAMPAIGN_SEQUENCE = ["Not Started", "Call / SMS", "Door Knock", "Letter 1", "Email", "Letter 2", "Quarterly Drip"]


def handle_done(lead: dict):
    """Advance a lead to the next campaign step."""
    fields = lead["fields"]
    addr = fields.get("Address", "?")
    current_step = fields.get("Campaign Step", "Not Started")

    try:
        idx = CAMPAIGN_SEQUENCE.index(current_step)
    except ValueError:
        idx = 0

    if idx >= len(CAMPAIGN_SEQUENCE) - 1:
        send_reply(f"{addr} is already at {current_step}. Campaign complete.")
        return

    next_step = CAMPAIGN_SEQUENCE[idx + 1]
    ts = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
    existing_notes = fields.get("Notes", "") or ""
    updated_notes = f"{existing_notes}\n[{ts}] Completed: {current_step}".strip()

    update_lead(lead["id"], {
        "Campaign Step": next_step,
        "Step Completed At": datetime.now(timezone.utc).isoformat(),
        "Notes": updated_notes,
    })
    send_reply(f"{addr}\nDone: {current_step}\nNext: {next_step}")


def check_owner_occupied(property_address: str, mailing_address: str) -> str:
    """Compare property address to owner mailing address. Returns Yes/No/Unknown."""
    if not mailing_address:
        return "Unknown"
    # Extract street number from both
    prop_num = re.match(r"(\d+)", property_address.strip())
    mail_num = re.match(r"(\d+)", mailing_address.strip())
    if not prop_num or not mail_num:
        return "Unknown"
    if prop_num.group(1) != mail_num.group(1):
        return "No"
    # Street numbers match — check street name similarity
    prop_words = property_address.lower().split()[:4]
    mail_words = mailing_address.lower().split()[:4]
    # If first 2-3 words overlap, it's a match
    overlap = set(prop_words) & set(mail_words)
    return "Yes" if len(overlap) >= 2 else "No"


def handle_list():
    """Reply with a count of active leads by status."""
    all_leads = get_all_leads()
    counts = {}
    for rec in all_leads:
        status = rec["fields"].get("Status", "Unknown")
        counts[status] = counts.get(status, 0) + 1

    lines = [f"Leads: {len(all_leads)} total"]
    for status in ["Campaigning", "Contacted", "New", "Under Contract", "Dead"]:
        if status in counts:
            lines.append(f"  {status}: {counts[status]}")
    send_reply("\n".join(lines))
