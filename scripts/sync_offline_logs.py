"""
Offline Call Logs Sync Utility.

Reads offline interaction records from data/call_logs_local.csv
and idempotently uploads any missing rows to Google Sheets.
Functions as a dead-letter queue (DLQ) reconciliation worker.

Usage:
    python scripts/sync_offline_logs.py
"""

import csv
import os
import sys

# Add project root to sys.path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import get_settings
import gspread


def sync_offline_logs():
    settings = get_settings()
    cred_path = settings.GOOGLE_SERVICE_ACCOUNT_JSON_PATH
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "call_logs_local.csv")

    # 1. Check if local CSV log file exists
    if not os.path.exists(csv_path):
        print(f"\n[INFO] No local CSV log file found at: {csv_path}")
        print("There are no offline records pending synchronization.\n")
        return

    # 2. Check Google Service Account credentials
    if not cred_path or not os.path.exists(cred_path):
        print("\n[ERROR] Google Service Account JSON not found.")
        print(f"Expected at: {cred_path}")
        print("Cannot sync to Google Sheets without valid credentials.\n")
        return

    print(f"\nConnecting to Google Sheet [{settings.GOOGLE_SHEET_NAME}]...")
    try:
        gc = gspread.service_account(filename=cred_path)
        spreadsheet = gc.open(settings.GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(settings.GOOGLE_SHEET_TAB_NAME)
    except Exception as e:
        print(f"[ERROR] Could not connect to Google Sheets: {str(e)}\n")
        return

    # 3. Read existing Call IDs from Google Sheet (Column A) for idempotency
    try:
        existing_remote_call_ids = set(worksheet.col_values(1))
    except Exception as e:
        print(f"[ERROR] Failed to fetch remote Call IDs: {str(e)}\n")
        return

    # 4. Read rows from local CSV and push missing rows
    synced_count = 0
    skipped_count = 0

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)  # Skip CSV header

        for row in reader:
            if not row:
                continue
                
            call_id = row[0].strip()

            # Skip if row is already present in Google Sheets
            if call_id in existing_remote_call_ids:
                skipped_count += 1
                continue

            # Append missing row to Google Sheets
            try:
                worksheet.append_row(row)
                existing_remote_call_ids.add(call_id)
                synced_count += 1
                print(f" [SYNCED] Call ID: {call_id} -> {row[2]} ({row[4]})")
            except Exception as e:
                print(f" [FAILED] Could not sync Call ID {call_id}: {str(e)}")

    print("\n--- Synchronization Summary ---")
    print(f" Newly Synced:      {synced_count} records")
    print(f" Already in Sheets: {skipped_count} records")
    print("--------------------------------\n")


if __name__ == "__main__":
    sync_offline_logs()
