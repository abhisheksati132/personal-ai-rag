import base64
import hashlib
import hmac
import logging
import secrets
import time
from typing import Any, Optional
from fastapi import Header, HTTPException, status

from src.config import settings

logger = logging.getLogger(__name__)

# Token lifetime: 30 days in seconds
DEFAULT_TOKEN_EXPIRY = 30 * 24 * 3600


def _get_signing_key() -> bytes:
    """Derive HMAC signing key from secret or app password."""
    if settings.AUTH_SECRET_KEY and settings.AUTH_SECRET_KEY.strip():
        return settings.AUTH_SECRET_KEY.strip().encode("utf-8")
    if settings.APP_PASSWORD and settings.APP_PASSWORD.strip():
        return hashlib.sha256(settings.APP_PASSWORD.strip().encode("utf-8")).digest()
    return b"antigravity-local-dev-signing-key-default"


def is_auth_enabled() -> bool:
    """Check if single-user authentication is enabled."""
    return bool(settings.APP_PASSWORD and settings.APP_PASSWORD.strip())


def verify_password(password: str) -> bool:
    """Verify input password against configured APP_PASSWORD using constant-time comparison."""
    if not is_auth_enabled():
        return True
    if not password:
        return False
    configured = settings.APP_PASSWORD.strip().encode("utf-8")
    candidate = password.strip().encode("utf-8")
    return secrets.compare_digest(candidate, configured)


def create_access_token(expires_in: int = DEFAULT_TOKEN_EXPIRY) -> dict[str, Any]:
    """Create a signed, timestamped session bearer token."""
    now = time.time()
    expires_at = now + expires_in
    nonce = secrets.token_hex(8)
    payload = f"{int(expires_at)}:{nonce}"
    sig = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw_token = f"{payload}:{sig}"
    encoded = base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")
    return {
        "token": encoded,
        "token_type": "bearer",
        "expires_at": expires_at,
    }


def verify_token(token: str) -> bool:
    """Verify cryptographic signature and expiry of a bearer token."""
    if not is_auth_enabled():
        return True
    if not token or not token.strip():
        return False

    try:
        raw = base64.urlsafe_b64decode(token.strip().encode("utf-8")).decode("utf-8")
        parts = raw.split(":")
        if len(parts) != 3:
            return False

        expires_str, nonce, signature = parts
        expires_at = float(expires_str)

        # Check expiry
        if time.time() > expires_at:
            logger.warning("Auth token has expired")
            return False

        # Recompute signature
        payload = f"{expires_str}:{nonce}"
        expected_sig = hmac.new(_get_signing_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return secrets.compare_digest(signature, expected_sig)
    except Exception as e:
        logger.warning(f"Failed to verify auth token: {e}")
        return False


def require_auth(authorization: Optional[str] = Header(None)) -> bool:
    """FastAPI dependency to protect private endpoints.
    Allows unauthenticated requests when APP_PASSWORD is not set (local dev mode).
    Enforces Bearer token verification with HTTP 401 when APP_PASSWORD is set.
    """
    if not is_auth_enabled():
        return True

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header: must be 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = parts[1]
    if not verify_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True
