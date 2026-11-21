"""
End-to-End Integration Tests for Vapi Webhook Scenarios.

Validates all 4 required Observe.AI interview scenarios:
1. Scenario 1: Happy Path (Lookup -> Verify PIN -> Read Claim & Instructions -> FAQ -> End of Call)
2. Scenario 2: Authentication Failure & 3-Strike Lockout
3. Scenario 3: Customer Not Found
4. Scenario 4: Representative Escalation & Emergency Handling
"""

from app.tools.dispatcher import tool_dispatcher
from app.session_store import session_store
from app.models.claims_models import PostCallRecord
from app.services.sheets_service import sheets_service


def test_scenario_1_happy_path():
    """
    Scenario 1: Happy Path.
    Tests: Phone lookup -> Blocked claim check -> PIN verification -> Claim read -> FAQ -> Audit Log.
    """
    call_id = "test_happy_path_001"
    
    # 1. Lookup Customer (Aarav Sharma)
    res1 = tool_dispatcher.dispatch(call_id, "lookup_customer", {"phone_number": "9876543210"})
    assert "Aarav Sharma" in res1
    assert "6-digit security PIN" in res1
    
    # 2. Blocked Claim Read (Unverified Security Gate)
    res2 = tool_dispatcher.dispatch(call_id, "get_claim_status", {})
    assert "cannot share claim details until your identity is verified" in res2
    
    # 3. Verify PIN Correctly
    res3 = tool_dispatcher.dispatch(call_id, "verify_identity", {"pin": "123456"})
    assert "verified successfully" in res3
    
    # 4. Successful Claim Read
    res4 = tool_dispatcher.dispatch(call_id, "get_claim_status", {})
    assert "CLM-90210" in res4
    assert "Documents Needed" in res4
    assert "FIR" in res4
    
    # 5. FAQ Query
    res5 = tool_dispatcher.dispatch(call_id, "answer_faq", {"question": "office hours"})
    assert "Monday through Friday" in res5
    
    # 6. End of Call Processing
    session = session_store.end_session(call_id)
    assert session is not None
    assert session.is_verified is True
    
    summary = session.generate_ground_truth_summary()
    assert "Aarav Sharma" in summary
    assert "Documents Needed" in summary
    
    post_record = PostCallRecord(
        call_id=call_id,
        timestamp_utc="2026-11-21T06:00:00Z",
        caller_name=session.caller_name,
        auth_outcome=session.auth_state.value,
        claim_status_read=session.customer_data.claim.status,
        call_summary=summary
    )
    assert sheets_service.log_call(post_record) is True


def test_scenario_2_auth_lockout():
    """
    Scenario 2: Authentication Lockout.
    Tests: 3 consecutive wrong PINs -> Permanent Lockout -> Blocked Claim.
    """
    call_id = "test_auth_lockout_002"
    
    # 1. Lookup Customer (Sneha Rao)
    tool_dispatcher.dispatch(call_id, "lookup_customer", {"phone_number": "9432109876"})
    
    # Strike 1: Wrong PIN
    res_fail1 = tool_dispatcher.dispatch(call_id, "verify_identity", {"pin": "000000"})
    assert "2 attempts remaining" in res_fail1
    
    # Strike 2: Wrong PIN
    res_fail2 = tool_dispatcher.dispatch(call_id, "verify_identity", {"pin": "111111"})
    assert "1 attempt remaining" in res_fail2
    
    # Strike 3: Wrong PIN -> LOCKOUT TRIGGERED!
    res_fail3 = tool_dispatcher.dispatch(call_id, "verify_identity", {"pin": "222222"})
    assert "maximum of 3 failed attempts" in res_fail3
    assert "locked" in res_fail3
    
    # Verify that claims are strictly blocked
    res_claim = tool_dispatcher.dispatch(call_id, "get_claim_status", {})
    assert "cannot share claim details" in res_claim
    
    session = session_store.get(call_id)
    assert session.is_locked is True


def test_scenario_3_customer_not_found():
    """
    Scenario 3: Customer Not Found.
    Tests: Non-existent phone number returns clean recovery prompt.
    """
    call_id = "test_not_found_003"
    
    res = tool_dispatcher.dispatch(call_id, "lookup_customer", {"phone_number": "9999900000"})
    assert "could not find an account registered" in res
    assert "file a new claim, or speak to a representative" in res


def test_scenario_4_escalation_and_emergency():
    """
    Scenario 4: Escalation & Emergency Triage.
    Tests: Callback scheduling for web audio and physical safety triaging to 112.
    """
    # 1. Callback scheduling
    res_esc = tool_dispatcher.dispatch("test_esc_004", "escalate_call", {"callback_phone": "9876543210"})
    assert "recorded your request for a representative" in res_esc
    assert "call you back" in res_esc
    
    # 2. Emergency handling
    res_em = tool_dispatcher.dispatch("test_em_005", "escalate_call", {"reason": "car accident hospital emergency"})
    assert "112" in res_em
    assert "Your safety is the priority" in res_em
