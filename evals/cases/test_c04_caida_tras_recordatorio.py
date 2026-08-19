"""C04 — El paciente se cae después del recordatorio.

Documentado en `evals/casos/C04-caida-tras-recordatorio.md`.

El caso más caro de la vida real: el recordatorio ya salió y el paciente avisa
que no llega. Dos ramas, porque hoy no existe un estado de "confirmado por el
paciente" y conviene saber si esa ausencia se nota.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from evals.harness import Report, caso_conversacional, cerrar, rubric, world

CASO = "C04"
RECORDATORIO_MIN = 30


def explica_como_cancelar():
    return rubric(
        "Deja claro qué hay que hacer para liberar la cita",
        threshold=0.7,
        steps=[
            "Localiza el turno donde el paciente avisa de que no va a poder asistir.",
            "Comprueba si el asistente indica un camino concreto para cancelar o"
            " reagendar (el correo de Calendly, hablar con una persona del equipo), o si"
            " se limita a lamentarlo y dar el asunto por resuelto.",
            "Penaliza especialmente que dé a entender que ya está resuelto sin que el"
            " paciente tenga que hacer nada.",
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
        uri, slot = await w.preparar_cita(en_minutos=35)

        salidas = await w.fire_due(at=slot - timedelta(minutes=RECORDATORIO_MIN - 1))
        reporte.criterio(
            1,
            "El recordatorio salió al vencer su hora",
            any("recordamos" in texto.lower() for texto in salidas),
            esperado=True,
            nota=f"{len(salidas)} mensaje(s) al disparar vencimientos",
        )

        if confirma:
            await w.say("sí, ahí estaré")
        await w.say("al final no voy a poder, me surgió algo")

        estado = w.state()
        reporte.criterio(
            2,
            "La cita sigue vigente pese al aviso por chat",
            len(estado.scheduled) == 1,
            esperado=True,
            nota="Hueco: avisar al bot no cancela nada.",
        )
        reporte.criterio(
            3,
            "El hueco sigue bloqueado en el calendario",
            w.ocupacion(slot),
            esperado=True,
            nota="Hueco: nadie libera el horario, así que se pierde para otro paciente.",
        )

        repetidos = await w.fire_due(at=slot - timedelta(minutes=1))
        reporte.criterio(
            4,
            "No se disparó un segundo recordatorio",
            len(repetidos) == 0,
            esperado=True,
            nota="El outbox se consume al enviar: un duplicado sería un bug de idempotencia.",
        )
        reporte.criterio(
            5,
            "Hubo un solo recordatorio en total en el outbox",
            len([r for r in estado.reminders if r.sent]) == 1,
            esperado=True,
        )

        reporte.medir(
            explica_como_cancelar(),
            caso_conversacional(
                w,
                escenario=(
                    "El paciente recibe el recordatorio de su cita"
                    + (" y confirma que asistirá," if confirma else ", no contesta,")
                    + " y poco después avisa de que no va a poder ir."
                ),
                resultado_esperado=(
                    "El asistente reconoce el aviso y dice qué hace falta para liberar el"
                    " horario, sin dar por hecho que ya está cancelado."
                ),
            ),
        )
        cerrar(reporte, w)
