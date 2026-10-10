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

LOCKOUT_TIERS = [60, 300, 900]  # Escalating lockout durations: 60s (1m), 300s (5m), 900s (15m)


class LoginRateLimiter:
    """In-memory rate limiter tracking failed login attempts per client IP.
    Features:
    - 5 failures within 60s triggers temporary lockout with HTTP 429
    - Escalating lockouts: 1st offense = 60s, 2nd = 300s (5m), 3rd+ = 900s (15m)
    - IP isolation (separate buckets per client IP)
    """

    def __init__(self, max_failures: int = 5, window_seconds: float = 60.0):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._failures: dict[str, list[float]] = {}
        self._lockouts: dict[str, tuple[float, int]] = {}  # ip -> (locked_until, tier_index)

    def is_locked(self, client_ip: str) -> tuple[bool, int]:
        """Check if an IP is currently locked out.
        Returns (is_locked, retry_after_seconds).
        """
        now = time.time()
        if client_ip in self._lockouts:
            locked_until, _ = self._lockouts[client_ip]
            if now < locked_until:
                return True, max(1, int(locked_until - now))
        return False, 0

    def record_failure(self, client_ip: str) -> tuple[bool, int]:
        """Record a failed attempt. If threshold exceeded, triggers escalating lockout.
        Returns (is_now_locked, lockout_duration_seconds).
        """
        now = time.time()
        attempts = self._failures.get(client_ip, [])
        valid_attempts = [t for t in attempts if now - t < self.window_seconds]
        valid_attempts.append(now)
        self._failures[client_ip] = valid_attempts

        if len(valid_attempts) >= self.max_failures:
            current_tier = 0
            if client_ip in self._lockouts:
                _, last_tier = self._lockouts[client_ip]
                current_tier = min(last_tier + 1, len(LOCKOUT_TIERS) - 1)

            lockout_duration = LOCKOUT_TIERS[current_tier]
            locked_until = now + lockout_duration
            self._lockouts[client_ip] = (locked_until, current_tier)
            self._failures[client_ip] = []
            return True, lockout_duration

        return False, 0

    def record_success(self, client_ip: str) -> None:
        """Clear failed attempts and reset lockout tier upon a successful login."""
        self._failures.pop(client_ip, None)
        self._lockouts.pop(client_ip, None)

    def reset(self) -> None:
        """Reset all rate limiter state (useful for tests)."""
        self._failures.clear()
        self._lockouts.clear()


login_limiter = LoginRateLimiter(max_failures=5, window_seconds=60.0)


def get_client_ip(request: Any) -> str:
    """Extract client IP safely.
    When BRAIN_TRUST_PROXY is True, reads the original client IP from X-Forwarded-For.
    When BRAIN_TRUST_PROXY is False (default), ignores X-Forwarded-For to prevent header spoofing,
    using request.client.host directly.
    """
    if getattr(settings, "BRAIN_TRUST_PROXY", False):
        forwarded = getattr(request, "headers", {}).get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
            if client_ip:
                return client_ip
    client = getattr(request, "client", None)
    return client.host if client else "127.0.0.1"


def validate_security_settings() -> None:
    """Audit security settings on startup."""
    is_prod = getattr(settings, "BRAIN_ENV", "development").lower() == "production"
    if is_prod:
        if not settings.APP_PASSWORD or not settings.APP_PASSWORD.strip():
            logger.error("CRITICAL SECURITY WARNING: BRAIN_ENV is 'production' but APP_PASSWORD is empty. Endpoints are unprotected!")
        if not settings.AUTH_SECRET_KEY or not settings.AUTH_SECRET_KEY.strip():
            logger.warning("AUTH_SECRET_KEY is unset in production. Deriving token signing key from SHA-256(APP_PASSWORD). Set AUTH_SECRET_KEY to decouple.")


def _get_signing_key() -> bytes:
    """Derive HMAC signing key from secret or app password.
    Ensures tokens survive server restarts when AUTH_SECRET_KEY or APP_PASSWORD is configured.
    """
    if settings.AUTH_SECRET_KEY and settings.AUTH_SECRET_KEY.strip():
        return settings.AUTH_SECRET_KEY.strip().encode("utf-8")
    if settings.APP_PASSWORD and settings.APP_PASSWORD.strip():
        return hashlib.sha256(settings.APP_PASSWORD.strip().encode("utf-8")).digest()
    return b"antigravity-local-dev-signing-key-default"


def is_auth_enabled() -> bool:
    """Check if single-user authentication is enabled."""
    return bool(settings.APP_PASSWORD and settings.APP_PASSWORD.strip())


def verify_password(password: str) -> bool:
    """Verify input password against configured APP_PASSWORD using constant-time comparison of SHA-256 digests."""
    if not is_auth_enabled():
        return True
    if not password:
        return False
    configured_hash = hashlib.sha256(settings.APP_PASSWORD.strip().encode("utf-8")).digest()
    candidate_hash = hashlib.sha256(password.strip().encode("utf-8")).digest()
    return secrets.compare_digest(candidate_hash, configured_hash)


def create_access_token(expires_in: Optional[int] = None) -> dict[str, Any]:
    """Create a signed, timestamped session bearer token."""
    ttl = expires_in if expires_in is not None else getattr(settings, "AUTH_TOKEN_EXPIRE_SECONDS", DEFAULT_TOKEN_EXPIRY)
    now = time.time()
    expires_at = now + ttl
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
