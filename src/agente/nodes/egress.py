"""Nodos de salida: enviar, persistir, handoff (T11, T12, T13)."""

import logging
from datetime import datetime, timezone

from ..chatwoot import get_chatwoot
from ..config import settings
from ..state import State
from ..store import get_store

log = logging.getLogger(__name__)


def enviar(state: State) -> dict:
    """Manda la respuesta al usuario por Chatwoot (T12)."""
    texto = state.get("salida", {}).get("texto", "")
    conv = state.get("meta", {}).get("conversation_id")
    cw = get_chatwoot()
    if not texto:
        log.info("enviar: sin texto, nada que mandar")
        return {}
    if cw is None:
        log.warning(
            "enviar: Chatwoot NO configurado (faltan CHATWOOT_BASE_URL/API_TOKEN/ACCOUNT_ID). "
            "Mensaje solo local → %s",
            texto,
        )
        return {}
    if conv is None:
        log.warning("enviar: sin conversation_id en el estado. Mensaje solo local → %s", texto)
        return {}
    try:
        cw.enviar_mensaje(conv, texto)
        log.info("enviar: mensaje enviado a conv=%s", conv)
    except Exception as e:  # noqa: BLE001
        log.error("enviar a Chatwoot falló (conv=%s): %s", conv, e)
    return {}


def persistir(state: State) -> dict:
    """Memoria larga por eventos (T11 · V5): CONFIRMADA → registra la cita."""
    tarea = state.get("tarea", {})
    if tarea.get("subestado") == "CONFIRMADA":
        user_id = state.get("meta", {}).get("user_id")
        fecha = tarea.get("slot_elegido") or datetime.now(timezone.utc).isoformat()
        if user_id:
            get_store().registrar_cita(user_id, fecha)
            log.info("memoria larga: +1 cita para %s", user_id)
    return {}


def handoff(state: State) -> dict:
    """Apaga el bot en la conversación y manda un mensaje (T13 · V7).

    Handoff = poner bot_activo=false (atributo de conversación en Chatwoot).
    El bot NO se reactiva solo; un humano cambia el valor externamente.
    """
    reason = state.get("meta", {}).get("handoff_reason") or "cortesia"
    if reason == "crisis":
        texto = state.get("salida", {}).get("texto") or settings.crisis_message
    else:
        texto = "Te conecto con alguien del equipo, en un momento te atienden 🙂"

    conv = state.get("meta", {}).get("conversation_id")
    cw = get_chatwoot()
    if cw and conv:
        try:
            if texto:
                cw.enviar_mensaje(conv, texto)
            cw.set_atributo(conv, "bot_activo", False)  # V7
        except Exception as e:  # noqa: BLE001
            log.error("handoff a Chatwoot falló: %s", e)
    else:
        log.info("HANDOFF (local, %s) → bot_activo=false", reason)

    return {"salida": {"texto": texto}, "meta": {"bot_activo": False}}
