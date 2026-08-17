"""Calendly webhook signature verification.

Calendly sends one header carrying both halves —
`Calendly-Webhook-Signature: t=<unix seconds>,v1=<hex hmac>` — and the
signed payload is `f"{t}.{raw_body}"`, **not** the body alone. Verifying the
body alone would accept a replay of any past delivery forever; the timestamp
is inside the MAC precisely so it cannot be swapped, and it is only worth
checking because of that.

Fails closed: no header, no signing key, a malformed header or a stale
timestamp are all a rejection.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

TOLERANCE = timedelta(minutes=5)


def verify_signature(
    raw_body: bytes,
    signature: str | None,
    signing_key: str,
    *,
    now: datetime,
    tolerance: timedelta = TOLERANCE,
) -> bool:
    if not signature or not signing_key:
        return False
    parts = _parts(signature)
    timestamp, provided = parts.get("t"), parts.get("v1")
    if not timestamp or not provided:
        return False
    try:
        signed_at = datetime.fromtimestamp(int(timestamp), UTC)
    except (ValueError, OverflowError, OSError):
        return False
    if abs(now - signed_at) > tolerance:
        return False
    expected = hmac.new(
        signing_key.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def sign(raw_body: bytes, signing_key: str, moment: datetime) -> str:
    """The header Calendly would send. Exists so tests never hand-roll the MAC."""
    timestamp = str(int(moment.timestamp()))
    digest = hmac.new(
        signing_key.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def _parts(signature: str) -> dict[str, str]:
    pairs = (item.split("=", 1) for item in signature.split(",") if "=" in item)
    return {name.strip(): value.strip() for name, value in pairs}
