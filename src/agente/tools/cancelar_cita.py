"""Release the patient's appointment — deliberately in two steps.

Cancelling is the first irreversible thing this assistant can do to something
real. The worst calendar failure used to be *too many* appointments — a phantom
booking, a dead slot. It is now *too few*: an appointment deleted because a
model read "creo que no voy a poder llegar" as a decision, and a patient who
finds out at the clinic door.

So the tool refuses to cancel on its first call. It answers with the
appointment it would release and an instruction to go ask, and only cancels when
called again with `confirmado`. That does not make a model honest — it can set
the flag whenever it likes — but it removes the failure that needs no dishonesty
at all: cancelling because cancelling was the obvious next token.

The other half is doing nothing when there is nothing. Someone asking to cancel
an appointment they never had must hear that, not a confirmation.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..domain.contacts import ContactKey
from ..domain.scheduling import Slot, slot_label
from ..services.booking import BookingService

SIN_CITA = (
    "Este contacto NO tiene ninguna cita agendada, así que no hay nada que cancelar."
    " Díselo con claridad — no des por hecha una cita que no existe ni confirmes"
    " ninguna cancelación — y ofrécele agendar una o hablar con el equipo."
)
CANCELADA = "Cita cancelada: el horario de {label} quedó liberado. Confírmaselo al paciente."


def confirmar(label: str) -> str:
    return (
        f"NO se ha cancelado nada todavía. La cita de este paciente es {label}."
        " Pregúntale si quiere que la cancele y espera su respuesta. Sólo si dice"
        " que sí de forma clara, vuelve a llamar a esta herramienta con"
        " confirmado=true. Dudar sobre si podrá asistir NO es pedir una cancelación:"
        " si sólo expresa dudas, ofrécele cancelar o reagendar y espera."
    )


async def cancelar_cita(
    booking: BookingService,
    key: ContactKey,
    now: datetime,
    timezone: str,
    *,
    confirmado: bool = False,
    motivo: str = "",
) -> str:
    vigentes = booking.scheduled_for(key)
    if not vigentes:
        return SIN_CITA
    label = slot_label(Slot(vigentes[0].slot_utc, vigentes[0].slot_utc), ZoneInfo(timezone), now)
    if not confirmado:
        return confirmar(label)
    liberado = await booking.cancel_for_contact(key, reason=motivo or "cancelada por el paciente")
    if liberado is None:
        return SIN_CITA
    return CANCELADA.format(label=label)
