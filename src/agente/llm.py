"""Cliente Anthropic + helpers de salida estructurada (compartidos por nodos LLM)."""

import logging
from functools import lru_cache
from typing import Literal, Optional, Type, TypeVar

from pydantic import BaseModel

from .config import settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# --- Esquemas de salida estructurada -----------------------------------------

class Clasificacion(BaseModel):
    """Salida del Supervisor (V8)."""

    intencion: Literal["faq", "agendar", "conversacion", "handoff"]
    motivo: str


class ChequeoCrisis(BaseModel):
    """Salida del chequeo de crisis (V2)."""

    crisis: bool
    motivo: str


class SlotExtraido(BaseModel):
    """Slot concreto extraído de un mensaje (V10)."""

    encontrado: bool
    start_time: Optional[str] = None  # ISO 8601 UTC


# --- Cliente + parse genérico ------------------------------------------------

@lru_cache(maxsize=1)
def get_client():
    """Cliente Anthropic, o None si no hay API key (los nodos caen al fallback)."""
    if not settings.anthropic_api_key:
        return None
    import anthropic

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _parse(model: str, system: str, contexto: str, schema: Type[T], max_tokens: int = 256) -> Optional[T]:
    """Llama con salida estructurada. None si no hay key o si falla (caller usa fallback)."""
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.messages.parse(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": contexto}],
            output_format=schema,
        )
        return resp.parsed_output
    except Exception as e:  # noqa: BLE001 — degradar a fallback, nunca tumbar el grafo
        log.warning("_parse(%s) falló, usando fallback: %s", schema.__name__, e)
        return None


# --- Wrappers por tarea ------------------------------------------------------

def clasificar_intencion(system: str, contexto: str) -> Optional[Clasificacion]:
    return _parse(settings.model_supervisor, system, contexto, Clasificacion)


def detectar_crisis(system: str, contexto: str) -> Optional[ChequeoCrisis]:
    return _parse(settings.model_crisis, system, contexto, ChequeoCrisis)


def extraer_slot_llm(system: str, contexto: str) -> Optional[SlotExtraido]:
    return _parse(settings.model_supervisor, system, contexto, SlotExtraido)


def generar(system_blocks: list, messages: list, model: str, max_tokens: int = 1024) -> Optional[str]:
    """Respuesta libre (no estructurada). None si no hay key o falla."""
    client = get_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=model, max_tokens=max_tokens, system=system_blocks, messages=messages
        )
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    except Exception as e:  # noqa: BLE001
        log.warning("generar falló: %s", e)
        return None
