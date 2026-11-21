"""
Speech Normalization Utilities.

Cleans noisy transcriptions from Speech-to-Text (STT) engines into standardized E.164 formats.
"""

import re
from typing import Optional


def extract_digits(text: str) -> str:
    """Extracts only numeric digit characters (0-9) from any input string."""
    if not text:
        return ""
    # Strip all non-digit characters (spaces, dashes, parentheses)
    return re.sub(r"\D", "", str(text))


def normalize_phone_number(raw_phone: str, default_country_code: str = "+91") -> Optional[str]:
    """
    Normalizes spoken phone numbers into strict E.164 international format.
    Handles Indian mobile numbers, trunk zeros, and spaced digits.
    """
    if not raw_phone:
        return None
        
    cleaned_input = str(raw_phone).strip()
    digits = extract_digits(cleaned_input)
    
    # 10-digit Indian mobile number
    if len(digits) == 10:
        return f"{default_country_code}{digits}"
        
    # 11 digits starting with trunk prefix '0' (e.g. 09876543210)
    if len(digits) == 11 and digits.startswith("0"):
        return f"{default_country_code}{digits[1:]}"
        
    # Spoken country code without plus sign (e.g. 919876543210)
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}"
        
    # Standard international format with leading '+'
    if cleaned_input.startswith("+") and 10 <= len(digits) <= 15:
        return f"+{digits}"
        
    # 11-digit US format (e.g. 15551234567)
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
        
    # Invalid length rejected to trigger reprompt
    return None


def normalize_pin(raw_pin: str) -> Optional[str]:
    """
    Normalizes spoken 6-digit PIN.
    Removes acoustic spacing from STT (e.g., '1 2 3 4 5 6' -> '123456').
    """
    if not raw_pin:
        return None
        
    digits = extract_digits(raw_pin)
    # Strict validation: Only exactly 6 digits are allowed
    if len(digits) == 6:
        return digits
        
    return None
