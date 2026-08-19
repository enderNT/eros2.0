"""C08 — F-WIKI: preguntar con palabras de paciente, no de índice.

Documentado en `evals/casos/C08-wiki.md`.

`Knowledge.find_sections` empareja los términos de la consulta contra los
**títulos** de sección, no contra el cuerpo. El agente sabe que debe consultar
por título, pero el paciente no escribe títulos. Este caso mide si esa distancia
se traduce en un "no encontré información" con el dato delante.
"""

from __future__ import annotations

from evals.harness import Report, cerrar, dice, world

CASO = "C08"

PREGUNTAS = [
    # (pregunta del paciente, sección real, señales de que el dato salió)
    ("cuánto me sale lo del papel para mi perrito del avión?", "ESA", ("2000",)),
    ("a qué hora abren?", "Horarios de atención", ("am", "a. m.", "lunes", "horario")),
    (
        "puedo pagar con tarjeta?",
        "Precios y formas de pago",
        ("tarjeta", "efectivo", "transferencia"),
    ),
]


async def test_recuperacion_con_palabras_de_paciente() -> None:
    reporte = Report(CASO, "F-WIKI: recuperación por título")
    async with world("C08-wiki", debounce_seconds=1.0) as w:
        for numero, (pregunta, seccion, señales) in enumerate(PREGUNTAS, start=1):
            intercambio = await w.say(pregunta)
            reporte.criterio(
                numero,
                f"Contesta con el dato de «{seccion}» ante: {pregunta}",
                dice(intercambio.reply, *señales),
                esperado=True,
                nota=f"herramientas: {', '.join(intercambio.tools) or 'ninguna'}",
            )
            reporte.criterio(
                numero + 10,
                f"No dice «no encontré información» teniendo el dato ({seccion})",
                not dice(intercambio.reply, "no encontre informacion", "no tengo esa informacion"),
                esperado=True,
            )
        cerrar(reporte, w)
