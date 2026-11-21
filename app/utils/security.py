"""
Security & PII Sanitization Utilities.

Implements PBKDF2 salted PIN hashing, constant-time verification,
and phone number masking for privacy and compliance.
"""

import hashlib
import hmac
import secrets
from typing import Optional
from app.utils.normalizers import extract_digits


PBKDF2_ALGORITHM = "sha256"
# 100k iterations: ~15ms check on server, but stops offline GPU rainbow table attacks
PBKDF2_ITERATIONS = 100_000
SALT_BYTES = 16


def hash_pin(pin: str, salt: Optional[str] = None, iterations: int = PBKDF2_ITERATIONS) -> str:
    """Hashes a 6-digit PIN using PBKDF2-HMAC-SHA256 with a unique cryptographic salt."""
    clean_pin = extract_digits(pin)
    # Strictly enforce exactly 6 numeric digits before hashing
    if len(clean_pin) != 6:
        raise ValueError("PIN must be exactly 6 numeric digits.")
        
    # Use cryptographically secure random salt to ensure identical PINs produce different hashes
    if not salt:
        salt = secrets.token_hex(SALT_BYTES)
        
    derived_key = hashlib.pbkdf2_hmac(
        hash_name=PBKDF2_ALGORITHM,
        password=clean_pin.encode("utf-8"),
        salt=salt.encode("utf-8"),
        iterations=iterations
    )
    
    # Store algorithm, iterations, salt, and hash together for self-contained verification
    return f"pbkdf2_{PBKDF2_ALGORITHM}${iterations}${salt}${derived_key.hex()}"


def verify_pin(plain_pin: str, stored_hash: str) -> bool:
    """Verifies a plain-text PIN against stored PBKDF2 hash using constant-time comparison."""
    if not plain_pin or not stored_hash:
        return False
        
    clean_pin = extract_digits(plain_pin)
    # Strictly reject any candidate PIN that is not exactly 6 numeric digits
    if len(clean_pin) != 6:
        return False
        
    try:
        parts = stored_hash.split("$")
        if len(parts) != 4 or parts[0] != "pbkdf2_sha256":
            return False
            
        iterations = int(parts[1])
        salt = parts[2]
        expected_hash_hex = parts[3]
        
        # Re-derive key using identical parameters stored in the hash
        computed_key = hashlib.pbkdf2_hmac(
            hash_name=PBKDF2_ALGORITHM,
            password=clean_pin.encode("utf-8"),
            salt=salt.encode("utf-8"),
            iterations=iterations
        )
        
        # hmac.compare_digest avoids early-exit timing leaks
        return hmac.compare_digest(computed_key.hex(), expected_hash_hex)
        
    except Exception:
        # Fail safe: Any parsing or formatting error results in authentication rejection
        return False


def mask_phone_number(phone: Optional[str]) -> str:
    """Masks phone number for safe logging without exposing PII."""
    if not phone:
        return "N/A"
        
    digits = extract_digits(phone)
    if len(digits) >= 10:
        last_three = digits[-3:]
        # Circle code (first 2 digits) + masked center + last 3 digits
        first_two = digits[-10:-8]
        if phone.startswith("+91") or digits.startswith("91"):
            return f"+91 {first_two}*** **{last_three}"
        elif phone.startswith("+1") or (len(digits) == 11 and digits.startswith("1")):
            return f"+1 ***-***-{digits[-4:]}"
        return f"{first_two}*** **{last_three}"
        
    elif len(digits) >= 4:
        return f"***{digits[-4:]}"
        
    return "***"


def get_phone_last_four(phone: Optional[str]) -> str:
    """Extracts only the last 4 digits of a phone number for the call log sheet."""
    if not phone:
        return "N/A"
    digits = extract_digits(phone)
    if len(digits) >= 4:
        return digits[-4:]
    return "N/A"
