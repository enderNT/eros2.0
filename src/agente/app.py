"""FastAPI application factory.

`create_app` is the composition root. Settings are loaded once in the lifespan
(or injected by tests) and hung off `app.state` for the routes; nothing is
built at import time. The database connection is opened and migrated here too
(SPEC §10); a database that cannot be opened leaves the app serving `/health`
degraded instead of dying silently.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from .adapters.kapso.client import KapsoClient
from .adapters.store import db as store_db
from .adapters.store.messages import SqliteMessagesRepository
from .adapters.store.mutes import SqliteMutesRepository
from .config import Settings, load_settings
from .domain.errors import StoreError
from .logging_setup import setup_logging
from .services.inbound import InboundService
from .web.health import router as health_router
from .web.panel import mount_static
from .web.panel import router as panel_router
from .web.webhooks import router as webhooks_router

if TYPE_CHECKING:
    import sqlite3

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings if settings is not None else load_settings()
        setup_logging(cfg.log_level)
        _prepare_database_dir(cfg)
        app.state.settings = cfg
        app.state.db = _open_database(cfg)
        app.state.channel = KapsoClient(cfg.kapso_base_url, cfg.kapso_api_key)
        app.state.inbound = InboundService(
            SqliteMessagesRepository(app.state.db),
            SqliteMutesRepository(app.state.db),
            app.state.channel,
            debounce_seconds=cfg.debounce_seconds,
        )
        try:
            yield
        finally:
            if app.state.db is not None:
                app.state.db.close()
            await app.state.channel.aclose()

    app = FastAPI(title="agente", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(panel_router)
    app.include_router(webhooks_router)
    mount_static(app)
    return app


def _prepare_database_dir(cfg: Settings) -> None:
    try:
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create database directory {cfg.db_path.parent}: {exc}") from exc


def _open_database(cfg: Settings) -> sqlite3.Connection | None:
    try:
        conn = store_db.connect(cfg.db_path)
    except StoreError as exc:
        log.error("database unavailable at boot, serving degraded", extra={"error": str(exc)})
        return None
    try:
        store_db.migrate(conn)
    except StoreError as exc:
        conn.close()
        log.error("database migration failed at boot, serving degraded", extra={"error": str(exc)})
        return None
    return conn


app = create_app()
