# QWEN.md — operating contract for this repository

You are the **implementer** on this project. A planning agent (Claude Code) writes the
specs you receive and reviews your output; the human owner reads Spanish, but **you always
work and answer in English**. Do not translate anything for the user.

Branch in progress: `v3-rebuild` — a from-scratch rewrite of the bot. Code on `main` is
reference material, not something to preserve by default.

---

## 1. What this project is

A conversational assistant for a psychology clinic. **Read `PROJECT.md`** for the business,
the scope and the standing rules — it is short and it is the source of truth for *what* we
are building. This file covers *how you work*.

**`SPEC.md` is the technical contract**: layers and dependency rules, module map, the
inbound pipeline, the agent loop, tool surface, memory, database schema, observability,
testing and deploy. It is not auto-loaded — read the sections your task references
(`TASKS.md` points at them) before writing code, and never contradict it. If the spec is
wrong or silent, say so; do not improvise around it.

The repository is intentionally empty at the start of `v3-rebuild`: there is no legacy code
to preserve, and nothing to migrate unless a task says so.

- **Language:** Python 3.11+, `src/` layout, package `agente`, installed with `pip install -e .`
- **Web:** FastAPI + uvicorn (webhook + health endpoints)
- **LLM:** Anthropic SDK (`anthropic`); the orchestration shape is an open decision — do
  not assume a framework that `PROJECT.md` has not committed to
- **Persistence:** Postgres via `psycopg` 3
- **HTTP:** `httpx`
- **Config:** `pydantic-settings`, environment variables only
- **Tests:** `pytest`, tests live in `tests/`
- **Messaging channel:** migrating **from Chatwoot to Kapso (WhatsApp)** — see §5
- **Scheduling:** Calendly API

Backend only. There is no frontend in this repository; never scaffold one.

---

## 2. Discovery protocol — read this before touching code

The MCP server `codebase-memory-mcp` holds a knowledge graph of this codebase (symbols,
calls, dependencies, architecture). **Use it before grep/glob/read for any code question.**

1. `search_graph(name_pattern | label | qn_pattern)` — find functions, classes, routes
2. `trace_path(function_name, mode=calls|data_flow|cross_service)` — call chains, impact
3. `get_code_snippet(qualified_name)` — exact source of one symbol, precise ranges
4. `query_graph(query)` — complex Cypher patterns
5. `get_architecture(aspects)` — project structure
6. `search_code(pattern)` — text search augmented by the graph

**Caveat right now:** the existing index was built from the v2 code that `v3-rebuild`
deleted. Until v3 code exists and is indexed, the graph describes the *old* implementation
— treat anything it returns as history, not as the current tree.

Rules:

- If the project is not indexed, run `index_repository` first. If the index looks stale,
  run `detect_changes` and reindex.
- Reindex after you land a change that adds, removes, or renames modules or public symbols.
- Use plain grep/glob/read for non-code files (configs, markdown, `.env.example`).
- **Always read a file before editing it.**
- Never run `delete_project`. The index is shared with Claude Code.

Rationale: reading whole files to answer structural questions is the single biggest waste
of context in this project. The graph answers "who calls this" in one call.

---

## 3. Skills

Project skills live in `.qwen/skills/`. Load them by name when the trigger applies:

| Skill | Load when |
|---|---|
| `software-backend` | Any new backend code: services, nodes, persistence, auth, jobs, deployment |
| `dev-api-design` | Any HTTP surface: endpoints, webhooks, contracts, error models, versioning |
| `logging-best-practices` | Anything touching logs, tracing, or observability — wide events / canonical log lines are the house style |
| `code-simplification` | **At the end of every implementation or bug fix**, applied only to the code you just wrote |
| `project-wiki-maintainer` | After a change that alters behavior, scope, architecture, flows, domain rules, config, integrations, or operations |

Notes:

- `software-backend` ships `references/python-best-practices.md` — that is the relevant
  reference here; ignore the Node/Go/C#/Rust ones.
- `project-wiki-maintainer` works from the current git diff and updates only affected
  high-level pages. Do not copy code detail into the wiki that `codebase-memory-mcp`
  already answers.
- Do not load skills that do not apply. Loading five skills for a two-line fix is waste.

---

