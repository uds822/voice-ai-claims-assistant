"""
Approved FAQ Knowledge Base Service.

Loads corporate FAQ answers from data/faq.json to prevent LLM hallucinations.
"""

import json
import os
from typing import Dict, Optional


class FAQService:
    def __init__(self, faq_file_path: Optional[str] = None):
        if not faq_file_path:
            faq_file_path = os.path.join(
                os.path.dirname(__file__), "..", "..", "data", "faq.json"
            )
        self.faq_file_path = os.path.abspath(faq_file_path)
        self._faq_data: Dict[str, str] = {}
        self._load_faq()

    def _load_faq(self):
        """Loads and caches FAQ JSON data into memory at startup."""
        if os.path.exists(self.faq_file_path):
            with open(self.faq_file_path, "r", encoding="utf-8") as f:
                self._faq_data = json.load(f)
        else:
            self._faq_data = {}

    def get_answer(self, query: str) -> Optional[str]:
        """
        Retrieves approved FAQ answer based on topic or keyword query.
        Returns None if query is unsupported so the agent offers a human.
        """
        if not query:
            return None
            
        normalized = query.lower().strip()

        # Direct dictionary key match
        if normalized in self._faq_data:
            return self._faq_data[normalized]

        # Fuzzy intent mapping for conversational variations
        if any(term in normalized for term in ["hour", "timing", "open", "time"]):
            return self._faq_data.get("office_hours")

        if any(term in normalized for term in ["address", "mail", "post", "location", "office", "send"]):
            return self._faq_data.get("mailing_address")

        if any(term in normalized for term in ["start", "new claim", "file", "submit claim"]):
            return self._faq_data.get("how_to_start_a_claim")

        if any(term in normalized for term in ["process", "workflow", "how long", "timeline", "steps"]):
            return self._faq_data.get("general_claims_process")

        # Unsupported topic: Return None so agent never hallucinates unverified policies
        return None


# Global singleton instance
faq_service = FAQService()
