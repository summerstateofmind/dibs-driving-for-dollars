"""One-time import of existing leads from xlsx into Airtable + skip trace missing owners."""

import re
import time
import logging
import openpyxl
import httpx
from datetime import datetime, timezone

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import config
from app.skip_trace import skip_trace

from pyairtable import Api

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

api = Api(config.AIRTABLE_PAT)
table = api.table(config.AIRTABLE_BASE_ID, "Leads")

# --- Campaign step sequence (for deriving step from old outreach data) ---
# Letter 1 → Door Knock → Email → Letter 2 → Letter 3 → Quarterly Drip
STEPS = ["Not Started", "Call / SMS", "Door Knock", "Letter 1", "Email", "Letter 2", "Quarterly Drip"]


def parse_city_state_zip(raw: str) -> tuple[str, str, str]:
    """Parse 'Seattle, WA 98108' into (city, state, zip)."""
    if not raw or not raw.strip():
        return ("Seattle", "WA", "")
    raw = raw.strip()
    # Skip non-location values
    if any(kw in raw.lower() for kw in ["renter", "abandoned", "find"]):
        return ("Seattle", "WA", "")
    m = re.match(r"^(.+?),\s*([A-Z]{2})\s*(\d{5})?", raw)
    if m:
        return (m.group(1).strip(), m.group(2), m.group(3) or "")
    return (raw, "WA", "")


def clean_address(addr: str) -> str:
    """Strip city/state/zip if embedded in address field."""
    if not addr:
        return ""
    # Remove trailing ", Seattle, WA 98136" patterns
    return re.sub(r",\s*Seattle,?\s*WA\s*\d*$", "", addr.strip(), flags=re.IGNORECASE).strip()


def clean_phone(raw) -> str:
    """Return cleaned phone or empty string."""
    if not raw or not isinstance(raw, str):
        return ""
    raw = raw.strip()
    if any(kw in raw.lower() for kw in ["bad", "no num", "in contacts", "none"]):
        return ""
    # Keep only if it looks like a phone number
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 10:
        return raw.strip()
    return ""


def split_emails(raw) -> list[str]:
    """Split comma-separated emails, clean trailing commas."""
    if not raw or not isinstance(raw, str):
        return []
    emails = [e.strip().rstrip(",") for e in raw.split(",") if "@" in e]
    return emails[:2]


def build_notes(row) -> str:
    """Consolidate outreach history into notes."""
    parts = []
    # row indices: 8=Notes, 9=Call Status, 10=SMS, 11=Email Status, 12=Mailer Status, 13=Door Knock
    labels = [
        (8, "Notes"),
        (9, "Calls"),
        (10, "SMS"),
        (11, "Email outreach"),
        (12, "Mailer"),
        (13, "Door knock"),
    ]
    for idx, label in labels:
        val = row[idx]
        if val and str(val).strip() and str(val).strip() != "-":
            parts.append(f"{label}: {str(val).strip()}")

    # Include owner address if present
    owner_addr = row[7]
    if owner_addr and str(owner_addr).strip():
        parts.append(f"Owner mailing address: {str(owner_addr).strip()}")

    # Include quality
    quality = row[3]
    if quality and str(quality).strip():
        parts.append(f"Lead quality: {str(quality).strip()}")

    # City/state field if it has notes (like "Renter - find owner")
    city_raw = row[1]
    if city_raw and any(kw in str(city_raw).lower() for kw in ["renter", "abandoned", "find"]):
        parts.append(f"Note: {str(city_raw).strip()}")

    return "\n".join(parts)


def derive_campaign_step(row) -> str:
    """Derive next campaign step from old outreach columns.
    Sequence: Not Started → Call / SMS → Door Knock → Letter 1 → Email → Letter 2 → Quarterly Drip
    """
    door_knock = row[13]
    mailer = row[12]
    email_status = row[11]
    call_status = row[9]
    sms_status = row[10]

    # Work backwards from furthest completed step to find what's NEXT
    if email_status and str(email_status).strip():
        return "Letter 2"
    if mailer and str(mailer).strip() and str(mailer).strip() != "To-send":
        return "Email"
    if door_knock and str(door_knock).strip() and str(door_knock).strip() != "To-send":
        return "Letter 1"
    if mailer and str(mailer).strip() == "To-send":
        return "Letter 1"
    if door_knock and str(door_knock).strip() == "To-send":
        return "Door Knock"
    if call_status or sms_status:
        return "Door Knock"  # Calls/SMS done, next is door knock
    return "Not Started"


