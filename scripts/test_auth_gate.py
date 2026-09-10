#!/usr/bin/env python3
"""Empirical test script for Single-User Authentication Gate.

Validates:
1. Public health check (/health) returns HTTP 200 without token
2. Unauthenticated calls to protected routes (/files, /sessions, /query) return HTTP 401
3. Bad password to /auth/login returns HTTP 401
4. Good password to /auth/login returns Bearer token
5. Authenticated calls with Bearer token return HTTP 200
"""

import argparse
import logging
import os
from pathlib import Path
import sys

import httpx
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_auth_gate")


def test_auth(api_url: str, password: str):
    api_url = api_url.rstrip("/")
    logger.info(f"Testing Authentication Gate at: {api_url}")

    with httpx.Client(timeout=15.0) as client:
        # 1. Public healthcheck
        logger.info("Checking public /health endpoint (should be 200)...")
        r_health = client.get(f"{api_url}/health")
        assert r_health.status_code == 200, f"Expected 200 on /health, got {r_health.status_code}"
        logger.info("✓ /health is public and responding 200 OK")

        # 2. Check /auth/status
        r_status = client.get(f"{api_url}/auth/status")
        assert r_status.status_code == 200, f"Expected 200 on /auth/status, got {r_status.status_code}"
        status_data = r_status.json()
        logger.info(f"✓ /auth/status reports: {status_data}")

        if not status_data.get("auth_enabled"):
            logger.warning("Authentication is not enabled on this instance (APP_PASSWORD not set).")
            return

        # 3. Unauthenticated requests to protected endpoints MUST fail with 401
        for endpoint in ["/files", "/sessions", "/stats"]:
            logger.info(f"Testing unauthenticated GET {endpoint} (should be 401)...")
            r = client.get(f"{api_url}{endpoint}")
            assert r.status_code == 401, f"Expected 401 on {endpoint}, got {r.status_code}: {r.text}"
            logger.info(f"✓ Protected endpoint {endpoint} correctly rejected with 401 Unauthorized")

        # 4. Incorrect password MUST fail with 401
        logger.info("Testing login with incorrect password (should be 401)...")
        r_bad = client.post(f"{api_url}/auth/login", json={"password": "definitely_wrong_password_xyz"})
        assert r_bad.status_code == 401, f"Expected 401 on bad password, got {r_bad.status_code}"
        logger.info("✓ Bad password correctly rejected with 401 Unauthorized")

        # 5. Correct password MUST succeed with 200 and return token
        logger.info("Testing login with correct password...")
        r_login = client.post(f"{api_url}/auth/login", json={"password": password})
        assert r_login.status_code == 200, f"Expected 200 on login, got {r_login.status_code}: {r_login.text}"
        token_data = r_login.json()
        assert "token" in token_data, "Login response missing 'token'"
        token = token_data["token"]
        logger.info("✓ Login succeeded, obtained valid session bearer token")

        # 6. Authenticated requests with Bearer token MUST succeed with 200
        headers = {"Authorization": f"Bearer {token}"}
        for endpoint in ["/files", "/sessions", "/stats"]:
            logger.info(f"Testing authenticated GET {endpoint} with Bearer token...")
            r_auth = client.get(f"{api_url}{endpoint}", headers=headers)
            assert r_auth.status_code == 200, f"Expected 200 on {endpoint} with token, got {r_auth.status_code}: {r_auth.text}"
            logger.info(f"✓ Authenticated request to {endpoint} succeeded with 200 OK")

    print("\n" + "=" * 60)
    print("✓ SINGLE-USER AUTHENTICATION GATE VERIFICATION PASSED!")
    print(f"  Target API: {api_url}")
    print("  401 Rejection & Token Authentication Confirmed")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test authentication gate against running API")
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--password", default=os.getenv("APP_PASSWORD") or os.getenv("BRAIN_APP_PASSWORD"))
    args = parser.parse_args()

    if not args.password:
        print("[ERROR] APP_PASSWORD is required to test auth gate.")
        sys.exit(1)

    test_auth(args.url, args.password)
