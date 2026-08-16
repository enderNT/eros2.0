# SPEC.md — technical specification, v3

What to build and how the pieces fit. `PROJECT.md` holds the *why* and the closed
decisions; this file is the contract an implementer works from. If the two disagree,
`PROJECT.md` wins and this file is wrong.

Most of this is a **migration**: v2 already proved the shape of the conversation. What
changes is the channel (Kapso), the storage (SQLite), the human handoff (our own switch),
and the discipline — v2 grew into modules that did five things each. The rules in §2 exist
to prevent that specific failure from happening again.

---

## 1. Vocabulary

| Term | Meaning |
|---|---|
| **Contact** | A person, identified by `(phone_number_id, contact_phone)`. The stable unit — survives conversations. |
| **Conversation** | Kapso's 24h-window thread. Ends on inactivity; a new one opens on the next message. **Never a key for our state.** |
| **Turn** | One inbound message and the reply it produced. |
| **Profile** | Small durable structured record per contact. Survives everything. |
| **Window** | The last N turns, verbatim, sent to the model. |
| **Summary** | Rolling compaction of everything older than the window. Lossy by design. |
| **Playbook** | Behaviour directives for the model: identity, tone, red lines. Stable, cached. |
| **Wiki** | Clinic facts as markdown sections: services, prices, logistics. Read by tool. |
| **Mute** | The bot is silenced for a contact, a number, or globally. |

Language rule: **code is English** — identifiers, modules, comments, log keys. Spanish
appears only where a human or the model reads it: prompts, playbook, wiki, tool names and
tool descriptions (they are part of the prompt surface), and user-facing text. Do not mix
the two inside an identifier.

## 2. Architecture rules

These are the anti-monolith rules. They are testable, and a reviewer should reject code
that breaks them.

1. **Four layers, dependencies point one way only:**

   ```
   web/      FastAPI routes, request/response models, templates   → depends on services
   services/ use cases: handle_inbound, reply, mute, schedule     → depends on domain+ports
   domain/   pure logic: window policy, time rules, redaction     → depends on nothing
   adapters/ kapso, anthropic, calendly, sqlite store             → depends on domain
   ```

   `domain/` imports nothing from the other three. A test for `domain/` needs no fakes,
   no I/O, no event loop. If a rule is hard to test, it is in the wrong layer.

2. **One reason to change per module.** A module that both talks HTTP and decides
   business outcomes is split. Soft ceiling: 200 lines; at 300 it is a defect, not a
   style preference. v2's `tools.py` was 20KB — that is the thing we are not repeating.

3. **All I/O behind a port.** Anthropic, Kapso, Calendly and the database are each
   reached through one adapter module with a narrow interface. Services never import
   `httpx`, never write SQL, never touch `anthropic` types.

4. **No global mutable state.** Settings are loaded once and injected. No module-level
   client singletons created at import time; construct them in the app lifespan and pass
   them down.

5. **Errors are domain types at boundaries.** Adapters translate their library's
   exceptions into `KapsoError`, `CalendlyError`, `ModelError`, `StoreError`. Services
   never see `httpx.HTTPError`. No bare `except`, no silent `pass`.

6. **Time and randomness are injected.** Every function that needs "now" takes a clock.
   This is not ceremony: v2's real bugs were timezone bugs, and they are only testable
   with a frozen clock.

7. **Async at the edges, sync in the middle.** Routes and adapters are `async`; domain
   logic is plain synchronous functions.

## 3. Module map

