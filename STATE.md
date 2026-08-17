# STATE.md — where the project stands

Living handoff note. **Anyone (or any agent) picking this up cold reads this file first**,
then `PROJECT.md` for the decisions, `SPEC.md` for the technical contract, and `TASKS.md`
for what to do next.

Keep it short. It is a status, not a history: overwrite stale lines instead of appending.

**Last updated:** 2026-08-17 · by Claude Code

---

## Phase

**T1–T13 complete. The backlog has no open task.** Branch `v3-rebuild`. The full inbound
path runs end to end: webhook → dedupe → debounce → mute gate → crisis pre-gate → agent
with four tools → chunked send → compaction, plus the Calendly return path
(`invitee.created` → appointment + profile + confirmation). Everything on `main` remains
reference-only.

**The operator sequence is in `RUNBOOK.md`, and the order matters:** deploy first (both
webhooks are inbound deliveries and there is no public URL yet) → register Calendly →
clinic content → full E2E → repoint Kapso last. The clinic's open questions are in
`content/PREGUNTAS-CLINICA.md`, one per `<<pendiente>>` marker.

**What stands between this and production is content and operator steps, not code:** the
clinic's real crisis message, the pending wiki sections, a real clinic event type in
Calendly, registering the Calendly webhook subscription (`CALENDLY_SIGNING_KEY` empty means
the route rejects every delivery, by design), and repointing the Kapso webhook. All of them
are human actions. `E2E-CHECKLIST.md` is the gate.

## What exists right now

- `PROJECT.md` — business, scope, stack, closed architecture decisions, open questions.
- `SPEC.md` — the technical contract: layers, module map, pipeline, agent loop, tools,
  memory, schema, observability, testing, deploy.
- `TASKS.md` — T1–T13, each executable without a prior conversation.
- `QWEN.md` / `CLAUDE.md` — how each agent works here.
- `.qwen/skills/` — backend, API design, logging, simplification, wiki, Kapso.
- `.qwen/commands/` — `/next`, `/handoff`, `/catchup`.
- **v3 code (T1):** `pyproject.toml`, `src/agente/` — `config.py` (§12 settings;
  boot fails on missing values and on the `<<pendiente>>` crisis message),
  `logging_setup.py` (JSON logs, deny-list redaction, phone hash + last two),
  `app.py` factory + `web/health.py`, every §3 package with docstrings.
  `.env.example`, `README.md`.
- **v3 code (T2):** `adapters/store/` — `db.py` (connect WAL+FK, `migrate()` with
  `schema_version`, health probe), `migrations/0001_initial.sql` (every §10 table),
  repositories `mutes` (three levels + expiry + audit), `messages` (dedupe, window),
  `contacts` (contact + profile); `summaries`/`appointments`/`traces` stubbed.
  `ports/store.py` (six protocols + row records), `domain/errors.py` (`StoreError`),
  `domain/contacts.py` (`ContactKey`). App opens + migrates the DB in the lifespan
  (`app.state.db`); a dead DB degrades `/health`, not the boot. `tests/` (52).
- **v3 code (T3):** pure `domain/` logic — E.164 contact normalization and safe
  phone masking; timezone-aware slot labels, broad sampling and buffer checks;
  token-budget window plans with overlap; WhatsApp reply chunking; strict crisis
  verdicts. All time is injected; domain code stays free of I/O. `tests/` (107).
- **v3 code (T4):** `adapters/kapso/payloads.py` — Pydantic models for single and
  batched webhook payloads (`extra="allow"`), HMAC-SHA256 verification (case-insensitive
  header lookup), `parse_webhook` dispatching and `KapsoError` on forged/malformed input.
  `adapters/kapso/client.py` — async `httpx` with explicit timeout; `send_text(…) -> str`
  returns kapso message id; `list_conversations(…, cursor, limit) -> ConversationList`
  yields typed rows from Kapso JSON; every `httpx.HTTPError` → `KapsoError`, structured
  safe logs (masked phone, no body). `ports/channel.py` — `Channel` Protocol with
  `send_text` and `list_conversations`; frozen `ConversationRow` dataclass carrying real
  contact phone for mute keying. Tests: 15 payload + 10 client = 25 tests green.
- **Kapso conversations, confirmed against the live API (2026-08-17):** the listing is
  `GET {KAPSO_BASE_URL}/{phone_number_id}/conversations` — same shape as the send path,
  *not* a separate `/whatsapp/phone-numbers/...` route (that 404s, which is what broke the
  panel). Rows carry `contact_name`, a bare `phone_number` (normalized to E.164 by the
  adapter, since the mute key depends on it), `status`, `last_active_at`, and everything
  about the last message under `kapso`. Pagination: read `paging.next`, send it back as
  the `after` param.
- **Calendly, confirmed against the live API (2026-08-17):** `start_time` must be
  *strictly* future — sending `now` is a 400, so the adapter pushes the window forward by
  `START_LEAD` (5 min). Availability rows carry `start_time`, `status`,
  `invitees_remaining` and a slot-specific `scheduling_url`, but **no `end_time`**: the
  duration comes from the event type (fetched once, cached). Ranges up to 30 days work.
  **Calendly cannot book on a patient's behalf** (`/scheduling_links` only mints a link),
  so `agendar_cita` hands over the slot link and states the appointment is not confirmed;
  the row is written only by the `invitee.created` webhook — see T9b.
