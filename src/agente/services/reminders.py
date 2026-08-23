"""Durable pre-appointment reminders and their manual panel trigger."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import KapsoError
from ..domain.scheduling import Slot, address_sentence, slot_label
from ..ports.channel import Channel
from ..ports.store import (
    AppointmentsRepository,
    MessagesRepository,
    MutesRepository,
    OutboxRepository,
    OutboxRow,
)

log = logging.getLogger(__name__)


def reminder_text(slot_utc: datetime, timezone: ZoneInfo, now: datetime, address: str = "") -> str:
    """El recordatorio: cuándo es la cita y a dónde hay que ir.

    La dirección se repite aquí aunque ya fuera en la confirmación, y a propósito.
    Entre una cosa y otra pueden pasar días; el recordatorio es el mensaje que la
    persona tiene delante justo cuando está a punto de salir de casa, y mandarla
    a buscar la dirección en el historial es hacerle trabajo que nos toca a
    nosotros.
    """
    label = slot_label(Slot(slot_utc, slot_utc), timezone, now)
    partes = [f"Hola, te recordamos que tienes una cita {label}."]
    direccion = address_sentence(address)
    if direccion:
        partes.append(direccion)
    partes.append("Si necesitas cambiarla, escríbeme por aquí.")
    return " ".join(partes)


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
        enabled: Callable[[], bool] = lambda: True,
        address: str = "",
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._outbox, self._appointments = outbox, appointments
        self._messages, self._mutes, self._channel = messages, mutes, channel
        self._timezone, self._minutes_before, self._now = ZoneInfo(timezone), minutes_before, now
        self._enabled, self._address = enabled, address

    def schedule(self, key: ContactKey, event_id: str, slot_utc: datetime, now: datetime) -> None:
        if not self._enabled() or slot_utc <= now:
            return
        due_at = max(now, slot_utc - timedelta(minutes=self._minutes_before()))
        self._outbox.schedule_appointment_reminder(
            key,
            event_id,
            slot_utc,
            reminder_text(slot_utc, self._timezone, now, self._address),
            due_at,
        )

    def reschedule_pending(self, now: datetime) -> None:
        """Apply a global timing change to all future, unsent reminders.

        Doubles as the way back from the off switch. Turning reminders off drops
        the queued rows, so turning them back on has to rebuild one per future
        appointment — otherwise every patient who booked while it was off would
        silently never be reminded.
        """
        if not self._enabled():
            return
        for appointment in self._appointments.scheduled():
            if appointment.slot_utc <= now:
                continue
            due_at = max(now, appointment.slot_utc - timedelta(minutes=self._minutes_before()))
            self._outbox.schedule_appointment_reminder(
                appointment.key,
                appointment.calendly_event_id,
                appointment.slot_utc,
                reminder_text(appointment.slot_utc, self._timezone, now, self._address),
                due_at,
                replace_pending=True,
            )

    async def send_due(self, now: datetime | None = None) -> None:
        if not self._enabled():
            return
        moment = now or self._now()
        for row in self._outbox.due(moment, kind="appointment_reminder"):
            await self._send(row, moment)

    async def send_now(self, key: ContactKey) -> str:
        """Send the pending reminder for exactly this contact, for local testing."""
        if not self._enabled():
            return "disabled"
        row = self._outbox.pending_appointment_reminder(key)
        if row is None:
            return "missing"
        return await self._send(row, self._now())

    def drop_pending(self) -> None:
        """Vaciar la cola de recordatorios, para cuando la clínica los apaga.

        Se pierde el `due_at` calculado, no la cita: `reschedule_pending` los
        reconstruye desde `appointments` en cuanto se vuelvan a encender.
        """
        self._outbox.cancel_kind("appointment_reminder")

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
