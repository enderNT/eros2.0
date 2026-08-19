"""C01 — Interés que se enfría: ¿alguien vuelve a escribirle?

Documentado en `evals/casos/C01-seguimiento.md`.

Lo que este caso demuestra ya se sabe leyendo el código
(`BookingFollowups.schedule_from_outbound` sale sin hacer nada si el mensaje
saliente no llevaba enlace de reserva). El caso existe para dejar constancia con
una conversación real de que un interesado que sólo preguntó el precio no recibe
nunca nada, y para que el día que eso se implemente el caso falle y avise.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evals.harness import Report, caso_conversacional, cerrar, dice, no_inventa, respuestas, world

CASO = "C01"
SEGUIMIENTO_MIN = 1


async def test_interes_que_se_enfria() -> None:
    reporte = Report(
        CASO, "Interés que se enfría", ajustes={"seguimiento": f"{SEGUIMIENTO_MIN} min"}
    )
    async with world("C01-seguimiento", debounce_seconds=1.0) as w:
        w.set_followup_minutes(SEGUIMIENTO_MIN)

        await w.say("hola")
        await w.say("vengo buscando terapia individual")
        await w.say("es la primera vez que voy a terapia, ando con mucha ansiedad")
        await w.say("y cuánto cuesta la primera consulta?")

        # El paciente se calla. Se adelanta el vencimiento tres veces el plazo:
        # si hubiera algo programado, aquí saldría.
        antes = len(w.channel.sent)
        salidas = await w.fire_due(at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 3))
        estado = w.state()
        dicho = respuestas(w)

        reporte.criterio(
            1,
            "Dio el precio de la valoración ($1,000 MXN) sin inventar cifras",
            dice(dicho, "1000"),
            esperado=True,
        )
        reporte.criterio(
            2,
            "Ofreció agendar o dejó la puerta abierta en vez de cerrar en seco",
            dice(dicho, "agendar", "horarios", "cita", "te comparto"),
            esperado=True,
        )
        reporte.criterio(
            3,
            "Llegó algún mensaje de seguimiento tras el silencio",
            len(salidas) > 0,
            esperado=False,
            nota=(
                "HUECO-01: sin enlace de reserva no hay token, y sin token"
                " `schedule_from_outbound` no programa nada."
            ),
        )
        reporte.criterio(
            4,
            "Quedó algo programado en el outbox para este contacto",
            len(estado.outbox) > 0,
            esperado=False,
            nota="Confirma que el criterio 3 es por ausencia de programación, no por temporizador.",
        )
        assert len(w.channel.sent) == antes + len(salidas)

        reporte.medir(
            no_inventa(),
            caso_conversacional(
                w,
                escenario=(
                    "Alguien pregunta por terapia individual, llega hasta el precio y deja"
                    " de responder."
                ),
                resultado_esperado=(
                    "El asistente informa del precio real y ofrece agendar sin presionar."
                ),
            ),
        )
        cerrar(reporte, w)
