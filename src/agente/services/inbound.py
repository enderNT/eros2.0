"""Inbound webhook pipeline through the mute gate (SPEC §4)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from ..adapters.kapso.payloads import WebhookPayload
from ..adapters.store.messages import SqliteMessagesRepository
from ..adapters.store.mutes import SqliteMutesRepository
from ..domain.contacts import ContactKey
from ..domain.crisis import CrisisVerdict, adds_crisis_directives
from ..domain.errors import DomainError, KapsoError
from ..domain.reply import split_reply
from ..ports.channel import Channel
from .crisis import Classifier, check

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
        responder: Callable[[ContactKey, str, str | None, str], Awaitable[str]] | None = None,
        crisis_classifier: Classifier | None = None,
        crisis_message: str = "",
        crisis_directives: str = "",
        debounce_seconds: float = 4.0,
        compactor: Callable[[ContactKey], Awaitable[bool]] | None = None,
    ) -> None:
        self._messages, self._mutes, self._channel, self._reply = messages, mutes, channel, reply
        self._responder = responder
        self._crisis_classifier, self._crisis_message = crisis_classifier, crisis_message
        self._crisis_directives = crisis_directives
        self._debounce_seconds = debounce_seconds
        self._compactor = compactor
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
        # One id per turn, on every log line and on every llm_trace row of this
        # turn. It is what makes "where did it break" answerable: without it the
        # model calls and the pipeline events cannot be tied together.
        turn = _Turn(turn_id=uuid.uuid4().hex[:12], message_id=message.id, merged=len(batch))
        if self._mutes.is_bot_muted(key, now):
            turn.finish(log.info, muted=True, outcome="muted")
            return
        try:
            merged = "\n".join(_text(item) for item in batch)
            verdict = await check(self._crisis_classifier, merged, turn_id=turn.turn_id)
            turn.verdict = verdict.value
            if verdict is CrisisVerdict.ACUTE:
                # The clinic's text, verbatim: the model never gets a turn to
                # paraphrase a crisis message.
                self._mutes.set_mute(key, now, actor="crisis", reason="acute crisis", urgent=True)
                outbound_id = await self._channel.send_text(
                    payload.phone_number_id, key.contact_phone, self._crisis_message
                )
                self._messages.add_outbound(
                    key, outbound_id, self._crisis_message, datetime.now(UTC)
                )
                turn.finish(log.warning, muted=True, outcome="crisis", chunks=1)
                return
            directives = self._crisis_directives if adds_crisis_directives(verdict) else None
            turn.directives = directives is not None
            reply = (
                await self._responder(key, merged, directives, turn.turn_id)
                if self._responder
                else self._reply
            )
            chunks = split_reply(reply)
            for chunk in chunks:
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
            turn.finish(log.error, muted=False, outcome="send_failed")
            return
        except DomainError as exc:
            # The store or the model gave up mid-turn. Without this the turn
            # vanished from the logs and the patient just never got an answer.
            turn.finish(log.error, muted=False, outcome="failed", error=type(exc).__name__)
            raise
        turn.finish(log.info, muted=False, outcome="sent", chunks=len(chunks))
        await self._compact(key)

    async def _compact(self, key: ContactKey) -> None:
        """Off the reply path: the patient already has the answer."""
        if self._compactor is None:
            return
        try:
            await self._compactor(key)
        except DomainError:
            log.error("compaction_failed", extra={"stage": "inbound"})


class _Turn:
    """Accumulates the wide event of SPEC §11 — one log line per turn.

    One line with everything beats five lines that have to be stitched: the
    question being answered is always "what happened to this turn, and where
    did it stop", and `turn_id` joins it to the `llm_trace` rows.
    """

    def __init__(self, *, turn_id: str, message_id: str, merged: int) -> None:
        self.turn_id, self.message_id, self.merged = turn_id, message_id, merged
        self.verdict: str | None = None
        self.directives = False
        self._started = time.monotonic()

    def finish(self, emit, **fields: object) -> None:
        emit(
            "inbound_turn",
            extra={
                "turn_id": self.turn_id,
                "message_id": self.message_id,
                "merged_messages": self.merged,
                "crisis_verdict": self.verdict,
                "crisis_directives": self.directives,
                "duration_ms": int((time.monotonic() - self._started) * 1000),
                **fields,
            },
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
