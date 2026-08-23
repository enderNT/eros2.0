"""C01 — Interés que se enfría: ¿alguien vuelve a escribirle?

Documentado en `evals/casos/C01-seguimiento.md`.

Este caso llevaba desde el principio documentando un hueco: quien preguntaba el
precio y se callaba no recibía nunca nada, porque el único seguimiento que
existía colgaba de un enlace de reserva que esa persona jamás llegó a recibir.

Ahora existe `InterestFollowups` y el caso pasa a exigirlo.

Lo que se mide no es sólo que llegue un mensaje: es que llegue **uno**, que sea
del tipo correcto, y que no se haya colado por el camino del recordatorio de
cita, que aquí no tiene nada que hacer.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evals.harness import Report, caso_conversacional, cerrar, dice, no_inventa, respuestas, world

CASO = "C01"
SEGUIMIENTO_MIN = 1


async def test_interes_que_se_enfria() -> None:
    reporte = Report(
        CASO, "Interés que se enfría", ajustes={"seguimiento de interés": f"{SEGUIMIENTO_MIN} min"}
    )
    async with world("C01-seguimiento", debounce_seconds=1.0) as w:
        w.set_interest_followup_minutes(SEGUIMIENTO_MIN)

        await w.say("hola")
        await w.say("vengo buscando terapia individual")
        await w.say("es la primera vez que voy a terapia, ando con mucha ansiedad")
        await w.say("y cuánto cuesta la primera consulta?")

        # Antes de que venza nada: lo programado tiene que estar ya ahí.
        programado = w.state()
        reporte.criterio(
            1,
            "Quedó un seguimiento de interés programado para este contacto",
            len(programado.seguimientos_interes) == 1,
            esperado=True,
            nota=(
                "Uno, no cuatro: cada respuesta del bot reprograma el mismo aviso en vez"
                " de encolar otro, así que el plazo cuenta desde lo último que se dijo."
            ),
        )
        reporte.criterio(
            2,
            "No se programó ningún recordatorio de cita",
            len(programado.reminders) == 0,
            esperado=True,
            nota=(
                "Los dos avisos comparten el outbox y nada más. Aquí no hay cita, así"
                " que un recordatorio significaría que se están mezclando."
            ),
        )

        # El paciente se calla. Se adelanta el vencimiento tres veces el plazo.
        antes = len(w.channel.sent)
        salidas = await w.fire_due(at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 3))
        estado = w.state()
        dicho = respuestas(w)

        reporte.criterio(
            3,
            "Llegó exactamente un mensaje de seguimiento tras el silencio",
            len(salidas) == 1,
            esperado=True,
            nota=f"salieron {len(salidas)} mensaje(s) al disparar vencimientos",
        )
        reporte.criterio(
            4,
            "El seguimiento retoma el contacto sin inventar una cita que no existe",
            bool(salidas) and not dice(salidas[0], "tu cita", "tu horario", "confirmada"),
            esperado=True,
            nota=(
                "A quien no llegó a agendar no se le puede preguntar '¿pudiste agendar tu"
                " cita para las 4?': no hay ninguna a la que referirse."
            ),
        )
        reporte.criterio(
            5,
            "El outbox quedó limpio: el aviso se consume al enviarse",
            not [item for item in estado.seguimientos_interes if not item.sent],
            esperado=True,
            nota="Si quedara pendiente, la persona recibiría el mismo mensaje otra vez.",
        )
        reporte.criterio(
            6,
            "Dio el precio de la valoración ($1,000 MXN) sin inventar cifras",
            dice(dicho, "1000"),
            esperado=True,
        )
        reporte.criterio(
            7,
            "Ofreció agendar o dejó la puerta abierta en vez de cerrar en seco",
            dice(dicho, "agendar", "horarios", "cita", "te comparto"),
            esperado=True,
        )
        assert len(w.channel.sent) == antes + len(salidas)

        reporte.medir(
            no_inventa(),
            caso_conversacional(
                w,
                escenario=(
                    "Alguien pregunta por terapia individual, llega hasta el precio y deja"
                    " de responder. Un rato después, el asistente retoma el contacto."
                ),
                resultado_esperado=(
                    "El asistente informa del precio real, ofrece agendar sin presionar y,"
                    " tras el silencio, escribe una vez para retomar la conversación."
                ),
            ),
        )
        cerrar(reporte, w)
