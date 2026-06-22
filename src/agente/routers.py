"""Aristas condicionales del grafo (ver docs/grafo.md).

Los routers solo leen el state y devuelven el nombre del siguiente nodo;
nunca mutan el state.
"""

from langgraph.graph import END

from .state import State


def r_bot_activo(state: State) -> str:
    """off → END (ignorar) | on → chequeo_crisis."""
    return "chequeo_crisis" if state.get("meta", {}).get("bot_activo", True) else END


def r_crisis(state: State) -> str:
    """crisis → handoff | no → ensamblar_contexto."""
    return "handoff" if state.get("meta", {}).get("crisis") else "ensamblar_contexto"


def r_intencion(state: State) -> str:
    """faq/agendar/conversacion → su agente | handoff → handoff."""
    intencion = state.get("ruteo", {}).get("intencion", "conversacion")
    return {
        "faq": "agente_faq",
        "agendar": "agente_citas",
        "conversacion": "agente_conversacion",
        "handoff": "handoff",
    }.get(intencion, "agente_conversacion")


def r_resultado(state: State) -> str:
    """resuelto → enviar | fuera_de_alcance | pide_humano → handoff."""
    resultado = state.get("salida", {}).get("resultado", "resuelto")
    return "enviar" if resultado == "resuelto" else "handoff"
