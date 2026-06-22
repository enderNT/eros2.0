"""App FastAPI: unidad desplegable (Coolify).

Orquestación lineal sin framework de grafos:

  webhook → ¿bot activo? no → ignorar
          → ¿crisis? sí → recursos + apagar bot
          → responder() (loop ReAct con herramientas)
          → enviar a Chatwoot + guardar historial
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .agent import responder
from .chatwoot import get_chatwoot
from .config import settings
from .llm import detectar_crisis
from .store import get_store
from .webhook import parse_evento

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)

app = FastAPI(title="Agente Clínica")


@app.get("/health")
def health():
    return {"status": "ok"}


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


def _procesar(ev: dict) -> str:
    """Lógica de un mensaje entrante (corre en threadpool: I/O bloqueante)."""
    conv = ev["conversation_id"]
    store = get_store()

    # 1) Crisis: pre-chequeo determinista, fuera del loop.
    if detectar_crisis(ev["texto"]):
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
        return texto

    # 2) Contexto: perfil (memoria larga) + historial (memoria corta).
    perfil = store.get_perfil(ev["user_id"])
    historial = store.cargar_historial(conv, settings.history_window)
    historial.append({"role": "user", "content": ev["texto"]})

    # 3) Loop del agente.
    ctx = {"conversation_id": conv, "user_id": ev["user_id"]}
    texto = responder(historial, perfil, ctx)

    # 4) Salida + persistencia (solo turnos de texto).
    _enviar(conv, texto)
    store.agregar_turno(conv, "user", ev["texto"])
    store.agregar_turno(conv, "assistant", texto)
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
