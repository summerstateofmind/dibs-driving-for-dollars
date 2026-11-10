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


def _escape_formula_string(value):
    """Escape text for use inside a double-quoted Airtable formula string.

    Backslashes are escaped first so an embedded or trailing backslash cannot
    cancel out the escaping of a quote and break out of the string.
    """
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def find_leads_by_address(fragment):
    """Find leads whose Address contains the given fragment (case-insensitive)."""
    safe = _escape_formula_string(fragment)
    formula = f'FIND(LOWER("{safe}"), LOWER({{Address}}))'
    return _get_table().all(formula=formula)


def get_all_leads():
    """Return all lead records."""
    return _get_table().all()


def get_campaigning_leads():
    """Return leads where Status = Campaigning (filtered server-side to save API calls)."""
    return _get_table().all(formula="{Status} = 'Campaigning'")


def update_lead(record_id, fields):
    """Update fields on an existing Lead record."""
    return _get_table().update(record_id, fields)