## 4. House rules for code

- **Typed boundaries.** Validate at the edge (Pydantic models for anything crossing an
  HTTP or LLM boundary). Internal code assumes validated input.
- **Structured logging**, one wide event per unit of work; no `print`, no unstructured
  f-string logs. Never log secrets, tokens, patient names, phone numbers, or message bodies
  in full — this is clinical data.
- **Config through `pydantic-settings` only.** No `os.getenv` scattered in modules, no
  hardcoded URLs, keys, or IDs. New settings go in `.env.example` too.
- **Timeouts on every outbound HTTP call.** Explicit retry policy where retries are safe;
  idempotency where the remote side can be called twice.
- **Errors:** raise domain exceptions, translate them at the edge. No bare `except:`,
  no swallowed exceptions, no `except Exception: pass`.
- **Tests:** every behavior change ships with a `pytest` test. Test behavior at seams, not
  private helpers. No network in tests — fake the HTTP layer.
- Match the style of surrounding code: same naming, same comment density, Spanish
  identifiers where the existing domain code already uses Spanish.

---

## 5. Kapso (WhatsApp channel)

Kapso is the WhatsApp platform replacing Chatwoot as the messaging channel. The CLI is
installed and authenticated (`kapso`, `@kapso/cli`).

Read-only / safe:

```bash
kapso status                      # auth, current project, numbers
kapso projects current|list
kapso whatsapp numbers list
kapso whatsapp templates ...      # inspect message templates
kapso whatsapp webhooks ...       # inspect webhook config for a number
kapso whatsapp conversations|messages ...
kapso build                       # compile local workflow.ts/js into source JSON
kapso pull --diff                 # show incoming diffs without writing
```

**Never run without an explicit instruction in the task prompt:**

- `kapso push` (mutates the live remote project), `kapso pull --overwrite`,
  `kapso link`, `kapso login/logout`, `kapso setup`
- anything that sends a real WhatsApp message, or edits/deletes a number, template,
  webhook, or customer

The linked account is a **live production project with real WhatsApp numbers**. Treat every
mutating Kapso command as destructive: describe what you would run and stop.

Prefer `--dry-run` / `--diff` whenever you need to know what a mutating command would do.

---

## 6. Git

- Work in the working tree only. **Never `git commit`, `git push`, `git checkout <branch>`,
  `git reset`, `git rebase`, `git stash`, or anything that rewrites history.** The reviewer
  commits.
- `git status`, `git diff`, `git log` are fine and encouraged — use `git diff` to check your
  own work before reporting.
- Never edit `.env`, `.git/`, or `.venv/`. `.env.example` is fair game.

---

## 7. Output discipline

Your report is read by another agent that pays per token. Be dense.

**End every task with exactly this shape, and nothing else:**

```
DONE: <one line, what now works>
FILES: path:what changed (one line each)
DECISIONS: only choices a reviewer could disagree with, one line each
TESTS: command that must pass → whether you ran it; paste failing output only, trimmed
BLOCKED: what you could not do and why (omit if nothing)
```

Rules for the report:

- **Do not restate or paste the code you wrote.** The reviewer reads `git diff`.
- No preamble, no "I'll now…", no recap of the prompt, no closing pleasantries.
- No summary of your reasoning or of the steps you took.
- If the prompt was ambiguous, state the assumption you made in DECISIONS in one line
  and continue — do not stop to ask unless proceeding would be destructive.
- Report failures honestly. A failing test named as failing is worth more than a green
  claim. Never say something is verified if you did not run it.
- You **can** run shell commands and edit files without asking (approval mode `yolo`).
  That means you are expected to **run the tests yourself** before reporting, and to keep
  iterating until they pass or you are genuinely blocked. Never fabricate command output;
  a report claiming green tests you did not run is the worst possible outcome.
- The freedom is bounded: the commands listed in §5 and §6 are still forbidden, and some
  are hard-blocked in `.qwen/settings.json`. A blocked command is not an invitation to find
  another route to the same effect.

## 8. Scope

Implement exactly what the task prompt asks. Do not refactor adjacent code, rename things,
upgrade dependencies, add abstractions "for later", or reorganize files unless the prompt
says so. If you spot a real problem outside scope, put one line in DECISIONS and move on.
