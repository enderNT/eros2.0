"""Cliente Anthropic + detección de crisis (pre-chequeo determinista).

La crisis se evalúa ANTES del loop del agente: un mensaje de riesgo no debe pasar
por el juicio conversacional del modelo, se escala directo (ADR 0003).
"""

import logging
from functools import lru_cache
from typing import Literal, Optional

from pydantic import BaseModel

from .config import settings
from .llm_logger import get_llm_logger, render_data_text, render_llm_request, render_llm_response

log = logging.getLogger(__name__)


# --- Cliente -----------------------------------------------------------------

@lru_cache(maxsize=1)
def get_client():
    """Cliente Anthropic, o None si no hay API key (los callers degradan)."""
    if not settings.anthropic_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


# --- Detección de crisis -----------------------------------------------------

class ChequeoCrisis(BaseModel):
    crisis: bool
    motivo: str


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
    t = (texto or "").lower()
    return any(s in t for s in _SENALES)


def detectar_crisis(texto: str, ctx: dict | None = None) -> bool:
    """True si el mensaje sugiere crisis. Haiku con salida estructurada; si no hay
    API key o falla, cae a palabras clave (sobre-escala por seguridad)."""
    client = get_client()
    ctx = ctx or {}
    if client is None:
        return _fallback_crisis(texto)
    try:
        request_text = render_llm_request(
            system=CRISIS_SYSTEM,
            messages=[{"role": "user", "content": texto or ""}],
        )
        resp = client.messages.parse(
            model=settings.model_crisis,
            max_tokens=128,
            system=CRISIS_SYSTEM,
            messages=[{"role": "user", "content": texto or ""}],
            output_format=ChequeoCrisis,
        )
        get_llm_logger().record(
            provider="anthropic",
            operation="messages.parse",
            model=settings.model_crisis,
            request_text=request_text,
            response_text=render_llm_response(resp),
            conversation_id=ctx.get("conversation_id"),
            flow_id=ctx.get("flow_id"),
            message_id=ctx.get("message_id"),
            stage="crisis_check",
            stage_label="Chequeo de crisis",
            stage_order=10,
            call_order=1,
            metadata={"purpose": "crisis_check", "incoming_text": ctx.get("incoming_text")},
        )
        out: Optional[ChequeoCrisis] = resp.parsed_output
        return out.crisis if out is not None else _fallback_crisis(texto)
    except Exception as e:  # noqa: BLE001
        log.warning("detectar_crisis falló, usando fallback: %s", e)
        if "request_text" in locals():
            get_llm_logger().record(
                provider="anthropic",
                operation="messages.parse",
                model=settings.model_crisis,
                request_text=request_text,
                response_text=str(e),
                status="error",
                conversation_id=ctx.get("conversation_id"),
                flow_id=ctx.get("flow_id"),
                message_id=ctx.get("message_id"),
                stage="crisis_check",
                stage_label="Chequeo de crisis",
                stage_order=10,
                call_order=1,
                metadata={"purpose": "crisis_check", "incoming_text": ctx.get("incoming_text")},
            )
        return _fallback_crisis(texto)


COMPACTION_SYSTEM = (
    "Resume de forma compacta el estado conversacional efímero de un chat de una "
    "clínica psicológica. Fusiona el resumen previo con los turnos nuevos. Conserva "
    "hechos concretos útiles para continuar: servicio en discusión, padecimiento "
    "mencionado, etapa del agendamiento, slot pedido o pendiente. NO repitas datos "
    "durables que pertenecen al perfil administrativo, como nombre, correo o citas "
    "confirmadas. No crezcas sin fin: máximo 8 bullets breves."
)


def compactar_historial(
    *,
    resumen_previo: str,
    turnos: list[dict],
    ctx: dict,
) -> str | None:
    """Genera un resumen rodante. None si no hay cliente o falla."""
    client = get_client()
    if client is None:
        return None

    messages = [
        {
            "role": "user",
            "content": (
                "Resumen previo:\n"
                f"{resumen_previo or '(vacío)'}\n\n"
                "Turnos a fusionar:\n"
                f"{render_data_text(turnos)}"
            ),
        }
    ]
    request_text = render_llm_request(system=COMPACTION_SYSTEM, messages=messages)
    try:
        resp = client.messages.create(
            model=settings.model_crisis,
            max_tokens=768,
            system=COMPACTION_SYSTEM,
            messages=messages,
        )
        response_text = render_llm_response(resp)
        get_llm_logger().record(
            provider="anthropic",
            operation="messages.create",
            model=settings.model_crisis,
            request_text=request_text,
            response_text=response_text,
            conversation_id=ctx.get("conversation_id"),
            flow_id=ctx.get("flow_id"),
            message_id=ctx.get("message_id"),
            stage="history_compaction",
            stage_label="Compactacion de historial",
            stage_order=50,
            call_order=1,
            metadata={"purpose": "history_compaction"},
        )
        return response_text.strip() or None
    except Exception as e:  # noqa: BLE001
        log.warning("compactar_historial falló: %s", e)
        get_llm_logger().record(
            provider="anthropic",
            operation="messages.create",
            model=settings.model_crisis,
            request_text=request_text,
            response_text=str(e),
            status="error",
            conversation_id=ctx.get("conversation_id"),
            flow_id=ctx.get("flow_id"),
            message_id=ctx.get("message_id"),
            stage="history_compaction",
            stage_label="Compactacion de historial",
            stage_order=50,
            call_order=1,
            metadata={"purpose": "history_compaction"},
        )
        return None
