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
availability, booking), the escalation paths, and the operational surface needed to run it
(health, logs, deploy).

Out of scope: any frontend or patient-facing UI, clinical decision-making, medical advice,
payment processing, and a general-purpose CRM.

## Stack

| Concern | Choice |
|---|---|
| Language | Python 3.11+, `src/` layout, package `agente` |
| Web | FastAPI + uvicorn — inbound webhook and health |
| LLM | Anthropic SDK (`anthropic`) |
| HTTP client | `httpx` |
| Persistence | Postgres via `psycopg` 3 |
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

**Human handoff — bot-off by foreign outbound.** Kapso's Inbox "Handoff" button pauses
*Kapso workflows*; our bot is not a workflow, and there is no handoff webhook event
(the events are `message.received|sent|delivered|read|failed`,
`conversation.created|ended|inactive`, `contact.identity_changed`). So the bot mutes itself
on evidence, not on notification: we subscribe to `whatsapp.message.sent`, and **an
outbound message we did not send means a human is in the conversation** → pause the bot for
that conversation. Reactivation is explicit (a timeout, or the human closing the
conversation). Secondary signal: conversation assignments via the API. This needs a live
test against the API before it is built.

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
- **Handoff, verified.** Does an Inbox takeover create an API-visible assignment, and does
  `whatsapp.message.sent` fire for messages a human sends from the Inbox? The bot-off
  design above depends on it. Test against the live API before building.
- **Retention.** Kapso holds the full history. How long do we keep our own copy (rolling
  window, summaries, profile), and what does a deletion request mean in practice?
- **Reminders / proactive outbound.** In scope for v3? If yes, an approved WhatsApp
  template is required — outside the 24-hour window nothing else can be sent.
- **Failure mode.** If Kapso or Anthropic is down mid-conversation: queue and retry, or
  drop and let the human see it in the Inbox?
- **The number is from Alabama (+1 205)** and the patients are not. Perception and
  conversation cost — worth revisiting before launch, not before code.
