import logging
import httpx
from app import config

log = logging.getLogger(__name__)

# Tracerfy instant lookup — sync, single address, 5 credits per hit, 0 on miss
TRACERFY_URL = "https://tracerfy.com/v1/api/trace/lookup/"


def skip_trace(address: str, city: str, state: str, zip_code: str) -> dict | None:
    """Skip trace via Tracerfy instant lookup. Returns owner info or None."""
    if not config.TRACERFY_API_KEY:
        log.warning("TRACERFY_API_KEY not set — skipping trace")
        return None

    try:
        resp = httpx.post(
            TRACERFY_URL,
            headers={
                "Authorization": f"Bearer {config.TRACERFY_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "address": address,
                "city": city,
                "state": state,
                "zip": zip_code,
                "find_owner": True,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        if not data.get("hit") or not data.get("persons"):
            log.info("Skip trace miss for %s", address)
            return None

        # Use first person (primary owner)
        person = data["persons"][0]
        name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()

        # Extract up to 3 phones ranked by priority, with type
        raw_phones = sorted(person.get("phones") or [], key=lambda p: p.get("rank", 99))
        phones = []
        for p in raw_phones[:3]:
            phones.append({
                "number": p.get("number", ""),
                "type": p.get("type", ""),  # Mobile or Landline
            })

        # Extract up to 2 emails ranked by priority (response is {email, rank})
        raw_emails = sorted(person.get("emails") or [], key=lambda e: e.get("rank", 99))
        emails = [e.get("email", "") for e in raw_emails[:2]]

        return {
            "owner_name": name or "Unknown",
            "phones": phones,
            "emails": emails,
            "llc_name": None,  # Tracerfy doesn't return LLC in instant lookup
        }
    except Exception:
        log.exception("Skip trace failed for %s, %s %s", address, city, state)
        return None
