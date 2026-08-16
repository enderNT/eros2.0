# TASKS.md — the backlog

Ordered. Each task is written to be handed to an implementer **as is**, with no other
context than `PROJECT.md`, `QWEN.md` and this file. Work top to bottom; do not skip ahead
unless a task says it is independent.

Mark progress by editing the checkbox and adding a one-line result under the task:

- `[ ]` not started · `[~]` in progress · `[x]` done

When a task is done: check it, add `→ result: <one line>`, and update `STATE.md`.

If a task turns out to be underspecified, **stop and write what is missing under it**
rather than inventing the answer. Tasks marked *spec pending* are not ready — they need a
design conversation first.

---

## [ ] T1 — Project skeleton

Create the minimal runnable service. No business logic.

- `pyproject.toml`: package `agente`, `src/` layout, hatchling, Python ≥3.11.
  Dependencies: `anthropic`, `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`,
  `jinja2`. Dev extra: `pytest`, `pytest-asyncio`, `httpx` test client.
- `src/agente/config.py`: `Settings` via `pydantic-settings`, loaded once. Fields for
  Kapso API key and phone number id, Anthropic API key and model names, SQLite path,
  panel password, log level. Every field mirrored in `.env.example` with a dummy value.
- `src/agente/app.py`: FastAPI app with `GET /health` returning version and a liveness
  check of the SQLite file.
- `tests/test_health.py`: health returns 200 and the expected shape.
- `README.md`: how to install, run and test, in ten lines. No architecture prose — that
  lives in `PROJECT.md`.

Acceptance: `pip install -e ".[dev]"` then `pytest -q` passes, and
`uvicorn agente.app:app` serves `/health`.

## [ ] T2 — Storage layer and mute state

One SQLite file, all access behind a repository module so a future Postgres move touches
one place.

- `src/agente/db.py`: connection factory, WAL mode, foreign keys on, a `migrate()` that
  applies ordered SQL migrations from `migrations/` and is safe to run at every startup.
- Schema, migration `0001`:
  - `mute(phone_number_id, contact_phone, muted, muted_until, reason, updated_at,
    updated_by)` — primary key `(phone_number_id, contact_phone)`.
  - `number_mute(phone_number_id PK, muted, muted_until, reason, updated_at, updated_by)`.
  - `global_state(id PK CHECK(id=1), bot_enabled, updated_at, updated_by)` — single row.
  - `audit_log(id, at, actor, action, target, detail)`.
- `src/agente/store/mutes.py`: `is_bot_muted(phone_number_id, contact_phone) -> bool`
  resolving the three levels in order (global → number → contact) and honouring expiry;
  `set_mute(...)`, `clear_mute(...)`, `set_global(...)`, each writing an audit row.
- Tests with a temp-file database: expiry boundary (`muted_until` in the past means not
  muted), precedence of the three levels, and that every mutation writes exactly one audit
  row.

Acceptance: `pytest -q` passes; no SQL outside the store package.

## [ ] T3 — Kapso client

Independent of T2; needs T1.

- `src/agente/kapso.py`: async `httpx` client with an explicit timeout on every call.
  - `send_text(phone_number_id, to, body)` → returns the Kapso message id.
  - `list_conversations(phone_number_id, cursor=None, limit=...)` → typed results with
    contact name, contact phone, last message text and timestamp, status.
  - Pydantic models for the inbound `whatsapp.message.received` payload, including the
    buffered/batch form (`X-Webhook-Batch: true`, `{batch: true, data: [...]}`).
- Errors: a domain `KapsoError` at the boundary; never leak `httpx` exceptions upward.
- Logging: one structured event per call — never the message body, never the full phone
  number.
- Tests against a mocked transport (`httpx.MockTransport`). **No network in tests, and
  never a real send.**

Acceptance: `pytest -q` passes; sending is exercised only against the mock.

## [ ] T4 — Control panel

Needs T2 and T3. This is the operator switchboard described in `PROJECT.md`.

- `GET /admin` — list of conversations read live from the Kapso API, each row showing
  contact name, masked phone, last message time, and a bot on/off toggle reflecting the
  local mute state. Global kill switch pinned at the top.
- `POST /admin/mute` and `POST /admin/global` — HTMX endpoints returning the updated row
  or switch fragment. Every action records the actor in the audit log.
- Auth from the first commit: shared password from settings, signed session cookie,
  every `/admin` route behind it. No password in the URL, no password in logs.
- **Mobile first.** Design the phone layout first: one column, thumb-sized toggles, no
  horizontal scroll, readable without zoom. Desktop is a widened version of the same page.
- Jinja2 templates plus HTMX loaded as a local static file — no CDN.
- Tests: auth required on every route, toggle round-trip changes `is_bot_muted`, the list
  renders with the Kapso client mocked.

Acceptance: `pytest -q` passes; the page works with JavaScript limited to HTMX.

## [ ] T5 — Inbound webhook and the mute gate

Needs T2 and T3.

- `POST /webhook/kapso`: verify authenticity, parse single and batched payloads, ack fast
  (return 200 before doing model work), and drop anything already seen (dedupe by message
  id).
- First thing after parsing: `is_bot_muted(...)`. If muted, persist the inbound message
  for context and **do not reply**. This gate runs before any model call.
- Tests: batched payload, duplicate delivery, muted contact produces no outbound call.

Acceptance: `pytest -q` passes; a muted contact never reaches the model path.

## [ ] T6 — Agent loop — *spec pending*

Blocked on the design conversation about the shape of the loop (crisis gate, tools, reply
path, the wiki in the cached prompt, the two-layer memory). Do not start this from
`PROJECT.md` alone.
