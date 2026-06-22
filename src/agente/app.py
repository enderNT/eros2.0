"""App FastAPI: unidad desplegable (Coolify).

Expone /health y /webhook/chatwoot. El grafo y el checkpointer SQLite se crean
una vez al arrancar y se reutilizan entre requests.
"""

import logging
import os
import sqlite3
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from langgraph.checkpoint.sqlite import SqliteSaver
from starlette.concurrency import run_in_threadpool

from .config import settings
from .graph import build_graph
from .webhook import parse_evento

logging.basicConfig(level=settings.log_level)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = settings.checkpoint_db_path
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    app.state.graph = build_graph(saver)
    app.state.db_conn = conn
    log.info("grafo listo · checkpointer SQLite en %s", db_path)
    try:
        yield
    finally:
        conn.close()


app = FastAPI(title="Agente Clínica", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


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
    log.info(
        "webhook → conv=%s msg=%s user=%s bot_activo=%s",
        ev["conversation_id"], ev.get("message_id"), ev["user_id"], ev["bot_activo"],
    )

    state_in = {
        "messages": [{"role": "user", "content": ev["texto"]}],
        "meta": {
            "user_id": ev["user_id"],
            "canal": "chatwoot",
            "conversation_id": ev["conversation_id"],
            "bot_activo": ev["bot_activo"],
        },
    }
    config = {"configurable": {"thread_id": f"chatwoot-{ev['conversation_id']}"}}
    result = await run_in_threadpool(app.state.graph.invoke, state_in, config)
    return {"ok": True, "salida": result.get("salida", {})}
