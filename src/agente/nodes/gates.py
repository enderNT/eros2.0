"""Gates tempranos: bot_activo y chequeo de crisis.

Van antes de ensamblar contexto: un mensaje con bot off o en crisis no paga
el costo de hidratar perfil ni clasificar (V1, V2 / ADR 0003).
"""

import logging

from ..config import settings
from ..llm import detectar_crisis
from ..state import State
from .util import ultimo_texto_usuario

log = logging.getLogger(__name__)


def entrada(state: State) -> dict:
    """Lee `bot_activo` (atributo de conversación de Chatwoot) y datos del canal.

    El valor llega en el state inicial desde el webhook. El router `r_bot_activo`
    decide si seguir o ignorar.
    TODO: si no viene en el payload, consultarlo vía Chatwoot API.
    """
    meta = state.get("meta", {})
    return {"meta": {"bot_activo": meta.get("bot_activo", True)}}


CRISIS_SYSTEM = (
    "Eres un detector de señales de crisis en un asistente de una clínica psicológica. "
    "Indica crisis=true SOLO si el mensaje sugiere riesgo inminente: ideación o intención "
    "suicida, autolesión, o crisis aguda que requiere atención humana inmediata. "
    "Ante duda razonable de riesgo, prefiere crisis=true. 'motivo' es una frase corta."
)

# Red de seguridad para el fallback (sin API key): mejor sobre-escalar que omitir.
_SENALES = (
    "suicid",
    "matarme",
    "quitarme la vida",
    "no quiero vivir",
    "autolesion",
    "autolesión",
    "lastimarme",
    "hacerme daño",
    "acabar con todo",
)


def _fallback_crisis(texto: str) -> bool:
    t = texto.lower()
    return any(s in t for s in _SENALES)


def chequeo_crisis(state: State) -> dict:
    """Detección de crisis de alta prioridad (Haiku, salida estructurada).

    Si crisis → recursos predefinidos (settings.crisis_message) + handoff_reason=crisis.
    El router `r_crisis` enruta a handoff. Fallback por palabras clave sin API key.
    """
    texto = ultimo_texto_usuario(state)
    res = detectar_crisis(CRISIS_SYSTEM, texto)
    crisis = res.crisis if res is not None else _fallback_crisis(texto)

    update: dict = {"meta": {"crisis": crisis}}
    if crisis:
        update["meta"]["handoff_reason"] = "crisis"
        update["salida"] = {"texto": settings.crisis_message}
        log.warning("crisis detectada")
    return update
