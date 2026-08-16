# STATE.md — where the project stands

Living handoff note. **Anyone (or any agent) picking this up cold reads this file first**,
then `PROJECT.md` for the decisions, then `TASKS.md` for what to do next.

Keep it short. It is a status, not a history: overwrite stale lines instead of appending.

**Last updated:** 2026-08-16 · by Claude Code

---

## Phase

**Planning → about to start implementation.** Branch `v3-rebuild`. The repository is
deliberately empty of application code: no `src/`, no tests, no `pyproject.toml` yet.
Everything on `main` is the v2 implementation, kept only as reference.

## What exists right now

- `PROJECT.md` — business, scope, stack, closed architecture decisions, open questions.
- `QWEN.md` / `CLAUDE.md` — how each agent works here.
- `.qwen/skills/` — backend, API design, logging, simplification, wiki, Kapso.
- `.qwen/commands/` — `/next`, `/handoff`, `/catchup`.
- `TASKS.md` — the ordered backlog. **This is the entry point for real work.**

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

- The concrete shape of the agent loop (how the crisis gate, the tools and the reply path
  fit together). **This is the next design conversation, and it blocks the agent code.**
- Retention of our own copy of the history, and what deletion means.
- Whether reminders / proactive outbound are in v3 (they would need an approved template).
- Behaviour when Kapso or Anthropic is down mid-conversation.
- Backup strategy for the SQLite volume.

## Gotchas worth remembering

- The Kapso account is **live production**. Never run `kapso push`, never send a real
  WhatsApp message from a task.
- The codebase-memory graph still describes the deleted v2 code. Reindex once v3 code
  exists; until then treat it as history.
- `qwen` must be invoked bare (`qwen -p "..."`), no env-var prefix, or Claude Code's
  permission rule will not match.
