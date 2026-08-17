"""Where a Calendly slot link becomes a real appointment (TASKS T9b).

`agendar_cita` only hands the patient a booking page — Calendly has no API to
book on their behalf — so nothing in our database says "appointment" until
Calendly tells us the invitee was created. This service is that moment: it
resolves the opaque token we put in the link, writes the row, updates the
durable profile and sends the one confirmation the patient gets.

Two properties matter more than anything else here:

* **Idempotency.** Calendly retries a delivery it thinks failed. The same
  `calendly_event_id` must never produce a second appointment row or a second
  WhatsApp message — a patient receiving "tu cita quedó confirmada" twice reads
  it as two appointments.
* **Silence on an unknown token.** A booking with no token is a human booking
  made outside our conversation. It is logged and ignored, never guessed at.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError, StoreError
from ..domain.scheduling import Slot, slot_label
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentsRepository,
    BookingTokensRepository,
    ContactsRepository,
    MessagesRepository,
    Profile,
)

log = logging.getLogger(__name__)

CREATED = "invitee.created"
CANCELED = "invitee.canceled"

CANCELED_TEXT = "Tu cita quedó cancelada. Si quieres, te paso otros horarios para reagendar."


def confirmation_text(slot_utc: datetime, timezone: str, now: datetime, address: str) -> str:
    """The patient-facing confirmation, in clinic local time.

    The address is only mentioned when it is actually configured: an invented
    address is worse than no address.
    """
    label = slot_label(Slot(slot_utc, slot_utc), ZoneInfo(timezone), now)
    parts = [_sentence(f"¡Listo! Tu cita quedó confirmada: {label}")]
    if address:
        parts.append(_sentence(f"La dirección es {address}"))
    parts.append("Si necesitas cambiarla, escríbeme por aquí.")
    return " ".join(parts)


def _sentence(text: str) -> str:
    """Close the sentence without doubling the period.

    Both halves can already end in one: the time label ends in "p. m." and the
    configured address is written by a human who may or may not punctuate it.
    """
    return text if text.rstrip().endswith((".", "!", "?")) else f"{text}."


class BookingService:
    def __init__(
        self,
        *,
        tokens: BookingTokensRepository,
        appointments: AppointmentsRepository,
        contacts: ContactsRepository,
        messages: MessagesRepository,
        channel: Channel,
        timezone: str,
        address: str = "",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._tokens, self._appointments = tokens, appointments
        self._contacts, self._messages, self._channel = contacts, messages, channel
        self._timezone, self._address, self._now = timezone, address, now

    async def handle(self, event: str, payload: dict[str, Any]) -> None:
        if event == CREATED:
            await self._created(payload)
        elif event == CANCELED:
            await self._canceled(payload)
        else:
            log.info("calendly_event_ignored", extra={"event": event})

    async def _created(self, payload: dict[str, Any]) -> None:
        event_uri = str(payload.get("event") or "")
        if not event_uri:
            log.warning("calendly_payload_incomplete", extra={"event": CREATED})
            return
        if self._appointments.find(event_uri) is not None:
            log.info("calendly_delivery_duplicate", extra={"event": CREATED})
            return
        token = str((payload.get("tracking") or {}).get("utm_content") or "")
        record = self._tokens.resolve(token) if token else None
        if record is None:
            # Someone booked straight from Calendly. Not our conversation, and
            # guessing whose it is would confirm an appointment to the wrong person.
            log.info("calendly_booking_unlinked", extra={"has_token": bool(token)})
            return
        now = self._now()
        slot = _start_time(payload) or record.slot_utc
        self._contacts.ensure_contact(record.key, now)
        try:
            self._appointments.add(record.key, event_uri, slot, now)
        except StoreError:
            # The unique index on calendly_event_id is the backstop for two
            # deliveries racing past the `find` check above.
            log.info("calendly_delivery_duplicate", extra={"event": CREATED})
            return
        self._save_profile(record.key, slot, now, payload)
        await self._notify(record.key, confirmation_text(slot, self._timezone, now, self._address))

    async def _canceled(self, payload: dict[str, Any]) -> None:
        event_uri = str(payload.get("event") or "")
        existing = self._appointments.find(event_uri) if event_uri else None
        if existing is None:
            log.info("calendly_cancel_unknown")
            return
        if existing.status == "canceled":
            log.info("calendly_delivery_duplicate", extra={"event": CANCELED})
            return
        now = self._now()
        self._appointments.update_status(event_uri, "canceled", now)
        self._clear_next_appointment(existing.key, now)
        await self._notify(existing.key, CANCELED_TEXT)

    def _save_profile(
        self, key: ContactKey, slot: datetime, now: datetime, payload: dict[str, Any]
    ) -> None:
        current = self._profile(key, now)
        self._contacts.save_profile(
            replace(
                current,
                name=current.name or _clean(payload.get("name")),
                email=current.email or _clean(payload.get("email")),
                kind="patient",
                appointment_count=current.appointment_count + 1,
                next_appointment_utc=slot,
                updated_at=now,
            )
        )

    def _clear_next_appointment(self, key: ContactKey, now: datetime) -> None:
        current = self._profile(key, now)
        self._contacts.save_profile(replace(current, next_appointment_utc=None, updated_at=now))

    def _profile(self, key: ContactKey, now: datetime) -> Profile:
        existing = self._contacts.get_profile(key)
        if existing is not None:
            return existing
        return Profile(
            key=key,
            name=None,
            email=None,
            kind="prospect",
            timezone=None,
            appointment_count=0,
            last_appointment_utc=None,
            next_appointment_utc=None,
            handoff_state="bot",
            updated_at=now,
        )

    async def _notify(self, key: ContactKey, text: str) -> None:
        try:
            outbound_id = await self._channel.send_text(
                key.phone_number_id, key.contact_phone, text
            )
        except KapsoError:
            # The appointment is already recorded; losing the notification must
            # not lose the booking.
            log.error("calendly_notify_failed")
            return
        self._messages.add_outbound(key, outbound_id, text, self._now())


def _start_time(payload: dict[str, Any]) -> datetime | None:
    value = (payload.get("scheduled_event") or {}).get("start_time")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value else ""
    return text or None
