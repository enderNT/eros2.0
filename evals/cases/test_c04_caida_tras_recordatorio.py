"""C04 — El paciente se cae después del recordatorio.

Documentado en `evals/casos/C04-caida-tras-recordatorio.md`.

El caso más caro de la vida real: el recordatorio ya salió y el paciente avisa
que no llega. Antes lo único que se podía medir era **cuánto tiempo quedaba un
hueco muerto bloqueado** y si el bot lo decía con claridad, porque nadie llamaba
a Calendly. Ahora el hueco se puede soltar, así que el listón sube: el asistente
tiene que ofrecerlo y, con el sí del paciente, hacerlo.

Se conservan las dos ramas. Que no exista un estado de "confirmado por el
paciente" sigue sin notarse en el código, y conviene seguir midiéndolo: soltar
el hueco de alguien que había confirmado y de alguien que nunca contestó
debería dar exactamente el mismo resultado.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from evals.harness import Report, caso_conversacional, cerrar, dice, rubric, world

CASO = "C04"
RECORDATORIO_MIN = 30


def ofrece_soltar_el_hueco():
    return rubric(
        "Ofrece liberar o mover la cita, en vez de sólo lamentarlo",
        threshold=0.7,
        steps=[
            "Localiza el turno donde el paciente avisa de que no va a poder asistir.",
            "Comprueba si el asistente ofrece encargarse él: cancelar la cita o moverla"
            " a otro horario, preguntando qué prefiere.",
            "Puntúa 0 si se limita a lamentarlo, si le pide al paciente que cancele por"
            " su cuenta, o si deja el asunto por resuelto sin hacer ni preguntar nada.",
            "Puntúa 0 también si afirma haberla cancelado sin que el paciente lo pidiera:"
            " avisar de que no se puede ir no es autorizar a borrar la cita.",
        ],
    )


@pytest.mark.parametrize(
    ("rama", "confirma"),
    [("A-confirma", True), ("B-silencio", False)],
)
async def test_se_cae_tras_el_recordatorio(rama: str, confirma: bool) -> None:
    reporte = Report(
        CASO,
        f"Caída tras el recordatorio ({rama})",
        ajustes={"recordatorio": f"{RECORDATORIO_MIN} min"},
    )
    async with world(f"C04-{rama}", debounce_seconds=1.0) as w:
        w.set_reminder_minutes(RECORDATORIO_MIN)
        reserva = await w.preparar_cita_directa(en_minutos=35)
        slot = reserva.slot_utc
        reporte.criterio(
            0,
            "La cita de la precondición la reservó el propio sistema, sin enlace",
            reserva.por_el_sistema,
            esperado=True,
        )

        salidas = await w.fire_due(at=slot - timedelta(minutes=RECORDATORIO_MIN - 1))
        reporte.criterio(
            1,
            "El recordatorio salió al vencer su hora",
            any("recordamos" in texto.lower() for texto in salidas),
            esperado=True,
            nota=f"{len(salidas)} mensaje(s) al disparar vencimientos",
        )
        reporte.criterio(
            "1b",
            "El recordatorio dice también dónde es, no sólo cuándo",
            any(dice(texto, "sócrates") for texto in salidas),
            esperado=True,
            nota=(
                "Es el mensaje que la persona tiene delante justo antes de salir de"
                " casa. Mandarla a buscar la dirección en el historial es hacerle"
                " trabajo que nos toca a nosotros."
            ),
        )

        if confirma:
            await w.say("sí, ahí estaré")
        await w.say("al final no voy a poder, me surgió algo")

        aviso = w.state()
        reporte.criterio(
            2,
            "Avisar no cancela por sí solo: la cita sigue vigente hasta el sí",
            len(aviso.scheduled) == 1,
            esperado=True,
            nota=(
                "'No voy a poder' no es 'cancélala'. El paciente puede querer moverla,"
                " y borrarle la cita por iniciativa propia es el daño nuevo que"
                " introduce tener `cancel`."
            ),
        )

        hasta_confirmar = len(w.exchanges)
        await w.say("sí, cancélala por favor")

        estado = w.state()
        reporte.criterio(
            3,
            "Con el sí explícito, la cita queda cancelada",
            bool(estado.appointments)
            and all(cita.status == "canceled" for cita in estado.appointments),
            esperado=True,
        )
        reporte.criterio(
            4,
            "El hueco se soltó y otro paciente puede tomarlo",
            None if w.ocupacion(slot) is None else not w.ocupacion(slot),
            esperado=True,
            nota="Éste es el dinero del caso: una hora de consulta recuperada en vez de"
            " un hueco muerto que nadie libera.",
        )

        repetidos = await w.fire_due(at=slot - timedelta(minutes=1))
        reporte.criterio(
            5,
            "No se disparó un segundo recordatorio",
            len(repetidos) == 0,
            esperado=True,
            nota="El outbox se consume al enviar: un duplicado sería un bug de idempotencia.",
        )
        reporte.criterio(
            6,
            "Hubo un solo recordatorio en total en el outbox",
            len([r for r in estado.reminders if r.sent]) == 1,
            esperado=True,
        )

        reporte.medir(
            ofrece_soltar_el_hueco(),
            caso_conversacional(
                w,
                hasta=hasta_confirmar,
                escenario=(
                    "El paciente recibe el recordatorio de su cita"
                    + (" y confirma que asistirá," if confirma else ", no contesta,")
                    + " y poco después avisa de que no va a poder ir."
                ),
                resultado_esperado=(
                    "El asistente se ofrece a cancelar o mover la cita él mismo y pregunta"
                    " qué prefiere el paciente, sin cancelarla todavía."
                ),
            ),
        )
        cerrar(reporte, w)
