# tools/db_client.py

"""
Temporary in-memory DB replacement.
Replace these stubs with your real database logic (MongoDB, PostgreSQL, etc.)
"""

from datetime import datetime
from typing import Dict, List, Optional

# This acts like an in-memory "DB table"
# Keys = lead_id, Values = lead records
_LEADS_DB: Dict[str, dict] = {}


def get_lead_by_id(lead_id: str) -> Optional[dict]:
    """Fetch a single lead record by ID (or return None if not found)."""
    return _LEADS_DB.get(lead_id)


def save_lead(lead_data: dict):
    """
    Create/update a lead record in the in-memory dictionary.
    Must contain at least an 'id' field.
    """
    lead_id = lead_data.get("id")
    if not lead_id:
        raise ValueError("Lead data must include an 'id' field")

    _LEADS_DB[lead_id] = lead_data
    print(f"[DB] Saved lead: {lead_id}")


def get_leads_for_followup() -> List[dict]:
    """
    Return leads that have a pending action or next_action_time due now or earlier.
    This is a simplified example. Adjust per your real logic.
    """
    now = datetime.now().isoformat()
    results = []

    for lead in _LEADS_DB.values():
        # Example check
        next_time = lead.get("next_action_time")
        pending = lead.get("pending_action")
        if pending in ["follow_up_node", "execute_call_node"] and next_time and next_time <= now:
            results.append(lead)

    return results
