"""Stateless HMAC reset tokens - no extra DB table needed.

Token format: base64url(user_id:timestamp):hmac_hex
Expiry is checked at verification time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

DEFAULT_EXPIRY_SECONDS = 3600  # 1 hour


def _encode(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode(value: str) -> str:
    padding = 4 - len(value) % 4
    return base64.urlsafe_b64decode(value + "=" * padding).decode()


def generate_reset_token(user_id: int, secret_key: str) -> str:
    ts = int(time.time())
    payload = f"{user_id}:{ts}"
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{_encode(payload)}.{sig}"


def verify_reset_token(
    token: str,
    secret_key: str,
    expiry_seconds: int = DEFAULT_EXPIRY_SECONDS,
) -> int | None:
    """Return user_id if token is valid and unexpired, else None."""
    try:
        encoded_payload, sig = token.rsplit(".", 1)
        payload = _decode(encoded_payload)
        user_id_str, ts_str = payload.split(":")
        expected_sig = hmac.new(
            secret_key.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if time.time() - int(ts_str) > expiry_seconds:
            return None
        return int(user_id_str)
    except Exception:
        return None
