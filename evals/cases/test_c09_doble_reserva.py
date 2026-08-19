"""C09 — "Quiero cambiar mi cita": el hueco de la doble reserva.

Documentado en `evals/casos/C09-doble-reserva.md`.

El bot no sabe cancelar pero sí sabe agendar. Ante un "quiero moverla", el camino
de menor resistencia es crear una segunda cita y dejar la primera viva: dos
huecos bloqueados y, potencialmente, dos recordatorios al mismo paciente.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from evals.harness import Report, caso_conversacional, cerrar, rubric, world

CASO = "C09"


def avisa_de_la_cita_vieja():
    return rubric(
        "Avisa de que la cita anterior sigue en pie",
        threshold=0.7,
        steps=[
            "Localiza el turno donde el paciente pide mover su cita a otro día.",
            "Comprueba si el asistente advierte que la cita original sigue reservada y hay"
            " que cancelarla aparte, o si ofrece horarios nuevos como si la anterior"
            " desapareciera sola.",
            "Puntúa 1 sólo si el aviso es explícito antes o al mandar el enlace nuevo.",
        ],
    )


async def test_cambiar_la_cita_crea_una_segunda() -> None:
    reporte = Report(CASO, "Doble reserva al pedir cambio", ajustes={"recordatorio": "60 min"})
    async with world("C09-doble-reserva", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        primera_uri, primera = await w.preparar_cita(en_minutos=300)
        tokens_antes = len(w.state().tokens)

        nuevo = (datetime.now(UTC) + timedelta(minutes=600)).replace(second=0, microsecond=0)
        w.calendar.add_slot(nuevo)
        etiqueta = nuevo.astimezone(ZoneInfo(w.settings.calendly_timezone)).strftime("%H:%M")

        await w.say("puedo mover mi cita para otro día?")
        for _ in range(3):
            if len(w.state().tokens) > tokens_antes:
                break
            await w.say(f"sí, prefiero hoy a las {etiqueta}")

        # Igual que en la precondición: se reserva el horario del token que el bot
        # acabó emitiendo, no el que se pidió, para no fabricar incoherencias.
        segunda = nuevo
        if len(w.state().tokens) > tokens_antes:
            token, segunda = w.tokens()[0]
            await w.book(token=token, slot=segunda)

        estado = w.state()
        reporte.criterio(
            1,
            "Quedaron dos citas vigentes a la vez",
            len(estado.scheduled) == 2,
            esperado=True,
            nota=(
                "Hueco: cambiar de cita crea una segunda y deja viva la primera."
                f" Vigentes: {[c.slot_utc.isoformat() for c in estado.scheduled]}"
            ),
        )
        reporte.criterio(
            2,
            "Hay dos recordatorios pendientes para el mismo paciente",
            len([r for r in estado.reminders if not r.sent]) == 2,
            esperado=True,
            nota="Hueco: el paciente recibiría dos avisos de dos citas distintas.",
        )
        reporte.criterio(
            3,
            "Los dos huecos quedaron bloqueados en el calendario",
            w.calendar.is_booked(primera) and w.calendar.is_booked(segunda),
            esperado=True,
        )
        reporte.criterio(
            4,
            "El panel muestra la cita más temprana",
            bool(estado.scheduled) and estado.scheduled[0].slot_utc == min(primera, segunda),
            esperado=True,
            nota=(
                "`for_contact` ordena por `slot_utc`: el panel enseña la vieja, que suele"
                " ser justo la que el paciente quería abandonar."
            ),
        )
        assert primera_uri

        reporte.medir(
            avisa_de_la_cita_vieja(),
            caso_conversacional(
                w,
                escenario=(
                    "Un paciente con cita confirmada pide moverla a otro horario hablando"
                    " con el asistente."
                ),
                resultado_esperado=(
                    "El asistente ofrece el horario nuevo y advierte de que la cita"
                    " anterior sigue reservada y hay que cancelarla."
                ),
            ),
        )
        cerrar(reporte, w)
