"""Parseo y deduplicación de webhooks de Chatwoot.

Separado de app.py para ser importable en tests sin arrastrar FastAPI/LangGraph.
"""

import logging
from collections import OrderedDict
from typing import Optional

log = logging.getLogger(__name__)

# Deduplicación: últimos 500 message_ids procesados (FIFO).
# Chatwoot puede disparar el mismo webhook dos veces ante reconexiones o reintentos.
_seen_ids: OrderedDict = OrderedDict()
_SEEN_MAX = 500


def _ya_procesado(msg_id) -> bool:
    """True si ya procesamos este message_id (y lo registra si es nuevo)."""
    if msg_id is None:
        return False
    if msg_id in _seen_ids:
        return True
    _seen_ids[msg_id] = True
    if len(_seen_ids) > _SEEN_MAX:
        _seen_ids.popitem(last=False)
    return False


def _coerce_bot(v) -> bool:
    if isinstance(v, str):
        return v.strip().lower() not in ("false", "0", "no", "off")
    return bool(v)


def parse_evento(payload: dict) -> Optional[dict]:
    """Extrae los campos relevantes de un message_created entrante de Chatwoot.

    Devuelve None para:
    - Eventos que no son message_created
    - Mensajes salientes (message_type 1/"outgoing") → evita el bucle bot→webhook→bot
    - Mensajes de agentes o bots (sender.type agent/agent_bot) → segunda capa anti-bucle
      (Chatwoot puede mandar el echo del bot con message_type=0 en algunos canales)
    - Notas privadas (private=True) → no son mensajes del cliente
    - IDs ya procesados → deduplicación ante webhooks duplicados de Chatwoot
    """
    if payload.get("event") != "message_created":
        return None

    # Capa 1: message_type 0/"incoming" = del cliente; 1/"outgoing" = del bot/agente
    if payload.get("message_type") not in ("incoming", 0, "0"):
        return None

    # Capa 2: notas privadas entre agentes
    if payload.get("private"):
        return None

    # Capa 3: remitente agente/bot — segunda barrera anti-bucle independiente del message_type
    sender = payload.get("sender", {}) or {}
    if sender.get("type") in ("agent", "agent_bot"):
        return None

    conv = payload.get("conversation", {}) or {}
    # El API de mensajes de Chatwoot usa el display_id, no el id global.
    conv_id = conv.get("display_id") or conv.get("id")
    if conv_id is None:
        return None

    # Capa 4: deduplicación por message_id
    msg_id = payload.get("id")
    if _ya_procesado(msg_id):
        log.info("webhook duplicado ignorado (message_id=%s)", msg_id)
        return None

    bot_activo = (conv.get("custom_attributes", {}) or {}).get("bot_activo", True)
    return {
        "conversation_id": conv_id,
        "message_id": msg_id,
        "texto": payload.get("content") or "",
        "user_id": str(sender.get("id") or conv_id),
        "bot_activo": _coerce_bot(bot_activo),
    }
