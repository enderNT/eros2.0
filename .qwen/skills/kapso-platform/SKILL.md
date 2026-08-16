---
name: kapso-platform
description: Kapso WhatsApp platform and its CLI (@kapso/cli). Use when working on the WhatsApp messaging channel — inbound webhooks, outbound messages, templates, conversations, numbers, or Kapso workflows/functions pulled into this repo. Also use before running any `kapso` command, to know which are safe and which mutate a live production project.
---

# Kapso platform

Kapso is the WhatsApp platform that replaces Chatwoot as this bot's messaging channel.
It provides WhatsApp Business numbers, webhooks for inbound messages, an API for outbound
messages and templates, plus source-controlled "workflows" and "functions" that can be
pulled into and pushed from a repo.

The CLI is installed and already authenticated on this machine.

## Safety first — this account is live

The linked Kapso account owns **real WhatsApp Business numbers with real conversations**.
Anything that mutates remote state or sends a message reaches real people.

**Never run these unless the task prompt explicitly instructs it, quoting the command:**

- `kapso push` — mutates remote workflows/functions
- `kapso pull --overwrite` — destroys local edits
- `kapso link`, `kapso login`, `kapso logout`, `kapso setup`
- `kapso whatsapp messages send` — sends a real WhatsApp message
- `kapso whatsapp numbers new`, `kapso whatsapp templates new`
- `kapso whatsapp webhooks new|update|delete`
- `kapso customers new`

When one of these is the right next step, **write the exact command in your DECISIONS or
BLOCKED line and stop.** Do not run it.

Preview flags exist — prefer them: `kapso push --dry-run`, `kapso pull --diff`.

## Safe, read-only commands

```bash
kapso status                          # auth, current project, counts
kapso projects current                # current project context
kapso projects list
kapso whatsapp numbers list           # numbers in the project
kapso whatsapp numbers get <ref>      # by Meta ID or display phone number
kapso whatsapp numbers health <ref>   # health check
kapso whatsapp numbers resolve <ref>  # -> canonical phone number ID
kapso whatsapp templates list         # templates for a number (cursor pagination)
kapso whatsapp templates get <id>
kapso whatsapp webhooks list          # webhook config for a number
kapso whatsapp webhooks get <id>
kapso whatsapp conversations list     # most recent activity first
kapso whatsapp conversations get <id>
kapso whatsapp messages list          # cursor pagination
kapso whatsapp messages get <id>
kapso customers list
kapso customers get <id>
kapso build                           # compile local workflow.ts/js -> source JSON
kapso pull --diff                     # show incoming diffs, writes nothing
```

Both `kapso whatsapp numbers list` and `kapso whatsapp:numbers list` work; the colon form
is what `--help` resolves reliably. Every topic accepts `--help` — use it instead of
guessing flags. Project-scoped commands take `--project=<id>` to override context.

## Source-controlled workflows and functions

- `kapso pull [function|workflow] [slug]` brings remote sources into the repo.
- `kapso build` compiles `workflow.ts` / `workflow.js` into the source JSON that Kapso
  consumes. Run `build` before considering a push; a push of uncompiled sources is wrong.
- `kapso push [function|workflow] [slug] --dry-run` shows the push plan. The real push is
  operator-only (see above).

Treat pulled Kapso sources as generated-adjacent: edit them deliberately, keep them in
git, and never mix an unrelated refactor into a pull/push cycle.

## Integrating the channel in this codebase

- Inbound: Kapso delivers messages to a **webhook**. The FastAPI app exposes the endpoint;
  validate the payload with Pydantic at the edge before anything else touches it, and
  verify the request's authenticity (shared secret / signature configured on the webhook)
  before processing.
- Outbound: send through Kapso's API with `httpx`, always with an explicit timeout, and
  treat sends as **non-idempotent** — a retry can double-send to a patient. Dedupe on a
  message key rather than blindly retrying.
- Templates: WhatsApp requires an approved template to open a conversation outside the
  24-hour customer service window. Template names/params are remote state — read them with
  `kapso whatsapp templates list`, never hardcode a template that may not exist.
- Credentials (API key, phone number ID, webhook secret) come from environment variables
  via `pydantic-settings`, and get added to `.env.example`. Never inline them, never log
  them.
- Never log full message bodies or phone numbers: this is clinical data. Log a hashed or
  truncated identifier plus the event shape.
