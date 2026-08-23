"""FastAPI application factory.

`create_app` is the composition root. Settings are loaded once in the lifespan
(or injected by tests) and hung off `app.state` for the routes; nothing is
built at import time. The database connection is opened and migrated here too
(SPEC §10); a database that cannot be opened leaves the app serving `/health`
degraded instead of dying silently.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request

from .adapters.anthropic.client import AnthropicClient
from .adapters.calendly.client import CalendlyClient
from .adapters.kapso.client import KapsoClient
from .adapters.store import db as store_db
from .adapters.store.appointments import SqliteAppointmentsRepository
from .adapters.store.contacts import SqliteContactsRepository
from .adapters.store.messages import SqliteMessagesRepository
from .adapters.store.mutes import SqliteMutesRepository
from .adapters.store.outbox import SqliteOutboxRepository
from .adapters.store.settings import SqliteRuntimeSettingsRepository
from .adapters.store.summaries import SqliteSummariesRepository
from .adapters.store.traces import SqliteTracesRepository
from .config import Settings, load_settings
from .domain.contacts import ContactKey
from .domain.errors import StoreError
from .logging_setup import setup_logging
from .services.agent import Agent, AgentResponder
from .services.booking import BookingService
from .services.compaction import compact, make_summarizer
from .services.crisis import make_classifier
from .services.inbound import InboundService
from .services.interest_followup import InterestFollowups
from .services.knowledge import Knowledge
from .services.reminders import AppointmentReminders
from .tools.registry import build_tools
from .web.health import router as health_router
from .web.panel import mount_static
from .web.panel import router as panel_router
from .web.panel_api import router as panel_api_router
from .web.webhooks import router as webhooks_router

if TYPE_CHECKING:
    import sqlite3

log = logging.getLogger(__name__)

# The rolling summary is capped at ~120 words by its own prompt; this only
# stops a runaway generation from costing a full conversation's budget.
_SUMMARY_MAX_TOKENS = 512
# The crisis pre-gate answers with a single tool call carrying one enum value.
# 64 was not enough: a call was observed stopping at `max_tokens`, which
# truncates the tool block and makes the gate fall back to `possible` for a
# budget reason rather than a clinical one. Headroom is cheaper than a wrong
# verdict on every turn.
_CRISIS_MAX_TOKENS = 256


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
        contacts = SqliteContactsRepository(app.state.db)
        appointments = SqliteAppointmentsRepository(app.state.db)
        outbox = SqliteOutboxRepository(app.state.db)
        runtime_settings = SqliteRuntimeSettingsRepository(app.state.db)
        app.state.runtime_settings = runtime_settings
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
            contacts,
            lambda key: _agent_tools(app, key),
            messages=messages,
            summaries=summaries,
        )
        crisis_classifier = make_classifier(
            AnthropicClient(
                cfg.anthropic_api_key, cfg.anthropic_model_crisis, _CRISIS_MAX_TOKENS, traces
            )
        )
        reminders = AppointmentReminders(
            outbox=outbox,
            appointments=appointments,
            messages=messages,
            mutes=SqliteMutesRepository(app.state.db),
            channel=app.state.channel,
            timezone=cfg.calendly_timezone,
            minutes_before=lambda: runtime_settings.appointment_reminder_minutes(
                cfg.appointment_reminder_minutes
            ),
            enabled=lambda: runtime_settings.appointment_reminder_enabled(
                cfg.appointment_reminder_enabled
            ),
        )
        app.state.appointment_reminders = reminders
        # Covers appointments confirmed before this feature was deployed.
        if app.state.db is not None:
            reminders.reschedule_pending(datetime.now(UTC))
        app.state.booking = BookingService(
            appointments=appointments,
            contacts=contacts,
            messages=messages,
            outbox=outbox,
            channel=app.state.channel,
            reminders=reminders,
            calendar=app.state.calendar,
            invitee_email=cfg.calendly_invitee_email,
            phone_number_id=cfg.kapso_phone_number_id,
            timezone=cfg.calendly_timezone,
            address=cfg.calendly_location_value,
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

        interest = InterestFollowups(
            outbox=outbox,
            appointments=appointments,
            messages=messages,
            mutes=SqliteMutesRepository(app.state.db),
            channel=app.state.channel,
            delay_minutes=lambda: runtime_settings.interest_followup_minutes(
                cfg.interest_followup_minutes
            ),
            enabled=lambda: runtime_settings.interest_followup_enabled(
                cfg.interest_followup_enabled
            ),
        )
        app.state.interest_followups = interest

        # El seguimiento cuelga de este par de ganchos. Se encadena aquí, en el
        # cableado, en vez de dárselo a `InboundService`: el servicio de entrada
        # no tiene por qué enterarse de qué hay que avisar ni de cuántas cosas.
        def on_inbound(key: ContactKey) -> None:
            interest.cancel_for_contact(key)

        def on_outbound(key: ContactKey, text: str, sent_at: datetime) -> None:
            interest.schedule_from_outbound(key, text, sent_at)

        app.state.inbound = InboundService(
            messages,
            SqliteMutesRepository(app.state.db),
            app.state.channel,
            responder=responder,
            crisis_classifier=crisis_classifier,
            crisis_message=cfg.crisis_message,
            crisis_directives=app.state.knowledge.crisis_directives(),
            debounce_seconds=cfg.debounce_seconds,
            compactor=compactor,
            on_inbound=on_inbound,
            on_outbound=on_outbound,
        )
        outbox_task = (
            asyncio.create_task(_run_outbox(interest, reminders, cfg.outbox_poll_seconds))
            if app.state.db is not None
            else None
        )
        try:
            yield
        finally:
            if outbox_task is not None:
                outbox_task.cancel()
                with suppress(asyncio.CancelledError):
                    await outbox_task
            if app.state.db is not None:
                app.state.db.close()
            await app.state.channel.aclose()
            await app.state.calendar.aclose()

    app = FastAPI(title="agente", lifespan=lifespan)

    @app.middleware("http")
    async def _no_store_panel(request: Request, call_next):  # type: ignore[no-untyped-def]
        """Never let a browser cache the panel.

        Every /admin response renders live mutable state (mutes, reminder
        settings, conversations). Without an explicit directive browsers apply
        heuristic caching and happily serve a stale panel whose HTML no longer
        matches the server — clicks then hit handlers that are gone.
        """
        response = await call_next(request)
        if request.url.path.startswith("/admin") and not request.url.path.startswith(
            "/admin/static"
        ):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(health_router)
    app.include_router(panel_router)
    app.include_router(panel_api_router)
    app.include_router(webhooks_router)
    mount_static(app)
    return app


async def _run_outbox(
    interest: InterestFollowups,
    reminders: AppointmentReminders,
    poll_seconds: float,
) -> None:
    """Un solo bucle para los dos avisos: lo que difiere es cuándo vencen."""
    while True:
        try:
            await interest.send_due()
            await reminders.send_due()
        except StoreError:
            log.error("outbox_poll_failed")
        await asyncio.sleep(poll_seconds)


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
        booking=app.state.booking,
        key=key,
        timezone=app.state.settings.calendly_timezone,
    )
