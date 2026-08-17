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

The link carries an opaque `utm_content` token so the webhook can tell whose
booking came back. It is a random id, never the phone number: the URL leaves
our control the moment we send it.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlparse, urlunparse

from ..domain.contacts import ContactKey
from ..domain.scheduling import Slot, is_bookable
from ..ports.calendar import CalendarSlot
from ..ports.store import AppointmentsRepository, BookingTokensRepository

BOOKING_BUFFER = timedelta(minutes=10)
EXPIRED = "Ese horario ya no está disponible. Ofrece otro de los horarios vigentes."
ALREADY_BOOKED = "Este contacto ya tiene una cita confirmada en ese horario."
NO_LINK = "No tengo el enlace de ese horario. Ofrece otro o escala a una persona."


def link_instructions(url: str) -> str:
    """What the model reads after a successful handover.

    The "copy it whole" rule is not stylistic. The `utm_content` parameter is
    the only thing that tells the webhook whose booking came back; a model that
    tidies the URL by dropping the query string silently breaks attribution,
    and the failure is invisible — the patient books fine and we never learn.
    Observed happening, hence the emphasis.
    """
    return (
        f"Envíale este enlace EXACTO, copiado completo y sin modificar:\n{url}\n"
        "No lo acortes, no le quites nada después del signo '?', no lo reescribas"
        " ni lo pongas en un texto con formato de enlace. Si le quitas la parte"
        " final, la cita no se podrá asociar a este paciente.\n"
        "IMPORTANTE: la cita NO está agendada todavía. Ahí completa su nombre y correo."
        " No le digas que ya quedó confirmada; pídele que te avise cuando termine."
    )


def tracked_url(url: str, token: str) -> str:
    """Append `utm_content` without dropping whatever query the link already has."""
    parts = urlparse(url)
    query = f"{parts.query}&" if parts.query else ""
    return urlunparse(parts._replace(query=query + urlencode({"utm_content": token})))


async def agendar_cita(
    appointments: AppointmentsRepository,
    tokens: BookingTokensRepository,
    key: ContactKey,
    slot: CalendarSlot,
    now: datetime,
    *,
    make_token: Callable[[], str] = lambda: secrets.token_urlsafe(16),
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
    token = make_token()
    tokens.issue(token, key, slot.start_utc, now)
    return link_instructions(tracked_url(slot.booking_url, token))