def derive_status(row, has_owner: bool) -> str:
    """Derive lifecycle status from outreach history."""
    notes_raw = str(row[8] or "").lower()
    call_raw = str(row[9] or "").lower()

    if "not interested" in notes_raw or "not interested" in call_raw:
        return "Dead"
    if "answered" in call_raw or "talked" in call_raw or "responded" in notes_raw:
        return "Contacted"
    if any(row[i] for i in [9, 10, 11, 12, 13] if row[i] and str(row[i]).strip() and str(row[i]).strip() != "-"):
        return "Campaigning"
    return "New"


def main():
    wb = openpyxl.load_workbook("Existing leads to parse and re-upload.xlsx")
    ws = wb["Prospects "]

    leads = []
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row, values_only=True):
        addr = row[0]
        if not addr or not isinstance(addr, str) or addr.strip() == "SS Facilities":
            continue
        # Skip empty-looking rows
        if not any(row[i] for i in range(1, 14)):
            # Check if address alone is meaningful (has a number)
            if not re.search(r"\d", addr):
                continue
        leads.append(row)

    log.info(f"Found {len(leads)} leads to import\n")

    results = {"created": 0, "skip_traced": 0, "skip_failed": [], "errors": []}

    for row in leads:
        addr_raw = str(row[0]).strip()
        address = clean_address(addr_raw)
        city, state, zip_code = parse_city_state_zip(str(row[1] or ""))
        owner_name = str(row[2]).strip() if row[2] else ""
        phone1 = clean_phone(row[4])
        phone2 = clean_phone(row[5])
        emails = split_emails(row[6])
        notes = build_notes(row)
        has_owner = bool(owner_name)
        campaign_step = derive_campaign_step(row)
        status = derive_status(row, has_owner)
        skip_status = "Complete" if has_owner else "Pending"

        fields = {
            "Address": address,
            "City": city,
            "State": state,
            "Zip": zip_code,
            "Status": status,
            "Campaign Step": campaign_step,
            "Owner Name": owner_name,
            "Skip Trace Status": skip_status,
            "Captured At": datetime.now(timezone.utc).isoformat(),
            "Notes": notes,
        }
        if phone1:
            fields["Phone 1"] = phone1
        if phone2:
            fields["Phone 2"] = phone2
        for i, email in enumerate(emails, 1):
            fields[f"Email {i}"] = email

        # Create record
        try:
            record = table.create(fields)
            results["created"] += 1
            log.info(f"+ {address} — {status}, step={campaign_step}")
        except Exception as e:
            log.error(f"  FAILED to create {address}: {e}")
            results["errors"].append(address)
            continue

        # Skip trace if no owner
        if not has_owner:
            log.info(f"  Running skip trace for {address}...")
            owner_info = skip_trace(address, city, state, zip_code)
            if owner_info:
                update_fields = {
                    "Owner Name": owner_info["owner_name"],
                    "Skip Trace Status": "Complete",
                }
                phones = owner_info.get("phones", [])
                for i, p in enumerate(phones[:3], 1):
                    update_fields[f"Phone {i}"] = p["number"]
                    update_fields[f"Phone Type {i}"] = p.get("type", "")
                trace_emails = owner_info.get("emails", [])
                for i, e in enumerate(trace_emails[:2], 1):
                    update_fields[f"Email {i}"] = e

                table.update(record["id"], update_fields)
                results["skip_traced"] += 1
                log.info(f"  → Owner: {owner_info['owner_name']}, {len(phones)} phones, {len(trace_emails)} emails")
            else:
                table.update(record["id"], {"Skip Trace Status": "Failed"})
                results["skip_failed"].append(address)
                log.info(f"  → Skip trace MISS — no owner found")

            time.sleep(0.5)  # Be polite to Tracerfy

    # Summary
    log.info(f"\n{'='*50}")
    log.info(f"IMPORT COMPLETE")
    log.info(f"  Created: {results['created']}")
    log.info(f"  Skip traced: {results['skip_traced']}")
    log.info(f"  Skip trace misses: {len(results['skip_failed'])}")
    if results["skip_failed"]:
        for addr in results["skip_failed"]:
            log.info(f"    - {addr}")
    if results["errors"]:
        log.info(f"  Errors: {len(results['errors'])}")
        for addr in results["errors"]:
            log.info(f"    - {addr}")


if __name__ == "__main__":
    main()
