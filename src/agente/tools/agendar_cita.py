"""Book a previously offered slot after rechecking its time boundary."""

from __future__ import annotations

from datetime import datetime, timedelta

from ..adapters.store.appointments import SqliteAppointmentsRepository
from ..domain.contacts import ContactKey
from ..domain.scheduling import Slot, is_bookable
from ..ports.calendar import Calendar, CalendarSlot


async def agendar_cita(
    calendar: Calendar,
    appointments: SqliteAppointmentsRepository,
    key: ContactKey,
    slot: CalendarSlot,
    name: str,
    email: str,
    now: datetime,
) -> str:
    if not is_bookable(Slot(slot.start_utc, slot.end_utc), now, timedelta(minutes=10)):
        return "Ese horario ya no está disponible. Elige otro, por favor."
    existing = [
        item
        for item in appointments.for_contact(key)
        if item.slot_utc == slot.start_utc and item.status == "scheduled"
    ]
    if existing:
        return "Ese horario ya está registrado para este contacto."
    event_id = await calendar.create_invitee(slot, name, email)
    appointments.add(key, event_id, slot.start_utc, now)
    return "Tu cita quedó registrada."
