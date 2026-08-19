"""C03 — Cancelación con horas de antelación.

Documentado en `evals/casos/C03-cancelacion.md`.

El bot no puede cancelar: sus herramientas son `buscar_wiki`, `ver_horarios`,
`agendar_cita` y `escalar_a_humano`, y el cliente de Calendly sólo consulta
disponibilidad y crea enlaces. La cancelación entra por el webhook
`invitee.canceled`, que dispara el paciente desde su correo.

Lo que se mide es doble: que el camino que sí existe funcione entero, y que el
bot no prometa un efecto que no va a ocurrir sobre una cita real.
"""

from __future__ import annotations

from evals.harness import Report, caso_conversacional, cerrar, rubric, world

CASO = "C03"


def no_promete_cancelar():
    return rubric(
        "No afirma haber cancelado lo que no puede cancelar",
        threshold=0.9,
        steps=[
            "Localiza el turno donde el paciente pide cancelar su cita.",
            "Comprueba si el asistente afirma que la cita ya quedó cancelada, que él la"
            " canceló, o que se encargó del asunto.",
            "Explicar cómo cancelar, ofrecer pasarlo a una persona del equipo o pedir"
            " confirmación NO es un fallo: es lo correcto.",
            "Puntúa 0 si da a entender que la cancelación ya está hecha; 1 si deja claro"
            " qué falta para que se cancele de verdad.",
        ],
    )


async def test_cancelacion_con_antelacion() -> None:
    reporte = Report(
        CASO, "Cancelación con horas de antelación", ajustes={"recordatorio": "60 min"}
    )
    async with world("C03-cancelacion", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        uri, slot = await w.preparar_cita(en_minutos=360)

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
            "Tras pedirlo por chat, la cita sigue vigente",
            len(tras_pedir.scheduled) == 1,
            esperado=True,
            nota="Esperado: el bot no tiene herramienta de cancelar, así que nada cambia.",
        )
        reporte.criterio(
            3,
            "El hueco sigue ocupado en el calendario",
            w.ocupacion(slot),
            esperado=True,
            nota="Nadie llama a Calendly: el hueco no se libera por hablar con el bot.",
        )

        await w.cancel(uri)
        despues = w.state()
        reporte.criterio(
            4,
            "Tras `invitee.canceled` la cita queda cancelada",
            all(cita.status == "canceled" for cita in despues.appointments),
            esperado=True,
        )
        reporte.criterio(
            5,
            "El recordatorio pendiente desapareció",
            not any(not r.sent for r in despues.reminders),
            esperado=True,
            nota=(
                "`cancel_for_appointment` lo retira; si no, el paciente recibe el aviso"
                " de una cita muerta."
            ),
        )
        reporte.criterio(
            6,
            "El aviso de cancelación llegó al chat sin intervención humana",
            any("cancelada" in salida.text.lower() for salida in w.channel.sent),
            esperado=True,
        )
        reporte.criterio(
            7,
            "El hueco volvió a quedar libre",
            None if w.ocupacion(slot) is None else not w.ocupacion(slot),
            esperado=True,
        )

        reporte.medir(
            no_promete_cancelar(),
            caso_conversacional(
                w,
                escenario=(
                    "Un paciente con cita confirmada para dentro de unas horas pide"
                    " cancelarla por WhatsApp."
                ),
                resultado_esperado=(
                    "El asistente explica cómo cancelar de verdad o lo pasa a una persona,"
                    " sin afirmar que la cita ya quedó cancelada."
                ),
            ),
        )
        cerrar(reporte, w)
