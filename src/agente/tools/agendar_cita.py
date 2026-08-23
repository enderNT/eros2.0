"""Reserve the slot the patient chose, on their behalf.

This tool used to hand out a booking page, because Calendly's API could not
create a booking for someone else. It can now (`POST /invitees`), and that
changes what the clinic's assistant is for: filling a form and digging a
confirmation out of an inbox was never the patient's job.

Two consequences worth stating, because they are the reason the old machinery
is gone:

* **No token, no link, no `utm_content`.** Attribution was only ever needed to
  work out whose booking came back from a page we did not control. We know
  whose it is: we made it.
* **The appointment exists when this returns.** The old tool had to insist the
  model not claim a confirmed appointment, because nothing was booked yet. Now
  the opposite is true, and saying so is correct.

Booking replaces any appointment the contact already had — see
`BookingService.book_for_contact`, where that rule lives.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.errors import SlotTakenError
from ..domain.scheduling import Slot, is_bookable, slot_label
from ..ports.calendar import CalendarSlot
from ..services.booking import BookingService

BOOKING_BUFFER = timedelta(minutes=10)
EXPIRED = "Ese horario ya no está disponible. Ofrece otro de los horarios vigentes."
TAKEN = (
    "Ese horario acaba de ocuparlo alguien más y la cita NO quedó agendada."
    " Díselo al paciente y ofrécele otro de los horarios vigentes."
)


def confirmed(label: str, movida: bool) -> str:
    """What the model reads after a successful booking.

    It is told the appointment exists, and told to say so — the opposite of the
    old link flow. When the booking replaced an earlier one, it is told that too,
    because a patient who moved their appointment needs to hear that the old time
    is gone, not just that a new one exists.
    """
    if movida:
        return (
            f"Cita reagendada para {label}. La cita anterior quedó cancelada y su horario"
            " liberado. Dile al paciente las DOS cosas, no sólo la primera: el día y la"
            " hora nuevos, y que su cita anterior ya quedó cancelada y no tiene que"
            " hacer nada con ella. Si sólo confirmas la nueva, se queda sin saber si"
            " sigue teniendo la vieja."
        )
    return (
        f"Cita agendada y confirmada para {label}. Confírmaselo al paciente con"
        " naturalidad, diciéndole el día y la hora. No le pidas que entre a ningún"
        " enlace ni que rellene nada: ya está hecho."
    )


async def agendar_cita(
    booking: BookingService,
    key: ContactKey,
    slot: CalendarSlot,
    now: datetime,
    timezone: str,
) -> str:
    if not is_bookable(Slot(slot.start_utc, slot.end_utc), now, BOOKING_BUFFER):
        return EXPIRED
    movida = bool(booking.scheduled_for(key))
    try:
        reservado = await booking.book_for_contact(key, slot)
    except SlotTakenError:
        return TAKEN
    label = slot_label(Slot(reservado, reservado), ZoneInfo(timezone), now)
    return confirmed(label, movida)
