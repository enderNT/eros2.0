"""Agente Citas: máquina de estados de agendamiento (ADR 0001 · V3 · V10 · V11).

El grafo gobierna las transiciones; el LLM solo redacta y extrae el slot.
Nunca se marca CONFIRMADA sin un 2xx de Calendly `POST /invitees`.

Subestados: OFRECER_AUTOSERVICIO → RECOPILANDO → CONFIRMANDO → CONFIRMADA
            (+ ABANDONADA por descarte explícito)
"""

import logging
from datetime import datetime, timedelta
from datetime import timezone as _tz
from typing import Optional

from ..calendly import get_calendly
from ..config import settings
from ..llm import extraer_slot_llm
from ..state import State
from .util import ultimo_texto_usuario

log = logging.getLogger(__name__)

CAMPOS = ("nombre", "correo", "asunto")
PREGUNTAS = {
    "nombre": "¿A nombre de quién agendo la cita?",
    "correo": "¿Cuál es tu correo?",
    "asunto": "¿Cuál es el motivo de la consulta?",
}

SLOT_SYSTEM = (
    "Extrae un horario concreto de cita del mensaje del usuario y conviértelo a "
    "ISO 8601 UTC (terminado en Z). Si el mensaje no nombra un horario concreto "
    "agendable, encontrado=false. Zona horaria del usuario: {tz}."
)


# --- Helpers -----------------------------------------------------------------

def _extraer_slot(state: State) -> Optional[str]:
    """T5: el agente Citas extrae el start_time UTC del mensaje (no el Supervisor)."""
    res = extraer_slot_llm(
        SLOT_SYSTEM.format(tz=settings.calendly_timezone), ultimo_texto_usuario(state)
    )
    if res is None:
        return None
    return res.start_time if res.encontrado else None


def _es_descarte(texto: str) -> bool:
    t = texto.lower()
    return any(k in t for k in ("ya no", "olvíd", "olvid", "déjal", "dejal", "cancel"))


def _es_confirmacion(texto: str) -> bool:
    t = texto.lower().strip()
    return t in ("si", "sí", "ok", "va", "dale", "confirmo", "correcto") or t.startswith(
        ("si ", "sí ", "confirm", "de acuerdo")
    )


def _falta(tarea: dict) -> Optional[str]:
    """Siguiente dato faltante para poder reservar, o None si está completo."""
    datos = tarea.get("datos", {})
    for c in CAMPOS:
        if not datos.get(c):
            return c
    if not tarea.get("slot_elegido"):
        return "slot"
    return None


