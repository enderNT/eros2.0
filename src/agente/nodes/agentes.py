"""Agentes simples de un paso: FAQ y Conversación (T6, T7).

Cada agente emite `salida = {texto, resultado}` con
resultado ∈ {resuelto, fuera_de_alcance, pide_humano} (ver ADR 0004).
Citas vive en nodes/citas.py.
"""

import logging

from ..config import settings
from ..llm import generar
from ..prompt import construir_prompt
from ..state import State

log = logging.getLogger(__name__)


def cargar_wiki() -> str:
    """Contenido de la Wiki (T16: la clínica lo llena)."""
    try:
        with open(settings.wiki_path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<<Wiki vacía — pendiente de contenido (T16)>>"


FAQ_BLOQUE_TMPL = (
    "Eres el módulo de preguntas frecuentes. Responde ÚNICAMENTE con información presente "
    "en la WIKI de abajo. Si la respuesta no está en la WIKI, dilo con naturalidad y ofrece "
    "conectar con el equipo humano; NO inventes nada.\n\n"
    "=== WIKI ===\n{wiki}\n=== FIN WIKI ==="
)

CONV_BLOQUE = (
    "Eres el módulo de conversación. Acompañas dentro del rol de asistente de clínica: "
    "cálido, breve y sin consejo clínico. No tienes una tarea accionable en este turno."
)


def agente_faq(state: State) -> dict:
    """Responde SOLO desde la Wiki; se abstiene + ofrece humano si falta (V4 / ADR 0005)."""
    bloque = FAQ_BLOQUE_TMPL.format(wiki=cargar_wiki())
    prompt = construir_prompt(state, bloque)
    texto = generar(prompt["system"], prompt["messages"], settings.model_agente)
    if texto is None:  # fallback sin API key
        texto = "Déjame confirmar ese dato con el equipo. ¿Quieres que te conecte con una persona?"
    return {"salida": {"texto": texto, "resultado": "resuelto"}}


def agente_conversacion(state: State) -> dict:
    """Continúa la conversación dentro del rol de asistente de clínica."""
    prompt = construir_prompt(state, CONV_BLOQUE)
    texto = generar(prompt["system"], prompt["messages"], settings.model_agente)
    if texto is None:  # fallback sin API key
        texto = "Aquí estoy para ayudarte. ¿En qué te puedo apoyar?"
    return {"salida": {"texto": texto, "resultado": "resuelto"}}
