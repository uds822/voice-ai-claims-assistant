"""
Integration #2: Google Sheets Call Logger Service.

Appends structured interaction records to Google Sheets at the end of every call.
Guarantees idempotency using call_id as a deduplication key across retries and restarts.
"""

import csv
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Optional, Set
import gspread
from app.config import get_settings
from app.models.claims_models import PostCallRecord

logger = logging.getLogger("observe.sheets")


class GoogleSheetsService:
    def __init__(self):
        self.settings = get_settings()
        self._worksheet = None
        # Thread lock to safely handle simultaneous duplicate webhook deliveries
        self._lock = threading.Lock()
        # In-memory deduplication set
        self._logged_call_ids: Set[str] = set()
        self._init_client()
        self._preload_local_csv_call_ids()

    def _init_client(self):
        """Authenticates with Google Sheets API via service account JSON."""
        cred_path = self.settings.GOOGLE_SERVICE_ACCOUNT_JSON_PATH
        if cred_path and os.path.exists(cred_path):
            try:
                gc = gspread.service_account(filename=cred_path)
                spreadsheet = gc.open(self.settings.GOOGLE_SHEET_NAME)
                self._worksheet = spreadsheet.worksheet(self.settings.GOOGLE_SHEET_TAB_NAME)
            except Exception as e:
                logger.warning(f"Google Sheets unavailable ({str(e)}). Using local CSV fallback.")
                self._worksheet = None
        else:
            self._worksheet = None

    def _preload_local_csv_call_ids(self):
        """Preloads previously logged call IDs from local CSV to guarantee idempotency across restarts."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "call_logs_local.csv"
        )
        if os.path.exists(csv_path):
            try:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    next(reader, None)  # Skip header
                    for row in reader:
                        if row and row[0]:
                            self._logged_call_ids.add(row[0].strip())
            except Exception as e:
                logger.warning(f"Could not preload local CSV call IDs: {str(e)}")

    def log_call(self, record: PostCallRecord) -> bool:
        """Appends a post-call interaction record, strictly skipping duplicates."""
        if not record or not record.call_id:
            logger.error("Cannot log post-call record: missing call_id.")
            return False

        # Lock ensures atomic duplicate check and write across concurrent webhook threads
        with self._lock:
            # 1. In-memory idempotency check (fast path)
            if record.call_id in self._logged_call_ids:
                logger.info(f"Duplicate post-call event for call_id [{record.call_id}] safely ignored.")
                return True

            row_data = [
                record.call_id,
                record.timestamp_utc or datetime.now(timezone.utc).isoformat(),
                record.caller_name,
                record.phone_last_four,
                record.auth_outcome,
                record.claim_status_read,
                "YES" if record.escalated else "NO",
                "YES" if record.emergency else "NO",
                "YES" if record.callback_requested else "NO",
                record.callback_phone or "N/A",
                record.sentiment,
                record.call_summary,
                record.ended_reason
            ]

            # 2. Live Google Sheets write
            if self._worksheet is not None:
                try:
                    # Persistent duplicate check across restarts by scanning Column A (Call ID)
                    existing_call_ids = self._worksheet.col_values(1)
                    if record.call_id in existing_call_ids:
                        logger.info(f"Call ID [{record.call_id}] already exists in Google Sheet. Skipping.")
                        self._logged_call_ids.add(record.call_id)
                        return True

                    self._worksheet.append_row(row_data)
                    self._logged_call_ids.add(record.call_id)
                    logger.info(f"Successfully logged call {record.call_id} to Google Sheets.")
                    return True
                except Exception as e:
                    logger.error(f"Google Sheets append failed: {str(e)}. Falling back to local CSV.")

            # 3. Local CSV Fallback: Never lose interaction data if Google API is unreachable
            return self._log_to_local_csv(record.call_id, row_data)

    def _log_to_local_csv(self, call_id: str, row_data: list) -> bool:
        """Saves interaction audit row to local CSV file with idempotency guard."""
        csv_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "data", "call_logs_local.csv"
        )
        file_exists = os.path.exists(csv_path)

        try:
            # Check existing call_ids in file to prevent duplicate rows across restarts
            if file_exists:
                with open(csv_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0] == call_id:
                            logger.info(f"Call ID [{call_id}] already exists in local CSV. Skipping.")
                            self._logged_call_ids.add(call_id)
                            return True

            with open(csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow([
                        "Call ID", "Timestamp (UTC)", "Caller Name", "Phone (Last 4)",
                        "Auth Outcome", "Claim Status", "Escalated", "Emergency",
                        "Callback Requested", "Callback Phone", "Sentiment", "Summary", "Ended Reason"
                    ])
                writer.writerow(row_data)

            self._logged_call_ids.add(call_id)
            logger.info(f"Saved call {call_id} to local CSV audit log.")
            return True
        except Exception as e:
            logger.error(f"Local CSV write failed: {str(e)}")
            return False


sheets_service = GoogleSheetsService()
