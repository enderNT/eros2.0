"""C18 — Dos silencios en la misma conversación: ¿dos seguimientos?

Documentado en `evals/casos/C18-silencios-repetidos.md`.

C01 mide **un** silencio. Éste mide qué pasa cuando la misma persona se calla,
vuelve, y se calla otra vez — que es lo que de verdad hace la gente.

La respuesta esperada es que sí, que reciba otro. No hay ningún límite de
seguimientos por conversación, y este caso existe en buena parte para dejar esa
ausencia por escrito: si algún día se añade un tope, este caso se pone rojo y
alguien tiene que decidir a propósito cuál es el número, en vez de descubrirlo
cuando un paciente se queje de que lo persiguen.

Tres ramas, y lo que varía es la longitud de la conversación antes del primer
silencio. La frontera que importa no son los turnos sino la **compactación**: al
resumirse, el historial deja de ser la lista de mensajes y pasa a ser un resumen,
y merece la pena comprobar que el seguimiento sigue armándose y cancelándose
igual a los dos lados de esa línea. La rama corta se queda claramente por debajo,
la media ronda los 17 turnos que ya usa C02, y la larga los deja muy atrás.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from evals.harness import (
    Report,
    caso_conversacional,
    cerrar,
    dice,
    no_inventa,
    respuestas,
    world,
)

CASO = "C18"
SEGUIMIENTO_MIN = 1

# Preguntas reales de alguien que se está informando, no relleno: si el bot
# tuviera que contestar veinte veces lo mismo, la conversación larga mediría la
# paciencia del modelo en vez de la mecánica del seguimiento.
APERTURA = [
    "hola, buenas",
    "vengo buscando terapia individual",
    "es la primera vez que voy a terapia, ando con mucha ansiedad",
    "y cuánto cuesta la primera consulta?",
]
INFORMARSE = [
    "las sesiones son presenciales o también en línea?",
    "cuánto dura cada sesión?",
    "atienden los sábados?",
    "manejan algún paquete si voy varias semanas seguidas?",
    "dan factura?",
    "aceptan tarjeta o nada más efectivo?",
    "el psicólogo es hombre o mujer?",
    "tienen estacionamiento?",
    "y si un día no puedo, con cuánto tiempo tengo que avisar?",
    "trabajan también con adolescentes?",
    "hay que llevar algo a la primera sesión?",
    "cuánto tiempo suele durar un proceso así?",
    "hacen terapia de pareja también?",
    "dónde están exactamente?",
    "puedo cambiar de psicólogo si no me siento cómoda?",
    "guardan lo que uno dice o eso se comparte con alguien?",
    "cómo sé si de verdad necesito terapia?",
    "tienen algún descuento para estudiantes?",
    "cuánto se tarda en notar una mejora?",
    "y si me da pena hablar de ciertas cosas?",
]

RAMAS = [
    ("corta", 5),
    ("media", 17),
    ("larga", 24),
]


def _guion(turnos: int) -> list[str]:
    """`turnos` mensajes del paciente, sin repetir ninguno."""
    guion = APERTURA + INFORMARSE
    if turnos > len(guion):
        raise AssertionError(f"no hay material para {turnos} turnos distintos")
    return guion[:turnos]


@pytest.mark.lento
@pytest.mark.parametrize(("rama", "turnos"), RAMAS)
async def test_dos_silencios_dos_seguimientos(rama: str, turnos: int) -> None:
    reporte = Report(
        CASO,
        f"Silencios repetidos ({rama}, {turnos} turnos)",
        ajustes={"seguimiento tras el silencio": f"{SEGUIMIENTO_MIN} min"},
    )
    async with world(f"C18-{rama}", debounce_seconds=1.0) as w:
        w.set_interest_followup_minutes(SEGUIMIENTO_MIN)

        for mensaje in _guion(turnos):
            await w.say(mensaje)

        compactado = w.hubo_compactacion()
        reporte.criterio(
            0,
            f"La conversación de {turnos} turnos llegó a compactarse",
            compactado,
            esperado=None,
            nota=(
                "Informativo, no aprobado ni reprobado. La compactación depende del"
                " presupuesto de tokens, no del número de turnos, así que exigir un"
                " lado concreto convertiría este caso en un test del compactador."
                " Lo que se registra es a qué lado se midió esta rama:"
                f" {'compactó' if compactado else 'no compactó'}."
            ),
        )

        # --- primer silencio ---------------------------------------------------
        programado = w.state()
        reporte.criterio(
            1,
            "Tras el último mensaje quedó un seguimiento programado",
            len(programado.seguimientos_interes) == 1,
            esperado=True,
            nota=(
                f"Uno, no {turnos}: cada respuesta del bot reprograma el mismo aviso,"
                " así que el plazo cuenta desde lo último que se dijo."
            ),
        )

        primeras = await w.fire_due(at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 3))
        reporte.criterio(
            2,
            "Llegó exactamente un seguimiento tras el primer silencio",
            len(primeras) == 1,
            esperado=True,
            nota=f"salieron {len(primeras)} mensaje(s)",
        )

        # --- el paciente vuelve, y la conversación sigue ------------------------
        await w.say("perdón, se me fue el santo al cielo")
        await w.say("sí, me interesa, déjame lo pienso tantito")

        segundo_programado = w.state()
        reporte.criterio(
            3,
            "Al volver a hablar, se armó un seguimiento nuevo",
            len([item for item in segundo_programado.seguimientos_interes if not item.sent]) == 1,
            esperado=True,
            nota=(
                "Es la pregunta del caso. Hoy no hay tope de seguimientos por"
                " conversación, así que un segundo silencio merece un segundo aviso."
                " Si esto sale NO, alguien puso un límite sin escribirlo aquí."
            ),
        )

        # --- segundo silencio --------------------------------------------------
        segundas = await w.fire_due(at=datetime.now(UTC) + timedelta(minutes=SEGUIMIENTO_MIN * 3))
        reporte.criterio(
            4,
            "Llegó un segundo seguimiento tras el segundo silencio",
            len(segundas) == 1,
            esperado=True,
            nota=f"salieron {len(segundas)} mensaje(s) en el segundo vencimiento",
        )

        final = w.state()
        reporte.criterio(
            5,
            "El outbox quedó limpio: los dos avisos se consumieron al enviarse",
            not [item for item in final.seguimientos_interes if not item.sent],
            esperado=True,
        )
        reporte.criterio(
            6,
            "En total salieron dos seguimientos, ni uno más",
            len([item for item in final.seguimientos_interes if item.sent]) == 2,
            esperado=True,
            nota="Dos silencios, dos avisos. Un tercero sería el bot persiguiendo solo.",
        )
        reporte.criterio(
            7,
            "Ningún seguimiento inventa una cita que no existe",
            not any(
                dice(texto, "tu cita", "tu horario", "confirmada") for texto in primeras + segundas
            ),
            esperado=True,
        )
        reporte.criterio(
            8,
            "No se programó ningún recordatorio de cita",
            len(final.reminders) == 0,
            esperado=True,
            nota="Nunca hubo cita. Un recordatorio aquí significaría que se mezclaron.",
        )
        reporte.criterio(
            9,
            "Dio el precio de la valoración ($1,000 MXN) sin inventar cifras",
            dice(respuestas(w), "1000"),
            esperado=True,
            nota=(
                "El dato duro que se persigue de punta a punta: en las ramas largas"
                " se pregunta antes de compactar y tiene que sobrevivir al resumen."
            ),
        )

        reporte.medir(
            no_inventa(),
            caso_conversacional(
                w,
                escenario=(
                    "Alguien se informa sobre terapia individual, se calla sin agendar,"
                    " responde al mensaje con el que el asistente lo retoma, y vuelve a"
                    " callarse."
                ),
                resultado_esperado=(
                    "El asistente informa con datos reales, y escribe una vez tras cada"
                    " silencio para retomar la conversación sin presionar ni dar por"
                    " hecha ninguna cita."
                ),
            ),
        )
        cerrar(reporte, w)
