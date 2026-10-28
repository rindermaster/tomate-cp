"""
TomateCP - Lightweight Authentication Module
Cookie-based session authentication with HMAC signature.
Zero external cryptographic dependencies (uses hashlib and hmac).
"""

import hmac
import time
import hashlib
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse


def create_session_token(username: str, secret_key: str, max_age_days: int = 7) -> str:
    """Creates a signed timestamped session token."""
    expires_at = int(time.time()) + (max_age_days * 86400)
    payload = f"{username}:{expires_at}"
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_session_token(token: Optional[str], secret_key: str) -> Optional[str]:
    """Verifies HMAC signature and expiration, returning username if valid."""
    if not token or ":" not in token:
        return None

    parts = token.split(":")
    if len(parts) != 3:
        return None

    username, expires_str, sig = parts
    try:
        expires_at = int(expires_str)
    except ValueError:
        return None

    if time.time() > expires_at:
        return None

    payload = f"{username}:{expires_at}"
    expected_sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if hmac.compare_digest(sig, expected_sig):
        return username
    return None


def get_current_user_optional(request: Request, config: Dict[str, Any]) -> Optional[str]:
    """Checks session cookie and returns username if logged in."""
    token = request.cookies.get("tomate_session")
    secret_key = config.get("secret_key", "default-tomate-secret")
    return verify_session_token(token, secret_key)


def require_auth(request: Request, config: Dict[str, Any]):
    """Enforces authentication. Raises HTTPException or redirects to login."""
    user = get_current_user_optional(request, config)
    if not user:
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão expirada ou não autenticado."
            )
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"}
        )
    return user
