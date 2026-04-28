import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import Response

from app import config
from app.airtable_client import create_lead, find_leads_by_address, update_lead
from app.parser import parse_sms
from app.skip_trace import skip_trace
from app.sms import send_sms

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="D4D SMS Tool")
EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'


# --- Webhook endpoint ---


@app.post("/sms")
async def handle_sms(request: Request, background_tasks: BackgroundTasks):
    """Twilio inbound SMS webhook. Returns immediately, processes in background."""
    form = await request.form()
    from_number = form.get("From", "")
    body = form.get("Body", "").strip()

    # Only accept messages from the owner
    if from_number != config.MY_PHONE_NUMBER:
        log.warning("Rejected SMS from %s", from_number)
        return Response(content=EMPTY_TWIML, media_type="text/xml")

    if not body:
        return Response(content=EMPTY_TWIML, media_type="text/xml")

    log.info("Received: %s", body)
    background_tasks.add_task(process_sms, body)
    return Response(content=EMPTY_TWIML, media_type="text/xml")


@app.get("/health")
def health():
    return {"status": "ok"}


# --- Processing ---


def process_sms(body: str):
    """Route an inbound SMS to the right handler."""
    try:
        parsed = parse_sms(body)
        log.info("Parsed: %s", parsed)

        msg_type = parsed.get("type")
        if msg_type == "capture":
            handle_capture(parsed)
        elif msg_type == "command":
            handle_command(parsed)
        else:
            send_sms("Couldn't parse that. Text HELP for commands.")
    except Exception:
        log.exception("Error processing: %s", body)
        send_sms("Something went wrong. Try again?")


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
        send_sms(
            f"Already tracking {lead.get('Address', address)}. "
            f"Status: {lead.get('Status', '?')}."
        )
        return

    skip_enabled = "-ns" not in flags
    campaign_enabled = "-nc" not in flags
    status = "Campaigning" if campaign_enabled else "New"

    # Create lead in Airtable
    record = create_lead(
        address=address,
        city=city,
        state=state,
        zip_code=zip_code,
        notes=notes,
        status=status,
        skip_trace_status="Pending" if skip_enabled else "Skipped",
    )

    # Skip trace
    owner_info = None
    if skip_enabled:
        owner_info = skip_trace(address, city, state, zip_code)
        if owner_info:
            phones = owner_info.get("phones", [])
            emails = owner_info.get("emails", [])
            fields = {
                "Owner Name": owner_info["owner_name"],
                "LLC Name": owner_info.get("llc_name") or "",
                "Skip Trace Status": "Complete",
            }
            # Spread phones into Phone 1/2/3 and Phone Type 1/2/3
            for i, p in enumerate(phones[:3], 1):
                fields[f"Phone {i}"] = p["number"]
                fields[f"Phone Type {i}"] = p.get("type", "")
            # Spread emails into Email 1/2
            for i, e in enumerate(emails[:2], 1):
                fields[f"Email {i}"] = e
            update_lead(record["id"], fields)
        else:
            update_lead(record["id"], {"Skip Trace Status": "Failed"})

    # Reply
    parts = [f"Logged {address}."]
    if owner_info:
        parts.append(f"Owner: {owner_info['owner_name']}.")
        phones = owner_info.get("phones", [])
        emails = owner_info.get("emails", [])
        pc, ec = len(phones), len(emails)
        parts.append(f"{pc} phone{'s' if pc != 1 else ''}, {ec} email{'s' if ec != 1 else ''}.")
    elif skip_enabled:
        parts.append("Skip trace failed — manual lookup needed.")
    if campaign_enabled:
        parts.append("First action (Letter 1) due Day 7.")

    send_sms(" ".join(parts))


# --- Command handlers ---


def handle_command(parsed: dict):
    cmd = parsed.get("command", "")

    if cmd == "help":
        send_sms(
            "D4D Commands:\n"
            "<address> = Log + skip + campaign\n"
            "<address> -ns = No skip trace\n"
            "<address> -nc = No campaign\n"
            "done <action> <addr> = Complete action\n"
            "kill <addr> = Mark dead\n"
            "status <addr> = Get info\n"
            "note <addr> <text> = Add note\n"
            "help = This message"
        )
        return

    fragment = parsed.get("address_fragment", "")
    if not fragment:
        send_sms(f"Need an address. E.g.: {cmd} 4823 32nd")
        return

    leads = find_leads_by_address(fragment)

    if not leads:
        send_sms(f"No lead matching '{fragment}'.")
        return

    if len(leads) > 1:
        options = "\n".join(
            f"{i + 1}. {l['fields'].get('Address', '?')}"
            for i, l in enumerate(leads[:5])
        )
        send_sms(f"Multiple matches:\n{options}")
        return

    lead = leads[0]
    fields = lead["fields"]
    addr = fields.get("Address", "?")

    if cmd == "status":
        lines = [addr, f"Status: {fields.get('Status', '?')}"]
        if fields.get("Owner Name"):
            lines.append(f"Owner: {fields['Owner Name']}")
        # Show available phones
        for i in range(1, 4):
            num = fields.get(f"Phone {i}")
            if num:
                ptype = fields.get(f"Phone Type {i}", "")
                label = f" ({ptype})" if ptype else ""
                lines.append(f"Ph{i}: {num}{label}")
        if fields.get("Condition Notes"):
            lines.append(f"Notes: {fields['Condition Notes']}")
        send_sms("\n".join(lines))

    elif cmd == "kill":
        update_lead(lead["id"], {"Status": "Dead"})
        send_sms(f"Killed {addr}.")

    elif cmd == "note":
        note_text = parsed.get("note_text", "")
        existing_notes = fields.get("Notes", "") or ""
        ts = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
        updated = f"{existing_notes}\n[{ts}] {note_text}".strip()
        update_lead(lead["id"], {"Notes": updated})
        send_sms(f"Note added to {addr}.")

    elif cmd in ("done", "skip", "start"):
        send_sms(f"'{cmd}' is coming in Weekend 2.")

    else:
        send_sms(f"Unknown command: {cmd}. Text HELP.")
