"""Calendly webhook HMAC verification."""

from __future__ import annotations

import hashlib
import hmac


def verify_signature(raw_body: bytes, signature: str | None, signing_key: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(signing_key.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
