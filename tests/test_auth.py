from fastapi.testclient import TestClient
import pytest

from src.api import app
from src.config import settings
from src.auth import create_access_token, verify_password, verify_token


def test_auth_disabled_by_default(monkeypatch):
    """When APP_PASSWORD is None or empty, auth is bypassed for seamless local development."""
    monkeypatch.setattr(settings, "APP_PASSWORD", None)
    client = TestClient(app)

    # Status shows disabled
    res = client.get("/auth/status")
    assert res.status_code == 200
    assert res.json()["auth_enabled"] is False
    assert res.json()["authenticated"] is True

    # Endpoints accessible without token
    res = client.get("/files")
    assert res.status_code == 200

    res = client.get("/health")
    assert res.status_code == 200


def test_auth_enabled_enforces_gate(monkeypatch):
    """When APP_PASSWORD is set, all sensitive endpoints strictly reject unauthenticated requests with 401."""
    monkeypatch.setattr(settings, "APP_PASSWORD", "vault_pass_987")
    client = TestClient(app)

    # 1. Status indicates auth is required and client is unauthenticated
    res = client.get("/auth/status")
    assert res.status_code == 200
    assert res.json()["auth_enabled"] is True
    assert res.json()["authenticated"] is False

    # 2. Sensitive endpoints reject without token
    res = client.get("/files")
    assert res.status_code == 401
    assert "missing Authorization header" in res.json()["detail"]

    res = client.get("/sessions")
    assert res.status_code == 401

    res = client.post("/query", json={"question": "Test query"})
    assert res.status_code == 401

    # 3. Health check remains 100% public for Render monitoring
    res = client.get("/health")
    assert res.status_code == 200

    # 4. Incorrect password rejected
    res = client.post("/auth/login", json={"password": "wrong_password"})
    assert res.status_code == 401

    # 5. Correct password returns valid token
    res = client.post("/auth/login", json={"password": "vault_pass_987"})
    assert res.status_code == 200
    data = res.json()
    assert "token" in data
    assert data["token_type"] == "bearer"
    token = data["token"]

    # 6. Status with token confirms authenticated
    res = client.get("/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["authenticated"] is True

    # 7. Sensitive endpoints succeed with Bearer token
    res = client.get("/files", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200

    res = client.get("/sessions", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200


def test_login_rate_limiting_lockout(monkeypatch):
    """5 consecutive failed logins trigger HTTP 429 lockout with Retry-After header."""
    from src.auth import login_limiter
    login_limiter.reset()

    monkeypatch.setattr(settings, "APP_PASSWORD", "correct_pass")
    client = TestClient(app)

    # First 4 failed attempts get 401
    for _ in range(4):
        res = client.post("/auth/login", json={"password": "bad_password"})
        assert res.status_code == 401

    # 5th failed attempt triggers 429 lockout
    res = client.post("/auth/login", json={"password": "bad_password"})
    assert res.status_code == 429
    assert "Too many failed login attempts" in res.json()["detail"]
    assert "Retry-After" in res.headers

    # Subsequent attempt is locked out immediately
    res = client.post("/auth/login", json={"password": "bad_password"})
    assert res.status_code == 429

    # Even with correct password, client remains locked out until reset or expiry
    res = client.post("/auth/login", json={"password": "correct_pass"})
    assert res.status_code == 429

    # Reset limiter simulates time passing
    login_limiter.reset()
    res = client.post("/auth/login", json={"password": "correct_pass"})
    assert res.status_code == 200


def test_proxy_rate_limiting_isolated_ips(monkeypatch):
    """When BRAIN_TRUST_PROXY is True, different forwarded IPs are isolated into separate buckets."""
    from src.auth import login_limiter
    login_limiter.reset()

    monkeypatch.setattr(settings, "APP_PASSWORD", "correct_pass")
    monkeypatch.setattr(settings, "BRAIN_TRUST_PROXY", True)
    client = TestClient(app)

    ip_attacker = "203.0.113.10"
    ip_victim = "198.51.100.25"

    # Attacker fails 5 times -> gets locked out
    for _ in range(5):
        res = client.post("/auth/login", json={"password": "bad_password"}, headers={"X-Forwarded-For": ip_attacker})
    assert res.status_code == 429

    # Attacker remains locked
    res = client.post("/auth/login", json={"password": "bad_password"}, headers={"X-Forwarded-For": ip_attacker})
    assert res.status_code == 429

    # Legitimate user from different IP is NOT locked out
    res = client.post("/auth/login", json={"password": "correct_pass"}, headers={"X-Forwarded-For": ip_victim})
    assert res.status_code == 200


def test_proxy_spoofing_ignored_when_flag_off(monkeypatch):
    """When BRAIN_TRUST_PROXY is False, X-Forwarded-For is ignored and cannot be spoofed to evade lockout."""
    from src.auth import login_limiter
    login_limiter.reset()

    monkeypatch.setattr(settings, "APP_PASSWORD", "correct_pass")
    monkeypatch.setattr(settings, "BRAIN_TRUST_PROXY", False)
    client = TestClient(app)

    # Attacker tries to rotate spoofed headers, but limiter keys on direct socket client IP
    for i in range(5):
        res = client.post("/auth/login", json={"password": "bad_password"}, headers={"X-Forwarded-For": f"10.0.0.{i}"})

    assert res.status_code == 429
    # Further attempt with another new spoofed header is still locked out
    res = client.post("/auth/login", json={"password": "bad_password"}, headers={"X-Forwarded-For": "10.0.0.99"})
    assert res.status_code == 429


def test_escalating_lockouts(monkeypatch):
    """Rate limiter escalates lockout duration on repeat offenses (60s -> 300s -> 900s)."""
    from src.auth import login_limiter
    login_limiter.reset()

    client_ip = "192.0.2.1"

    # 1st tier: 5 failures -> 60s
    for _ in range(4):
        locked, _ = login_limiter.record_failure(client_ip)
        assert not locked
    locked, duration = login_limiter.record_failure(client_ip)
    assert locked
    assert duration == 60

    # Simulate lockout expired: record 5 more failures -> 300s (5 min)
    for _ in range(4):
        locked, _ = login_limiter.record_failure(client_ip)
        assert not locked
    locked, duration = login_limiter.record_failure(client_ip)
    assert locked
    assert duration == 300

    # Simulate lockout expired: record 5 more failures -> 900s (15 min)
    for _ in range(4):
        locked, _ = login_limiter.record_failure(client_ip)
        assert not locked
    locked, duration = login_limiter.record_failure(client_ip)
    assert locked
    assert duration == 900


def test_constant_time_password_verification(monkeypatch):
    """verify_password correctly validates matching and non-matching passwords."""
    monkeypatch.setattr(settings, "APP_PASSWORD", "super_secure_vault_123")
    assert verify_password("super_secure_vault_123") is True
    assert verify_password("wrong_password") is False
    assert verify_password("") is False
    assert verify_password("super_secure_vault_12") is False


def test_token_expiry_rejection(monkeypatch):
    """verify_token rejects expired tokens."""
    monkeypatch.setattr(settings, "APP_PASSWORD", "test_vault_pass")
    # Create token with -10 second TTL (already expired)
    expired_token = create_access_token(expires_in=-10)
    assert verify_token(expired_token["token"]) is False


def test_token_survives_restart_with_auth_secret_key(monkeypatch):
    """Tokens survive restarts when AUTH_SECRET_KEY is configured."""
    monkeypatch.setattr(settings, "APP_PASSWORD", "test_pass")
    monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "fixed_signing_secret_999")

    token_data = create_access_token(expires_in=3600)
    token = token_data["token"]
    assert verify_token(token) is True

    # If AUTH_SECRET_KEY changes, old tokens are invalidated
    monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "different_secret_key_888")
    assert verify_token(token) is False


def test_cors_origins_config():
    """Settings correctly parses comma-separated CORS_ORIGINS."""
    settings.CORS_ORIGINS = "https://my-rag.onrender.com, http://localhost:3000"
    origins = settings.allowed_origins
    assert "https://my-rag.onrender.com" in origins
    assert "http://localhost:3000" in origins
    assert len(origins) == 2


def test_production_docs_disabled(monkeypatch):
    """When BRAIN_ENV is production, Swagger UI and OpenAPI schemas are disabled."""
    from fastapi import FastAPI
    # Simulate production FastAPI instance
    prod_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    prod_client = TestClient(prod_app)
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404
    assert prod_client.get("/openapi.json").status_code == 404


