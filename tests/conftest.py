"""Pytest configuration ensuring complete isolation from cloud services and .env credentials."""
import os
import dotenv
import pytest

# 1. Blank all cloud credentials in environment BEFORE any src module is imported.
CLOUD_ENV_VARS = [
    "DATABASE_URL", "BRAIN_DATABASE_URL",
    "QDRANT_URL", "BRAIN_QDRANT_URL",
    "QDRANT_API_KEY", "BRAIN_QDRANT_API_KEY",
    "APP_PASSWORD", "BRAIN_APP_PASSWORD",
    "AUTH_SECRET_KEY", "BRAIN_AUTH_SECRET_KEY",
    "GROQ_API_KEY", "BRAIN_GROQ_API_KEY",
]
for var in CLOUD_ENV_VARS:
    os.environ[var] = ""

# 2. Neutralize dotenv.load_dotenv so importing src.config does not re-read .env credentials into os.environ
dotenv.load_dotenv = lambda *args, **kwargs: False

# 3. Import settings and ensure cloud attributes are cleanly unset (None)
from src.config import settings

settings.DATABASE_URL = None
settings.QDRANT_URL = None
settings.QDRANT_API_KEY = None
settings.APP_PASSWORD = None
settings.AUTH_SECRET_KEY = None
settings.GROQ_API_KEY = None


def pytest_sessionstart(session):
    """Hard guard: abort pytest session immediately if cloud credentials leak into settings."""
    if settings.DATABASE_URL or settings.QDRANT_URL or settings.QDRANT_API_KEY:
        pytest.exit(
            "ABORT: Test isolation breached! Live cloud credentials detected in test settings: "
            f"DATABASE_URL={bool(settings.DATABASE_URL)}, QDRANT_URL={bool(settings.QDRANT_URL)}",
            returncode=1,
        )


@pytest.fixture(autouse=True)
def ensure_isolated_settings_per_test():
    """Ensure per-test setting isolation remains intact across all tests."""
    yield
    # Reset in case a test mutated settings without monkeypatch
    if settings.DATABASE_URL or settings.QDRANT_URL:
        settings.DATABASE_URL = None
        settings.QDRANT_URL = None
        settings.QDRANT_API_KEY = None
