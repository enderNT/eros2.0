"""Durable pre-appointment reminders and their manual panel trigger."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError
from ..domain.scheduling import Slot, slot_label
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentsRepository,
    MessagesRepository,
    MutesRepository,
    OutboxRepository,
    OutboxRow,
)

log = logging.getLogger(__name__)


def reminder_text(slot_utc: datetime, timezone: ZoneInfo, now: datetime) -> str:
    label = slot_label(Slot(slot_utc, slot_utc), timezone, now)
    return (
        f"Hola, te recordamos que tienes una cita {label}. "
        "Si necesitas cambiarla, escríbeme por aquí."
    )


class AppointmentReminders:
    """Schedule one message per confirmed Calendly event.

    An outbox row is the source of truth: it makes restarts harmless, keeps
    webhook retries idempotent, and lets the panel force the exact pending
    reminder for one contact without waking up anyone else.
    """

    def __init__(
        self,
        *,
        outbox: OutboxRepository,
        appointments: AppointmentsRepository,
        messages: MessagesRepository,
        mutes: MutesRepository,
        channel: Channel,
        timezone: str,
        minutes_before: Callable[[], int],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._outbox, self._appointments = outbox, appointments
        self._messages, self._mutes, self._channel = messages, mutes, channel
        self._timezone, self._minutes_before, self._now = ZoneInfo(timezone), minutes_before, now

    def schedule(self, key: ContactKey, event_id: str, slot_utc: datetime, now: datetime) -> None:
        if slot_utc <= now:
            return
        due_at = max(now, slot_utc - timedelta(minutes=self._minutes_before()))
        self._outbox.schedule_appointment_reminder(
            key,
            event_id,
            slot_utc,
            reminder_text(slot_utc, self._timezone, now),
            due_at,
        )

    def reschedule_pending(self, now: datetime) -> None:
        """Apply a global timing change to all future, unsent reminders."""
        for appointment in self._appointments.scheduled():
            if appointment.slot_utc <= now:
                continue
            due_at = max(now, appointment.slot_utc - timedelta(minutes=self._minutes_before()))
            self._outbox.schedule_appointment_reminder(
                appointment.key,
                appointment.calendly_event_id,
                appointment.slot_utc,
                reminder_text(appointment.slot_utc, self._timezone, now),
                due_at,
                replace_pending=True,
            )

    async def send_due(self, now: datetime | None = None) -> None:
        moment = now or self._now()
        for row in self._outbox.due(moment, kind="appointment_reminder"):
            await self._send(row, moment)

    async def send_now(self, key: ContactKey) -> str:
        """Send the pending reminder for exactly this contact, for local testing."""
        row = self._outbox.pending_appointment_reminder(key)
        if row is None:
            return "missing"
        return await self._send(row, self._now())

    async def _send(self, row: OutboxRow, now: datetime) -> str:
        event_id = row.appointment_event_id
        appointment = self._appointments.find(event_id) if event_id else None
        if appointment is None or appointment.status != "scheduled":
            self._outbox.consume(row.id, now)
            return "missing"
        if self._mutes.is_bot_muted(row.key, now):
            return "muted"
        if not self._outbox.consume(row.id, now):
            return "already_sent"
        try:
            message_id = await self._channel.send_text(
                row.key.phone_number_id, row.key.contact_phone, row.text
            )
            self._messages.add_outbound(row.key, message_id, row.text, now)
        except KapsoError:
            log.error("appointment_reminder_send_failed")
            return "failed"
        return "sent"
