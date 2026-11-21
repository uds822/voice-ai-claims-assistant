"""
In-Memory Call Session Store & State Machine.

Maintains server-side state for active calls keyed by Vapi call_id.
Enforces authentication boundaries, tracks failed attempts, and prevents
unauthorized access to sensitive claims data.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from app.config import get_settings
from app.models.claims_models import AuthState, CustomerClaimData
from app.utils.security import mask_phone_number

logger = logging.getLogger("observe.session")


class CallSession(BaseModel):
    """
    Represents the complete state of a single live phone or browser call.
    Tracks authentication, attempt limits, call flags, and an audit trail.
    """
    call_id: str
    caller_phone: Optional[str] = None
    caller_name: Optional[str] = None
    auth_state: AuthState = AuthState.NOT_STARTED
    failed_auth_attempts: int = 0
    
    # Cached customer and claim data once retrieved
    customer_data: Optional[CustomerClaimData] = None
    
    # Call handling flags
    is_escalated: bool = False
    is_emergency: bool = False
    callback_requested: bool = False
    callback_phone: Optional[str] = None
    
    # Cost & Abuse protection: count consecutive out-of-scope queries
    unsupported_query_count: int = 0
    
    # Audit log of actions observed by the server during this call
    events: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_verified(self) -> bool:
        """Helper to check if caller has successfully verified their PIN."""
        return self.auth_state == AuthState.VERIFIED

    @property
    def is_locked(self) -> bool:
        """Helper to check if caller is locked out due to excessive failed PIN attempts."""
        return self.auth_state == AuthState.LOCKED

    def record_event(self, event_name: str):
        """Appends a factual event to the call's audit log with a timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.events.append(f"[{timestamp}] {event_name}")
        self.last_activity = datetime.now(timezone.utc)

    # =========================================================================
    # State Machine Transition Methods
    # =========================================================================

    def identify_customer(self, customer_data: CustomerClaimData):
        """
        Transitions state when customer phone is successfully looked up.
        If a different phone was already verified, resets auth for security.
        """
        new_phone = customer_data.customer.phone
        # Security: Changing phone number mid-call resets verification
        if self.caller_phone and self.caller_phone != new_phone:
            self.auth_state = AuthState.NOT_STARTED
            self.failed_auth_attempts = 0
            self.record_event(f"phone_changed_reset_auth: {mask_phone_number(new_phone)}")

        self.caller_phone = new_phone
        self.caller_name = customer_data.customer.caller_name
        self.customer_data = customer_data
        
        # Only set to IDENTIFIED if not already locked
        if not self.is_locked:
            self.auth_state = AuthState.IDENTIFIED
            self.record_event(f"customer_identified: {self.caller_name}")

    def record_auth_success(self):
        """Transitions state to VERIFIED upon entering correct 6-digit PIN."""
        self.auth_state = AuthState.VERIFIED
        self.failed_auth_attempts = 0
        self.record_event("pin_verified_successfully")

    def record_auth_failure(self) -> bool:
        """
        Records an incorrect PIN attempt.
        Locks the session if consecutive failures reach MAX_AUTH_ATTEMPTS (3).
        Returns True if locked out, False otherwise.
        """
        self.failed_auth_attempts += 1
        settings = get_settings()

        if self.failed_auth_attempts >= settings.MAX_AUTH_ATTEMPTS:
            self.auth_state = AuthState.LOCKED
            self.record_event(f"auth_locked_out_after_{self.failed_auth_attempts}_attempts")
            return True

        self.auth_state = AuthState.FAILED
        self.record_event(f"pin_failed_attempt_{self.failed_auth_attempts}")
        return False

    def record_unsupported_query(self) -> bool:
        """
        Increments off-topic query counter.
        Returns True if circuit breaker is tripped (>= 2 consecutive unsupported queries).
        """
        self.unsupported_query_count += 1
        self.record_event(f"unsupported_query_count_{self.unsupported_query_count}")
        return self.unsupported_query_count >= 2

    def reset_unsupported_query_count(self):
        """Resets off-topic counter when a valid insurance query is asked."""
        self.unsupported_query_count = 0

    def set_escalated(self, callback_phone: Optional[str] = None):
        """Flags call as escalated to human support, recording callback phone if provided."""
        self.is_escalated = True
        if callback_phone:
            self.callback_requested = True
            self.callback_phone = callback_phone
            self.record_event(f"escalated_callback_scheduled: {mask_phone_number(callback_phone)}")
        else:
            self.record_event("escalated_to_representative")

    def set_emergency(self):
        """Flags call as physical emergency, stopping all claims processing."""
        self.is_emergency = True
        self.record_event("emergency_flagged_triaged_to_112")

    def generate_ground_truth_summary(self) -> str:
        """Builds a factual, non-hallucinated summary from server-observed events."""
        parts = []
        if self.caller_name:
            parts.append(f"Caller: {self.caller_name}.")
        else:
            parts.append("Caller: Unverified.")

        parts.append(f"Auth: {self.auth_state.value}.")

        if self.is_emergency:
            parts.append("CRITICAL: Active emergency reported; caller directed to 112.")
        elif self.is_escalated:
            if self.callback_requested and self.callback_phone:
                parts.append(f"Escalated: Callback requested for {mask_phone_number(self.callback_phone)}.")
            else:
                parts.append("Escalated: Transferred to human support.")
        elif self.is_verified and self.customer_data and self.customer_data.claim:
            parts.append(f"Claim {self.customer_data.claim.claim_id} status '{self.customer_data.claim.status}' communicated.")
        else:
            parts.append("Call completed.")

        return " ".join(parts)


# =============================================================================
# Session Store Manager (Thread-Safe In-Memory Registry)
# =============================================================================

class SessionStore:
    """
    Manages active call sessions in memory.
    Provides thread-safe access, state retrieval, and automatic stale session cleanup.
    """
    def __init__(self):
        self._sessions: Dict[str, CallSession] = {}
        self._lock = threading.Lock()

    def get_or_create(self, call_id: str) -> CallSession:
        """Retrieves existing session for call_id or initializes a fresh one."""
        with self._lock:
            if call_id not in self._sessions:
                logger.info(f"Initializing new CallSession for call_id: {call_id}")
                self._sessions[call_id] = CallSession(call_id=call_id)
            return self._sessions[call_id]

    def get(self, call_id: str) -> Optional[CallSession]:
        """Retrieves session by call_id if it exists, otherwise None."""
        with self._lock:
            return self._sessions.get(call_id)

    def end_session(self, call_id: str) -> Optional[CallSession]:
        """
        Retrieves and removes a completed call session from active memory.
        Used at end-of-call to finalize reporting.
        """
        with self._lock:
            session = self._sessions.pop(call_id, None)
            if session:
                logger.info(f"Closed CallSession for call_id: {call_id}")
            return session

    def cleanup_stale_sessions(self, max_age_seconds: int = 7200):
        """
        Removes abandoned sessions older than max_age_seconds (default 2 hours)
        to prevent memory leaks.
        """
        now = datetime.now(timezone.utc)
        with self._lock:
            stale_keys = [
                cid for cid, sess in self._sessions.items()
                if (now - sess.last_activity).total_seconds() > max_age_seconds
            ]
            for cid in stale_keys:
                del self._sessions[cid]
                logger.info(f"Evicted stale session: {cid}")


# Global singleton instance for clean dependency injection
session_store = SessionStore()
