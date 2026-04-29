import logging
import re
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import Response

from app import config
from app.airtable_client import create_lead, find_leads_by_address, update_lead, get_all_leads
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

    send_sms(reply)


# --- Command handlers ---


def handle_command(parsed: dict):
    cmd = parsed.get("command", "")

    if cmd == "help":
        send_sms(
            "D4D Commands:\n"
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
        send_sms("\n".join(lines))

    elif cmd == "kill":
        update_lead(lead["id"], {"Status": "Dead"})
        send_sms(f"Killed {addr}. RIP.")

    elif cmd == "note":
        note_text = parsed.get("note_text", "")
        existing_notes = fields.get("Notes", "") or ""
        ts = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
        updated = f"{existing_notes}\n[{ts}] {note_text}".strip()
        update_lead(lead["id"], {"Notes": updated})
        send_sms(f"Note added to {addr}.")

    elif cmd == "done":
        handle_done(lead)

    elif cmd in ("skip", "start"):
        send_sms(f"'{cmd}' coming soon.")

    else:
        send_sms(f"Unknown command: {cmd}. Text HELP.")


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
        send_sms(f"{addr} is already at {current_step}. Campaign complete.")
        return

    next_step = CAMPAIGN_SEQUENCE[idx + 1]
    ts = datetime.now(timezone.utc).strftime("%m/%d %I:%M%p")
    existing_notes = fields.get("Notes", "") or ""
    updated_notes = f"{existing_notes}\n[{ts}] Completed: {current_step}".strip()

    update_lead(lead["id"], {
        "Campaign Step": next_step,
        "Notes": updated_notes,
    })
    send_sms(f"{addr}\nDone: {current_step}\nNext: {next_step}")


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
    send_sms("\n".join(lines))
