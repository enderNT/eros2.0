"""Ensamblar contexto: hidrata el perfil desde el store (T10 · V6)."""

import logging

from ..state import State
from ..store import get_store

log = logging.getLogger(__name__)

_PERFIL_VACIO = {"identidad": {}, "memoria_larga": {"citas_previas": 0, "ultima_cita": None}}


def ensamblar_contexto(state: State) -> dict:
    """Hidrata `perfil` fresco desde el store por user_id (V6).

    El checkpoint solo guarda user_id (ADR 0002). El recordatorio de estado se
    arma en el ensamblado del prompt (prompt.py), no aquí.
    """
    user_id = state.get("meta", {}).get("user_id")
    perfil = get_store().get_perfil(user_id) if user_id else dict(_PERFIL_VACIO)
    log.debug("perfil hidratado para %s", user_id)
    return {"perfil": perfil}
