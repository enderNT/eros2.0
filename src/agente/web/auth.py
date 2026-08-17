"""Session authentication for the control panel (SPEC §3, PROJECT.md).

Shared password from settings, HMAC-signed session cookie with expiry.
Every ``/admin`` route except login is guarded by ``require_panel_session``.
No password in URLs or logs — the redaction filter already drops ``password``
keys (§11).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request, Response

_COOKIE_NAME = "agente_panel"
_MAX_AGE = 28_800  # 8 hours — a clinic workday
_ACTOR = "panel"


def _sign(payload: dict[str, Any], secret: str) -> str:
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    mac = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(body).decode() + "." + base64.urlsafe_b64encode(mac).decode()


def _verify(token: str, secret: str) -> dict[str, Any] | None:
    try:
        body_b64, mac_b64 = token.rsplit(".", 1)
        body = base64.urlsafe_b64decode(body_b64.encode())
        expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
        actual = base64.urlsafe_b64decode(mac_b64.encode())
        if not hmac.compare_digest(expected, actual):
            return None
        payload = json.loads(body)
        if not isinstance(payload, dict):
            return None
        if float(payload.get("exp", 0)) < time.time():
            return None
        return payload
    except (ValueError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError):
        return None


def set_session(response: Response, secret: str) -> None:
    payload = {"authed": True, "exp": int(time.time()) + _MAX_AGE}
    response.set_cookie(
        _COOKIE_NAME,
        _sign(payload, secret),
        httponly=True,
        samesite="lax",
        path="/admin",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(_COOKIE_NAME, path="/admin")


def is_authed(request: Request) -> bool:
    token = request.cookies.get(_COOKIE_NAME)
    if not token:
        return False
    payload = _verify(token, request.app.state.settings.panel_session_secret)
    return payload is not None and payload.get("authed") is True


def require_panel_session(request: Request) -> None:
    if not is_authed(request):
        raise HTTPException(status_code=401, detail="panel authentication required")


def panel_actor() -> str:
    """Identifier written to ``audit_log.actor`` for panel-initiated mutations."""
    return _ACTOR
