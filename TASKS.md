# TASKS.md — the backlog

Ordered. Each task is written to be handed to an implementer **as is**, with no context
beyond `PROJECT.md`, `SPEC.md`, `QWEN.md` and this file. Work top to bottom; a task says
when it is independent.

`SPEC.md` is the contract. Section references below (§4, §5, …) point into it — read the
section before starting, and **do not contradict it**. If the spec is wrong or missing
something, say so instead of improvising.

Mark progress: `[ ]` not started · `[~]` in progress · `[x]` done. When done, check it,
add `→ result: <one line>`, and update `STATE.md`.

Every task ends the same way: tests pass, `code-simplification` applied to the new code
only, nothing committed.

---

## [x] T1 — Skeleton and layer scaffolding

→ result: scaffold live — pyproject (hatchling/src layout/dev extras), all §3 packages,
`config.py` (§12 settings, boot fails on missing values and on the `<<pendiente>>` crisis
message), `logging_setup.py` (JSON logs, deny-list redaction, phone hash+last2), `app.py`
factory + `web/health.py` (version + SQLite probe), AST layer test for §2.1, `.env.example`,
README. 16 tests green; `/health` verified live under uvicorn; layer test verified to fail
on an injected `from ..services import x` in `domain/`.

The empty shape of §2 and §3, so nothing lands in the wrong place later.

