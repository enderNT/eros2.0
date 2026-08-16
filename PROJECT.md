# PROJECT.md — what we are building

Single high-level description of the project: the business, the scope, the stack and the
non-negotiable rules. Deliberately short. Detail lives in code, in the knowledge graph
(`codebase-memory-mcp`) and in the wiki once there is something to document.

This is the **third rewrite**. The repository was emptied on branch `v3-rebuild` on
purpose: nothing from the previous implementation is carried over unless we decide,
explicitly and case by case, that it earns its place.

---

## Business

A conversational assistant for a **psychology clinic**. It talks to patients and
prospective patients over WhatsApp and covers three jobs:

1. **Conversation** — greet, understand intent, keep the thread coherent across messages.
2. **Information / FAQ** — answer questions about the clinic: services, pricing,
   modality, logistics.
3. **Scheduling** — find real availability and book an appointment.

Two cross-cutting behaviors that are not features but obligations:

- **Crisis detection.** If a message suggests risk (self-harm, suicidal ideation, acute
  emergency), the assistant stops trying to be useful and follows the escalation path.
- **Human handoff.** The bot must be able to step aside — silently, and stay aside — when
  a human takes over the conversation.

Anything the assistant says is said by a healthcare provider. Wrong information about
availability, price or clinical matters is a real cost, not a bug report.

## Scope

In scope: the WhatsApp conversational layer, its state, its tools (FAQ retrieval,
availability, booking), the escalation paths, the operational surface needed to run it
(health, logs, deploy), and **one internal control panel** (see *Control panel* below).

Out of scope: any patient-facing UI, clinical decision-making, medical advice, payment
processing, and a general-purpose CRM. The control panel is an operator switchboard, not
a product surface — humans still *reply* from the Kapso Inbox.

## Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+, `src/` layout, package `agente` |
| Web | FastAPI + uvicorn — inbound webhook and health |
| LLM | Anthropic SDK (`anthropic`) |
| HTTP client | `httpx` |
| Persistence | **SQLite** (WAL), one file on a Coolify volume — no database service |
| Control panel | Server-rendered Jinja2 + HTMX inside the same FastAPI app — no build step |
| Config | `pydantic-settings`, environment only |
| Tests | `pytest` |
| Messaging channel | **Kapso** (WhatsApp Business) — transport *and* human inbox |
| Human console | Kapso Inbox. **Chatwoot is gone**; nothing replaces it |
| Scheduling | Calendly API |
| Deploy | Docker; Coolify as the host |

**Orchestration is an open decision for v3.** Previous versions used a graph of nodes;
that is not a given. Do not assume a framework until it is written here.

## Architecture decisions

Closed. Each line is a decision, not a description — change it here before changing code.

**Channel.** Kapso is transport only: inbound webhook (`whatsapp.message.received`),
outbound send API, and the shared Inbox for humans. The conversational logic lives in this
repository — we do **not** move the brain into Kapso Workflows.

**Number.** One production number today: `Nutrificha`, `+1 205-294-3796`,
`phone_number_id 1087343774471931`, in Kapso project *Casas Inc*. Its only webhook pointed
at a dead ngrok tunnel, so it is free to repoint. Embedded signup (customer-owned numbers)
comes later, but the data model is **multi-number from day one**: `phone_number_id` is part
of the key everywhere. Reusing *Casas Inc* is a deliberate temporary choice.

**No Chatwoot.** The Kapso Inbox covers human takeover for the 1–2 clinic people who need
it, and can be embedded by iframe if we ever want it inside our own page. Mirroring every
message into a second system would mean two sources of truth about who is handling a
conversation, plus another Coolify deployment. Consequence accepted: **the conversation
history lives in Kapso**, not on our server.

**Human handoff — an explicit switch we own.** Kapso's Inbox "Handoff" button pauses
*Kapso workflows*; our bot is not a workflow, and there is no handoff webhook event
(the events are `message.received|sent|delivered|read|failed`,
`conversation.created|ended|inactive`, `contact.identity_changed`). Rejected: inferring
takeover from outbound messages we did not send — it guesses at intent from a side effect,
and it silently depends on Kapso's event semantics staying as they are.

Instead, **the bot is muted by an explicit switch that lives in our database**, flipped by
a human in our own control panel. Nothing about the mute path depends on Kapso: the check
is one local SQLite read on the inbound path, before any model call.

Three levels, checked in this order:

1. **Global kill switch** — the bot answers nobody. One row, one click, for "stop
   everything right now".
2. **Per-number** — a whole WhatsApp number is muted (matters once embedded signup brings
   more numbers).
3. **Per-contact** — this patient talks only to humans.

**The switch is keyed by contact, never by conversation.** Kapso ends a conversation after
24h of inactivity and opens a new one on the next message; a per-conversation flag would
silently un-mute the bot the next morning. Key: `(phone_number_id, contact_phone)`.

A mute is either indefinite or has an expiry (`muted_until`), so nobody discovers three
weeks later that the bot was off for a patient. Every flip is written to an audit log —
who, when, why — because "why did the bot not answer this person" is a question that will
be asked about a real patient.

**Control panel.** A small internal page served by the same FastAPI app:

