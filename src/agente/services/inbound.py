"""Inbound webhook pipeline through the mute gate (SPEC §4)."""

from __future__ import annotations

import asyncio
import logging
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
    ) -> None:
        self._messages, self._mutes, self._channel, self._reply = messages, mutes, channel, reply
        self._locks: dict[ContactKey, asyncio.Lock] = {}

    async def handle(self, payload: WebhookPayload) -> None:
        message = payload.message
        key = ContactKey(payload.phone_number_id, message.from_)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            await self._handle_locked(payload, key)

    async def _handle_locked(self, payload: WebhookPayload, key: ContactKey) -> None:
        message = payload.message
        now = _timestamp(message.timestamp)
        text = (
            (message.text.body if message.text else None)
            or (message.kapso.content if message.kapso else "")
            or ""
        )
        if not self._messages.add_inbound(key, message.id, text, now):
            return
        if self._mutes.is_bot_muted(key, now):
            log.info(
                "inbound_turn", extra={"message_id": message.id, "muted": True, "outcome": "muted"}
            )
            return
        try:
            for chunk in split_reply(self._reply):
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
