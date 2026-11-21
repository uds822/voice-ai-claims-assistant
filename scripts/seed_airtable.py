"""
Automated Airtable Seeding Script.

Reads test customer records from data/seed_data.json,
hashes their PINs using PBKDF2, and inserts/updates them into Airtable.
"""

import json
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import get_settings
from app.utils.security import hash_pin, mask_phone_number
from pyairtable import Api


def seed_database():
    settings = get_settings()

    if not settings.AIRTABLE_API_KEY or not settings.AIRTABLE_BASE_ID:
        print("\n[ERROR] AIRTABLE_API_KEY or AIRTABLE_BASE_ID not found in environment or .env file.")
        print("Please add them to your .env file before running this script.")
        print("See .env.example for guidance.\n")
        sys.exit(1)

    seed_file_path = os.path.join(os.path.dirname(__file__), "..", "data", "seed_data.json")
    if not os.path.exists(seed_file_path):
        print(f"[ERROR] Seed data file not found at: {seed_file_path}")
        sys.exit(1)

    with open(seed_file_path, "r", encoding="utf-8") as f:
        customers = json.load(f)

    print(f"\nConnecting to Airtable Base [{settings.AIRTABLE_BASE_ID}]...")
    api = Api(settings.AIRTABLE_API_KEY)
    table = api.table(settings.AIRTABLE_BASE_ID, settings.AIRTABLE_TABLE_NAME)

    print(f"Seeding {len(customers)} customer records with PBKDF2 salted PIN hashes...\n")

    for cust in customers:
        phone = cust["Phone"]
        plain_pin = cust["Pin"]
        hashed_pin = hash_pin(plain_pin)

        fields = {
            "Phone": phone,
            "CallerName": cust["CallerName"],
            "PinHash": hashed_pin,
            "ClaimId": cust["ClaimId"],
            "Status": cust["Status"],
            "DocumentsRequired": cust.get("DocumentsRequired", False),
            "DocumentInstructions": cust.get("DocumentInstructions", ""),
            "LastUpdated": cust.get("LastUpdated", "")
        }

        # Never print full phone number or plain PIN to the console
        masked_phone = mask_phone_number(phone)
        existing_records = table.all(formula=f"{{Phone}} = '{phone}'")
        if existing_records:
            record_id = existing_records[0]["id"]
            table.update(record_id, fields)
            print(f" [UPDATED] {cust['CallerName']} ({masked_phone}) -> PIN: [SECURE_HASHED]")
        else:
            table.create(fields)
            print(f" [CREATED] {cust['CallerName']} ({masked_phone}) -> PIN: [SECURE_HASHED]")

    print("\nAirtable seeding completed successfully!\n")


if __name__ == "__main__":
    seed_database()
