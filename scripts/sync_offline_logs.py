"""
Offline Call Logs Sync & DLQ Reconciliation Utility.

Reads offline interaction records from data/call_logs_local.csv
and idempotently reconciles any unsynced rows to Airtable CallLogs
(and Google Sheets, if service account credentials are provided).
Functions as an enterprise Dead-Letter Queue (DLQ) reconciliation worker.

Usage:
    python scripts/sync_offline_logs.py
"""

import csv
import os
import sys

# Add project root to sys.path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import get_settings
from pyairtable import Api


def sync_offline_logs():
    settings = get_settings()
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "call_logs_local.csv")

    # 1. Check if local CSV log file exists
    if not os.path.exists(csv_path):
        print(f"\n[INFO] No local CSV log file found at: {csv_path}")
        print("There are no offline records pending synchronization.\n")
        return

    # 2. Reconcile with Airtable CallLogs (Primary Integration #2)
    if settings.AIRTABLE_API_KEY and settings.AIRTABLE_BASE_ID:
        print(f"\n[Airtable DLQ] Connecting to Base [{settings.AIRTABLE_BASE_ID}]...")
        try:
            api = Api(settings.AIRTABLE_API_KEY)
            table = api.base(settings.AIRTABLE_BASE_ID).table(settings.AIRTABLE_LOGS_TABLE_NAME)
            existing_records = table.all(fields=["CallId"])
            existing_airtable_ids = {
                r.get("fields", {}).get("CallId")
                for r in existing_records
                if r.get("fields", {}).get("CallId")
            }
            print(f"[Airtable DLQ] Found {len(existing_airtable_ids)} existing remote call records.")

            airtable_synced = 0
            airtable_skipped = 0

            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)

                for row in reader:
                    if not row:
                        continue
                    call_id = row[0].strip()

                    if call_id in existing_airtable_ids:
                        airtable_skipped += 1
                        continue

                    # Parse PhoneLast4
                    raw_phone_last4 = row[3].strip() if len(row) > 3 else None
                    phone_last4 = int(raw_phone_last4) if (raw_phone_last4 and raw_phone_last4.isdigit()) else None

                    fields = {
                        "CallId": call_id,
                        "Timestamp": row[1] if len(row) > 1 else "",
                        "CallerName": row[2] if len(row) > 2 else "Unverified Caller",
                        "PhoneLast4": phone_last4,
                        "AuthOutcome": row[4] if len(row) > 4 else "not_started",
                        "ClaimStatus": row[5] if len(row) > 5 else "N/A",
                        "Escalated": row[6] if len(row) > 6 else "NO",
                        "Emergency": row[7] if len(row) > 7 else "NO",
                        "CallbackRequested": row[8] if len(row) > 8 else "NO",
                        "CallbackPhone": row[9] if len(row) > 9 else "N/A",
                        "Sentiment": row[10] if len(row) > 10 else "Neutral",
                        "Summary": row[11] if len(row) > 11 else "",
                        "EndedReason": row[12] if len(row) > 12 else "unknown"
                    }
                    try:
                        table.create(fields)
                        existing_airtable_ids.add(call_id)
                        airtable_synced += 1
                        print(f" [Airtable SYNCED] Call ID: {call_id} -> {fields['CallerName']} ({fields['AuthOutcome']})")
                    except Exception as e:
                        print(f" [Airtable FAILED] Call ID {call_id}: {e}")

            print(f"[Airtable DLQ] Synced: {airtable_synced} | Already Present: {airtable_skipped}")

        except Exception as e:
            print(f"[Airtable DLQ ERROR] Connection failed: {e}")

    # 3. Optional: Reconcile with Google Sheets if credentials exist
    cred_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON_PATH
    if cred_path and os.path.exists(cred_path):
        print(f"\n[Google Sheets] Connecting to Sheet [{settings.GOOGLE_SHEET_NAME}]...")
        try:
            import gspread
            gc = gspread.service_account(filename=cred_path)
            spreadsheet = gc.open(settings.GOOGLE_SHEET_NAME)
            worksheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_TAB_NAME)
            existing_remote_call_ids = set(worksheet.col_values(1))

            sheets_synced = 0
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if not row or row[0].strip() in existing_remote_call_ids:
                        continue
                    worksheet.append_row(row)
                    existing_remote_call_ids.add(row[0].strip())
                    sheets_synced += 1
            print(f"[Google Sheets] Synced: {sheets_synced} records.")
        except Exception as e:
            print(f"[Google Sheets] Skipped or failed: {e}")

    print("\n[SUCCESS] Dead-Letter Queue reconciliation complete.\n")


if __name__ == "__main__":
    sync_offline_logs()
