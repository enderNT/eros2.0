# STATE.md — where the project stands

Living handoff note. **Anyone (or any agent) picking this up cold reads this file first**,
then `PROJECT.md` for the decisions, `SPEC.md` for the technical contract, and `TASKS.md`
for what to do next.

Keep it short. It is a status, not a history: overwrite stale lines instead of appending.

**Last updated:** 2026-08-16 · by Codex

---

## Phase

**Implementing: T3 done, T4 next.** Branch `v3-rebuild`. Scaffold (T1), the
storage foundation (T2), and pure domain logic (T3) are in place; everything on
`main` remains reference-only.

`SPEC.md` and `TASKS.md` cover T1–T13. **T4 (Kapso adapter) is ready to start
right now**; it is independent of T3.

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

## Decided since the rewrite started

Full text in `PROJECT.md`; the headline versions:

- Kapso is the WhatsApp channel *and* the human inbox. **Chatwoot is gone.**
- Number: `Nutrificha +1 205-294-3796` (`phone_number_id 1087343774471931`), project
  *Casas Inc*, temporary. Its old webhook was a dead ngrok tunnel — free to repoint.
- The brain stays in this repo (FastAPI + Anthropic SDK), not in Kapso Workflows.
- Muting the bot is an **explicit switch we own**, keyed by contact, flipped from our own
  mobile-first control panel. Nothing is inferred from Kapso events.
- Persistence: **one SQLite file** (WAL) on a Coolify volume. No Postgres.
- Knowledge: curated markdown wiki inside the cached prompt. No RAG, no embeddings.
- Memory: durable structured profile + rolling window compacted by token budget.
- One conversational voice (Sonnet) + narrow Haiku jobs (crisis check, summarization) +
  deterministic scheduling tools.

## Not decided yet — do not invent these

- **Clinic content.** The playbook and the wiki ship as skeletons with
  `<<pendiente>>` markers. Prices, services and policies come from the clinic. Never
  invent them.
- **The crisis message text.** Written by the clinic. Boot fails while it is a placeholder.
- Retention of our own copy of the history, and what deletion means.
- Whether reminders / proactive outbound are in v3 (they would need an approved template).
- Behaviour when Kapso or Anthropic is down mid-conversation.
- Backup strategy for the SQLite volume.

## Gotchas worth remembering

- The Kapso account is **live production**. Never run `kapso push`, never send a real
  WhatsApp message from a task.
- The codebase-memory graph was reindexed at T2 and now describes the v3 tree;
  reindex again after changes that add, remove or rename modules.
- `qwen` must be invoked bare (`qwen -p "..."`), no env-var prefix, or Claude Code's
  permission rule will not match.
