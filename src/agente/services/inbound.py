"""Inbound webhook pipeline through the mute gate (SPEC §4)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ..adapters.kapso.payloads import WebhookPayload
from ..adapters.store.messages import SqliteMessagesRepository
from ..adapters.store.mutes import SqliteMutesRepository
from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError
from ..domain.reply import split_reply
from ..ports.channel import Channel

log = logging.getLogger(__name__)
FALLBACK = "Estoy teniendo un problema técnico. ¿Quieres que te conecte con una persona?"


class InboundService:
    def __init__(
        self,
        messages: SqliteMessagesRepository,
        mutes: SqliteMutesRepository,
        channel: Channel,
        *,
        reply: str = "Gracias por tu mensaje.",
        responder: Callable[[ContactKey, str], Awaitable[str]] | None = None,
        debounce_seconds: float = 4.0,
    ) -> None:
        self._messages, self._mutes, self._channel, self._reply = messages, mutes, channel, reply
        self._responder = responder
        self._debounce_seconds = debounce_seconds
        self._pending: dict[ContactKey, list[WebhookPayload]] = {}
        self._pending_lock = asyncio.Lock()

    async def handle(self, payload: WebhookPayload) -> None:
        message = payload.message
        key = ContactKey(payload.phone_number_id, message.from_)
        now = _timestamp(message.timestamp)
        text = _text(payload)
        if not self._messages.add_inbound(key, message.id, text, now):
            return
        async with self._pending_lock:
            waiting = self._pending.setdefault(key, [])
            waiting.append(payload)
            if len(waiting) > 1:
                return
        await asyncio.sleep(self._debounce_seconds)
        async with self._pending_lock:
            batch = self._pending.pop(key, [])
        if batch:
            await self._handle_locked(batch, key)

    async def _handle_locked(self, batch: list[WebhookPayload], key: ContactKey) -> None:
        payload = batch[-1]
        message = payload.message
        now = _timestamp(message.timestamp)
        if self._mutes.is_bot_muted(key, now):
            log.info(
                "inbound_turn", extra={"message_id": message.id, "muted": True, "outcome": "muted"}
            )
            return
        try:
            merged = "\n".join(_text(item) for item in batch)
            reply = await self._responder(key, merged) if self._responder else self._reply
            for chunk in split_reply(reply):
                outbound_id = await self._channel.send_text(
                    payload.phone_number_id, key.contact_phone, chunk
                )
                self._messages.add_outbound(key, outbound_id, chunk, datetime.now(UTC))
        except KapsoError:
            try:
                outbound_id = await self._channel.send_text(
                    payload.phone_number_id, key.contact_phone, FALLBACK
                )
                self._messages.add_outbound(key, outbound_id, FALLBACK, datetime.now(UTC))
            except KapsoError:
                pass
            log.error(
                "inbound_turn",
                extra={"message_id": message.id, "muted": False, "outcome": "send_failed"},
            )
            return
        log.info(
            "inbound_turn", extra={"message_id": message.id, "muted": False, "outcome": "sent"}
        )


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(UTC)
    return result if result.tzinfo else result.replace(tzinfo=UTC)


def _text(payload: WebhookPayload) -> str:
    message = payload.message
    return (
        (message.text.body if message.text else None)
        or (message.kapso.content if message.kapso else "")
        or ""
    )
