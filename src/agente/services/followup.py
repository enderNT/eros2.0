"""One gentle, cancelable follow-up after a booking link is delivered."""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError
from ..domain.scheduling import Slot, slot_label
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentsRepository,
    BookingTokensRepository,
    MessagesRepository,
    MutesRepository,
    OutboxRepository,
)

log = logging.getLogger(__name__)
_URL = re.compile(r"https?://[^\s]+")


class BookingFollowups:
    def __init__(
        self,
        *,
        outbox: OutboxRepository,
        booking_tokens: BookingTokensRepository,
        appointments: AppointmentsRepository,
        messages: MessagesRepository,
        mutes: MutesRepository,
        channel: Channel,
        timezone: str,
        delay_minutes: Callable[[], int] = lambda: 90,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._outbox, self._tokens, self._appointments = outbox, booking_tokens, appointments
        self._messages, self._mutes, self._channel = messages, mutes, channel
        self._timezone, self._delay_minutes, self._now = ZoneInfo(timezone), delay_minutes, now

    def schedule_from_outbound(self, key: ContactKey, text: str, sent_at: datetime) -> None:
        token = _booking_token(text)
        if token is None:
            return
        record = self._tokens.resolve(token)
        if record is None or record.key != key:
            return
        label = slot_label(Slot(record.slot_utc, record.slot_utc), self._timezone, sent_at)
        followup = f"Hola, ¿pudiste agendar tu cita para {label}?"
        self._outbox.schedule_booking_followup(
            key,
            token,
            record.slot_utc,
            followup,
            sent_at + timedelta(minutes=self._delay_minutes()),
        )

    def cancel_for_contact(self, key: ContactKey) -> None:
        self._outbox.cancel_for_contact(key)

    def cancel_for_token(self, token: str) -> None:
        self._outbox.cancel_for_token(token)

    async def send_due(self, now: datetime | None = None) -> None:
        moment = now or self._now()
        for row in self._outbox.due(moment):
            if not self._outbox.consume(row.id, moment):
                continue
            if self._mutes.is_bot_muted(row.key, moment) or _is_confirmed(
                self._appointments, row.key, row.slot_utc
            ):
                continue
            try:
                message_id = await self._channel.send_text(
                    row.key.phone_number_id, row.key.contact_phone, row.text
                )
                self._messages.add_outbound(row.key, message_id, row.text, moment)
            except KapsoError:
                log.error("booking_followup_send_failed")


def _booking_token(text: str) -> str | None:
    for match in _URL.finditer(text):
        url = match.group().rstrip(".,!?;:)]}")
        token = parse_qs(urlparse(url).query).get("utm_content", [None])[0]
        if token:
            return token
    return None


def _is_confirmed(
    appointments: AppointmentsRepository, key: ContactKey, slot_utc: datetime | None
) -> bool:
    return slot_utc is not None and any(
        item.slot_utc == slot_utc and item.status == "scheduled"
        for item in appointments.for_contact(key)
    )
