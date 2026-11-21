"""
Vapi Webhook & Tool Calling Contracts.

Defines schemas for incoming Vapi webhooks (tool-calls and end-of-call-report)
and the exact response format Vapi expects back.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ==========================================
# 1. Incoming Tool Call Schemas (from Vapi)
# ==========================================

class VapiFunctionCall(BaseModel):
    """The specific function the LLM decided to invoke."""
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)


class VapiToolCallItem(BaseModel):
    """A single tool call item in Vapi's request."""
    id: str
    type: str = "function"
    function: VapiFunctionCall


class VapiCallObject(BaseModel):
    """Metadata about the ongoing phone/web call."""
    id: str
    status: Optional[str] = None
    startedAt: Optional[str] = None
    endedAt: Optional[str] = None


class VapiAnalysis(BaseModel):
    """Automated post-call analysis provided by Vapi (optional)."""
    summary: Optional[str] = None
    sentiment: Optional[str] = None
    successEvaluation: Optional[str] = None


class VapiMessagePayload(BaseModel):
    """
    The inner 'message' object sent in Vapi webhooks.
    Can be a 'tool-calls' event or an 'end-of-call-report' event.
    """
    type: str                                    # e.g. "tool-calls" or "end-of-call-report"
    call: Optional[VapiCallObject] = None
    toolCalls: Optional[List[VapiToolCallItem]] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    analysis: Optional[VapiAnalysis] = None
    endedReason: Optional[str] = None


class VapiWebhookRequest(BaseModel):
    """Top-level webhook envelope sent by Vapi."""
    message: VapiMessagePayload


# ==========================================
# 2. Outgoing Tool Response Schema (to Vapi)
# ==========================================

class VapiToolResultItem(BaseModel):
    """Result for an individual tool execution."""
    toolCallId: str
    result: str                                  # Flat string response spoken or consumed by LLM


class VapiToolResponse(BaseModel):
    """
    The standard response format Vapi expects for tool-calls.
    Vapi matches each result back to the corresponding toolCallId.
    """
    results: List[VapiToolResultItem]
