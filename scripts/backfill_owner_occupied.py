"""Backfill Owner Address and Owner Occupied? for existing leads by re-running skip trace."""

import re
import time
import logging
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyairtable import Api
from app import config
from app.skip_trace import skip_trace

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)

api = Api(config.AIRTABLE_PAT)
table = api.table(config.AIRTABLE_BASE_ID, "Leads")


def check_owner_occupied(property_address, mailing_address):
    if not mailing_address:
        return "Unknown"
    prop_num = re.match(r"(\d+)", property_address.strip())
    mail_num = re.match(r"(\d+)", mailing_address.strip())
    if not prop_num or not mail_num:
        return "Unknown"
    if prop_num.group(1) != mail_num.group(1):
        return "No"
    prop_words = property_address.lower().split()[:4]
    mail_words = mailing_address.lower().split()[:4]
    overlap = set(prop_words) & set(mail_words)
    return "Yes" if len(overlap) >= 2 else "No"


def main():
    records = table.all()
    log.info(f"Found {len(records)} leads\n")

    stats = {"skipped": 0, "traced": 0, "miss": 0, "already_has": 0}
    misses = []

    for rec in records:
        f = rec["fields"]
        addr = f.get("Address", "")
        owner = f.get("Owner Name", "")
        existing_owner_addr = f.get("Owner Address", "")

        # Skip leads with no owner (can't determine occupancy)
        if not owner:
            log.info(f"  SKIP {addr} — no owner name")
            stats["skipped"] += 1
            continue

        # If we already have an owner address from old data in Notes, try parsing it
        if not existing_owner_addr:
            notes = f.get("Notes", "") or ""
            m = re.search(r"Owner mailing address:\s*(.+?)(?:\n|$)", notes)
            if m and m.group(1).strip():
                existing_owner_addr = m.group(1).strip()
                occupied = check_owner_occupied(addr, existing_owner_addr)
                table.update(rec["id"], {
                    "Owner Address": existing_owner_addr,
                    "Owner Occupied?": occupied,
                })
                log.info(f"  {addr} — from Notes: {existing_owner_addr} → {occupied}")
                stats["already_has"] += 1
                continue

        # Need to re-skip trace to get mailing address
        city = f.get("City", "Seattle")
        state = f.get("State", "WA")
        zip_code = f.get("Zip", "")

        log.info(f"  Tracing {addr}...")
        result = skip_trace(addr, city, state, zip_code)

        if result and result.get("mailing_address"):
            mailing = result["mailing_address"]
            occupied = check_owner_occupied(addr, mailing)
            table.update(rec["id"], {
                "Owner Address": mailing,
                "Owner Occupied?": occupied,
            })
            log.info(f"  {addr} → {mailing} → {occupied}")
            stats["traced"] += 1
        else:
            table.update(rec["id"], {"Owner Occupied?": "Unknown"})
            log.info(f"  {addr} — trace miss or no mailing address")
            misses.append(addr)
            stats["miss"] += 1

        time.sleep(0.5)

    log.info(f"\n{'='*50}")
    log.info(f"BACKFILL COMPLETE")
    log.info(f"  From Notes: {stats['already_has']}")
    log.info(f"  Re-traced: {stats['traced']}")
    log.info(f"  Misses: {stats['miss']}")
    log.info(f"  Skipped (no owner): {stats['skipped']}")
    if misses:
        log.info(f"  Miss addresses:")
        for a in misses:
            log.info(f"    - {a}")


if __name__ == "__main__":
    main()
