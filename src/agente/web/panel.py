"""Mobile-first local control panel (SPEC §3, §11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..adapters.store.mutes import SqliteMutesRepository
from ..adapters.store.purge import SqlitePurgeRepository
from ..adapters.store.settings import (
    MAX_BOOKING_FOLLOWUP_MINUTES,
    MIN_BOOKING_FOLLOWUP_MINUTES,
    SqliteRuntimeSettingsRepository,
)
from ..adapters.store.traces import SqliteTracesRepository
from ..domain.contacts import ContactKey, mask_phone
from ..domain.errors import KapsoError
from ..ports.channel import ConversationRow
from .auth import panel_actor, require_panel_session, set_session

router = APIRouter()
_ROOT = Path(__file__).parent
templates = Jinja2Templates(directory=str(_ROOT / "templates"))
templates.env.globals["mask_phone"] = mask_phone
_SLIDER_STEPS = (1, 2, 3, 5, 6, 9, 10, 15, 18, 30, 45, 90)


def mount_static(app) -> None:  # type: ignore[no-untyped-def]
    app.mount("/admin/static", StaticFiles(directory=str(_ROOT / "static")), name="admin-static")


async def _form(request: Request) -> dict[str, str]:
    data = parse_qs((await request.body()).decode(), keep_blank_values=True)
    return {key: values[-1] for key, values in data.items()}


def _until(value: str, now: datetime) -> datetime | None:
    if not value:
        return None
    try:
        seconds = int(value)
    except ValueError:
        return None
    return now + timedelta(seconds=seconds) if seconds > 0 else None


def one_row_per_contact(
    rows: list[ConversationRow],
) -> tuple[list[ConversationRow], dict[str, int]]:
    """Collapse Kapso's conversations into one row per person.

    Kapso ends a conversation after 24h of inactivity and opens a new one
    with the next message, so the same patient comes back three or four
    times in the listing. The mute switch is keyed by contact, never by
    conversation, so the panel shows the contact once — its most recent
    conversation — plus how many that contact has.
    """
    latest: dict[str, ConversationRow] = {}
    counts: dict[str, int] = {}
    for row in rows:
        identity = row.contact_phone or row.conversation_id
        counts[identity] = counts.get(identity, 0) + 1
        current = latest.get(identity)
        if current is None or _activity(row) > _activity(current):
            latest[identity] = row
    ordered = sorted(latest.values(), key=_activity, reverse=True)
    return ordered, counts


def _activity(row: ConversationRow) -> datetime:
    return row.last_activity_at or datetime.min.replace(tzinfo=UTC)


def _mutes(request: Request) -> SqliteMutesRepository:
    return SqliteMutesRepository(request.app.state.db)


def _runtime_settings(request: Request) -> SqliteRuntimeSettingsRepository:
    return SqliteRuntimeSettingsRepository(request.app.state.db)


def _booking_followup_minutes(request: Request) -> int:
    return _runtime_settings(request).booking_followup_minutes(
        request.app.state.settings.booking_followup_minutes
    )


def _slider_step(value: str) -> int:
    try:
        step = int(value)
    except ValueError:
        return 1
    return step if step in _SLIDER_STEPS else 1


@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login_fragment.html", {"error": None})


@router.post("/admin/login", response_class=HTMLResponse)
async def login(request: Request) -> HTMLResponse:
    form = await _form(request)
    if form.get("password") != request.app.state.settings.panel_password:
        return templates.TemplateResponse(
            request, "login_fragment.html", {"error": "Contraseña inválida"}, status_code=401
        )
    response = RedirectResponse("/admin", status_code=303)
    set_session(response, request.app.state.settings.panel_session_secret)
    return response


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)])
async def panel(request: Request) -> HTMLResponse:
    error = None
    try:
        conversations = (
            await request.app.state.channel.list_conversations(
                request.app.state.settings.kapso_phone_number_id
            )
        ).conversations
    except KapsoError:
        conversations, error = [], "No se pudieron cargar las conversaciones."
    conversations, conversation_counts = one_row_per_contact(conversations)
    mutes = _mutes(request)
    states = {
        row.contact_phone: mutes.contact_mute(
            ContactKey(request.app.state.settings.kapso_phone_number_id, row.contact_phone)
        )
        for row in conversations
        if row.contact_phone
    }
    return templates.TemplateResponse(
        request,
        "contact_list.html",
        {
            "conversations": conversations,
            "conversation_counts": conversation_counts,
            "mute_states": states,
            "global_muted": mutes.global_mute() is not None,
            "number_muted": mutes.number_mute(request.app.state.settings.kapso_phone_number_id)
            is not None,
            "booking_followup_minutes": _booking_followup_minutes(request),
            "booking_followup_slider_step": 1,
            "booking_followup_steps": _SLIDER_STEPS,
            "booking_followup_step_count": MAX_BOOKING_FOLLOWUP_MINUTES,
            "error": error,
        },
    )


@router.post(
    "/admin/mute", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)]
)
async def contact_mute(request: Request) -> HTMLResponse:
    form, now = await _form(request), datetime.now(UTC)
    key = ContactKey(form["phone_number_id"], form["contact_phone"])
    repo = _mutes(request)
    muted = form.get("muted") == "true"
    if muted:
        repo.set_mute(
            key,
            now,
            actor=panel_actor(),
            reason="panel",
            until=_until(form.get("expires_in", ""), now),
        )
    else:
        repo.clear_mute(key, now, actor=panel_actor(), reason="panel")
    return templates.TemplateResponse(
        request,
        "contact_mute_toggle.html",
        {"key": key, "mute_state": repo.contact_mute(key)},
    )


@router.post(
    "/admin/reset", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)]
)
async def contact_reset(request: Request) -> HTMLResponse:
    """Erase everything stored about one contact. Irreversible, and audited."""
    form, now = await _form(request), datetime.now(UTC)
    key = ContactKey(form["phone_number_id"], form["contact_phone"])
    removed = SqlitePurgeRepository(request.app.state.db).contact(
        key, now, actor=panel_actor(), reason="panel"
    )
    return templates.TemplateResponse(
        request,
        "contact_controls.html",
        # The purge cleared the mute too, so the toggle below it is redrawn
        # from the store rather than assumed.
        {
            "key": key,
            "mute_state": _mutes(request).contact_mute(key),
            "purged": sum(removed.values()),
        },
    )


@router.post(
    "/admin/number-mute", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)]
)
async def number_mute(request: Request) -> HTMLResponse:
    form, now = await _form(request), datetime.now(UTC)
    muted = form.get("muted") == "true"
    _mutes(request).set_number_mute(
        form["phone_number_id"],
        muted,
        now,
        actor=panel_actor(),
        reason="panel",
        until=_until(form.get("expires_in", ""), now),
    )
    return templates.TemplateResponse(
        request,
        "number_mute_toggle.html",
        {"phone_number_id": form["phone_number_id"], "number_muted": muted},
    )


@router.post(
    "/admin/global", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)]
)
async def global_mute(request: Request) -> HTMLResponse:
    form, now = await _form(request), datetime.now(UTC)
    muted = form.get("muted") == "true"
    _mutes(request).set_global(
        muted,
        now,
        actor=panel_actor(),
        reason="panel",
        until=_until(form.get("expires_in", ""), now),
    )
    return templates.TemplateResponse(request, "global_kill_switch.html", {"global_muted": muted})


@router.post(
    "/admin/booking-followup",
    response_class=HTMLResponse,
    dependencies=[Depends(require_panel_session)],
)
async def booking_followup(request: Request) -> HTMLResponse:
    form = await _form(request)
    try:
        minutes = int(form.get("minutes", ""))
        _runtime_settings(request).set_booking_followup_minutes(minutes, datetime.now(UTC))
    except ValueError:
        minutes = _booking_followup_minutes(request)
    slider_step = _slider_step(form.get("slider_step", "1"))
    return templates.TemplateResponse(
        request,
        "booking_followup_control.html",
        {
            "booking_followup_minutes": minutes,
            "booking_followup_min": MIN_BOOKING_FOLLOWUP_MINUTES,
            "booking_followup_max": MAX_BOOKING_FOLLOWUP_MINUTES,
            "booking_followup_slider_step": slider_step,
            "booking_followup_steps": _SLIDER_STEPS,
            "booking_followup_step_count": MAX_BOOKING_FOLLOWUP_MINUTES // slider_step,
        },
    )


@router.get(
    "/admin/traces", response_class=HTMLResponse, dependencies=[Depends(require_panel_session)]
)
async def traces(request: Request) -> HTMLResponse:
    try:
        rows = SqliteTracesRepository(request.app.state.db).recent()
    except NotImplementedError:
        rows = []
    return templates.TemplateResponse(request, "traces_view.html", {"traces": rows, "error": None})
