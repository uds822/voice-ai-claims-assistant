"""
Unit Tests for CallSession and SessionStore State Machine.

Validates authentication transitions, 3-strike lockout, phone-switch reset,
circuit breaker for off-topic queries, and ground-truth summary generation.
"""

from app.models.claims_models import AuthState, CustomerClaimData, CustomerRecord, ClaimRecord
from app.session_store import SessionStore, CallSession


def test_session_lifecycle_and_transitions():
    """Validates session state transitions from NOT_STARTED to VERIFIED."""
    store = SessionStore()
    session = store.get_or_create("call_test_lifecycle")
    
    # Initial state
    assert session.auth_state == AuthState.NOT_STARTED
    assert not session.is_verified
    assert not session.is_locked
    
    # Identify customer
    cust_data = CustomerClaimData(
        customer=CustomerRecord(
            phone="+919876543210",
            caller_name="Aarav Sharma",
            pin_hash="mock_hash",
            claim_id="CLM-90210"
        ),
        claim=ClaimRecord(claim_id="CLM-90210", status="Documents Needed")
    )
    session.identify_customer(cust_data)
    assert session.auth_state == AuthState.IDENTIFIED
    assert session.caller_name == "Aarav Sharma"
    
    # Verify PIN
    session.record_auth_success()
    assert session.auth_state == AuthState.VERIFIED
    assert session.is_verified


def test_three_strike_lockout():
    """Validates that exactly 3 failed PIN attempts locks the session permanently."""
    store = SessionStore()
    session = store.get_or_create("call_test_lockout")
    
    # Attempt 1
    locked1 = session.record_auth_failure()
    assert not locked1
    assert session.failed_auth_attempts == 1
    assert session.auth_state == AuthState.FAILED
    
    # Attempt 2
    locked2 = session.record_auth_failure()
    assert not locked2
    assert session.failed_auth_attempts == 2
    
    # Attempt 3 (Strike 3)
    locked3 = session.record_auth_failure()
    assert locked3 is True
    assert session.failed_auth_attempts == 3
    assert session.auth_state == AuthState.LOCKED
    assert session.is_locked


def test_phone_switch_resets_verification():
    """Security check: Changing registered phone number mid-call revokes verification."""
    store = SessionStore()
    session = store.get_or_create("call_test_phone_switch")
    
    # Authenticate User 1
    cust1 = CustomerClaimData(
        customer=CustomerRecord(phone="+919876543210", caller_name="Aarav", pin_hash="h1")
    )
    session.identify_customer(cust1)
    session.record_auth_success()
    assert session.is_verified is True
    
    # Attempt to switch to User 2's phone
    cust2 = CustomerClaimData(
        customer=CustomerRecord(phone="+919812345678", caller_name="Priya", pin_hash="h2")
    )
    session.identify_customer(cust2)
    
    # Verification MUST be revoked immediately
    assert session.auth_state != AuthState.VERIFIED
    assert session.is_verified is False
    assert session.caller_phone == "+919812345678"


def test_off_topic_circuit_breaker():
    """Validates that 2 consecutive unsupported queries trips the circuit breaker."""
    store = SessionStore()
    session = store.get_or_create("call_test_breaker")
    
    # Query 1: Off-topic
    tripped1 = session.record_unsupported_query()
    assert tripped1 is False
    assert session.unsupported_query_count == 1
    
    # Query 2: Off-topic -> Trips circuit breaker!
    tripped2 = session.record_unsupported_query()
    assert tripped2 is True
    assert session.unsupported_query_count == 2
    
    # Asking a valid question resets the counter
    session.reset_unsupported_query_count()
    assert session.unsupported_query_count == 0


def test_ground_truth_summary_generation():
    """Validates that post-call summary is generated from server ground truth events."""
    store = SessionStore()
    session = store.get_or_create("call_test_summary")
    
    cust_data = CustomerClaimData(
        customer=CustomerRecord(phone="+919876543210", caller_name="Aarav Sharma", pin_hash="h1"),
        claim=ClaimRecord(claim_id="CLM-90210", status="Documents Needed")
    )
    session.identify_customer(cust_data)
    session.record_auth_success()
    
    summary = session.generate_ground_truth_summary()
    assert "Aarav Sharma" in summary
    assert "Auth: verified" in summary
    assert "CLM-90210" in summary
    assert "Documents Needed" in summary