- **v3 code (T9 partial / T10 / T12, 2026-08-17):** `tools/registry.py` is the single
  place that defines and wires the four tools (`buscar_wiki`, `ver_horarios`,
  `agendar_cita`, `escalar_a_humano`); every domain failure becomes a sentence the model
  can act on, since the agent loop only rescues `ValueError`/`RuntimeError`. Booking
  resolves the model's ISO identifier against live availability, so an invented slot is
  refused. `services/compaction.py` is watermark-aware and summarized by Haiku;
  `AgentResponder` builds the turn from the stored window plus the summary (roles merged
  and alternating for the Messages API); `InboundService` compacts after the reply is
  sent. `CalendlyClient` gained `aclose()`. Tests: 170 green.
- **v3 code (T5):** `web/auth.py` signed, expiring panel session; `web/panel.py` and
  Jinja2/locally served HTMX templates provide the mobile-first admin panel. Conversations
  are read live from injected Kapso channel; contact, number and global mute actions audit
  locally; the trace list reads `llm_trace`. Rows are grouped one per contact and every
  switch carries an inline `i` hint.
- **v3 code (T9b, 2026-08-17):** the booking loop closes. `agendar_cita` mints an opaque
  `utm_content` token (never the phone number — the URL leaves our control), stored by
  `adapters/store/booking_tokens.py` (migration `0002`). `adapters/calendly/signature.py`
  verifies Calendly's real scheme: header `t=<unix>,v1=<hex>` over `f"{t}.{raw_body}"`,
  5-minute tolerance, and no signing key configured means reject. `services/booking.py`
  handles `invitee.created` / `invitee.canceled`: appointment row, durable profile
  (`next_appointment_utc`, `appointment_count`, name/email from the invitee), one
  confirmation in clinic local time. Idempotent per `calendly_event_id`; an unknown token
  is logged and ignored, because a booking made straight from Calendly is not ours to
  confirm. `POST /webhook/calendly` verifies inline and 401s forged or stale deliveries.
- **v3 code (T11, 2026-08-17):** `services/crisis.py` is the pre-gate — one Haiku call, the
  verdict returned through a tool schema with an `enum` so nothing is string-matched, and
  every failure mode (unknown value, no tool call, model error, timeout) resolves to
  `possible`. `acute` sends the clinic text verbatim, mutes the contact, writes an urgent
  audit row and never reaches the agent; `possible` appends the playbook's crisis section as
  a fourth system block for that turn (no cache breakpoint — it would invalidate the three
  stable blocks on every other turn).
- **v3 code (T13):** `Dockerfile` (non-root, single process) and `docker-compose.yml` with
  the persistent `agente-data` volume; `README.md` covers the volume requirement, the
  environment variables and the operator-only Kapso webhook registration. Verified by
  running the container against the live APIs.

## Decided since the rewrite started

Full text in `PROJECT.md`; the headline versions:

- Kapso is the WhatsApp channel *and* the human inbox. **Chatwoot is gone.**
- Number: `Nutrificha +1 205-294-3796` (`phone_number_id 1087343774471931`), project
  *Casas Inc*, temporary. Its old webhook was a dead ngrok tunnel — free to repoint.
- The brain stays in this repo (FastAPI + Anthropic SDK), not in Kapso Workflows.
- Muting the bot is an **explicit switch we own**, keyed by contact, flipped from our own
  mobile-first control panel. Nothing is inferred from Kapso events.
- Persistence: **one SQLite file** (WAL) on a Coolify volume. No Postgres.
- Knowledge: curated markdown playbook plus a wiki exposed by deterministic lookup. No
  RAG, no embeddings. The clinic facts and Nora's operating guidance were migrated from
  `main`; unknown policies remain visibly marked as pending.
- Memory: durable structured profile + rolling window compacted by token budget.
- One conversational voice (Sonnet) + narrow Haiku jobs (crisis check, summarization) +
  deterministic scheduling tools.

## Not decided yet — do not invent these

- **Remaining clinic content.** Cancellation/rebooking, confidentiality, first-visit
  requirements, public team profiles, billing/insurance and the priority crisis channel
  still need confirmation. Never invent them.
- **The crisis message text.** Written by the clinic. Boot fails while it is a placeholder.
- Retention of our own copy of the history, and what deletion means.
- Whether reminders / proactive outbound are in v3 (they would need an approved template).
- Behaviour when Kapso or Anthropic is down mid-conversation.
- Backup strategy for the SQLite volume.

## How to test it end to end

`E2E-CHECKLIST.md` — harness (local sink instead of the real Kapso API), case matrix and
quality rubric. Read it before touching anything that talks to a patient.

## Gotchas worth remembering

- The Kapso account is **live production**. Never run `kapso push`, never send a real
  WhatsApp message from a task.
- The codebase-memory graph was reindexed at T2 and now describes the v3 tree;
  reindex again after changes that add, remove or rename modules.
- `Knowledge.find_sections` matches the query against wiki **headings only**, not bodies.
  The tool description tells the model to query with the index title; if lookups start
  missing facts that exist, that is the cause.
- `escalar_a_humano` mutes **indefinitely, by decision** — see PROJECT.md. A tool failure
  does hand the patient over until a human flips the switch back; that is the intended
  behaviour, not a bug to fix with an expiry.
- The test event type is `Discovery call` (15 min) on a personal Calendly, with slots
  outside the clinic's 8:00–17:00. Fine for plumbing, useless for judging answer quality.
- The crisis pre-gate now runs on **every** inbound turn — one Haiku call per message,
  before the agent. That is the intended cost; it is also why a Kapso/Anthropic outage
  makes every turn `possible` rather than silently `none`.
- `CALENDLY_SIGNING_KEY` is empty until an operator registers the webhook subscription.
  While it is empty, `/webhook/calendly` 401s everything and no booking is ever confirmed —
  correct, but it means a booking made during a test will look like it "did nothing".
- `qwen` must be invoked bare (`qwen -p "..."`), no env-var prefix, or Claude Code's
  permission rule will not match.