```
src/agente/
  config.py              Settings (pydantic-settings), loaded once
  app.py                 FastAPI factory, lifespan, router mounting
  logging_setup.py       structlog-style wide-event logging, redaction filters

  domain/
    contacts.py          ContactKey, phone normalization and masking
    memory.py            window/summary policy: what goes verbatim, what compacts, when
    scheduling.py        slot math, timezone rules, human-readable slot labels
    crisis.py            crisis verdict type and escalation rules
    reply.py             splitting a reply into WhatsApp-sized chunks
    errors.py            domain exception types

  ports/
    channel.py           Protocol: send_text, list_conversations
    model.py             Protocol: complete(system, messages, tools) -> ModelReply
    calendar.py          Protocol: availability, create_invitee
    store.py             Protocols for each repository

  adapters/
    kapso/client.py      HTTP client
    kapso/payloads.py    inbound webhook models, single and batched
    anthropic/client.py  Messages API, cache breakpoints, tool plumbing
    calendly/client.py   availability + invitee creation
    calendly/signature.py HMAC verification
    store/db.py          connection, WAL, migrate()
    store/contacts.py    profile repository
    store/messages.py    turns, dedupe, window reads
    store/summaries.py   rolling summaries
    store/mutes.py       three-level mute resolution + audit
    store/traces.py      LLM call traces

  services/
    inbound.py           the pipeline of §4 — the only orchestrator
    agent.py             the model loop of §5
    crisis.py            the pre-gate
    compaction.py        summary maintenance
    mutes.py             mute use cases
    knowledge.py         playbook + wiki loading and section lookup

  tools/                 the model's tool surface (§6), one file per tool
  web/
    webhooks.py          POST /webhook/kapso, POST /webhook/calendly
    panel.py             GET /admin and the HTMX endpoints
    health.py            GET /health
    auth.py              panel session auth
    templates/           Jinja2, mobile-first
    static/              htmx.min.js — local, never a CDN
```

## 4. The inbound pipeline

`services/inbound.py` is the only place that knows the order of operations. Everything
else is called by it.

1. **Receive.** `POST /webhook/kapso` verifies authenticity, parses single or batched
   (`X-Webhook-Batch: true`) payloads, and returns **200 immediately**. Processing
   continues in the background — Kapso must never wait on a model call.
2. **Dedupe.** Drop messages whose Kapso message id was already stored. Webhooks retry;
   double-replying to a patient is the failure this prevents.
3. **Persist inbound.** The message is stored before anything can fail. Storage is
   append-only truth; everything downstream is derived.
4. **Mute gate.** `is_bot_muted(contact)` — global, then number, then contact, honouring
   expiry. If muted: stop. The message is already stored, so when the bot is unmuted the
   history is intact. **No model call happens behind a mute.**
5. **Debounce.** Wait a short window (default 4s, configurable) for more messages from the
   same contact and merge them into one turn. People send WhatsApp in bursts of three
   fragments; answering each one is the tell of a bot. Cancel and restart the timer on
   each new message; cap the merge at 5 messages or 20 seconds.
6. **Crisis gate.** §7. Runs before the agent, on the merged text. A positive verdict
   short-circuits: send the crisis message, mute the contact, escalate. The agent never
   runs.
7. **Agent.** §5. Produces reply text.
8. **Send.** Split into chunks (§8), send through Kapso in order, store each outbound
   message with its Kapso id — so an inbox reply by a human is distinguishable from ours
   later.
9. **Compaction.** If the window exceeds its token budget, schedule compaction (§9). Off
   the reply path — never make the patient wait for bookkeeping.

**Concurrency.** One in-flight turn per contact, enforced by a lock keyed on the contact.
A second burst while the agent is running joins the debounce buffer of the next turn
rather than racing it. SQLite has one writer: all writes go through the store layer, which
serializes them.

