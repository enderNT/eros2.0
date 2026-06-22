"""App FastAPI: unidad desplegable (Coolify).

Orquestación lineal sin framework de grafos:

  webhook → ¿bot activo? no → ignorar
          → ¿crisis? sí → recursos + apagar bot
          → responder() (loop ReAct con herramientas)
          → enviar a Chatwoot + guardar historial
"""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .agent import responder
from .chatwoot import get_chatwoot
from .config import settings
from .llm import detectar_crisis
from .llm_logger import get_llm_logger, render_data_text
from .store import get_store
from .webhook import parse_evento

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(title="Agente Clínica")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/llm-logs")
def llm_logs(limit: int = 100, q: str = ""):
    return {
        "enabled": get_llm_logger().enabled,
        "logs": get_llm_logger().list_calls(limit, q),
    }


@app.get("/debug/llm-flows")
def llm_flows(limit: int = 100, q: str = ""):
    return {
        "enabled": get_llm_logger().enabled,
        "flows": get_llm_logger().list_flows(limit, q),
    }


@app.get("/debug/llm-flow")
def llm_flow(flow_id: str):
    flow = get_llm_logger().get_flow(flow_id)
    if flow is None:
        return JSONResponse({"ok": False, "error": "not_found"}, status_code=404)
    return {"ok": True, "flow": flow}


def _enviar(conversation_id, texto: str) -> None:
    """Manda un mensaje saliente por Chatwoot (si está configurado)."""
    cw = get_chatwoot()
    if cw is None:
        log.warning("Chatwoot NO configurado; respuesta solo local → %s", texto)
        return
    try:
        cw.enviar_mensaje(conversation_id, texto)
        log.info("respuesta enviada a conv=%s", conversation_id)
    except Exception as e:  # noqa: BLE001
        log.error("enviar a Chatwoot falló (conv=%s): %s", conversation_id, e)


def _log_memory_event(
    *,
    operation: str,
    request: dict,
    response: dict,
    ctx: dict,
    stage: str,
    stage_label: str,
    stage_order: int,
    call_order: int,
    status: str = "ok",
) -> None:
    get_llm_logger().record(
        provider="memory",
        operation=operation,
        model=None,
        status=status,
        conversation_id=ctx.get("conversation_id"),
        flow_id=ctx.get("flow_id"),
        message_id=ctx.get("message_id"),
        stage=stage,
        stage_label=stage_label,
        stage_order=stage_order,
        call_order=call_order,
        request_text=render_data_text(request),
        response_text=render_data_text(response),
        metadata={"purpose": operation},
    )


def _procesar(ev: dict) -> str:
    """Lógica de un mensaje entrante (corre en threadpool: I/O bloqueante)."""
    conv = ev["conversation_id"]
    store = get_store()
    message_id = ev.get("message_id")
    flow_id = f"chatwoot:{message_id}" if message_id is not None else f"local:{uuid4().hex}"
    llm_ctx = {
        "conversation_id": conv,
        "user_id": ev["user_id"],
        "message_id": message_id,
        "flow_id": flow_id,
        "incoming_text": ev["texto"],
    }

    # 1) Crisis: pre-chequeo determinista, fuera del loop.
    if detectar_crisis(ev["texto"], llm_ctx):
        log.warning("crisis detectada en conv=%s → escalando", conv)
        texto = settings.crisis_message
        cw = get_chatwoot()
        if cw is not None:
            try:
                cw.set_atributo(conv, "bot_activo", False)  # apaga el bot
            except Exception as e:  # noqa: BLE001
                log.error("crisis: set_atributo falló: %s", e)
        _enviar(conv, texto)
        store.agregar_turno(conv, "user", ev["texto"])
        store.agregar_turno(conv, "assistant", texto)
        _log_memory_event(
            operation="memory.history.write",
            request={
                "conversation_id": conv,
                "turnos_a_guardar": [
                    {"role": "user", "content": ev["texto"]},
                    {"role": "assistant", "content": texto},
                ],
            },
            response={"status": "ok", "turnos_guardados": 2},
            ctx=llm_ctx,
            stage="history_persist",
            stage_label="Persistencia de historial",
            stage_order=40,
            call_order=1,
        )
        return texto

    # 2) Contexto: perfil (memoria larga) + historial (memoria corta).
    perfil = store.get_perfil(ev["user_id"])
    historial = store.cargar_historial(conv, settings.history_window)
    _log_memory_event(
        operation="memory.read",
        request={
            "user_id": ev["user_id"],
            "conversation_id": conv,
            "history_window": settings.history_window,
            "mensaje_entrante": ev["texto"],
            "lecturas": ["perfil", "historial"],
        },
        response={
            "perfil_recuperado": perfil,
            "historial_recuperado": historial,
        },
        ctx=llm_ctx,
        stage="memory_read",
        stage_label="Lectura de memoria",
        stage_order=20,
        call_order=1,
    )
    historial.append({"role": "user", "content": ev["texto"]})

    # 3) Loop del agente.
    ctx = dict(llm_ctx)
    texto = responder(historial, perfil, ctx)

    # 4) Salida + persistencia (solo turnos de texto).
    _enviar(conv, texto)
    store.agregar_turno(conv, "user", ev["texto"])
    store.agregar_turno(conv, "assistant", texto)
    _log_memory_event(
        operation="memory.history.write",
        request={
            "conversation_id": conv,
            "turnos_a_guardar": [
                {"role": "user", "content": ev["texto"]},
                {"role": "assistant", "content": texto},
            ],
        },
        response={"status": "ok", "turnos_guardados": 2},
        ctx=llm_ctx,
        stage="history_persist",
        stage_label="Persistencia de historial",
        stage_order=40,
        call_order=1,
    )
    return texto


@app.post("/webhook/chatwoot")
async def chatwoot_webhook(request: Request):
    if settings.chatwoot_webhook_token:
        if request.query_params.get("token") != settings.chatwoot_webhook_token:
            return JSONResponse({"ok": False, "error": "unauthorized"}, status_code=401)

    payload = await request.json()
    ev = parse_evento(payload)
    if ev is None:
        log.info(
            "webhook ignorado (event=%s, message_type=%s)",
            payload.get("event"),
            payload.get("message_type"),
        )
        return {"ok": True, "ignored": True}

    # V1: bot apagado en esta conversación → ni siquiera procesamos.
    if not ev["bot_activo"]:
        log.info("bot apagado en conv=%s → ignorado", ev["conversation_id"])
        return {"ok": True, "ignored": "bot_off"}

    log.info(
        "webhook → conv=%s msg=%s user=%s",
        ev["conversation_id"], ev.get("message_id"), ev["user_id"],
    )
    texto = await run_in_threadpool(_procesar, ev)
    return {"ok": True, "respuesta": texto}