- `pyproject.toml`: package `agente`, `src/` layout, hatchling, Python ≥3.11. Deps:
  `anthropic`, `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `httpx`, `jinja2`.
  Dev: `pytest`, `pytest-asyncio`, `freezegun` (or an injected clock fake), `ruff`.
- Create every package in §3 with `__init__.py` and a one-line docstring naming its
  responsibility. Empty is fine; the map is the deliverable.
- `config.py`: `Settings` covering §12, loaded once, injected — no import-time singleton.
  Every field mirrored in `.env.example` with a dummy value. Boot fails loudly on missing
  required settings and on a placeholder crisis message.
- `logging_setup.py`: structured logging with the redaction filter of §11 — a deny-list of
  field keys, phone numbers rendered as hash + last two digits. Message bodies can never
  be logged, even by mistake.
- `app.py`: FastAPI factory with lifespan; `GET /health` reports version and database
  reachability.
- A ruff config and an import-linter-style test asserting the layer rule of §2.1:
  `domain/` imports nothing from `web/`, `services/`, `adapters/`. A plain test that walks
  the AST of `domain/*.py` is enough — no new dependency needed.
- `README.md`: install, run, test. Ten lines. No architecture prose.

Acceptance: `pip install -e ".[dev]"`, `pytest -q` green, `uvicorn agente.app:app` serves
`/health`, and the layer test fails if you add `from ..services import x` to a domain
module (verify by trying it, then remove).

## [x] T2 — Storage foundation

→ result: `adapters/store/` live — `db.py` (connect WAL+FK, idempotent `migrate()`
with `schema_version`, health probe), migration `0001` with every §10 table and the
dedupe/window/outbox-due indexes, six repository protocols in `ports/store.py`,
mutes (global→number→contact with expiry, one audit row per mutation), messages
(dedupe by kapso id, window reads), contacts/profiles implemented; summaries,
appointments and traces stubbed until their tasks. Migrations run at app boot and a
dead database degrades `/health` instead of killing the app. 52 tests green; no SQL
outside `adapters/store/`.

§10. All of it behind repositories; no SQL escapes the store package.

- `adapters/store/db.py`: connection factory, WAL, foreign keys on, `migrate()` applying
  `migrations/NNNN_*.sql` in order, idempotent, recording applied versions.
- Migration `0001`: every table in §10. UTC ISO-8601 strings for times. Indexes for the
  lookups the code actually does (dedupe by kapso message id; window read by contact and
  time; due rows in `outbox`).
- `ports/store.py`: one Protocol per repository — contacts, messages, summaries, mutes,
  appointments, traces.
- Implement `store/contacts.py`, `store/messages.py`, `store/mutes.py` now; the rest may
  raise `NotImplementedError` until their task.
- `store/mutes.py`: `is_bot_muted(contact_key, now)` resolving global → number → contact
  with expiry; `set_mute`, `clear_mute`, `set_number_mute`, `set_global`, each writing
  exactly one `audit_log` row.
- Tests on a temp-file database: three-level precedence, `muted_until` boundary at exactly
  now, dedupe uniqueness on kapso message id, one audit row per mutation.

Acceptance: `pytest -q` green; grep finds no SQL outside `adapters/store/`.

## [x] T3 — Domain logic

→ result: pure `domain/` modules live — `contacts` normalizes E.164 identity and
masks logs; `scheduling` renders local labels, samples slots broadly and honours the
booking buffer; `memory` plans token-budget compaction with overlap; `reply` emits at
most three nonempty sentence-safe chunks; `crisis` exposes the strict verdict type.
Explicit DST, buffer-edge, token-budget and no-paragraph tests are green (107 total).

§2.6 and the pure parts of §8 and §9. **No I/O anywhere in this task** — these tests need
no fakes at all.

- `domain/contacts.py`: `ContactKey`, phone normalization to E.164, masking for logs.
- `domain/scheduling.py`: local-time labels for slots, part-of-day bucketing, the broad
  sampling rule of §6 (cap ~12 slots, at most 2 per part of day, spread across days), and
  a `is_bookable(slot, now, buffer)` that rejects past slots and slots inside the buffer.
  All timezone-aware, clock injected.
- `domain/memory.py`: the window policy of §9 — given turns and a token budget, decide
  what stays verbatim, what compacts, and where the overlap sits. Pure function over a
  token-estimate callable.
- `domain/reply.py`: chunking per §8 — at most 3 chunks, paragraph boundaries, never
  mid-sentence, never empty.
- `domain/errors.py`, `domain/crisis.py`: the types.

Tests: frozen clock, explicit DST transition cases for the clinic timezone, a slot exactly
at the buffer edge, a window of ten one-word turns versus ten long turns producing
different decisions, and a reply with no paragraph breaks.

Acceptance: `pytest -q` green; `domain/` tests import nothing from `adapters/` or
`services/`.

## [x] T4 — Kapso adapter

Independent of T2 and T3; needs T1. §3, §11.
→ result: payloads (15 tests) + client (10 tests) + channel protocol live —
`adapters/kapso/payloads.py` Pydantic models for single/batch webhook with
`extra="allow"`, HMAC-SHA256 verification (case-insensitive header lookup),
`parse_webhook` dispatching and `KapsoError` on forged/malformed input;
`adapters/kapso/client.py` async httpx with 10s timeout, `send_text` → kapso_message_id,
paginated `list_conversations` → typed rows, every httpx failure → KapsoError, structured
safe logs; `ports/channel.py` Channel Protocol. All time injected, no network, no real send.
25 tests green.

- `adapters/kapso/payloads.py`: Pydantic models for `whatsapp.message.received`, both the
  single form and the batched form (`X-Webhook-Batch: true`,
  `{batch: true, data: [...]}`), plus webhook authenticity verification.
- `adapters/kapso/client.py`: async `httpx`, explicit timeout on every call.
  - `send_text(phone_number_id, to, body) -> kapso_message_id`
  - `list_conversations(phone_number_id, cursor, limit)` → typed rows: contact name,
    contact phone, last message text, last activity, status.
- Translate every `httpx` failure into `KapsoError`. One structured log line per call, no
  body, no full phone number.
- `ports/channel.py`: the Protocol the services depend on; the client satisfies it.

Tests with `httpx.MockTransport`: batched and single payloads, a rejected forged webhook,
a timeout surfacing as `KapsoError`, pagination. **No network, no real send, ever.**

Acceptance: `pytest -q` green; services can be written against `ports/channel.py` alone.

---

# ⛔ STOP — human review required

**`/next` must not cross this line.** Everything above (T1–T4) is foundation: disjoint
paths, contracts fixed by the spec, and tests that verify behaviour rather than shape. It
is safe to run unattended.

Everything below needs a human between tasks, for reasons stated in each task. If you
reach this line in an autonomous run: stop, report that the foundation is complete, and
say what a reviewer should look at first.

To lift the barrier, a human moves this block down past the tasks they have approved.

---

## [x] T5 — Control panel

→ result: authenticated mobile-first Jinja2/HTMX panel live — signed expiring session,
local HTMX/static assets, live Kapso conversation list, contact/number/global mute controls
with audit and expiry display, and traces placeholder. 3 behavioral panel tests green.

Needs T2 and T4. §3, §11, and the panel decision in `PROJECT.md`.

- `web/auth.py`: shared password from settings, signed session cookie, dependency that
  guards every `/admin` route. No password in URLs or logs.
- `GET /admin`: conversations read **live** from Kapso (never mirrored), each row showing
  contact name, masked phone, last activity, and a toggle reflecting local mute state.
  Global kill switch pinned at the top.
- `POST /admin/mute`, `POST /admin/number-mute`, `POST /admin/global`: HTMX endpoints
  returning the updated fragment. Each records the actor in `audit_log`. Optional expiry
  on a mute.
- `GET /admin/traces`: the LLM trace list from `llm_trace` (empty until T8).
- **Mobile first**: design the phone layout first — one column, thumb-sized toggles, no
  horizontal scroll, legible without zoom. Desktop is the same page, wider.
- Jinja2 templates, HTMX served from `web/static/`. No CDN, no build step.

Tests: every route 401s without a session; a toggle round-trip changes `is_bot_muted`; the
list renders with the Kapso client faked; expiry renders correctly.

Acceptance: `pytest -q` green; the page is usable at 375px wide.

## [x] T6 — Inbound pipeline with the mute gate

→ result: authenticated background webhook and debounced per-contact inbound pipeline live;
dedupe, persistence, mute gate, response send/persistence and one fallback covered by tests.

Needs T2, T3, T4. §4. **This is the spine — read §4 in full before starting.**

- `web/webhooks.py`: `POST /webhook/kapso` verifies, parses, acks 200 immediately, and
  hands off to background processing.
- `services/inbound.py`: steps 1–5 and 8 of §4 — dedupe, persist inbound, mute gate,
  debounce/merge, send, persist outbound. Steps 6 and 7 (crisis, agent) are called through
  seams that are stubbed in this task: a stub crisis check returning `none` and a stub
  responder returning a fixed string.
- Per-contact locking so one turn is in flight at a time; a burst during processing joins
  the next turn's buffer.
- Fallback behaviour and the wide event of §11 on every turn.

Tests against fake ports: duplicate message id produces exactly one reply; muted contact
produces zero model calls and zero sends but the inbound is stored; a three-message burst
inside the debounce window produces one merged turn; a send failure logs and does not
retry blindly.

Acceptance: `pytest -q` green; the pipeline is exercised end to end with no network.

## [x] T7 — Knowledge: playbook and wiki

→ result: clinic-safe placeholder content plus deterministic section loader, TOC and lookup live.

Needs T1. §5, §6.

- `content/playbook.md` and `content/wiki.md` as **structured placeholders** with the real
  section skeleton (services, modality, pricing, logistics, policies, what the bot must
  never answer) and obvious `<<pendiente: definir con la clínica>>` markers. Do **not**
  invent clinic facts — inventing prices or clinical claims is the worst failure this
  project can produce.
- `services/knowledge.py`: load both at startup, parse the wiki into sections by heading,
  build the table of contents string that goes in system block 1, and expose a
  deterministic `find_sections(query) -> list[Section]` over headings and keywords. **No
  model call, no embeddings.**
- Returns at most 2 sections, says when it truncated, and says plainly when nothing
  matched.

Tests: TOC generation, exact and fuzzy-ish heading matches, no-match wording, truncation
wording, and a wiki with a malformed heading not crashing the loader.

Acceptance: `pytest -q` green; swapping the wiki file changes the TOC with no code change.

## [ ] T8 — Anthropic adapter and the agent loop

Needs T3, T7. §5, §11. The heart of the migration.

- `adapters/anthropic/client.py`: Messages API behind `ports/model.py`. Handles the
  system-block list with cache breakpoints (§5), tool definitions, tool-result turns, and
  translates failures into `ModelError`. Writes one `llm_trace` row per call: model,
  tokens in/out, cache read/write, latency, stop reason, tools called, turn id.
- `services/agent.py`: the loop — call, execute tools while stop reason is `tool_use`,
  append results, repeat, capped at `max_iterations`; on cap, fallback text plus a wide
  event. Tool turns are ephemeral and never persisted; only the final assistant text is
  memory.
- System assembly per §5: block 1 core + playbook + wiki TOC, block 2 profile, block 3
  summary — each a cache breakpoint, in that order.
- Wire the real responder into `services/inbound.py`, replacing T6's stub.

Tests with a scripted fake model: a two-round tool conversation, hitting the iteration cap
produces the fallback exactly once, a tool raising produces a readable tool-result rather
than a crash, and the system blocks are assembled in the specified order with breakpoints.

Acceptance: `pytest -q` green; no `anthropic` import outside `adapters/anthropic/`.

## [ ] T9 — Calendly adapter and the scheduling tools

Needs T3, T8. §6. **The highest-risk area — v2's real bugs lived here.**

- `adapters/calendly/client.py`: availability for the configured event type, invitee
  creation with the location kind the event type requires, HMAC signature verification in
  `signature.py`, everything behind `ports/calendar.py`, failures as `CalendlyError`.
- `tools/ver_horarios.py`: availability → `domain/scheduling.py` sampling → local labels
  with a stable slot id. Never a raw dump, never UTC, never a past slot.
- `tools/agendar_cita.py`: preflight that the slot is still future and still free; create
  the invitee; write the appointment to the profile and the `appointment` table;
  idempotent per `(contact, slot_id)`; on conflict return an actionable message with
  alternatives, not a stack trace.
- `POST /webhook/calendly`: verify token and HMAC, update appointment status on
  cancel/reschedule.

Tests: mocked transport; a slot that expires between listing and booking; double booking
the same `(contact, slot_id)` creating exactly one invitee; DST boundary; a forged webhook
signature rejected.

Acceptance: `pytest -q` green; no real Calendly call in any test.

## [ ] T10 — Remaining tools: wiki lookup and escalation

Needs T7, T8. §6.

- `tools/buscar_wiki.py` over `services/knowledge.py`.
- `tools/escalar_a_humano.py`: mute the contact, audit the reason, return the text the
  model reads back to the patient. The human continues in the Kapso Inbox.
- Register both in the tool surface with Spanish names and descriptions written *for the
  model* — when to reach for it, when not to.

Tests: escalation actually mutes and audits; the wiki tool returns the no-match wording
rather than an empty string.

Acceptance: `pytest -q` green.

## [ ] T11 — Crisis gate

Needs T8. §7.

- `services/crisis.py`: one Haiku call on the merged inbound text, strict enum output
  (`none | possible | acute`) parsed by schema, not string matching.
- Wire into §4 step 6: `acute` short-circuits (crisis message verbatim, mute, urgent
  audit, no agent); `possible` appends the playbook's crisis directives as a fourth system
  block for that turn; `none` proceeds.
- **Fail closed**: an error or timeout is `possible`, never `none`.

Tests: each verdict's branch, a timeout treated as `possible`, `acute` producing zero
agent calls, and the crisis message sent verbatim with no model paraphrase.

Acceptance: `pytest -q` green; a configured placeholder crisis message fails at boot.

## [ ] T12 — Compaction

Needs T3, T8. §9.

- `services/compaction.py`: triggered by token budget, runs off the reply path, summarizes
  in Haiku with a prompt that forbids inventing and forbids restating profile facts,
  writes `summary` with its watermark, keeps the overlap.
- Non-fatal on failure: keep the longer window, retry next turn.

Tests with a fake model and a fake token estimator: the trigger fires at the budget and
not before, the watermark advances correctly, overlap is preserved, and a failing
summarizer leaves the window intact.

Acceptance: `pytest -q` green.

## [ ] T13 — Deployment

Needs everything above. §15.

- `Dockerfile`: one process, non-root, no dev dependencies in the image.
- `docker-compose.yml` for local: the app plus a mounted volume for the SQLite file.
- Document in `README.md`: the Coolify **persistent volume** requirement (without it, a
  redeploy erases everything), the required environment variables, and the one-time
  operator step of pointing the Kapso webhook at the deployed URL — including that
  `kapso whatsapp webhooks new` is run **by a human, never by an agent**.
- `GET /health` verifies the database file is writable.

Acceptance: `docker build` succeeds and the container serves `/health`.

---

## Blocked, not ready

- **Reminders / proactive outbound** — out of v3 by decision (§13). The `outbox` table and
  the dispatcher seam exist. Needs a product decision plus an approved WhatsApp template
  before it becomes a task.
- **Retention and deletion** — how long our copy of history lives, and what a deletion
  request does. Open question in `PROJECT.md`.
- **SQLite backups** — who takes them and how. Open question in `PROJECT.md`.