**Failure.** If the model or Kapso fails after retries: log a wide event with the failure,
leave the inbound stored, and send the fallback text once ("estoy teniendo un problema
técnico… ¿quieres que te conecte con una persona?"). Never retry a send blindly — sends
are not idempotent.

## 5. The agent loop

A ReAct loop over the Anthropic Messages API. Migrated from v2, which worked; the changes
are the model, the prompt assembly and where the wiki lives.

**Models** (all configurable, these are the defaults):

| Job | Model |
|---|---|
| Conversation | `claude-sonnet-5` |
| Crisis check | `claude-haiku-4-5-20251001` |
| Summarization | `claude-haiku-4-5-20251001` |

**System prompt, in blocks ordered by volatility, each a cache breakpoint:**

1. Core instruction + **playbook** + **wiki table of contents** — identical for every
   contact, so it caches once and is shared across all conversations.
2. **Profile** — per contact.
3. **Rolling summary** — per contact, when one exists.

The wiki's *index* is in block 1 so the model knows what it can look up; the wiki's
*content* is not — it is fetched by tool (§6). This is the middle ground between v2's
choice (everything by tool) and stuffing the whole wiki into context: cheap, cacheable,
and it scales past the point where the wiki would blow the budget. No embeddings, no
vector store — if lookup quality ever becomes the problem, improve the index, do not
reach for RAG.

**Messages** = the verbatim window (§9). Tool-use turns are ephemeral: they live inside
one loop execution and are **not** persisted. Only the final assistant text becomes memory.

**Loop:** call the model with the tool list; while the stop reason is `tool_use`, execute
the tools, append results, call again. Cap at `max_iterations` (default 6). On hitting the
cap, return the fallback text and log a wide event — a loop that spins is a bug to see,
not to hide.

**Every model call is traced** (§11): tokens in/out, cache hits, latency, tools called,
stop reason, and an id linking the trace to the turn.

## 6. Tool surface

Four tools, Spanish names because they are part of the prompt. Each lives in its own
module under `tools/`, exposes a schema and a handler, and returns a **string for the
model** — never a Python object, never a raw API response.

**`buscar_wiki(consulta)`** — returns the matching wiki sections. Deterministic lookup
over section headings and keywords; no model call inside a tool. Returns at most 2
sections and says so when it truncates. On no match, says so plainly so the model does not
invent an answer.

**`ver_horarios(preferencia?)`** — available slots from Calendly. Returns a small, spread
sample (v2's broad sampling: cap ~12 slots, at most 2 per part of day) rendered as local
day/time labels with a stable id per slot. Never dumps a raw availability list. Always in
the clinic's timezone, never UTC, and never a slot in the past — including the buffer that
prevents booking a slot that becomes past while the patient is typing.

**`agendar_cita(slot_id, nombre, correo)`** — books it. Preflight-validates the slot is
still in the future and still free; creates the Calendly invitee with the location the
event type requires; returns a confirmation the model can read back, or a specific,
actionable failure ("ese horario acaba de ocuparse, quedan estos otros"). Writes the
appointment to the profile. Idempotent per `(contact, slot_id)`.

**`escalar_a_humano(motivo)`** — mutes the bot for the contact, records the reason in the
audit log, and tells the patient a person will follow up. The human then works from the
Kapso Inbox.

## 7. Crisis gate

A single Haiku call on the merged inbound text, before the agent, with one job: is there
indication of risk to life. Output is a strict enum — `none | possible | acute` — parsed
with a schema, not with string matching.

- `acute`: send the clinic-provided crisis message verbatim, mute the contact, write an
  audit entry marked urgent. The agent does not run.
- `possible`: the agent runs, but the playbook's crisis directives are appended as a
  fourth system block for that turn.
- `none`: normal path.

The crisis message text is configuration, **written by the clinic, not by us**. Ship with
an obvious placeholder that fails loudly if it was never set.

Fail closed: if the crisis check errors or times out, treat it as `possible`, never as
`none`.

## 8. Reply shaping

WhatsApp replies read as chat, not as email. Rules, applied in `domain/reply.py`:

- Split on paragraph boundaries into at most 3 chunks; never split a sentence.
- A chunk over ~600 characters is a smell — the playbook tells the model to be brief, and
  the splitter is the safety net, not the strategy.
- Send chunks in order with a short inter-message delay so they arrive in a human rhythm.
- Never send an empty message; if the model returns nothing usable, send the fallback.

## 9. Memory

**Two layers, as decided.**

*Profile* (durable, structured, per contact): name, email, patient/prospect, timezone,
appointment count, last appointment, next appointment, handoff state, updated timestamps.
A confirmed appointment lives here — **never only in a summary.**

*Window and summary*: the last turns go to the model verbatim. Everything older is folded
into one rolling summary.

**The trigger is a token budget, not a message count** (this is the change from v2, which
counted messages: `history_window=10`, `compact_limit=16`, `overlap=1`). Estimate tokens
of the window; when it exceeds `window_token_budget`, compact the oldest turns until it
fits, keeping `overlap` turns of continuity. Rationale: ten one-word messages and ten
paragraphs are not the same context, and only one of them justifies a summarization call.

Compaction runs asynchronously, in Haiku, and its prompt forbids inventing and forbids
restating profile facts. A compaction failure is non-fatal: keep the longer window and
retry next turn.

## 10. Persistence

One SQLite file, WAL, foreign keys on, migrations in `migrations/NNNN_*.sql` applied at
startup and safe to re-run. Times are stored as UTC ISO-8601 strings; conversion to local
happens in `domain/scheduling.py` and nowhere else.

Tables:

- `contact` — `(phone_number_id, contact_phone)` PK, display name, timezone, created/updated.
- `profile` — one row per contact: the fields in §9, as columns, not as a JSON blob.
- `message` — every inbound and outbound: contact key, direction, kapso message id
  (unique, for dedupe), text, created_at, and whether we sent it.
- `summary` — one rolling summary per contact plus the turn watermark it covers.
- `mute` / `number_mute` / `global_state` — the three levels, with `muted_until`.
- `audit_log` — who did what, when, why. Mute flips, escalations, crisis events.
- `appointment` — contact, calendly event id, slot in UTC, status, created_at.
- `llm_trace` — one row per model call (§11).
- `outbox` — scheduled outbound messages. Empty in v3; the seam for reminders (§13).

## 11. Observability

One **wide event per turn**: a single structured log line carrying contact hash, phone
number id, message id, whether muted, crisis verdict, tools called, model, tokens in/out,
cache read/write tokens, iterations, latency per stage, outcome. One line you can grep for
an entire turn — the `logging-best-practices` skill's canonical log line.

**Redaction is enforced in the logger, not by discipline.** Message bodies are never
logged. Phone numbers are logged as a stable hash plus the last two digits. A filter drops
any field whose key is in the deny list, so a careless `log.info(..., text=body)` cannot
leak.

**LLM traces** go to the `llm_trace` table and are readable from a page in the panel.
v2 shipped a separate `log-viewer` container for this; v3 does not — same container, same
auth, one less thing to deploy.

## 12. Configuration

All settings via `pydantic-settings`, every one mirrored in `.env.example`. Groups:
Anthropic (key, three model names, max tokens, thinking, effort, `max_iterations`), Kapso
(API key, `phone_number_id`, webhook secret), Calendly (token, event type URI, timezone,
location kind and value, scheduling link, webhook token and signing key), storage (SQLite
path), panel (password, session secret), behaviour (debounce seconds, window token budget,
overlap, reply chunk limits, crisis message), logging (level).

Startup validates: missing required settings abort the boot with a clear message. A
placeholder crisis message is a hard failure, not a warning.

## 13. Explicitly out of v3

- **Reminders.** v2 had them (`lead_minutes=1440,10`, a 60s poller). They need an approved
  WhatsApp template to send outside the 24h window, which is a product decision that is
  not made. The `outbox` table and the dispatcher seam exist so this is an addition, not a
  redesign.
- **Chatwoot**, Postgres, the separate log-viewer container, LangGraph, the supervisor
  node, and the Twilio path. Gone; do not port them.
- Multi-number operation is designed for (the key includes `phone_number_id`) but not
  exercised until embedded signup.

## 14. Testing

- `domain/` — pure unit tests, no fakes. Timezone and slot math get a frozen clock and
  explicit DST cases.
- `services/` — tested against fake ports (in-memory channel, scripted model, fake clock).
  The pipeline of §4 is tested as a sequence: muted contact produces no model call; a
  duplicate message id produces no second reply; a crisis verdict short-circuits.
- `adapters/` — `httpx.MockTransport` for HTTP, a temp file for SQLite. **No network in
  any test, and no real send, ever.**
- `web/` — FastAPI test client: auth required on every panel route, webhook acks fast,
  malformed payloads return 4xx and are not processed.
- Every behaviour change ships with a test. A test that needs the network is a bug.

## 15. Deployment

One container, one process. `Dockerfile` builds the app; Coolify runs it with the SQLite
file on a **persistent volume** — without that volume, a redeploy erases every profile,
summary and mute. `GET /health` checks the database is reachable and reports the version.
The Kapso webhook is pointed at the deployed URL by an operator, by hand, once: the
webhook must be created with the number's secret and subscribed to
`whatsapp.message.received`. That is a `kapso whatsapp webhooks new` call — **an operator
action, never an agent action.**
