"""C03 — Cancelación con horas de antelación, hecha por el bot.

Documentado en `evals/casos/C03-cancelacion.md`.

Antes este caso medía que el bot **no prometiera** cancelar lo que no podía
cancelar: no tenía herramienta y la cancelación sólo entraba por el correo de
Calendly. Con `cancel` en el puerto eso se invierte — el trabajo es del
asistente, no del paciente.

Pero cancelar es la primera acción irreversible que el bot puede tomar sobre una
cita real, así que el caso mide dos cosas a la vez y en este orden:

1. que **no** cancele con el primer mensaje, sino que pida confirmación;
2. que, confirmada, la cancelación ocurra de verdad y entera — cita, hueco,
   recordatorio y aviso.

Un bot que cancela a la primera aprueba la segunda mitad y reprueba la primera,
y eso es peor que no saber cancelar.
"""

from __future__ import annotations

from evals.harness import Report, caso_conversacional, cerrar, dice, rubric, world

CASO = "C03"


def pide_confirmacion_antes_de_cancelar():
    return rubric(
        "Pide confirmación antes de cancelar, y no da por hecho el destrozo",
        threshold=0.8,
        steps=[
            "Localiza el primer turno donde el paciente dice que quiere cancelar.",
            "Comprueba si el asistente confirma qué cita va a cancelar y pide un sí"
            " explícito, en vez de darla por cancelada de inmediato.",
            "Puntúa 0 si afirma que ya la canceló en ese primer turno.",
            "Puntúa 0 también si ignora la petición o la deriva sin más: puede hacerlo.",
            "Ofrecer reagendar en lugar de cancelar no es un fallo si además pregunta.",
        ],
    )


async def test_cancelacion_con_antelacion() -> None:
    reporte = Report(
        CASO, "Cancelación con horas de antelación", ajustes={"recordatorio": "60 min"}
    )
    async with world("C03-cancelacion", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        reserva = await w.preparar_cita_directa(en_minutos=360)
        reporte.criterio(
            0,
            "La cita de la precondición la reservó el propio sistema, sin enlace",
            reserva.por_el_sistema,
            esperado=True,
        )

        antes = w.state()
        reporte.criterio(
            1,
            "La precondición dejó una cita vigente y un recordatorio pendiente",
            len(antes.scheduled) == 1 and any(not r.sent for r in antes.reminders),
            esperado=True,
        )

        await w.say("necesito cancelar la cita de hoy")
        tras_pedir = w.state()
        reporte.criterio(
            2,
            "Con el primer mensaje todavía NO cancela: pide confirmación",
            len(tras_pedir.scheduled) == 1,
            esperado=True,
            nota=(
                "Cancelar es irreversible. Un 'creo que no voy a poder' no debe borrar"
                " una cita real; ver C13, que prueba justo ese caso ambiguo."
            ),
        )

        hasta_confirmar = len(w.exchanges)
        await w.say("sí, confírmalo, cancélala por favor")

        despues = w.state()
        reporte.criterio(
            3,
            "Confirmada, la cita queda cancelada",
            bool(despues.appointments)
            and all(cita.status == "canceled" for cita in despues.appointments),
            esperado=True,
            nota="El trabajo es del asistente: el paciente no debería tener que buscar"
            " un correo de Calendly para soltar su propia cita.",
        )
        reporte.criterio(
            4,
            "El recordatorio pendiente desapareció",
            not any(not r.sent for r in despues.reminders),
            esperado=True,
            nota="Si no, el paciente recibe el aviso de una cita muerta.",
        )
        reporte.criterio(
            5,
            "El hueco volvió a quedar libre en el calendario",
            None if w.ocupacion(reserva.slot_utc) is None else not w.ocupacion(reserva.slot_utc),
            esperado=True,
        )
        reporte.criterio(
            6,
            "El bot dijo en el chat que la cita quedó cancelada",
            any(dice(salida.text, "cancel") for salida in w.channel.sent[-3:]),
            esperado=True,
            nota="Cancelar sin decirlo deja al paciente creyendo que sigue teniendo cita.",
        )

        reporte.medir(
            pide_confirmacion_antes_de_cancelar(),
            caso_conversacional(
                w,
                hasta=hasta_confirmar,
                escenario=(
                    "Un paciente con cita confirmada para dentro de unas horas pide"
                    " cancelarla por WhatsApp."
                ),
                resultado_esperado=(
                    "El asistente confirma de qué cita se trata y pide un sí explícito"
                    " antes de cancelarla, sin darla por cancelada todavía."
                ),
            ),
        )
        cerrar(reporte, w)
