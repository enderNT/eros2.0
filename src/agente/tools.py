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
from datetime import tzinfo as _tzinfo
from zoneinfo import ZoneInfo

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
            "días. Úsalo SIEMPRE antes de proponer un horario; nunca inventes horarios. "
            "Devuelve una lista en 'horarios', donde cada elemento trae 'etiqueta' (hora "
            "local ya legible, ej. 'jueves 2 jul, 7:00 p.m.' — úsala para mostrar y para "
            "que el paciente elija) e 'id' (identificador opaco que debes copiar TAL CUAL "
            "en agendar_cita; no lo conviertas ni lo edites). La lista es un muestreo que "
            "ya cubre distintos días y franjas (mañana/tarde/noche): ofrécela amplia."
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
                    "description": "El 'id' EXACTO de un horario devuelto por ver_horarios (ISO 8601 UTC, ej. 2026-07-01T18:00:00Z). Cópialo tal cual; no uses la etiqueta legible ni lo recalcules.",
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


# Nombres en español, sin depender del locale del sistema (locale puede no estar
# instalado en el contenedor). weekday(): lunes=0 … domingo=6.
_DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES_ES = ["", "ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _zona_local() -> _tzinfo:
    """ZoneInfo de la zona configurada; cae a UTC si el nombre es inválido."""
    try:
        return ZoneInfo(settings.calendly_timezone)
    except Exception:  # noqa: BLE001
        return _tz.utc


def _etiqueta_local(dt_local: datetime) -> str:
    """'jueves 2 jul, 7:00 p.m.' — hora ya en zona local, lista para mostrar."""
    dia = _DIAS_ES[dt_local.weekday()]
    h12 = dt_local.hour % 12 or 12
    ampm = "a.m." if dt_local.hour < 12 else "p.m."
    return f"{dia} {dt_local.day} {_MESES_ES[dt_local.month]}, {h12}:{dt_local.minute:02d} {ampm}"


def _franja(hora: int) -> int:
    """Mañana (<12) | tarde (12–16) | noche (>=17). Para muestrear amplio."""
    if hora < 12:
        return 0
    if hora < 17:
        return 1
    return 2


def _muestreo_amplio(locales: list[tuple], cap: int = 12, por_franja: int = 2) -> list[tuple]:
    """Reemplaza el recorte ciego (los primeros N) por un muestreo que enseñe la
    amplitud real de la agenda. `locales` = [(id_utc, dt_local)] ya ordenado.

    Por día y franja toma hasta `por_franja` slots repartidos (extremos de la
    franja, no consecutivos); luego reparte el cupo global round-robin entre días
    para que el primer día no se coma todas las opciones. Determinista."""
    por_dia: dict = {}
    for utc, dl in locales:
        por_dia.setdefault(dl.date(), []).append((utc, dl))

    candidatos_por_dia: list[list[tuple]] = []
    for fecha in sorted(por_dia):
        franjas: dict = {}
        for utc, dl in por_dia[fecha]:
            franjas.setdefault(_franja(dl.hour), []).append((utc, dl))
        elegidos: list[tuple] = []
        for f in sorted(franjas):
            grupo = franjas[f]
            if len(grupo) <= por_franja:
                elegidos.extend(grupo)
            elif por_franja == 1:
                elegidos.append(grupo[0])
            else:
                paso = (len(grupo) - 1) / (por_franja - 1)
                idxs = sorted({round(i * paso) for i in range(por_franja)})
                elegidos.extend(grupo[i] for i in idxs)
        elegidos.sort(key=lambda x: x[1])
        candidatos_por_dia.append(elegidos)

    salida: list[tuple] = []
    i = 0
    while len(salida) < cap and any(i < len(d) for d in candidatos_por_dia):
        for d in candidatos_por_dia:
            if i < len(d):
                salida.append(d[i])
                if len(salida) >= cap:
                    break
        i += 1
    salida.sort(key=lambda x: x[1])
    return salida


def _ver_horarios(args: dict, ctx: dict) -> str:
    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return json.dumps({"error": "agenda no configurada", "horarios": []})
    dias = min(int(args.get("dias", 7) or 7), 7)
    ahora = datetime.now(_tz.utc)
    # Calendly exige start_time estrictamente futuro y lo evalúa contra SU reloj:
    # si mandamos "ahora" exacto, con la latencia/desfase ya es pasado al llegar
    # (400 "start_time must be in the future"). Colchón para cubrirlo. El end se
    # ancla a `ahora` para que la ventana quede por debajo del tope de 7 días.
    inicio = ahora + timedelta(minutes=2)
    try:
        slots = cal.available_times(
            settings.calendly_event_type,
            inicio.strftime("%Y-%m-%dT%H:%M:%SZ"),
            (ahora + timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ"),
            ctx=ctx,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("ver_horarios falló: %s", e)
        return json.dumps({"error": "no pude consultar la agenda ahora", "horarios": []})

    # A: convertimos a hora local UNA vez, en código. El modelo nunca hace
    # aritmética de zonas: lee 'etiqueta' y reenvía 'id' tal cual a agendar_cita.
    zona = _zona_local()
    locales: list[tuple] = []
    for s in slots:
        st = s.get("start_time")
        if not st:
            continue
        try:
            dl = datetime.fromisoformat(st.replace("Z", "+00:00")).astimezone(zona)
        except ValueError:
            continue
        locales.append((st, dl))
    locales.sort(key=lambda x: x[1])

    # C: muestreo representativo en vez de los primeros 8 consecutivos.
    elegidos = _muestreo_amplio(locales)
    horarios = [{"id": utc, "etiqueta": _etiqueta_local(dl)} for utc, dl in elegidos]
    return json.dumps(
        {"horarios": horarios, "zona": settings.calendly_timezone},
        ensure_ascii=False,
    )


def _agendar_cita(args: dict, ctx: dict) -> str:
    cal = get_calendly()
    if cal is None or not settings.calendly_event_type:
        return json.dumps({"status": "error", "detalle": "agenda no configurada"})

    res = None
    for intento in range(2):  # un reintento ante error técnico transitorio
        res = cal.crear_invitee(
            event_type=settings.calendly_event_type,
            start_time=args["slot"],
            nombre=args["nombre"],
            correo=args["correo"],
            timezone=settings.calendly_timezone,
            location_kind=settings.calendly_location_kind,
            location_value=settings.calendly_location_value or None,
            asunto=args.get("asunto"),
            ctx=ctx,
            call_order=intento + 1,
        )
        if res.status != "error":
            break

    # Log del agendado: input = lo que se manda a Calendly, output = resultado real.
    get_llm_logger().record(
        provider="calendly",
        operation="tool.agendar_cita",
        model=None,
        status="ok" if res.status == "ok" else "error",
        conversation_id=ctx.get("conversation_id"),
        flow_id=ctx.get("flow_id"),
        message_id=ctx.get("message_id"),
        stage="agendar_cita",
        stage_label="Agendamiento de cita",
        stage_order=34,
        call_order=1,
        request_text=render_data_text(
            {
                "event_type": settings.calendly_event_type,
                "slot": args.get("slot"),
                "nombre": args.get("nombre"),
                "correo": args.get("correo"),
                "asunto": args.get("asunto"),
                "timezone": settings.calendly_timezone,
                "location_kind": settings.calendly_location_kind,
            }
        ),
        response_text=render_data_text(
            {
                "status": res.status,
                "slot": args.get("slot"),
                "invitee_uri": getattr(res, "invitee_uri", None),
                "event_uri": getattr(res, "event_uri", None),
                "cancel_url": getattr(res, "cancel_url", None),
                "reschedule_url": getattr(res, "reschedule_url", None),
                "detalle": (getattr(res, "detail", "") or None) and res.detail[:300],
            }
        ),
        metadata={"purpose": "tool", "tool": "agendar_cita"},
    )

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
        return json.dumps({"status": "slot_taken", "detalle": res.detail[:200] or "ese horario se ocupó"})
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
        leads = leads_minutes()
        n = get_store().crear_recordatorios(
            invitee_uri=getattr(res, "invitee_uri", None),
            event_uri=getattr(res, "event_uri", None),
            conversation_id=conv,
            user_id=ctx.get("user_id"),
            nombre=args.get("nombre"),
            correo=args.get("correo"),
            slot=slot_dt,
            leads_minutes=leads,
        )
        log.info("recordatorios encolados: %s (conv=%s)", n, conv)
        get_llm_logger().record(
            provider="recordatorio",
            operation="recordatorio.encolar",
            model=None,
            status="ok",
            conversation_id=conv,
            flow_id=ctx.get("flow_id"),
            message_id=ctx.get("message_id"),
            stage="recordatorio_encolado",
            stage_label="Recordatorios programados",
            stage_order=37,
            call_order=1,
            request_text=render_data_text(
                {
                    "conversation_id": conv,
                    "nombre": args.get("nombre"),
                    "correo": args.get("correo"),
                    "cita": args.get("slot"),
                    "invitee_uri": getattr(res, "invitee_uri", None),
                    "leads_minutes": leads,
                }
            ),
            response_text=render_data_text({"recordatorios_insertados": n}),
            metadata={"purpose": "recordatorio", "etapa": "encolado"},
        )
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
