"""Control panel shell: serves the built React app and its assets (SPEC §3).

The panel is a Vite/React SPA; every read and write it performs goes through
`panel_api`. This module only hands the browser the shell and the compiled
bundle, so it is deliberately session-free — the shell carries no patient
data, and the API refuses to answer without a cookie.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..ports.channel import ConversationRow

router = APIRouter()
_ROOT = Path(__file__).parent
_STATIC = _ROOT / "static"
_SHELL = _STATIC / "panel" / "index.html"

_NOT_BUILT = """<!doctype html><html lang="es"><meta charset="utf-8">
<title>Panel sin compilar</title>
<body style="font:16px system-ui;padding:24px">
<h1>El panel no está compilado</h1>
<p>Ejecuta <code>npm --prefix panel-ui install &amp;&amp; npm --prefix panel-ui run build</code>
y recarga.</p>"""


def mount_static(app) -> None:  # type: ignore[no-untyped-def]
    _STATIC.mkdir(parents=True, exist_ok=True)
    app.mount("/admin/static", StaticFiles(directory=str(_STATIC)), name="admin-static")


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


@router.get("/admin", response_class=HTMLResponse)
@router.get("/admin/login", response_class=HTMLResponse)
@router.get("/admin/traces", response_class=HTMLResponse)
async def shell() -> HTMLResponse:
    if not _SHELL.is_file():
        return HTMLResponse(_NOT_BUILT, status_code=503)
    return HTMLResponse(_SHELL.read_text(encoding="utf-8"))
