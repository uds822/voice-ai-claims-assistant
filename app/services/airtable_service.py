"""
Integration #1: Airtable Claims Service.

Retrieves customer identity and active claim status by phone number.
"""

import json
import logging
import os
from typing import Optional
import requests
from pyairtable import Api
from app.config import get_settings
from app.models.claims_models import CustomerRecord, ClaimRecord, CustomerClaimData, PostCallRecord
from app.utils.normalizers import normalize_phone_number
from app.utils.security import mask_phone_number, hash_pin

logger = logging.getLogger("observe.airtable")


class AirtableService:
    def __init__(self):
        self.settings = get_settings()
        self._table = None
        self._logs_table = None
        self._cache = {}

        # 0. Pre-load local seed data into RAM cache so lookups are 0.001s (Instant voice response)
        self._warm_cache()

        # Only initialize Airtable client if API keys are provided in environment
        if self.settings.AIRTABLE_API_KEY and self.settings.AIRTABLE_BASE_ID:
            try:
                # 3s connect / 5s read timeout: fail fast on slow networks during voice calls
                api = Api(self.settings.AIRTABLE_API_KEY, timeout=(3.0, 5.0))
                self._table = api.table(
                    self.settings.AIRTABLE_BASE_ID,
                    self.settings.AIRTABLE_TABLE_NAME
                )
                self._logs_table = api.table(
                    self.settings.AIRTABLE_BASE_ID,
                    self.settings.AIRTABLE_LOGS_TABLE_NAME
                )
            except Exception as e:
                logger.error("Failed to initialize Airtable client. Check API credentials.")
                self._table = None
                self._logs_table = None

    def _warm_cache(self):
        """Pre-populates in-memory cache with demo seed records for instant <5ms lookups."""
        seed_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "seed_data.json"
        )
        if not os.path.exists(seed_path):
            return
        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                raw_phone = item.get("Phone", "")
                norm = normalize_phone_number(raw_phone)
                if norm:
                    res = self._lookup_from_local_seed(norm)
                    if res:
                        self._cache[norm] = res
            logger.info(f"Pre-warmed claims cache with {len(self._cache)} records.")
        except Exception as e:
            logger.warning(f"Failed to pre-warm cache: {e}")

    def get_customer_and_claim_by_phone(self, phone: str) -> Optional[CustomerClaimData]:
        """Looks up customer by phone and returns their account and claim details."""
        normalized_phone = normalize_phone_number(phone)
        if not normalized_phone:
            # Mask input in logs to protect potential PII
            logger.warning(f"Invalid phone number rejected before DB query: {mask_phone_number(phone)}")
            return None

        masked_phone = mask_phone_number(normalized_phone)

        # 0. Check in-memory cache for ultra-low latency voice response (< 1ms)
        if normalized_phone in self._cache:
            logger.info(f"Cache hit for customer: {masked_phone} (0ms latency)")
            return self._cache[normalized_phone]

        # 1. Query live Airtable base if credentials are configured
        if self._table is not None:
            try:
                digits_only = normalized_phone.lstrip("+")
                formula = f"OR({{Phone}} = '{normalized_phone}', {{Phone}} = '{digits_only}', {{Phone}} = {digits_only})"
                # max_records=1 prevents Airtable from paginating the entire table, cutting network latency
                records = self._table.all(formula=formula, max_records=1)
                
                # Missing customer record: cleanly return None
                if not records:
                    logger.info(f"Customer record not found for: {masked_phone}")
                    return None
                    
                fields = records[0].get("fields", {})
                if not isinstance(fields, dict):
                    logger.error(f"Malformed response fields received for: {masked_phone}")
                    return None

                pin_hash = str(fields.get("PinHash", "")).strip()
                # Security: Reject customer record if PIN hash is completely missing
                if not pin_hash:
                    logger.warning(f"Customer found but lacks security PIN hash: {masked_phone}")
                    return None

                raw_phone = str(fields.get("Phone", normalized_phone))
                stored_phone = normalize_phone_number(raw_phone) or normalized_phone

                customer = CustomerRecord(
                    phone=stored_phone,
                    caller_name=str(fields.get("CallerName", "Valued Customer")),
                    pin_hash=pin_hash,
                    claim_id=str(fields.get("ClaimId")) if fields.get("ClaimId") else None
                )
                
                claim = None
                claim_id = fields.get("ClaimId")
                if claim_id:
                    claim = ClaimRecord(
                        claim_id=str(claim_id),
                        status=str(fields.get("Status", "Under Review")),
                        # Airtable REST API omits unchecked checkboxes; default to False
                        documents_required=bool(fields.get("DocumentsRequired", False)),
                        document_instructions=str(fields.get("DocumentInstructions", "")),
                        last_updated=str(fields.get("LastUpdated", ""))
                    )
                    
                result = CustomerClaimData(customer=customer, claim=claim)
                self._cache[normalized_phone] = result
                return result
                
            except (TimeoutError, requests.exceptions.Timeout):
                logger.error(f"Airtable API request timed out for {masked_phone}")
                if self.settings.ENABLE_DEMO_FALLBACK:
                    logger.warning("Falling back to local seed data due to Airtable timeout.")
                    return self._lookup_from_local_seed(normalized_phone)
                raise RuntimeError("Claims database request timed out. Please try again.")
            except Exception as e:
                # Never expose API tokens or raw exception dumps to caller
                logger.error(f"Airtable API error occurred while querying {masked_phone}: {type(e).__name__}")
                if self.settings.ENABLE_DEMO_FALLBACK:
                    logger.warning("Falling back to local seed data due to Airtable error.")
                    return self._lookup_from_local_seed(normalized_phone)
                raise RuntimeError("External claims database temporarily unavailable.")

        # 2. Local seed fallback: Allowed only when ENABLE_DEMO_FALLBACK is True
        if self.settings.ENABLE_DEMO_FALLBACK:
            return self._lookup_from_local_seed(normalized_phone)
        else:
            logger.error("Airtable not configured and demo fallback is disabled.")
            raise RuntimeError("Claims database service is not configured.")

    def _lookup_from_local_seed(self, normalized_phone: str) -> Optional[CustomerClaimData]:
        """Fallback reader for local offline demo using data/seed_data.json."""
        seed_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "seed_data.json"
        )
        if not os.path.exists(seed_path):
            return None

        try:
            with open(seed_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            logger.error("Failed to read local seed data file.")
            return None

        for item in data:
            if item.get("Phone") == normalized_phone:
                raw_pin = item.get("Pin")
                pin_hash = item.get("PinHash")
                
                # Derive PBKDF2 hash from raw PIN if not pre-hashed
                if not pin_hash and raw_pin:
                    try:
                        pin_hash = hash_pin(str(raw_pin))
                    except ValueError:
                        pin_hash = None

                # Security: Reject records that lack any valid PIN
                if not pin_hash:
                    logger.warning(f"Seed record rejected due to missing or invalid PIN: {mask_phone_number(normalized_phone)}")
                    return None
                
                customer = CustomerRecord(
                    phone=item["Phone"],
                    caller_name=item.get("CallerName", "Valued Customer"),
                    pin_hash=pin_hash,
                    claim_id=item.get("ClaimId")
                )
                
                claim = None
                if item.get("ClaimId"):
                    claim = ClaimRecord(
                        claim_id=str(item["ClaimId"]),
                        status=item.get("Status", "Under Review"),
                        documents_required=bool(item.get("DocumentsRequired", False)),
                        document_instructions=item.get("DocumentInstructions", ""),
                        last_updated=item.get("LastUpdated", "")
                    )
                    
                return CustomerClaimData(customer=customer, claim=claim)

        return None

    def log_call(self, record: PostCallRecord) -> bool:
        """Integration #2: Appends a post-call interaction record to Airtable CallLogs table."""
        if not self._logs_table or not record or not record.call_id:
            return False
        try:
            fields = {
                "CallId": str(record.call_id),
                "Timestamp": record.timestamp_utc or "",
                "CallerName": str(record.caller_name or "Unverified Caller"),
                "PhoneLast4": str(record.phone_last_four or "N/A"),
                "AuthOutcome": str(record.auth_outcome or "not_started"),
                "ClaimStatus": str(record.claim_status_read or "N/A"),
                "Escalated": "YES" if record.escalated else "NO",
                "Emergency": "YES" if record.emergency else "NO",
                "CallbackRequested": "YES" if record.callback_requested else "NO",
                "CallbackPhone": str(record.callback_phone or "N/A"),
                "Sentiment": str(record.sentiment or "Neutral"),
                "Summary": str(record.call_summary or ""),
                "EndedReason": str(record.ended_reason or "unknown")
            }
            self._logs_table.create(fields)
            logger.info(f"[{record.call_id}] Successfully recorded post-call log in Airtable CallLogs table.")
            return True
        except Exception as e:
            logger.warning(f"[{record.call_id}] Could not write call log to Airtable: {e}")
            return False


airtable_service = AirtableService()
