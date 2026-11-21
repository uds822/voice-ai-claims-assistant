"""
CLI Helper to generate salted PBKDF2 PIN hashes.

Usage:
    python scripts/hash_pin.py 123456
"""

import sys
import os

# Add parent directory to path so we can import from app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.security import hash_pin, verify_pin


def main():
    if len(sys.argv) < 2:
        pin = input("Enter a 6-digit PIN to hash: ").strip()
    else:
        pin = sys.argv[1].strip()

    if len(pin) != 6 or not pin.isdigit():
        print("Error: PIN must be exactly 6 numeric digits.")
        sys.exit(1)

    hashed = hash_pin(pin)
    print(f"\nPlain PIN:   {pin}")
    print(f"Hashed PIN:  {hashed}")
    
    # Verify to ensure test passes
    is_valid = verify_pin(pin, hashed)
    print(f"Self-check verification: {'SUCCESS' if is_valid else 'FAILED'}\n")


if __name__ == "__main__":
    main()
