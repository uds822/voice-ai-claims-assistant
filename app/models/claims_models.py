"""
Domain Models for Observe Insurance Claims.

These Pydantic models define the structure for Customers, Claims,
Authentication states, and Post-Call interaction logs.
"""

from typing import Optional
from enum import Enum
from pydantic import BaseModel, Field


class AuthState(str, Enum):
    """Possible authentication states for a call session."""
    NOT_STARTED = "not_started"
    IDENTIFIED = "identified"     # Phone found, awaiting PIN
    VERIFIED = "verified"         # Correct PIN confirmed
    FAILED = "failed"             # Incorrect PIN
    LOCKED = "locked"             # 3 consecutive incorrect PINs


class CustomerRecord(BaseModel):
    """Customer account details retrieved from Airtable."""
    phone: str
    caller_name: str
    pin_hash: str                 # Salted hash (never store plain PIN)
    claim_id: Optional[str] = None


class ClaimRecord(BaseModel):
    """Claim details retrieved from Airtable."""
    claim_id: str
    status: str                   # e.g., "Approved", "Under Review", "Documents Needed"
    documents_required: bool = False
    document_instructions: Optional[str] = None
    last_updated: Optional[str] = None


class CustomerClaimData(BaseModel):
    """Combined customer and claim view used during a verified session."""
    customer: CustomerRecord
    claim: Optional[ClaimRecord] = None


class PostCallRecord(BaseModel):
    """
    Data structure written to Airtable CallLogs table (and backup CSV DLQ) at the end of every call.
    Matches the fields in the 'CallLogs' table.
    """
    call_id: str
    timestamp_utc: str
    caller_name: str = "Unverified Caller"
    phone_last_four: str = "N/A"
    auth_outcome: str             # "verified", "locked", "not_started", etc.
    claim_status_read: str = "N/A"
    escalated: bool = False
    emergency: bool = False
    callback_requested: bool = False
    callback_phone: Optional[str] = None
    sentiment: str = "Neutral"
    call_summary: str = ""
    ended_reason: str = "unknown"
