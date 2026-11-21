"""
Pytest Configuration and Shared Test Fixtures.

Provides a TestClient fixture configured for the FastAPI app.
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    """Provides a fresh FastAPI test client for simulated HTTP webhook requests."""
    return TestClient(app)
