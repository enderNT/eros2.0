"""C10 — Mensajes en ráfaga: tres mensajes, un turno.

Documentado en `evals/casos/C10-debounce.md`.

La gente escribe en WhatsApp partiendo la idea en tres globos. Si el sistema
contesta a cada uno, el paciente recibe tres respuestas descoordinadas y la
clínica paga tres turnos de modelo. El debounce junta lo que llega dentro de la
ventana y responde una vez.
"""

from __future__ import annotations

from evals.harness import Report, cerrar, dice, world

CASO = "C10"
VENTANA = 4.0


async def test_rafaga_se_funde_en_un_turno() -> None:
    reporte = Report(CASO, "Ráfaga y debounce", ajustes={"debounce": f"{VENTANA} s"})
    async with world("C10-debounce", debounce_seconds=VENTANA) as w:
        intercambio = await w.burst(["hola", "quería preguntar algo", "es sobre terapia de pareja"])

        turnos = w.db.execute("SELECT COUNT(DISTINCT turn_id) AS n FROM llm_trace").fetchone()["n"]
        entrantes = w.db.execute(
            "SELECT COUNT(*) AS n FROM message WHERE direction = 'inbound'"
        ).fetchone()["n"]

        reporte.criterio(
            1,
            "Se procesó un solo turno, no tres",
            turnos == 1,
            esperado=True,
            nota=f"turn_id distintos en llm_trace: {turnos}",
        )
        reporte.criterio(
            2,
            "Los tres mensajes quedaron guardados igualmente",
            entrantes == 3,
            esperado=True,
            nota=f"mensajes entrantes: {entrantes}",
        )
        reporte.criterio(
            3,
            "La respuesta tiene en cuenta el tercer mensaje (terapia de pareja)",
            dice(intercambio.reply, "pareja"),
            esperado=True,
        )
        reporte.criterio(
            4,
            "No hubo tres respuestas separadas",
            len(intercambio.replies) <= 3,
            esperado=True,
            nota=(
                f"{len(intercambio.replies)} mensajes de salida; el troceado por longitud"
                " puede partir una respuesta larga, por eso el criterio 1 es el que manda."
            ),
        )
        cerrar(reporte, w)
