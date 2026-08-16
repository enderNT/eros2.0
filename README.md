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
