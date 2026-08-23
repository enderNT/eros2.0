"""C16 — El seguimiento tras el silencio, apagado desde el panel.

Documentado en `evals/casos/C16-seguimiento-apagado.md`.

C01 mide que el seguimiento salga. Éste mide lo contrario, que es una conducta
distinta y no la negación trivial de la otra: una clínica que no quiere que el
bot escriba por su cuenta tiene que poder apagarlo, y apagado tiene que
significar *nada*, no "más tarde".

El apagado se hace **después** de armar el aviso, a propósito. Es el caso que de
verdad puede fallar: no encolar cuando está apagado es fácil; lo difícil es que
lo ya encolado no salga, ni al vencer ni al volver a encender. Por eso el
interruptor se mueve por la ruta del panel y no escribiendo el ajuste a mano —
vaciar la cola es parte de apagar, y un caso que se salte la ruta no lo vería.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from evals.harness import Report, cerrar, world

CASO = "C16"
SEGUIMIENTO_MIN = 1


async def test_seguimiento_de_interes_apagado_no_escribe() -> None:
    reporte = Report(
        CASO,
        "Seguimiento tras el silencio, apagado",
        ajustes={"seguimiento de interés": f"{SEGUIMIENTO_MIN} min, luego APAGADO"},
    )
    async with world("C16-seguimiento-apagado", debounce_seconds=1.0) as w:
        w.set_interest_followup_minutes(SEGUIMIENTO_MIN)

        await w.say("hola, quería preguntar por terapia individual")
        await w.say("y cuánto cuesta la primera consulta?")

        armado = w.state()
        reporte.criterio(
            1,
            "Con el interruptor encendido, el seguimiento quedó programado",
            len(armado.seguimientos_interes) == 1,
            esperado=True,
            nota=(
                "Precondición del caso. Si aquí no hay nada, lo que venga después no"
                " demuestra que el interruptor haga algo: demuestra que nunca hubo aviso."
            ),
        )

        # El panel apaga la conducta. La persona ya se había callado.
        await w.set_interest_followup_enabled(False)

        tras_apagar = w.state()
        reporte.criterio(
            2,
            "Apagarlo vació lo que ya estaba en cola",
            not [item for item in tras_apagar.seguimientos_interes if not item.sent],
            esperado=True,
            nota=(
                "Si la fila sobreviviera, volver a encender el interruptor un mes después"
                " soltaría de golpe un '¿sigues por ahí?' a quien se calló en marzo."
            ),
        )

        antes = len(w.channel.sent)
        salidas = await w.fire_due(at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 3))
        reporte.criterio(
            3,
            "Pasado el plazo, no salió ningún mensaje",
            len(salidas) == 0,
            esperado=True,
            nota=f"salieron {len(salidas)} mensaje(s) con el seguimiento apagado",
        )

        # Y sigue apagado aunque el bot vuelva a hablar: no se rearma solo.
        await w.say("perdón, se me fue el santo al cielo")
        rearmado = w.state()
        reporte.criterio(
            4,
            "Una nueva respuesta del bot tampoco vuelve a armarlo",
            not [item for item in rearmado.seguimientos_interes if not item.sent],
            esperado=True,
            nota=(
                "Apagado tiene que dejar de encolar, no sólo dejar de mandar. Si se"
                " rearmara, bastaría con encenderlo un momento para que saliera todo."
            ),
        )

        salidas_finales = await w.fire_due(
            at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 6)
        )
        reporte.criterio(
            5,
            "Tampoco sale nada en el segundo vencimiento",
            len(salidas_finales) == 0,
            esperado=True,
        )
        assert len(w.channel.sent) >= antes  # el bot sí contesta; lo que no hace es perseguir

        cerrar(reporte, w)