- Lists conversations **read live from the Kapso API** (`GET /conversations`, cursor
  pagination). We do not mirror conversations into our database — Kapso stays the source of
  truth for message history.
- Joins each row with the local mute state and shows a toggle per contact, plus the global
  kill switch.
- Server-rendered Jinja2 + HTMX. No SPA, no build step, no second deployment, no CORS. The
  point of this panel is to *remove* friction, so it ships inside the existing container.
- Behind auth from the first commit — it lists patient phone numbers. Shared password from
  the environment, session cookie, and never reachable without HTTPS.
- Read-only besides the switches. Replying is the Kapso Inbox's job; embedding that Inbox
  by iframe into the same page is a later nicety, not v3 scope.

**Persistence: SQLite, single file.** Mute state, audit log, durable profiles, rolling
summaries and scheduling state all live in one SQLite database in WAL mode, on a Coolify
volume. Rationale: a single-container deployment with no Postgres service to provision,
back up or connect — the same friction reduction that killed Chatwoot. Cost of the choice:
the volume must be persistent and backed up (a redeploy without it loses everything), and
one writer at a time — fine for one webhook process, a hard limit if we ever scale out.
Postgres is the escape hatch if that day comes; keep all database access behind a repository
layer so it stays one module's problem.

**One voice, several minds.** Split by *kind of decision*, never by topic:

| Job | Who | Why |
|---|---|---|
| Talking to the patient | One agent, Sonnet, with tools | Splitting the writing across agents breaks tone, and tone is the product on WhatsApp |
| Crisis check | Cheap classifier (Haiku) on every inbound, before the agent | Binary safety decision, not a conversation |
| History compaction | Haiku, asynchronous, off the reply path | Mechanical, must not add latency |
| Scheduling | Deterministic code exposed as tools | v2's bugs were dates and timezones; that is fixed with code and fixed-clock tests, not with more LLM |

**Knowledge: an LLM wiki in context, not RAG.** Clinic knowledge lives as curated markdown
written for the model, loaded into the cached system prompt. No embeddings, no vector
store, no retrieval step. If the wiki outgrows the cache budget (~10–15k tokens), the next
step is a page selector, **not** a switch to embeddings.

**Memory: two layers.**

1. *Durable profile* — small structured record per contact: name, preferred modality,
   timezone, confirmed appointment, handoff state. A confirmed appointment never lives in
   a summary.
2. *Rolling window* — the last few turns verbatim, everything older folded into a rolling
   summary. Compaction triggers on **tokens**, not message count, and is written by Haiku.

## Rules

- **Clinical data.** Never log message bodies, phone numbers or patient identifiers in the
  clear. Log event shape plus a truncated or hashed reference. Assume every log line may
  be read by someone who should not see who said what.
- **Secrets** come from the environment through `pydantic-settings`, and every new setting
  is mirrored in `.env.example`. Never inline a key, an ID or a URL.
- **Kapso is production.** The linked account owns live WhatsApp numbers. Mutating Kapso
  commands and real message sends are operator actions, never agent actions. See
  `.qwen/skills/kapso-platform/SKILL.md`.
- **Time is a known trap.** Calendly availability, timezones and slot boundaries caused
  real bugs in v2. Anything touching dates carries explicit timezone handling and tests
  with fixed clocks.
- **Outbound sends are not idempotent.** A retry can double-message a patient. Deduplicate
  on a message key instead of retrying blindly.
- **Every behavior change ships with a test.** No network in tests.

## Who does what

- `CLAUDE.md` — how Claude Code operates here: plans, specs, reviews, delegates.
- `QWEN.md` — the implementation contract for `qwen`: discovery protocol, skills, house
  rules, output format.
- `.qwen/skills/` — skills available to the implementer.

## Open questions

Answered with the owner before they become code:

- **Orchestration shape** for v3: how the agent loop, the crisis gate and the tools fit
  together concretely.
- **Muting is manual by design.** Nobody clicks the switch when a human jumps into the
  Inbox in a hurry, and then bot and human answer the same patient at once. Do we accept
  that, or does the panel eventually need an assist (a "human replied recently" hint read
  from the Kapso API, shown as a suggestion, never as an automatic action)?
- **Who watches the panel.** With 1–2 clinic people, is anyone actually looking at it
  during the day, or is the realistic flow "the psychologist notices in WhatsApp and mutes
  from their phone"? That decides how mobile-first the panel has to be.
- **Retention.** Kapso holds the full history. How long do we keep our own copy (rolling
  window, summaries, profile), and what does a deletion request mean in practice?
- **Backups of the SQLite volume.** Losing that file means losing every profile, summary
  and mute. Who takes the backup and how often — Coolify volume snapshot, or a periodic
  `VACUUM INTO` copy pushed somewhere?
- **Reminders / proactive outbound.** In scope for v3? If yes, an approved WhatsApp
  template is required — outside the 24-hour window nothing else can be sent.
- **Failure mode.** If Kapso or Anthropic is down mid-conversation: queue and retry, or
  drop and let the human see it in the Inbox?
- **The number is from Alabama (+1 205)** and the patients are not. Perception and
  conversation cost — worth revisiting before launch, not before code.
