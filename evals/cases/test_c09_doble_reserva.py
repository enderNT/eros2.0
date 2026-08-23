"""C09 — "Quiero cambiar mi cita": que mover no signifique duplicar.

Documentado en `evals/casos/C09-doble-reserva.md`.

Este caso cambió de signo. Cuando el bot sólo sabía mandar enlaces, el camino de
menor resistencia ante un "quiero moverla" era crear una segunda cita y dejar la
primera viva, y el caso **documentaba** ese hueco: esperaba dos citas. Con un
calendario en el que se puede escribir, reagendar es cancelar y volver a
reservar, así que ahora exige lo contrario — una sola cita, la nueva, y el hueco
viejo libre.

Mientras `agendar_cita` siga entregando enlaces, los criterios 2 y 4 dan NO. Ese
es el rojo que se busca: dice exactamente qué falta.
"""

from __future__ import annotations

from evals.harness import Report, caso_conversacional, cerrar, rubric, world

CASO = "C09"


def confirma_el_cambio_sin_dejar_cabos():
    return rubric(
        "Confirma el horario nuevo y deja claro que el viejo se soltó",
        threshold=0.7,
        steps=[
            "Localiza el turno donde el paciente pide mover su cita a otro día.",
            "Comprueba si el asistente confirma el horario nuevo y dice, explícita o"
            " implícitamente, que la cita anterior deja de estar reservada.",
            "Puntúa 0 si ofrece un horario nuevo dando a entender que el paciente tiene"
            " que cancelar el anterior por su cuenta, o si no menciona qué pasa con él.",
            "Puntúa 0 también si afirma haber movido la cita sin que conste el cambio.",
        ],
    )


async def test_mover_la_cita_no_deja_dos() -> None:
    reporte = Report(
        CASO, "Mover la cita sin dejar la vieja en pie", ajustes={"recordatorio": "60 min"}
    )
    async with world("C09-doble-reserva", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(60)
        reserva = await w.preparar_cita_directa(en_minutos=300)
        reporte.criterio(
            0,
            "La cita de la precondición la reservó el propio sistema, sin enlace",
            reserva.por_el_sistema,
            esperado=True,
            nota=(
                "Si da NO, `agendar_cita` sigue entregando enlaces y el arnés tuvo que"
                " simular la reserva por webhook: la causa de los criterios 2 y 4."
            ),
        )

        nuevo = await w.calendar.elegir_hueco(600)
        await w.say("puedo mover mi cita para otro día?")
        for _ in range(4):
            if w.state().scheduled and w.state().scheduled[0].slot_utc != reserva.slot_utc:
                break
            await w.say(f"sí, muévela {w.frase_horario(nuevo)} por favor")

        estado = w.state()
        vigentes = estado.scheduled
        reporte.criterio(
            1,
            "Quedó exactamente una cita vigente",
            len(vigentes) == 1,
            esperado=True,
            nota=(
                "Ojo al leerlo: si el sistema no hizo nada, este criterio da SÍ por"
                " inacción. El que delata es el 2."
                f" Vigentes: {[c.slot_utc.isoformat() for c in vigentes]}"
            ),
        )
        reporte.criterio(
            2,
            "La cita vigente ya no es la del horario original",
            bool(vigentes) and vigentes[0].slot_utc != reserva.slot_utc,
            esperado=True,
            nota="Se compara contra el horario reservado, no contra el pedido: el modelo"
            " puede haber ofrecido otro hueco y da igual cuál, mientras cambie.",
        )
        reporte.criterio(
            3,
            "Hay un solo recordatorio pendiente",
            len([r for r in estado.reminders if not r.sent]) == 1,
            esperado=True,
            nota="Dos recordatorios significan dos avisos de dos citas al mismo paciente.",
        )
        reporte.criterio(
            4,
            "El hueco viejo volvió a quedar libre",
            None if w.ocupacion(reserva.slot_utc) is None else not w.ocupacion(reserva.slot_utc),
            esperado=True,
            nota="Un hueco muerto es una hora de consulta que nadie puede tomar.",
        )

        reporte.medir(
            confirma_el_cambio_sin_dejar_cabos(),
            caso_conversacional(
                w,
                escenario=(
                    "Un paciente con cita confirmada pide moverla a otro horario hablando"
                    " con el asistente."
                ),
                resultado_esperado=(
                    "El asistente mueve la cita: confirma el horario nuevo y deja claro"
                    " que el anterior queda liberado, sin pedirle al paciente que cancele"
                    " por su cuenta."
                ),
            ),
        )
        cerrar(reporte, w)
