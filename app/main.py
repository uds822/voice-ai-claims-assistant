"""
FastAPI Main Application & Webhook Handler.

Exposes HTTP endpoints for Vapi voice platform integration:
- GET  /health: Uptime and readiness probe
- POST /webhook: Unified handler for 'tool-calls' and 'end-of-call-report' events
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.models.claims_models import PostCallRecord
from app.models.vapi_models import (
    VapiToolCallItem,
    VapiToolResponse,
    VapiToolResultItem,
    VapiWebhookRequest,
)
from app.services.sheets_service import sheets_service
from app.session_store import session_store
from app.tools.dispatcher import tool_dispatcher
from app.utils.security import get_phone_last_four, mask_phone_number

# Configure structured application logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("observe.main")

settings = get_settings()

app = FastAPI(
    title="Observe Insurance Voice Claims Agent",
    description="Deterministic backend for Observe.AI Voice AI claims assessment",
    version="1.0.0"
)

# Enable CORS for local testing widgets
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["Monitoring"])
def health_check():
    """Uptime health probe for load balancers and container orchestrators."""
    return {
        "status": "healthy",
        "service": "observe-insurance-claims-agent",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": settings.ENVIRONMENT
    }


@app.post("/webhook", tags=["Vapi Webhook"])
async def vapi_webhook(
    request: Request,
    authorization: str = Header(None, alias="Authorization"),
    x_vapi_secret: str = Header(None, alias="x-vapi-secret")
):
    """
    Unified webhook handler for Vapi voice events.
    Handles 'tool-calls' during active calls and 'end-of-call-report' upon completion.
    """
    # 1. Transport Security Check (Bearer token or x-vapi-secret)
    if settings.VAPI_SECRET_TOKEN:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        elif x_vapi_secret:
            token = x_vapi_secret.strip()

        if token != settings.VAPI_SECRET_TOKEN:
            logger.warning("Unauthorized webhook request rejected: invalid secret token.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unauthorized: Invalid Vapi secret token."
            )

    # 2. Parse incoming JSON payload
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload.")

    # Debug: Append raw incoming payload for observability
    try:
        debug_log_path = os.path.join(os.path.dirname(__file__), "..", "data", "webhook_debug.jsonl")
        with open(debug_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(body) + "\n")
    except Exception:
        pass

    message = body.get("message") if isinstance(body.get("message"), dict) else body
    message_type = message.get("type") or body.get("type")
    call_obj = message.get("call") or body.get("call") or {}
    call_id = call_obj.get("id") or body.get("callId") or message.get("callId") or "unknown_call"

    logger.info(f"[{call_id}] Received Vapi webhook event: '{message_type}'")

    # =========================================================================
    # Event 1: Tool Calls (During active live call)
    # =========================================================================
    if message_type in ["tool-calls", "tool-call", "function-call"]:
        raw_tool_calls = (
            message.get("toolCalls")
            or message.get("toolWithToolCallList")
            or message.get("toolCallList")
            or body.get("toolCalls")
            or body.get("toolWithToolCallList")
            or []
        )
        # Handle single tool call item directly
        if not raw_tool_calls and (message.get("toolCall") or body.get("toolCall")):
            raw_tool_calls = [message.get("toolCall") or body.get("toolCall")]

        results: List[Dict[str, Any]] = []

        for item in raw_tool_calls:
            if not isinstance(item, dict):
                continue

            actual_call = item.get("toolCall") if isinstance(item.get("toolCall"), dict) else item
            tool_call_id = actual_call.get("id") or item.get("id") or "unknown_tool_call_id"

            func = actual_call.get("function") if isinstance(actual_call.get("function"), dict) else actual_call
            name = func.get("name") or actual_call.get("name")
            arguments = func.get("arguments") or actual_call.get("arguments") or {}

            # Parse stringified JSON arguments if provided by LLM
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except Exception:
                    arguments = {}

            # Execute tool in dispatcher
            output_string = tool_dispatcher.dispatch(call_id, name, arguments)

            results.append({
                "toolCallId": tool_call_id,
                "result": output_string
            })

        logger.info(f"[{call_id}] Returning {len(results)} tool results to Vapi: {results}")
        # Return exact format expected by Vapi
        return JSONResponse(content={"results": results})

    # =========================================================================
    # Event 2: End of Call Report (Call has terminated)
    # =========================================================================
    elif message_type == "end-of-call-report":
        session = session_store.end_session(call_id)
        ended_reason = message.get("endedReason") or "customer-ended-call"
        analysis = message.get("analysis") or {}

        # Extract sentiment (prefer Vapi analysis if available, otherwise Neutral)
        sentiment = analysis.get("sentiment") or "Neutral"
        if sentiment not in ["Positive", "Neutral", "Frustrated"]:
            sentiment = "Neutral"

        # Construct factual summary from ground-truth session events
        if session:
            ground_truth_summary = session.generate_ground_truth_summary()
            caller_name = session.caller_name or "Unverified Caller"
            phone_last_four = get_phone_last_four(session.caller_phone)
            auth_outcome = session.auth_state.value
            claim_status = (
                session.customer_data.claim.status
                if session.customer_data and session.customer_data.claim and session.is_verified
                else "N/A"
            )
            escalated = session.is_escalated
            emergency = session.is_emergency
            callback_requested = session.callback_requested
            callback_phone = session.callback_phone
        else:
            ground_truth_summary = message.get("summary") or "Call completed without recorded session."
            caller_name = "Unverified Caller"
            phone_last_four = "N/A"
            auth_outcome = "not_started"
            claim_status = "N/A"
            escalated = False
            emergency = False
            callback_requested = False
            callback_phone = None

        post_call_record = PostCallRecord(
            call_id=call_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            caller_name=caller_name,
            phone_last_four=phone_last_four,
            auth_outcome=auth_outcome,
            claim_status_read=claim_status,
            escalated=escalated,
            emergency=emergency,
            callback_requested=callback_requested,
            callback_phone=callback_phone,
            sentiment=sentiment,
            call_summary=ground_truth_summary,
            ended_reason=ended_reason
        )

        # Write to Google Sheets (or local CSV fallback)
        success = sheets_service.log_call(post_call_record)
        logger.info(f"[{call_id}] Post-call audit logging status: {'SUCCESS' if success else 'FAILED'}")

        return {"status": "recorded", "call_id": call_id}

    # =========================================================================
    # Other Vapi Lifecycle Events (e.g. 'status-update', 'speech-update')
    # =========================================================================
    return {"status": "ignored", "event_type": message_type}
