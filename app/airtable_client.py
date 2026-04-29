import logging
from datetime import datetime, timezone
from pyairtable import Api
from app import config

log = logging.getLogger(__name__)
_table = None


def _get_table():
    global _table
    if _table is None:
        _table = Api(config.AIRTABLE_PAT).table(config.AIRTABLE_BASE_ID, "Leads")
    return _table


def create_lead(*, address, city, state, zip_code, notes, status, skip_trace_status, campaign_step="Not Started"):
    """Create a new Lead record in Airtable."""
    return _get_table().create({
        "Address": address,
        "City": city,
        "State": state,
        "Zip": zip_code,
        "Condition Notes": notes,
        "Status": status,
        "Skip Trace Status": skip_trace_status,
        "Campaign Step": campaign_step,
        "Captured At": datetime.now(timezone.utc).isoformat(),
    })


def find_leads_by_address(fragment):
    """Find leads whose Address contains the given fragment (case-insensitive)."""
    safe = fragment.replace('"', '\\"')
    formula = f'FIND(LOWER("{safe}"), LOWER({{Address}}))'
    return _get_table().all(formula=formula)


def get_all_leads():
    """Return all lead records."""
    return _get_table().all()


def update_lead(record_id, fields):
    """Update fields on an existing Lead record."""
    return _get_table().update(record_id, fields)
