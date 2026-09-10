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
