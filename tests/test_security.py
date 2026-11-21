"""
Unit Tests for Speech Normalization and Security Utilities.

Validates phone number cleaning (Indian +91), PIN 6-digit enforcement,
PBKDF2 salted hashing, and PII masking.
"""

import pytest
from app.utils.normalizers import extract_digits, normalize_phone_number, normalize_pin
from app.utils.security import hash_pin, verify_pin, mask_phone_number, get_phone_last_four


def test_normalize_phone_number_indian():
    """Validates Indian phone normalization across spoken STT formats."""
    # 1. Standard 10-digit mobile
    assert normalize_phone_number("9876543210") == "+919876543210"
    
    # 2. Spoken with spaces from Deepgram
    assert normalize_phone_number("9 8 7 6 5 4 3 2 1 0") == "+919876543210"
    
    # 3. Leading trunk zero
    assert normalize_phone_number("09876543210") == "+919876543210"
    
    # 4. Spoken country code without plus sign
    assert normalize_phone_number("919876543210") == "+919876543210"
    
    # 5. Full E.164 with plus
    assert normalize_phone_number("+91 98765 43210") == "+919876543210"
    
    # 6. Invalid numbers rejected
    assert normalize_phone_number("12345") is None
    assert normalize_phone_number("") is None


def test_normalize_pin():
    """Validates 6-digit PIN normalization and whitespace stripping."""
    assert normalize_pin("1 2 3 4 5 6") == "123456"
    assert normalize_pin("12-34-56") == "123456"
    assert normalize_pin("12345") is None      # Too short
    assert normalize_pin("1234567") is None    # Too long
    assert normalize_pin("") is None


def test_pbkdf2_hash_and_verify():
    """Validates PBKDF2 hashing, salt generation, and verification."""
    pin = "123456"
    hashed = hash_pin(pin)
    
    assert hashed.startswith("pbkdf2_sha256$100000$")
    assert verify_pin("123456", hashed) is True
    assert verify_pin("654321", hashed) is False


def test_strict_pin_length_enforcement():
    """Ensures non-6-digit PINs are rejected before cryptographic operations."""
    with pytest.raises(ValueError, match="must be exactly 6 numeric digits"):
        hash_pin("12345")
        
    # Verification of invalid candidate lengths fails immediately
    valid_hash = hash_pin("123456")
    assert verify_pin("12345", valid_hash) is False
    assert verify_pin("1234567", valid_hash) is False


def test_pii_phone_masking():
    """Validates safe masking of customer phone numbers in logs."""
    masked = mask_phone_number("+919876543210")
    assert masked == "+91 98*** **210"
    assert get_phone_last_four("+919876543210") == "3210"
