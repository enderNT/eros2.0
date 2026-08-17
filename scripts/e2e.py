"""Local end-to-end harness: drive the running service like production does.

Runs **inside the container** (see `docker compose exec` in the RUNBOOK section
of this file's `--help`), because that is where the SQLite file and the service
both live. It speaks to the app over HTTP exactly the way Kapso and Calendly do
— same signatures, same payload shapes — so a green run here means the wiring
is real, not mocked.

Subcommands:

  msg "texto"      simulate an inbound WhatsApp message from the test contact
  tokens           list the booking tokens issued so far (newest first)
  book [token]     simulate Calendly's invitee.created for that token
                   (default: the newest one)
  cancel [token]   simulate invitee.canceled for that token's appointment
  state            dump what the database says about the test contact
  reset            wipe the test contact's history, profile and appointments

Nothing here bypasses the app: every write goes through the real webhook
routes. `reset` is the one exception and it touches only the test contact.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sqlite3
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta

import httpx

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")
DB_PATH = os.environ.get("DB_PATH", "/data/agente.db")
PHONE_NUMBER_ID = os.environ["KAPSO_PHONE_NUMBER_ID"]
CONTACT = os.environ.get("E2E_CONTACT", "+525619878083")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------------------------- inbound


def cmd_msg(args: argparse.Namespace) -> int:
    """POST a signed Kapso webhook, then wait out the debounce and show the reply."""
    secret = os.environ["KAPSO_WEBHOOK_SECRET"]
    body = json.dumps(
        {
            "message": {
                "id": f"e2e-{uuid.uuid4().hex[:12]}",
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "type": "text",
                "from": CONTACT,
                "text": {"body": args.text},
            },
            "conversation": {"id": "e2e"},
            "phone_number_id": PHONE_NUMBER_ID,
        }
    ).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    before = _last_message_id()
    response = httpx.post(
        f"{BASE_URL}/webhook/kapso",
        content=body,
        headers={"X-Webhook-Signature": signature, "Content-Type": "application/json"},
        timeout=30,
    )
    print(f"→ {args.text}")
    print(f"  webhook: {response.status_code}")
    if response.status_code != 200:
        return 1
    _print_new_replies(before, args.wait)
    return 0


def _last_message_id() -> int:
    row = _db().execute(
        "SELECT COALESCE(MAX(id), 0) AS id FROM message"
        " WHERE phone_number_id = ? AND contact_phone = ?",
        (PHONE_NUMBER_ID, CONTACT),
    ).fetchone()
    return int(row["id"])


def _print_new_replies(after_id: int, wait: float) -> None:
    """Poll instead of sleeping blind: the debounce plus a model call is not a fixed cost."""
    deadline = time.monotonic() + wait
    seen: set[int] = set()
    while time.monotonic() < deadline:
        rows = _db().execute(
            "SELECT id, direction, text FROM message"
            " WHERE phone_number_id = ? AND contact_phone = ? AND id > ?"
            " AND direction = 'outbound' ORDER BY id",
            (PHONE_NUMBER_ID, CONTACT, after_id),
        ).fetchall()
        for row in rows:
            if row["id"] not in seen:
                seen.add(row["id"])
                print(f"← {row['text']}")
        if seen:
            deadline = min(deadline, time.monotonic() + 3)
        time.sleep(0.5)
    if not seen:
        print("  (sin respuesta — mirá los logs del contenedor)")


# -------------------------------------------------------------------- calendly


def cmd_tokens(_args: argparse.Namespace) -> int:
    rows = _db().execute(
        "SELECT token, slot_utc, created_at FROM booking_token"
        " WHERE phone_number_id = ? AND contact_phone = ? ORDER BY created_at DESC",
        (PHONE_NUMBER_ID, CONTACT),
    ).fetchall()
    if not rows:
        print("(sin tokens — pedile un horario al bot primero)")
        return 1
    for row in rows:
        print(f"{row['token']}  slot={row['slot_utc']}  emitido={row['created_at']}")
    return 0


def _newest_token() -> sqlite3.Row | None:
    return _db().execute(
        "SELECT token, slot_utc FROM booking_token"
        " WHERE phone_number_id = ? AND contact_phone = ?"
        " ORDER BY created_at DESC LIMIT 1",
        (PHONE_NUMBER_ID, CONTACT),
    ).fetchone()


def _post_calendly(payload: dict) -> int:
    """Sign exactly the way Calendly does: HMAC over f"{t}.{raw_body}"."""
    key = os.environ.get("CALENDLY_SIGNING_KEY", "")
    if not key:
        print("CALENDLY_SIGNING_KEY está vacía: el webhook va a rechazar todo (401).")
        print("Poné cualquier valor en .env para probar en local y reiniciá el contenedor.")
        return 1
    body = json.dumps(payload).encode()
    stamp = str(int(time.time()))
    digest = hmac.new(key.encode(), f"{stamp}.".encode() + body, hashlib.sha256).hexdigest()
    response = httpx.post(
        f"{BASE_URL}/webhook/calendly",
        content=body,
        headers={
            "Calendly-Webhook-Signature": f"t={stamp},v1={digest}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    print(f"  webhook: {response.status_code}")
    return 0 if response.status_code == 200 else 1


def cmd_book(args: argparse.Namespace) -> int:
    token, slot = args.token, args.slot
    if token is None:
        row = _newest_token()
        if row is None:
            print("(sin tokens — pedile un horario al bot primero)")
            return 1
        token, slot = row["token"], row["slot_utc"]
    event = args.event or f"https://api.calendly.com/scheduled_events/{uuid.uuid4()}"
    print(f"→ invitee.created  token={token}")
    # Captured before the POST: printing from `last - 1` would re-show the previous
    # message and make an idempotent replay look like a duplicate send.
    before = _last_message_id()
    code = _post_calendly(
        {
            "event": "invitee.created",
            "payload": {
                "event": event,
                "name": args.name,
                "email": args.email,
                "tracking": {"utm_content": token},
                "scheduled_event": {"start_time": slot} if slot else {},
            },
        }
    )
    if code == 0:
        _print_new_replies(before, 5)
        print(f"  event_uri: {event}")
    return code


def cmd_cancel(args: argparse.Namespace) -> int:
    event = args.event or _latest_event_uri()
    if event is None:
        print("(no hay cita registrada que cancelar)")
        return 1
    print(f"→ invitee.canceled  event={event}")
    before = _last_message_id()
    code = _post_calendly({"event": "invitee.canceled", "payload": {"event": event}})
    if code == 0:
        _print_new_replies(before, 5)
    return code


def _latest_event_uri() -> str | None:
    row = _db().execute(
        "SELECT calendly_event_id FROM appointment"
        " WHERE phone_number_id = ? AND contact_phone = ? AND status = 'scheduled'"
        " ORDER BY id DESC LIMIT 1",
        (PHONE_NUMBER_ID, CONTACT),
    ).fetchone()
    return row["calendly_event_id"] if row else None


# ----------------------------------------------------------------------- state


def cmd_state(_args: argparse.Namespace) -> int:
    conn = _db()
    where = (PHONE_NUMBER_ID, CONTACT)
    print(f"contacto: {CONTACT}\n")

    print("-- perfil --")
    profile = conn.execute(
        "SELECT name, email, kind, appointment_count, next_appointment_utc, handoff_state"
        " FROM profile WHERE phone_number_id = ? AND contact_phone = ?",
        where,
    ).fetchone()
    print(dict(profile) if profile else "(sin perfil todavía)")

    print("\n-- citas --")
    rows = conn.execute(
        "SELECT slot_utc, status, calendly_event_id FROM appointment"
        " WHERE phone_number_id = ? AND contact_phone = ? ORDER BY id",
        where,
    ).fetchall()
    for row in rows or []:
        print(f"{row['slot_utc']}  {row['status']}  {row['calendly_event_id']}")
    if not rows:
        print("(ninguna)")

    print("\n-- mute --")
    mute = conn.execute(
        "SELECT muted_at, muted_until FROM mute WHERE phone_number_id = ? AND contact_phone = ?",
        where,
    ).fetchone()
    print(dict(mute) if mute else "(el bot responde)")

    print("\n-- resumen --")
    summary = conn.execute(
        "SELECT watermark_message_id, text FROM summary"
        " WHERE phone_number_id = ? AND contact_phone = ?",
        where,
    ).fetchone()
    print(f"watermark={summary['watermark_message_id']}\n{summary['text']}" if summary
          else "(sin compactar todavía)")

    print("\n-- últimos 10 mensajes --")
    for row in conn.execute(
        "SELECT direction, text FROM message"
        " WHERE phone_number_id = ? AND contact_phone = ? ORDER BY id DESC LIMIT 10",
        where,
    ).fetchall()[::-1]:
        arrow = "→" if row["direction"] == "inbound" else "←"
        print(f"{arrow} {row['text']}")
    return 0


def cmd_traces(args: argparse.Namespace) -> int:
    """Model calls, newest first, grouped by turn — cost and latency per turn."""
    rows = _db().execute(
        "SELECT turn_id, model, tokens_in, tokens_out, cache_read_tokens, latency_ms,"
        " stop_reason, tools_called, created_at FROM llm_trace"
        " ORDER BY id DESC LIMIT ?",
        (args.limit,),
    ).fetchall()
    if not rows:
        print("(sin trazas todavía)")
        return 1
    current = object()
    for row in rows:
        if row["turn_id"] != current:
            current = row["turn_id"]
            print(f"\n=== turno {current or '(sin id)'} ===")
        tools = json.loads(row["tools_called"] or "[]")
        print(
            f"  {row['model']:<28} in={row['tokens_in']:<6} out={row['tokens_out']:<5}"
            f" cache={row['cache_read_tokens']:<6} {row['latency_ms']:>5}ms"
            f"  stop={row['stop_reason']}"
            + (f"  tools={','.join(tools)}" if tools else "")
        )
    return 0


def cmd_reset(_args: argparse.Namespace) -> int:
    """Start a clean conversation. Touches only the test contact."""
    conn = _db()
    where = (PHONE_NUMBER_ID, CONTACT)
    with conn:
        for table in ("message", "summary", "appointment", "booking_token", "mute", "profile"):
            conn.execute(
                f"DELETE FROM {table} WHERE phone_number_id = ? AND contact_phone = ?", where
            )
    print(f"listo: {CONTACT} vuelve a ser un contacto nuevo")
    print("nota: el bot sigue muteado a nivel número o global si lo dejaste así en el panel")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    subs = parser.add_subparsers(dest="command", required=True)

    msg = subs.add_parser("msg", help="mensaje entrante del paciente")
    msg.add_argument("text")
    msg.add_argument("--wait", type=float, default=45, help="segundos a esperar la respuesta")
    msg.set_defaults(func=cmd_msg)

    subs.add_parser("tokens", help="tokens de reserva emitidos").set_defaults(func=cmd_tokens)

    book = subs.add_parser("book", help="simular que el paciente completó la reserva")
    book.add_argument("token", nargs="?")
    book.add_argument("--slot", help="ISO UTC; por defecto el del token")
    book.add_argument("--event", help="event uri; por defecto uno nuevo")
    book.add_argument("--name", default="Paciente de Prueba")
    book.add_argument("--email", default="prueba@example.com")
    book.set_defaults(func=cmd_book)

    cancel = subs.add_parser("cancel", help="simular una cancelación en Calendly")
    cancel.add_argument("event", nargs="?")
    cancel.set_defaults(func=cmd_cancel)

    subs.add_parser("state", help="qué sabe la base del contacto").set_defaults(func=cmd_state)

    traces = subs.add_parser("traces", help="llamadas al modelo agrupadas por turno")
    traces.add_argument("--limit", type=int, default=20)
    traces.set_defaults(func=cmd_traces)
    subs.add_parser("reset", help="borrar el historial del contacto de prueba").set_defaults(
        func=cmd_reset
    )

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
