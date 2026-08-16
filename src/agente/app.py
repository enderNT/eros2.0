"""FastAPI application factory.

`create_app` is the composition root. Settings are loaded once in the lifespan
(or injected by tests) and hung off `app.state` for the routes; nothing is
built at import time.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import Settings, load_settings
from .logging_setup import setup_logging
from .web.health import router as health_router


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings if settings is not None else load_settings()
        setup_logging(cfg.log_level)
        _prepare_database_dir(cfg)
        app.state.settings = cfg
        yield

    app = FastAPI(title="agente", lifespan=lifespan)
    app.include_router(health_router)
    return app


def _prepare_database_dir(cfg: Settings) -> None:
    try:
        cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"cannot create database directory {cfg.db_path.parent}: {exc}") from exc


app = create_app()
