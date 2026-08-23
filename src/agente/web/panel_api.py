"""JSON API behind the control panel SPA (SPEC §3, §11).

The panel used to be server-rendered fragments; it is a Vite/React app now,
so every route here answers JSON and the browser owns the rendering. What did
not change: the switches are the only writes, the session cookie is the only
gate, and the raw contact phone still crosses the wire because the mute key
is built from it — it is masked for *display* by `masked_phone`, never by
dropping it from the payload.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..adapters.store.appointments import SqliteAppointmentsRepository
from ..adapters.store.mutes import SqliteMutesRepository
from ..adapters.store.purge import SqlitePurgeRepository
from ..adapters.store.settings import (
    MAX_APPOINTMENT_REMINDER_MINUTES,
    MAX_INTEREST_FOLLOWUP_MINUTES,
    MIN_APPOINTMENT_REMINDER_MINUTES,
    MIN_INTEREST_FOLLOWUP_MINUTES,
    SqliteRuntimeSettingsRepository,
)
from ..adapters.store.traces import SqliteTracesRepository
from ..domain.contacts import ContactKey, mask_phone
from ..domain.errors import KapsoError
from ..ports.store import AppointmentRow, MuteState
from .auth import clear_session, is_authed, panel_actor, require_panel_session, set_session
from .panel import one_row_per_contact

router = APIRouter(prefix="/admin/api")
_guard = Depends(require_panel_session)


class LoginBody(BaseModel):
    password: str


class ContactBody(BaseModel):
    phone_number_id: str
    contact_phone: str


class ContactMuteBody(ContactBody):
    muted: bool
    expires_in: int | None = Field(default=None, ge=0)


class NumberMuteBody(BaseModel):
    phone_number_id: str
    muted: bool
    expires_in: int | None = Field(default=None, ge=0)


class GlobalMuteBody(BaseModel):
    muted: bool
    expires_in: int | None = Field(default=None, ge=0)


class MinutesBody(BaseModel):
    minutes: int


class EnabledBody(BaseModel):
    enabled: bool


def _mutes(request: Request) -> SqliteMutesRepository:
    return SqliteMutesRepository(request.app.state.db)


def _runtime_settings(request: Request) -> SqliteRuntimeSettingsRepository:
    return SqliteRuntimeSettingsRepository(request.app.state.db)


def _interest_followup_minutes(request: Request) -> int:
    return _runtime_settings(request).interest_followup_minutes(
        request.app.state.settings.interest_followup_minutes
    )


def _interest_followup_enabled(request: Request) -> bool:
    return _runtime_settings(request).interest_followup_enabled(
        request.app.state.settings.interest_followup_enabled
    )


def _appointment_reminder_enabled(request: Request) -> bool:
    return _runtime_settings(request).appointment_reminder_enabled(
        request.app.state.settings.appointment_reminder_enabled
    )


def _appointment_reminder_minutes(request: Request) -> int:
    return _runtime_settings(request).appointment_reminder_minutes(
        request.app.state.settings.appointment_reminder_minutes
    )


def _until(seconds: int | None, now: datetime) -> datetime | None:
    return now + timedelta(seconds=seconds) if seconds else None


def _mute_json(state: MuteState | None) -> dict[str, Any] | None:
    if state is None:
        return None
    return {
        "muted_at": state.muted_at.isoformat(),
        "muted_until": state.muted_until.isoformat() if state.muted_until else None,
    }


def _appointment_json(appointment: AppointmentRow | None) -> dict[str, Any] | None:
    if appointment is None:
        return None
    return {"slot_utc": appointment.slot_utc.isoformat(), "status": appointment.status}


def _scheduled(request: Request, key: ContactKey) -> AppointmentRow | None:
    rows = SqliteAppointmentsRepository(request.app.state.db).for_contact(key)
    return next((row for row in rows if row.status == "scheduled"), None)


@router.get("/session")
async def session(request: Request) -> dict[str, bool]:
    return {"authed": is_authed(request)}


@router.post("/login")
async def login(request: Request, body: LoginBody, response: Response) -> dict[str, bool]:
    if body.password != request.app.state.settings.panel_password:
        raise HTTPException(status_code=401, detail="Contraseña inválida")
    set_session(response, request.app.state.settings.panel_session_secret)
    return {"authed": True}


@router.post("/logout")
async def logout(response: Response) -> dict[str, bool]:
    clear_session(response)
    return {"authed": False}


@router.get("/state", dependencies=[_guard])
async def state(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    phone_number_id = settings.kapso_phone_number_id
    error = None
    try:
        rows = (await request.app.state.channel.list_conversations(phone_number_id)).conversations
    except KapsoError:
        rows, error = [], "No se pudieron cargar las conversaciones."
    rows, counts = one_row_per_contact(rows)
    mutes = _mutes(request)
    contacts = []
    for row in rows:
        key = ContactKey(phone_number_id, row.contact_phone) if row.contact_phone else None
        contacts.append(
            {
                "conversation_id": row.conversation_id,
                "name": row.contact_name,
                "phone": row.contact_phone,
                "masked_phone": mask_phone(row.contact_phone) if row.contact_phone else None,
                "last_activity_at": (
                    row.last_activity_at.isoformat() if row.last_activity_at else None
                ),
                "status": row.status,
                "conversation_count": counts.get(row.contact_phone or row.conversation_id, 1),
                "mute": _mute_json(mutes.contact_mute(key)) if key else None,
                "appointment": _appointment_json(_scheduled(request, key)) if key else None,
            }
        )
    return {
        "phone_number_id": phone_number_id,
        "error": error,
        "global_muted": mutes.global_mute() is not None,
        "number_muted": mutes.number_mute(phone_number_id) is not None,
        "interest_followup": {
            "minutes": _interest_followup_minutes(request),
            "min": MIN_INTEREST_FOLLOWUP_MINUTES,
            "max": MAX_INTEREST_FOLLOWUP_MINUTES,
            "enabled": _interest_followup_enabled(request),
        },
        "appointment_reminder": {
            "minutes": _appointment_reminder_minutes(request),
            "min": MIN_APPOINTMENT_REMINDER_MINUTES,
            "max": MAX_APPOINTMENT_REMINDER_MINUTES,
            "enabled": _appointment_reminder_enabled(request),
        },
        "contacts": contacts,
    }


@router.post("/mute", dependencies=[_guard])
async def contact_mute(request: Request, body: ContactMuteBody) -> dict[str, Any]:
    now = datetime.now(UTC)
    key = ContactKey(body.phone_number_id, body.contact_phone)
    repo = _mutes(request)
    if body.muted:
        repo.set_mute(
            key, now, actor=panel_actor(), reason="panel", until=_until(body.expires_in, now)
        )
    else:
        repo.clear_mute(key, now, actor=panel_actor(), reason="panel")
    return {"mute": _mute_json(repo.contact_mute(key))}


@router.post("/reset", dependencies=[_guard])
async def contact_reset(request: Request, body: ContactBody) -> dict[str, Any]:
    """Erase everything stored about one contact. Irreversible, and audited."""
    now = datetime.now(UTC)
    key = ContactKey(body.phone_number_id, body.contact_phone)
    removed = SqlitePurgeRepository(request.app.state.db).contact(
        key, now, actor=panel_actor(), reason="panel"
    )
    # The purge cleared the mute too, so the toggle is re-read from the store
    # rather than assumed.
    return {
        "purged": sum(removed.values()),
        "mute": _mute_json(_mutes(request).contact_mute(key)),
        "appointment": _appointment_json(_scheduled(request, key)),
    }


@router.post("/number-mute", dependencies=[_guard])
async def number_mute(request: Request, body: NumberMuteBody) -> dict[str, Any]:
    now = datetime.now(UTC)
    _mutes(request).set_number_mute(
        body.phone_number_id,
        body.muted,
        now,
        actor=panel_actor(),
        reason="panel",
        until=_until(body.expires_in, now),
    )
    return {"number_muted": body.muted}


@router.post("/global", dependencies=[_guard])
async def global_mute(request: Request, body: GlobalMuteBody) -> dict[str, Any]:
    now = datetime.now(UTC)
    _mutes(request).set_global(
        body.muted,
        now,
        actor=panel_actor(),
        reason="panel",
        until=_until(body.expires_in, now),
    )
    return {"global_muted": body.muted}


@router.post("/interest-followup", dependencies=[_guard])
async def interest_followup(request: Request, body: MinutesBody) -> dict[str, Any]:
    """Cuánto silencio se espera antes de retomar a quien no llegó a agendar."""
    try:
        _runtime_settings(request).set_interest_followup_minutes(body.minutes, datetime.now(UTC))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"minutes": body.minutes}


@router.post("/interest-followup-enabled", dependencies=[_guard])
async def interest_followup_enabled(request: Request, body: EnabledBody) -> dict[str, Any]:
    """Encender o apagar del todo el seguimiento tras el silencio.

    Apagar vacía lo que ya estaba en cola. Es lo que espera quien mueve el
    interruptor: "que no se le escriba a nadie", no "que no se le escriba a
    quien se calle a partir de ahora". Volver a encender no resucita nada —
    el siguiente mensaje del bot arma el aviso de quien corresponda.
    """
    _runtime_settings(request).set_interest_followup_enabled(body.enabled, datetime.now(UTC))
    if not body.enabled:
        request.app.state.interest_followups.drop_pending()
    return {"enabled": body.enabled}


@router.post("/appointment-reminder-enabled", dependencies=[_guard])
async def appointment_reminder_enabled_route(request: Request, body: EnabledBody) -> dict[str, Any]:
    """Encender o apagar el recordatorio previo a la cita.

    Aparte del seguimiento de interés a propósito: son dos decisiones distintas.
    Retomar a quien se calló es iniciativa de la clínica; recordar una cita que
    ya existe es un servicio a quien la pidió, y hay clínicas que querrán lo
    segundo sin lo primero.

    A diferencia del otro, aquí encender sí reconstruye: la cita sigue ahí, así
    que `reschedule_pending` vuelve a poner un recordatorio por cada cita futura,
    incluidas las que se agendaron mientras estuvo apagado.
    """
    now = datetime.now(UTC)
    _runtime_settings(request).set_appointment_reminder_enabled(body.enabled, now)
    reminders = request.app.state.appointment_reminders
    if body.enabled:
        reminders.reschedule_pending(now)
    else:
        reminders.drop_pending()
    return {"enabled": body.enabled}


@router.post("/interest-followup-send", dependencies=[_guard])
async def interest_followup_send(request: Request, body: ContactBody) -> dict[str, Any]:
    """Mandar ya el seguimiento pendiente de un contacto, sin esperar su plazo."""
    key = ContactKey(body.phone_number_id, body.contact_phone)
    result = await request.app.state.interest_followups.send_now(key)
    return {"result": result}


@router.post("/appointment-reminder-settings", dependencies=[_guard])
async def appointment_reminder_settings(request: Request, body: MinutesBody) -> dict[str, Any]:
    now = datetime.now(UTC)
    try:
        _runtime_settings(request).set_appointment_reminder_minutes(body.minutes, now)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request.app.state.appointment_reminders.reschedule_pending(now)
    return {"minutes": body.minutes}


@router.post("/appointment-reminder", dependencies=[_guard])
async def appointment_reminder(request: Request, body: ContactBody) -> dict[str, Any]:
    key = ContactKey(body.phone_number_id, body.contact_phone)
    result = await request.app.state.appointment_reminders.send_now(key)
    return {"result": result, "appointment": _appointment_json(_scheduled(request, key))}


@router.get("/traces", dependencies=[_guard])
async def traces(request: Request) -> dict[str, Any]:
    try:
        rows = SqliteTracesRepository(request.app.state.db).recent()
    except NotImplementedError:
        rows = []
    return {
        "traces": [
            {
                "model": row.model,
                "tokens_in": row.tokens_in,
                "tokens_out": row.tokens_out,
                "latency_ms": row.latency_ms,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }
