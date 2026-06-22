"""Herramientas del agente: ver_horarios, agendar_cita, escalar_a_humano.

El esquema (TOOLS) se manda al modelo; los ejecutores corren la acción real y
devuelven un texto que el modelo lee como tool_result. Aquí viven las garantías
duras: una cita solo se da por hecha si Calendly devolvió `ok` (antes V3).
"""

import json
import logging
from datetime import datetime, timedelta
from datetime import timezone as _tz

from .calendly import get_calendly
from .chatwoot import get_chatwoot
from .config import settings
from .store import get_store

log = logging.getLogger(__name__)


# --- Esquemas (lo que ve el modelo) ------------------------------------------

TOOLS = [
    {
        "name": "ver_horarios",
        "description": (
            "Devuelve horarios disponibles para la cita de valoración en los próximos "
            "días. Úsalo SIEMPRE antes de proponer un horario; nunca inventes horarios."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": "Ventana en días hacia adelante (máx 7). Por defecto 7.",
                }
            },
        },
    },
    {
        "name": "agendar_cita",
        "description": (
            "Reserva la cita de valoración en Calendly. Solo puedes afirmar que la cita "
            "quedó agendada si esta herramienta devuelve status 'ok'. Requiere un horario "
            "concreto tomado de ver_horarios."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre completo del paciente."},
                "correo": {"type": "string", "description": "Correo del paciente."},
                "slot": {
                    "type": "string",
                    "description": "Horario elegido en ISO 8601 UTC (ej. 2026-07-01T18:00:00Z), de los que devolvió ver_horarios.",
                },
                "asunto": {
                    "type": "string",
                    "description": "Motivo breve de la consulta (opcional).",
                },
            },
            "required": ["nombre", "correo", "slot"],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Transfiere la conversación a una persona del equipo y apaga el bot en este "
            "chat. Úsalo cuando lo pidan, cuando la duda exceda tu información, o ante "
            "molestia/casos especiales. Tras llamarla, despídete con calidez."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "motivo": {"type": "string", "description": "Por qué se escala (breve)."}
            },
        },
    },
]


# --- Ejecutores --------------------------------------------------------------

def _ver_horarios(args: dict, ctx: dict) -> str:
    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return json.dumps({"error": "agenda no configurada", "horarios": []})
    dias = min(int(args.get("dias", 7) or 7), 7)
    ahora = datetime.now(_tz.utc)
    try:
        slots = cal.available_times(
            settings.calendly_event_type,
            ahora.strftime("%Y-%m-%dT%H:%M:%SZ"),
            (ahora + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("ver_horarios falló: %s", e)
        return json.dumps({"error": "no pude consultar la agenda ahora", "horarios": []})
    horarios = [s["start_time"] for s in slots if s.get("start_time")][:8]
    return json.dumps({"horarios": horarios, "zona": settings.calendly_timezone})


def _agendar_cita(args: dict, ctx: dict) -> str:
    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return json.dumps({"status": "error", "detalle": "agenda no configurada"})

    res = None
    for _ in range(2):  # un reintento ante error técnico transitorio
        res = cal.crear_invitee(
            event_type=settings.calendly_event_type,
            start_time=args["slot"],
            nombre=args["nombre"],
            correo=args["correo"],
            timezone=settings.calendly_timezone,
            location_kind=settings.calendly_location_kind,
            asunto=args.get("asunto"),
        )
        if res.status != "error":
            break

    if res.status == "ok":
        # Memoria larga determinista: +1 cita para este usuario.
        user_id = ctx.get("user_id")
        if user_id:
            try:
                get_store().registrar_cita(user_id, args["slot"])
            except Exception as e:  # noqa: BLE001
                log.warning("registrar_cita falló: %s", e)
        return json.dumps({"status": "ok", "slot": args["slot"]})
    if res.status == "slot_taken":
        return json.dumps({"status": "slot_taken", "detalle": "ese horario se ocupó"})
    return json.dumps({"status": "error", "detalle": res.detail[:200]})


def _escalar_a_humano(args: dict, ctx: dict) -> str:
    """Apaga el bot en la conversación (Chatwoot custom attribute). Marca el side-effect
    en ctx para que el orquestador no reactive el bot en este turno."""
    ctx["escalado"] = True
    conv = ctx.get("conversation_id")
    cw = get_chatwoot()
    if cw and conv is not None:
        try:
            cw.set_atributo(conv, "bot_activo", False)
        except Exception as e:  # noqa: BLE001
            log.error("escalar_a_humano: set_atributo falló: %s", e)
    else:
        log.info("escalar_a_humano (local) motivo=%s", args.get("motivo"))
    return json.dumps({"status": "escalado"})


_EJECUTORES = {
    "ver_horarios": _ver_horarios,
    "agendar_cita": _agendar_cita,
    "escalar_a_humano": _escalar_a_humano,
}


def ejecutar_tool(nombre: str, args: dict, ctx: dict) -> str:
    """Despacha una herramienta por nombre. Devuelve siempre un string (tool_result)."""
    fn = _EJECUTORES.get(nombre)
    if fn is None:
        return json.dumps({"error": f"herramienta desconocida: {nombre}"})
    try:
        return fn(args or {}, ctx)
    except Exception as e:  # noqa: BLE001 — nunca tumbar el loop por una tool
        log.error("tool %s falló: %s", nombre, e)
        return json.dumps({"error": "fallo interno de la herramienta"})
