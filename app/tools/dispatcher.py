"""
Tool Dispatcher & Business Logic Router.

Executes function calls requested by the Voice AI agent during live calls.
Enforces backend authorization rules, manages session state, and returns
concise, natural-language string responses for text-to-speech output.
"""

import logging
from typing import Any, Dict, Optional
from app.config import get_settings
from app.models.claims_models import AuthState
from app.services.airtable_service import airtable_service
from app.services.faq_service import faq_service
from app.session_store import session_store, CallSession
from app.utils.normalizers import normalize_phone_number, normalize_pin
from app.utils.security import verify_pin, mask_phone_number

logger = logging.getLogger("observe.dispatcher")


class ToolDispatcher:
    """Dispatches tool calls to specific business handlers with security gating."""

    def dispatch(self, call_id: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """
        Master dispatch entrypoint.
        Retrieves the caller's session, executes the tool, and returns a flat string.
        """
        session = session_store.get_or_create(call_id)
        logger.info(f"[{call_id}] Executing tool: '{tool_name}' with args: {arguments}")

        try:
            if tool_name == "lookup_customer":
                return self._handle_lookup_customer(session, arguments)
            elif tool_name == "verify_identity":
                return self._handle_verify_identity(session, arguments)
            elif tool_name == "get_claim_status":
                return self._handle_get_claim_status(session, arguments)
            elif tool_name == "answer_faq":
                return self._handle_answer_faq(session, arguments)
            elif tool_name == "escalate_call":
                return self._handle_escalate_call(session, arguments)
            else:
                logger.warning(f"[{call_id}] Unknown tool requested: '{tool_name}'")
                return "Unsupported tool requested. Let me connect you with a representative."
        except Exception as e:
            logger.error(f"[{call_id}] Error in tool '{tool_name}': {str(e)}")
            return "Our system is temporarily experiencing a delay. Let me connect you with a representative."

    # =========================================================================
    # 1. Tool: lookup_customer
    # =========================================================================
    def _handle_lookup_customer(self, session: CallSession, arguments: Dict[str, Any]) -> str:
        """Looks up a customer by phone number in Airtable."""
        raw_phone = arguments.get("phone_number") or arguments.get("phone") or ""
        normalized_phone = normalize_phone_number(str(raw_phone))

        if not normalized_phone:
            return "That phone number appears to be invalid. Please state your 10-digit registered mobile number."

        # Lockout enforcement: If session is already locked, reject new lookups
        if session.is_locked:
            return "This call session is locked due to security limits. Please hold while I transfer you to a representative."

        customer_data = airtable_service.get_customer_and_claim_by_phone(normalized_phone)

        if not customer_data:
            session.record_event(f"lookup_failed_not_found: {mask_phone_number(normalized_phone)}")
            return (
                f"I could not find an account registered under {mask_phone_number(normalized_phone)}. "
                "Would you like to repeat the number, file a new claim, or speak to a representative?"
            )

        # Transition session to IDENTIFIED
        session.identify_customer(customer_data)
        return (
            f"Thank you. I found an account for {session.caller_name}. "
            "For security verification, please provide your 6-digit security PIN."
        )

    # =========================================================================
    # 2. Tool: verify_identity
    # =========================================================================
    def _handle_verify_identity(self, session: CallSession, arguments: Dict[str, Any]) -> str:
        """Verifies the caller's 6-digit PIN against the stored PBKDF2 hash."""
        # Precondition check: Customer must be looked up first
        if not session.customer_data or session.auth_state == AuthState.NOT_STARTED:
            return "Please provide your registered phone number first so I can find your account."

        if session.is_locked:
            return "Verification is locked due to too many failed attempts. I am transferring you to a representative."

        raw_pin = arguments.get("pin") or arguments.get("pin_number") or ""
        clean_pin = normalize_pin(str(raw_pin))

        if not clean_pin:
            return "Please provide a valid 6-digit numeric security PIN."

        stored_hash = session.customer_data.customer.pin_hash
        is_valid = verify_pin(clean_pin, stored_hash)

        if is_valid:
            session.record_auth_success()
            return (
                f"Thank you, {session.caller_name}. Your identity has been verified successfully. "
                "How can I assist you with your claim today?"
            )
        else:
            is_now_locked = session.record_auth_failure()
            if is_now_locked:
                session.set_escalated()
                return (
                    "That PIN is incorrect. You have reached the maximum of 3 failed attempts. "
                    "For security reasons, your verification is locked. I will connect you with a representative."
                )
            else:
                settings = get_settings()
                remaining = settings.MAX_AUTH_ATTEMPTS - session.failed_auth_attempts
                return (
                    f"That PIN was incorrect. You have {remaining} attempt{'s' if remaining > 1 else ''} remaining. "
                    "Please state your 6-digit PIN carefully."
                )

    # =========================================================================
    # 3. Tool: get_claim_status (Strict Security Gate)
    # =========================================================================
    def _handle_get_claim_status(self, session: CallSession, arguments: Dict[str, Any]) -> str:
        """
        Returns active claim status and document submission instructions.
        STRICT SECURITY GATE: Refuses to disclose claim details unless verified.
        """
        # Backend-enforced authorization gate
        if not session.is_verified:
            session.record_event("claim_read_blocked_unverified")
            return (
                "For your security, I cannot share claim details until your identity is verified. "
                "Please provide your registered phone number and 6-digit PIN first."
            )

        if not session.customer_data or not session.customer_data.claim:
            session.record_event("no_active_claims_on_file")
            return f"{session.caller_name}, you do not have any active claims on file with us currently."

        claim = session.customer_data.claim
        session.record_event(f"claim_read_status_{claim.status}")

        response_parts = [
            f"Your claim {claim.claim_id} is currently '{claim.status}'."
        ]

        if claim.last_updated:
            response_parts.append(f"It was last updated on {claim.last_updated}.")

        if claim.documents_required and claim.document_instructions:
            response_parts.append(f"Additional documentation is required: {claim.document_instructions}")
        elif claim.documents_required:
            response_parts.append("Additional documents are required. Please upload them through your online portal.")
        else:
            response_parts.append("No additional documents are needed from you at this time.")

        return " ".join(response_parts)

    # =========================================================================
    # 4. Tool: answer_faq
    # =========================================================================
    def _handle_answer_faq(self, session: CallSession, arguments: Dict[str, Any]) -> str:
        """Answers verified corporate FAQs and tracks consecutive out-of-scope queries."""
        query = str(arguments.get("question") or arguments.get("topic") or "").strip()
        answer = faq_service.get_answer(query)

        if answer:
            # Valid question answered: reset off-topic counter
            session.reset_unsupported_query_count()
            session.record_event(f"faq_answered: {query[:30]}")
            return answer

        # Query not found in approved FAQ (Off-topic / unsupported)
        tripped = session.record_unsupported_query()
        if tripped:
            session.set_escalated()
            return (
                "I don't have verified information on that topic, and want to make sure you get the right help. "
                "Let me connect you with a representative."
            )

        return (
            "I don't have verified information on that specific question. "
            "I can assist with our office hours, mailing address, filing a new claim, or checking your claim status."
        )

    # =========================================================================
    # 5. Tool: escalate_call
    # =========================================================================
    def _handle_escalate_call(self, session: CallSession, arguments: Dict[str, Any]) -> str:
        """Handles representative escalation, callback scheduling, and emergency triaging."""
        reason = str(arguments.get("reason") or "").lower()
        callback_phone = arguments.get("callback_phone") or arguments.get("phone")

        # Emergency Detection
        if any(term in reason for term in ["emergency", "accident", "danger", "hurt", "hospital", "injury", "ambulance"]):
            session.set_emergency()
            return (
                "If anyone is injured or in immediate danger, please hang up and call local emergency services immediately at 112. "
                "Your safety is the priority. We can assist with your insurance claim once you are in a safe location."
            )

        if callback_phone:
            clean_callback = normalize_phone_number(str(callback_phone))
            session.set_escalated(callback_phone=clean_callback or str(callback_phone))
            return (
                f"I have recorded your request for a representative. "
                f"A team member will call you back at {mask_phone_number(clean_callback or str(callback_phone))}. "
                "Is there anything else I can assist with before we conclude?"
            )

        session.set_escalated()
        return "I am connecting you with a customer representative now. Please hold for just a moment."


# Global singleton instance
tool_dispatcher = ToolDispatcher()
