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
| Messaging channel | **Kapso** (WhatsApp Business) — replaces Chatwoot |
| Scheduling | Calendly API |
| Deploy | Docker; Coolify as the host |

**Orchestration is an open decision for v3.** Previous versions used a graph of nodes;
that is not a given. Do not assume a framework until it is written here.

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

- Orchestration shape for v3, and how much of the v2 node design survives.
- Which Kapso project and number the clinic bot binds to.
- Conversation memory: what is stored, for how long, and what gets deleted.
- Whether reminders / proactive outbound messaging are in scope for v3.
