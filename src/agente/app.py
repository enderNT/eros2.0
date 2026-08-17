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
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import FastAPI

from .adapters.anthropic.client import AnthropicClient
from .adapters.calendly.client import CalendlyClient
from .adapters.kapso.client import KapsoClient
from .adapters.store import db as store_db
from .adapters.store.appointments import SqliteAppointmentsRepository
from .adapters.store.contacts import SqliteContactsRepository
from .adapters.store.messages import SqliteMessagesRepository
from .adapters.store.mutes import SqliteMutesRepository
from .adapters.store.summaries import SqliteSummariesRepository
from .adapters.store.traces import SqliteTracesRepository
from .config import Settings, load_settings
from .domain.contacts import ContactKey
from .domain.errors import StoreError
from .logging_setup import setup_logging
from .services.agent import Agent, AgentResponder
from .services.compaction import compact, make_summarizer
from .services.inbound import InboundService
from .services.knowledge import Knowledge
from .tools.registry import build_tools
from .web.health import router as health_router
from .web.panel import mount_static
from .web.panel import router as panel_router
from .web.webhooks import router as webhooks_router

if TYPE_CHECKING:
    import sqlite3

log = logging.getLogger(__name__)

# The rolling summary is capped at ~120 words by its own prompt; this only
# stops a runaway generation from costing a full conversation's budget.
_SUMMARY_MAX_TOKENS = 512


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        cfg = settings if settings is not None else load_settings()
        setup_logging(cfg.log_level)
        _prepare_database_dir(cfg)
        app.state.settings = cfg
        app.state.db = _open_database(cfg)
        app.state.channel = KapsoClient(cfg.kapso_base_url, cfg.kapso_api_key)
        app.state.calendar = CalendlyClient(cfg.calendly_token, cfg.calendly_event_type_uri)
        content_root = cfg.content_dir.resolve()
        app.state.knowledge = Knowledge.load(content_root / "playbook.md", content_root / "wiki.md")
        traces = SqliteTracesRepository(app.state.db)
        messages = SqliteMessagesRepository(app.state.db)
        summaries = SqliteSummariesRepository(app.state.db)
        model = AnthropicClient(
            cfg.anthropic_api_key,
            cfg.anthropic_model_conversation,
            cfg.anthropic_max_tokens,
            traces,
        )
        summarizer = make_summarizer(
            AnthropicClient(
                cfg.anthropic_api_key,
                cfg.anthropic_model_summarization,
                _SUMMARY_MAX_TOKENS,
                traces,
            )
        )
        responder = AgentResponder(
            Agent(model, {}, max_iterations=cfg.anthropic_max_iterations),
            app.state.knowledge,
            SqliteContactsRepository(app.state.db),
            lambda key: _agent_tools(app, key),
            messages=messages,
            summaries=summaries,
        )

        async def compactor(key: ContactKey) -> bool:
            return await compact(
                key,
                messages,
                summaries,
                summarizer,
                datetime.now(UTC),
                budget=cfg.window_token_budget,
                overlap_turns=cfg.overlap_turns,
            )

        app.state.inbound = InboundService(
            messages,
            SqliteMutesRepository(app.state.db),
            app.state.channel,
            responder=responder,
            crisis_message=cfg.crisis_message,
            debounce_seconds=cfg.debounce_seconds,
            compactor=compactor,
        )
        try:
            yield
        finally:
            if app.state.db is not None:
                app.state.db.close()
            await app.state.channel.aclose()
            await app.state.calendar.aclose()

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


def _agent_tools(app: FastAPI, key: ContactKey):
    """The tool surface for one contact's turn (SPEC §6)."""
    return build_tools(
        knowledge=app.state.knowledge,
        mutes=SqliteMutesRepository(app.state.db),
        calendar=app.state.calendar,
        appointments=SqliteAppointmentsRepository(app.state.db),
        key=key,
        timezone=app.state.settings.calendly_timezone,
    )
