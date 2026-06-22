"""Supervisor: clasifica la intención y enruta (ADR 0004 · V8 · V11).

Camino normal: Haiku con salida estructurada. Si no hay API key o falla, cae a
un fallback determinista por palabras clave (para dev/test sin red). Recibe una
versión recortada del contexto (sin Wiki ni bloques de nodo) + la tarea activa.
"""

import logging
from typing import Tuple

from ..llm import clasificar_intencion
from ..state import State
from .util import ultimo_texto_usuario, ventana

log = logging.getLogger(__name__)

INTENCIONES = ("faq", "agendar", "conversacion", "handoff")

SUPERVISOR_SYSTEM = (
    "Eres el clasificador de un asistente de una clínica psicológica. "
    "Clasifica la intención del MENSAJE ACTUAL en exactamente una de: "
    "faq (pregunta factual: precios, horarios, ubicación, servicios), "
    "agendar (quiere o continúa una cita), "
    "conversacion (charla dentro del rol, sin tarea accionable), "
    "handoff (pide explícitamente un humano, o está fuera del alcance del asistente). "
    "Si hay una TAREA ACTIVA (p.ej. una cita en curso), por defecto clasifica para "
    "continuarla (agendar), salvo que el usuario claramente cambie de tema o pida un humano. "
    "'motivo' es una frase corta que justifica la elección."
)


def _tarea_activa(state: State) -> bool:
    t = state.get("tarea", {})
    return t.get("tipo") == "citas" and t.get("subestado") not in (
        None,
        "CONFIRMADA",
        "ABANDONADA",
    )


def _contexto_supervisor(state: State) -> str:
    """Contexto recortado: recientes + tarea activa + mensaje actual."""
    lineas = []
    msgs = ventana(state)
    if len(msgs) > 1:
        lineas.append("RECIENTES:")
        for m in msgs[:-1]:
            rol = (m.get("role") if isinstance(m, dict) else getattr(m, "type", "")) or ""
            txt = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
            lineas.append(f"- {rol}: {txt}")
    tarea_desc = (
        f"{state.get('tarea', {}).get('tipo')}/{state.get('tarea', {}).get('subestado')}"
        if _tarea_activa(state)
        else "ninguna"
    )
    lineas.append(f"TAREA ACTIVA: {tarea_desc}")
    lineas.append(f"MENSAJE ACTUAL: {ultimo_texto_usuario(state)}")
    return "\n".join(lineas)


def _heuristica(texto: str, state: State) -> Tuple[str, str]:
    """Fallback determinista. 'pide humano' sobre-escribe el sticky (V11)."""
    texto = texto.lower()
    if "humano" in texto or "persona" in texto or "asesor" in texto:
        return "handoff", "fallback: pide humano"
    if _tarea_activa(state):
        return "agendar", "fallback sticky: cita en curso"
    if any(k in texto for k in ("cita", "agendar", "agenda", "horario", "reserv")):
        return "agendar", "fallback: keyword agendar"
    if "?" in texto or any(
        k in texto for k in ("precio", "cuesta", "ubicaci", "donde", "dónde", "horarios")
    ):
        return "faq", "fallback: keyword faq"
    return "conversacion", "fallback: default"


def _validar(intencion: str) -> str:
    """V8: la intención siempre cae en el set permitido."""
    return intencion if intencion in INTENCIONES else "conversacion"


def supervisor(state: State) -> dict:
    clasif = clasificar_intencion(SUPERVISOR_SYSTEM, _contexto_supervisor(state))
    if clasif is not None:
        intencion, motivo = _validar(clasif.intencion), clasif.motivo
    else:
        intencion, motivo = _heuristica(ultimo_texto_usuario(state), state)
        intencion = _validar(intencion)
    log.info("ruteo: %s (%s)", intencion, motivo)
    return {"ruteo": {"intencion": intencion, "motivo": motivo}}