def _ofrecer_horarios(tarea: dict) -> str:
    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return "¿Qué día y hora te queda bien?"
    try:
        ahora = datetime.now(_tz.utc)
        slots = cal.available_times(
            settings.calendly_event_type,
            ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            (ahora + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("available_times falló: %s", e)
        return "¿Qué día y hora te queda bien?"
    opciones = [s.get("start_time") for s in slots[:3] if s.get("start_time")]
    if not opciones:
        return "No veo horarios disponibles esta semana, ¿te checo otra fecha?"
    # TODO: mapear "el primero/segundo" contra estas opciones; por ahora el usuario re-nombra el horario.
    return "Tengo estas opciones: " + ", ".join(opciones) + ". ¿Cuál prefieres?"


def _resp(tarea: dict, texto: str, resultado: str = "resuelto", meta: Optional[dict] = None) -> dict:
    out = {"tarea": tarea, "salida": {"texto": texto, "resultado": resultado}}
    if meta:
        out["meta"] = meta
    return out


def _pedir_siguiente(tarea: dict, prefijo: str = "") -> dict:
    """Pide el siguiente dato faltante, o pasa a CONFIRMANDO si está todo."""
    falta = _falta(tarea)
    if falta in CAMPOS:
        tarea["pidiendo"] = falta
        return _resp(tarea, (prefijo + " " + PREGUNTAS[falta]).strip())
    if falta == "slot":
        tarea["pidiendo"] = "slot"
        return _resp(tarea, (prefijo + " " + _ofrecer_horarios(tarea)).strip())
    # Completo → CONFIRMANDO
    tarea["subestado"] = "CONFIRMANDO"
    tarea["pidiendo"] = None
    d = tarea["datos"]
    resumen = (
        f"Te agendo el {tarea['slot_elegido']} a nombre de {d['nombre']} "
        f"({d['correo']}). ¿Confirmo?"
    )
    return _resp(tarea, resumen)


# --- Subestados --------------------------------------------------------------

def _recopilar(state: State, tarea: dict, texto: str) -> dict:
    pidiendo = tarea.get("pidiendo")
    if pidiendo == "slot":
        slot = _extraer_slot(state)
        if slot:
            tarea["slot_elegido"] = slot
    elif pidiendo in CAMPOS:
        tarea.setdefault("datos", {})[pidiendo] = texto.strip()
    return _pedir_siguiente(tarea)


def _confirmar(state: State, tarea: dict, texto: str) -> dict:
    if not _es_confirmacion(texto):
        # El usuario cambió algo → volver a recopilar (e intentar un slot nuevo).
        tarea["subestado"] = "RECOPILANDO"
        slot = _extraer_slot(state)
        if slot:
            tarea["slot_elegido"] = slot
        return _pedir_siguiente(tarea)

    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return _resp(tarea, "", "fuera_de_alcance", {"handoff_reason": "cortesia"})

    d = tarea["datos"]
    res = None
    for _ in range(2):  # reintento 1 vez ante error técnico
        res = cal.crear_invitee(
            event_type=settings.calendly_event_type,
            start_time=tarea["slot_elegido"],
            nombre=d["nombre"],
            correo=d["correo"],
            timezone=settings.calendly_timezone,
            location_kind=settings.calendly_location_kind,
            asunto=d.get("asunto"),
        )
        if res.status != "error":
            break

    if res.status == "ok":  # V3: única transición a CONFIRMADA
        tarea["subestado"] = "CONFIRMADA"
        msg = f"¡Listo! Tu cita quedó para el {tarea['slot_elegido']}."
        if res.cancel_url:
            msg += " Para cancelar o reagendar revisa tu correo."
        return _resp(tarea, msg)
    if res.status == "slot_taken":
        tarea["slot_elegido"] = None
        tarea["subestado"] = "RECOPILANDO"
        tarea["pidiendo"] = "slot"
        return _resp(tarea, "Ese horario se acaba de ocupar. " + _ofrecer_horarios(tarea))
    # error técnico persistente → handoff
    return _resp(tarea, "", "fuera_de_alcance", {"handoff_reason": "cortesia"})


# --- Nodo --------------------------------------------------------------------

def agente_citas(state: State) -> dict:
    tarea = dict(state.get("tarea", {}))
    tarea.setdefault("datos", {})
    texto = ultimo_texto_usuario(state)

    # ENTRADA: tarea nueva
    if not tarea.get("tipo"):
        tarea["tipo"] = "citas"
        slot = _extraer_slot(state)
        if slot:  # slot-directo → RECOPILANDO (sin link)
            tarea["slot_elegido"] = slot
            tarea["link_enviado"] = False
            tarea["subestado"] = "RECOPILANDO"
            return _pedir_siguiente(tarea, "Perfecto, déjame tomar tus datos.")
        # sin slot → OFRECER_AUTOSERVICIO (manda link)
        tarea["subestado"] = "OFRECER_AUTOSERVICIO"
        tarea["link_enviado"] = True
        link = settings.calendly_scheduling_link or "<<link de autoservicio — configurar>>"
        return _resp(tarea, f"Puedes agendar tú mismo aquí: {link}")

    # Descarte explícito en cualquier punto de una tarea activa
    if _es_descarte(texto):
        tarea["subestado"] = "ABANDONADA"
        return _resp(tarea, "Sin problema, aquí estoy si cambias de idea.")

    sub = tarea.get("subestado")
    if sub == "OFRECER_AUTOSERVICIO":
        # insiste / propone / "no vi horarios" → RECOPILANDO
        tarea["subestado"] = "RECOPILANDO"
        slot = _extraer_slot(state)
        if slot:
            tarea["slot_elegido"] = slot
        return _pedir_siguiente(tarea, "Con gusto te agendo.")
    if sub == "RECOPILANDO":
        return _recopilar(state, tarea, texto)
    if sub == "CONFIRMANDO":
        return _confirmar(state, tarea, texto)

    # CONFIRMADA / ABANDONADA: terminal (no debería re-entrar por sticky)
    return _resp(tarea, "Tu cita ya está registrada. ¿Algo más?")
