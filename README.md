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
without it, redeploying erases the SQLite history. Do not point the live Kapso webhook at
this service until an operator has completed the final controlled test.
