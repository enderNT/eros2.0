"""Herramientas del agente: ver_horarios, agendar_cita, escalar_a_humano.

El esquema (TOOLS) se manda al modelo; los ejecutores corren la acción real y
devuelven un texto que el modelo lee como tool_result. Aquí viven las garantías
duras: una cita solo se da por hecha si Calendly devolvió `ok` (antes V3).
"""

import json
import logging
import unicodedata
from datetime import datetime, timedelta
from datetime import timezone as _tz

from .calendly import get_calendly
from .chatwoot import get_chatwoot
from .config import settings
from .llm_logger import get_llm_logger, render_data_text
from .store import get_store

log = logging.getLogger(__name__)


# --- Esquemas (lo que ve el modelo) ------------------------------------------

TOOLS = [
    {
        "name": "buscar_wiki",
        "description": (
            "Busca información factual de la clínica (precios, horarios, servicios, "
            "ubicación, formas de pago, políticas) en la base de conocimiento. Úsala "
            "SIEMPRE que necesites un dato concreto; nunca inventes datos. Pasa palabras "
            "clave en 'consulta'. Devuelve solo las secciones relevantes. Si no hay "
            "coincidencias, devuelve el índice de secciones para que reformules."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Palabras clave del dato buscado, ej. 'precio valoración' u 'horarios polanco'.",
                }
            },
            "required": ["consulta"],
        },
    },
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

def _normaliza(s: str) -> str:
    """minúsculas + sin acentos, para comparar sin importar tildes."""
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _secciones_wiki() -> list[tuple[str, str]]:
    """Parte la wiki en (título, cuerpo) por encabezados markdown. Se relee en cada
    llamada: así editar wiki.md se refleja sin reiniciar, y escala a medida que crece."""
    try:
        with open(settings.wiki_path, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        return []
    secciones: list[tuple[str, str]] = []
    titulo, buf = "(intro)", []
    for linea in texto.splitlines():
        if linea.lstrip().startswith("#"):
            if any(l.strip() for l in buf):
                secciones.append((titulo, "\n".join(buf).strip()))
            titulo = linea.lstrip("#").strip() or "(sin título)"
            buf = [linea]
        else:
            buf.append(linea)
    if any(l.strip() for l in buf):
        secciones.append((titulo, "\n".join(buf).strip()))
    return secciones


def _buscar_wiki(args: dict, ctx: dict) -> str:
    """Devuelve hasta 3 secciones relevantes por solapamiento de palabras clave
    (título pesa más). Sin coincidencias → índice de secciones para reformular."""
    secciones = _secciones_wiki()
    if not secciones:
        return json.dumps({"error": "base de conocimiento no disponible", "resultados": []})

    indice = [t for t, _ in secciones]
    terminos = {w for w in _normaliza(args.get("consulta", "")).split() if len(w) > 2}
    if not terminos:
        return json.dumps({"indice": indice})

    puntuadas = []
    for titulo, cuerpo in secciones:
        cuerpo_norm = _normaliza(cuerpo)
        titulo_norm = _normaliza(titulo)
        score = sum(cuerpo_norm.count(w) for w in terminos)
        score += sum(3 for w in terminos if w in titulo_norm)  # coincidencia en título pesa más
        if score > 0:
            puntuadas.append((score, titulo, cuerpo))

    if not puntuadas:
        return json.dumps(
            {"resultados": [], "indice": indice, "nota": "sin coincidencias; reformula o revisa el índice"}
        )
    puntuadas.sort(key=lambda x: -x[0])
    top = [{"seccion": t, "contenido": c} for _, t, c in puntuadas[:3]]
    return json.dumps({"resultados": top})


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
                get_llm_logger().record(
                    provider="memory",
                    operation="memory.long.write",
                    model=None,
                    status="ok",
                    conversation_id=ctx.get("conversation_id"),
                    flow_id=ctx.get("flow_id"),
                    message_id=ctx.get("message_id"),
                    stage="long_memory_write",
                    stage_label="Escritura de memoria larga",
                    stage_order=35,
                    call_order=1,
                    request_text=render_data_text(
                        {
                            "user_id": user_id,
                            "memoria_a_guardar": {
                                "evento": "cita_confirmada",
                                "ultima_cita": args["slot"],
                                "incrementar_citas_previas": 1,
                            },
                            "origen": "tool.agendar_cita",
                        }
                    ),
                    response_text=render_data_text({"status": "ok", "guardado": True}),
                    metadata={"purpose": "memory.long.write", "tool": "agendar_cita"},
                )
            except Exception as e:  # noqa: BLE001
                log.warning("registrar_cita falló: %s", e)
                get_llm_logger().record(
                    provider="memory",
                    operation="memory.long.write",
                    model=None,
                    status="error",
                    conversation_id=ctx.get("conversation_id"),
                    flow_id=ctx.get("flow_id"),
                    message_id=ctx.get("message_id"),
                    stage="long_memory_write",
                    stage_label="Escritura de memoria larga",
                    stage_order=35,
                    call_order=1,
                    request_text=render_data_text(
                        {
                            "user_id": user_id,
                            "memoria_a_guardar": {
                                "evento": "cita_confirmada",
                                "ultima_cita": args["slot"],
                                "incrementar_citas_previas": 1,
                            },
                            "origen": "tool.agendar_cita",
                        }
                    ),
                    response_text=render_data_text({"status": "error", "error": str(e)}),
                    metadata={"purpose": "memory.long.write", "tool": "agendar_cita"},
                )
        _encolar_recordatorios(res, args, ctx)
        return json.dumps({"status": "ok", "slot": args["slot"]})
    if res.status == "slot_taken":
        return json.dumps({"status": "slot_taken", "detalle": "ese horario se ocupó"})
    return json.dumps({"status": "error", "detalle": res.detail[:200]})


def _encolar_recordatorios(res, args: dict, ctx: dict) -> None:
    """Crea las filas de recordatorio para una cita recién confirmada. Best-effort:
    cualquier fallo se registra pero no afecta la confirmación de la cita."""
    if not settings.recordatorio_enabled:
        return
    conv = ctx.get("conversation_id")
    if conv is None:
        return  # sin conversación no hay a dónde mandar el recordatorio
    try:
        from datetime import datetime

        from .recordatorios import leads_minutes

        slot_dt = datetime.fromisoformat(args["slot"].replace("Z", "+00:00"))
        n = get_store().crear_recordatorios(
            invitee_uri=getattr(res, "invitee_uri", None),
            event_uri=getattr(res, "event_uri", None),
            conversation_id=conv,
            user_id=ctx.get("user_id"),
            nombre=args.get("nombre"),
            correo=args.get("correo"),
            slot=slot_dt,
            leads_minutes=leads_minutes(),
        )
        log.info("recordatorios encolados: %s (conv=%s)", n, conv)
    except Exception as e:  # noqa: BLE001
        log.warning("encolar recordatorios falló: %s", e)


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
    "buscar_wiki": _buscar_wiki,
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
