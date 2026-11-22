"""
Application Configuration Module.

Uses Pydantic Settings to load, validate, and manage environment variables.
Follows the 12-Factor App methodology: all config is stored in the environment.
"""

from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Settings schema.
    
    Pydantic automatically reads matching environment variables from .env or OS.
    If a required field without a default is missing, startup fails immediately.
    """
    
    # --- Server Settings ---
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    ENVIRONMENT: str = "development"
    
    # --- Vapi Security ---
    # Shared secret header token. If empty, token check is bypassed in local dev.
    VAPI_SECRET_TOKEN: Optional[str] = None
    
    # --- Integration #1: Airtable (Customer & Claims) ---
    AIRTABLE_API_KEY: Optional[str] = None
    AIRTABLE_BASE_ID: Optional[str] = None
    AIRTABLE_TABLE_NAME: str = "Claims"
    AIRTABLE_LOGS_TABLE_NAME: str = "CallLogs"
    
    # --- Integration #2: Google Sheets (Post-Call Logs) ---
    GOOGLE_SERVICE_ACCOUNT_JSON_PATH: Optional[str] = "credentials/google_service_account.json"
    GOOGLE_SHEET_NAME: str = "Observe_Insurance_Call_Logs"
    GOOGLE_SHEET_TAB_NAME: str = "CallLogs"
    
    # --- Security & Lockout Settings ---
    MAX_AUTH_ATTEMPTS: int = 3

    # --- Demo / Testing Controls ---
    # When True, falls back to data/seed_data.json if Airtable credentials are not set
    ENABLE_DEMO_FALLBACK: bool = True
    
    # --- Pydantic Settings Configuration ---
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore unexpected environment variables safely
    )


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached instance of the Settings object.
    
    Using @lru_cache ensures the .env file is parsed only once at startup,
    rather than on every incoming API request, avoiding disk I/O latency.
    """
    return Settings()
