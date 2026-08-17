# agente

WhatsApp conversational assistant for a psychology clinic.

## Install

    python3 -m venv .venv && . .venv/bin/activate
    pip install -e ".[dev]"

## Run

    cp .env.example .env   # fill real values; CRISIS_MESSAGE must be the clinic's text
    uvicorn agente.app:app

## Test

    pytest -q

## Manual local test

Run `uvicorn agente.app:app --reload`, then open
`http://127.0.0.1:8000/admin/login` and use `PANEL_PASSWORD`.

Container option: `docker compose up --build`. The `agente-data` volume is required;
without it, redeploying erases the SQLite history. On Coolify the same applies: declare a
persistent volume for `DB_PATH` or every deploy starts from an empty database.

Environment variables: every one of them is listed in `.env.example` with a dummy value;
the app refuses to boot if a required one is missing or if `CRISIS_MESSAGE` is still the
placeholder.

Two one-time **operator steps, never agent ones**: a human runs
`kapso whatsapp webhooks new` against the live account to point WhatsApp at the deployed
URL, and a human registers the Calendly subscription for `invitee.created` /
`invitee.canceled` at `/webhook/calendly`, putting the signing key Calendly returns into
`CALENDLY_SIGNING_KEY`. Until that key is set the route rejects every delivery, so no
appointment is ever confirmed. Do not point the live
Kapso webhook at this service until an operator has completed the final controlled test.
