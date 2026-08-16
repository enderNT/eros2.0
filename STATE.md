# STATE.md — where the project stands

Living handoff note. **Anyone (or any agent) picking this up cold reads this file first**,
then `PROJECT.md` for the decisions, `SPEC.md` for the technical contract, and `TASKS.md`
for what to do next.

Keep it short. It is a status, not a history: overwrite stale lines instead of appending.

**Last updated:** 2026-08-16 · by Qwen

---

## Phase

**Implementing: T1 done, T2 next.** Branch `v3-rebuild`. The v3 scaffold is in
place (package map, settings, redacted logging, app factory with `/health`,
layer test); everything on `main` remains reference-only.

`SPEC.md` and `TASKS.md` cover T1–T13. **T2 (storage foundation) is ready to
start right now** — nothing blocks it.

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
  `tests/` (16), `.env.example`, `README.md`.

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
- The codebase-memory graph was reindexed at T1 and now describes the v3 tree;
  reindex again after changes that add, remove or rename modules.
- `qwen` must be invoked bare (`qwen -p "..."`), no env-var prefix, or Claude Code's
  permission rule will not match.
