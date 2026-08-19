"""C02 — Certificado ESA con desvíos: ¿reencarrila y aguanta 17 turnos?

Documentado en `evals/casos/C02-esa-larga.md`.

Dos cosas a la vez, porque en la vida real llegan juntas: que el asistente
devuelva la conversación a su cauce cuando el paciente se va por las ramas, y
que no se degrade en una conversación larga.

El tema es el certificado de animal de apoyo emocional, que sí está en la wiki
($2,000 MXN, cartilla de vacunación vigente, requisitos según aerolínea), así
que hay un dato duro que perseguir del principio al final.

Es el caso más caro del conjunto: 17 turnos son 17 llamadas al modelo de
conversación más 17 al clasificador de riesgo. Va marcado `lento`.
"""

from __future__ import annotations

import pytest

from evals.harness import (
    Report,
    caso_conversacional,
    cerrar,
    coherente,
    dice,
    no_inventa,
    reconduce,
    world,
)

CASO = "C02"

EN_TEMA = [
    "hola, me interesa el certificado para que mi perro pueda viajar conmigo en el avión",
    "qué incluye exactamente?",
    "cuánto cuesta?",
    "y cuánto tarda en salir?",
]
DESVIO_SUAVE = [
    "es un beagle, se llama Kiwi, lo adopté hace dos años y es mi todo",
    "los gatos también sirven para eso o nada más perros?",
    "oye y con ese papel puede entrar conmigo a restaurantes?",
    "qué opinas de los chalecos de servicio esos que venden en internet?",
]
DESVIO_DURO = [
    "sabes qué aerolínea es la más barata a Madrid?",
    "hace un calor horrible hoy, no?",
    "oye, eres una persona real o un bot?",
    "cuánto gana un psicólogo al mes más o menos?",
]
VUELTA = [
    "bueno, volviendo a lo del certificado",
    "necesito llevar algo del perro? papeles o algo",
    "me recuerdas cuánto era el costo?",
    "y sirve para cualquier aerolínea?",
    "perfecto, cómo le hago para empezar?",
]


@pytest.mark.lento
async def test_esa_con_desvios() -> None:
    reporte = Report(CASO, "ESA con desvíos, 17 turnos")
    async with world("C02-esa-larga", debounce_seconds=1.0) as w:
        for mensaje in EN_TEMA:
            await w.say(mensaje)
        primeros = "\n".join(i.reply for i in w.exchanges)

        for mensaje in DESVIO_SUAVE + DESVIO_DURO:
            await w.say(mensaje)
        for mensaje in VUELTA:
            await w.say(mensaje)
        ultimos = "\n".join(i.reply for i in w.exchanges[-5:])

        resumen = w.db.execute(
            "SELECT watermark_message_id FROM summary WHERE contact_phone = ?",
            (w.key.contact_phone,),
        ).fetchone()

        reporte.criterio(
            1,
            "Dio el costo de $2,000 MXN en los primeros turnos",
            dice(primeros, "2000"),
            esperado=True,
        )
        reporte.criterio(
            2,
            "Repitió el mismo costo al final, tras la compactación",
            dice(ultimos, "2000"),
            esperado=True,
            nota=(
                "Este es el criterio que mide la compactación: si el precio se pierde o"
                " cambia después del turno ~10, el resumen no conservó lo importante."
            ),
        )
        reporte.criterio(
            3,
            "Mencionó la cartilla de vacunación cuando se le preguntó por requisitos",
            dice(ultimos, "cartilla", "vacuna"),
            esperado=True,
        )
        reporte.criterio(
            4,
            "La conversación llegó a compactarse",
            resumen is not None,
            esperado=True,
            nota=(
                f"watermark: {resumen['watermark_message_id'] if resumen else 'sin resumen'}."
                " Si no compactó, el criterio 2 no probó lo que dice probar."
            ),
        )

        caso = caso_conversacional(
            w,
            escenario=(
                "Una persona interesada en el certificado ESA para su perro se va por las"
                " ramas durante ocho turnos y luego vuelve al trámite y repregunta el"
                " costo."
            ),
            resultado_esperado=(
                "El asistente reconduce con naturalidad, mantiene los datos del trámite"
                " sin contradecirse y termina explicando cómo empezar."
            ),
        )
        reporte.medir(reconduce(), caso)
        reporte.medir(coherente(), caso)
        reporte.medir(no_inventa(), caso)
        cerrar(reporte, w)
