"""Kapso HTTP client (SPEC §3, §11).

Async ``httpx`` with an explicit timeout on every call.  Every
``httpx`` failure — timeout, connection error, non-2xx — surfaces as
:class:`~agente.domain.errors.KapsoError`.  One structured log line per
call: phone is masked, message bodies never appear, and the response
body is never logged.

The API paths and response shapes follow Kapso's REST conventions; the
exact contract must be confirmed against a live delivery in T6.
``transport`` is injectable so tests use ``httpx.MockTransport`` — no
network, ever.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from ...domain.contacts import mask_phone, normalize_phone
from ...domain.errors import InvalidPhoneError, KapsoError
from ...ports.channel import ConversationList, ConversationRow

logger = logging.getLogger("agente.kapso")

_DEFAULT_TIMEOUT = 10.0


class KapsoClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout: float = _DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
        )
        self._headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json",
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    async def send_text(self, phone_number_id: str, to: str, body: str) -> str:
        url = f"{self._base_url}/{phone_number_id}/messages"
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"body": body},
        }
        started = time.monotonic()
        try:
            response = await self._client.post(url, json=payload, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "kapso.send_text failed",
                extra={
                    "phone_number_id": phone_number_id,
                    "to": mask_phone(to),
                    "error_type": type(exc).__name__,
                },
            )
            raise KapsoError(f"send_text failed: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        data = response.json()
        message_id = str((data.get("messages") or [{}])[0].get("id", ""))
        logger.info(
            "kapso.send_text ok",
            extra={
                "phone_number_id": phone_number_id,
                "to": mask_phone(to),
                "kapso_message_id": message_id,
                "latency_ms": latency_ms,
            },
        )
        return message_id

    async def list_conversations(
        self, phone_number_id: str, *, cursor: str | None = None, limit: int = 20
    ) -> ConversationList:
        url = f"{self._base_url}/{phone_number_id}/conversations"
        params: dict[str, str | int] = {"limit": limit}
        if cursor is not None:
            params["after"] = cursor
        started = time.monotonic()
        try:
            response = await self._client.get(url, params=params, headers=self._headers)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error(
                "kapso.list_conversations failed",
                extra={
                    "phone_number_id": phone_number_id,
                    "cursor": cursor,
                    "limit": limit,
                    "error_type": type(exc).__name__,
                },
            )
            raise KapsoError(f"list_conversations failed: {exc}") from exc
        latency_ms = int((time.monotonic() - started) * 1000)
        data = response.json()
        rows = [_conversation_row(item) for item in data.get("data", [])]
        next_cursor = (data.get("paging") or {}).get("next")
        logger.info(
            "kapso.list_conversations ok",
            extra={
                "phone_number_id": phone_number_id,
                "count": len(rows),
                "has_next": next_cursor is not None,
                "latency_ms": latency_ms,
            },
        )
        return ConversationList(conversations=rows, next_cursor=next_cursor)


def _conversation_row(item: dict[str, Any]) -> ConversationRow:
    """Map one row of `GET /{phone_number_id}/conversations`.

    Shape confirmed against the live API (2026-08-17): the contact phone
    arrives bare (`525619878083`) and is normalized to E.164 here, because
    the mute switch is keyed by it and the inbound path stores it that way.
    Everything about the last message sits under `kapso`.
    """
    kapso = item.get("kapso") or {}
    if not isinstance(kapso, dict):
        kapso = {}
    return ConversationRow(
        conversation_id=str(item.get("id", "")),
        contact_name=item.get("contact_name") or kapso.get("contact_name"),
        contact_phone=_normalized(item.get("phone_number")),
        last_message_text=kapso.get("last_message_text"),
        last_activity_at=_parse_datetime(item.get("last_active_at"))
        or _parse_datetime(kapso.get("last_message_timestamp")),
        status=item.get("status"),
    )


def _normalized(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return normalize_phone(value)
    except InvalidPhoneError:
        return None


def _parse_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
