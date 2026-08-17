"""Hand the patient the booking page for the slot they chose.

Calendly's public API cannot create a booking on someone's behalf —
`/scheduling_links` only mints a link — so this tool never claims a
confirmed appointment. It returns the slot-specific booking page and says,
in the tool result the model reads, that nothing is booked yet. The
appointment row is written only when Calendly's `invitee.created` webhook
confirms it (TASKS T9b).

The patient fills in their own name and email on that page, which is why
this tool does not take them: a model-invented email would silently send
the confirmation nowhere.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..domain.contacts import ContactKey
from ..domain.scheduling import Slot, is_bookable
from ..ports.calendar import CalendarSlot
from ..ports.store import AppointmentsRepository

BOOKING_BUFFER = timedelta(minutes=10)
EXPIRED = "Ese horario ya no está disponible. Ofrece otro de los horarios vigentes."
ALREADY_BOOKED = "Este contacto ya tiene una cita confirmada en ese horario."
NO_LINK = "No tengo el enlace de ese horario. Ofrece otro o escala a una persona."


def link_instructions(url: str) -> str:
    return (
        f"Envíale este enlace para que confirme el horario: {url}\n"
        "IMPORTANTE: la cita NO está agendada todavía. Ahí completa su nombre y correo."
        " No le digas que ya quedó confirmada; pídele que te avise cuando termine."
    )


async def agendar_cita(
    appointments: AppointmentsRepository,
    key: ContactKey,
    slot: CalendarSlot,
    now: datetime,
) -> str:
    if not is_bookable(Slot(slot.start_utc, slot.end_utc), now, BOOKING_BUFFER):
        return EXPIRED
    booked = [
        item
        for item in appointments.for_contact(key)
        if item.slot_utc == slot.start_utc and item.status == "scheduled"
    ]
    if booked:
        return ALREADY_BOOKED
    if not slot.booking_url:
        return NO_LINK
    return link_instructions(slot.booking_url)
