"""Webhook edge: authenticate, then hand off. Nothing unverified gets through."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from ..adapters.calendly.signature import verify_signature
from ..adapters.kapso.payloads import parse_webhook
from ..domain.errors import KapsoError

log = logging.getLogger(__name__)
router = APIRouter()

CALENDLY_SIGNATURE_HEADER = "Calendly-Webhook-Signature"


@router.post("/webhook/kapso", status_code=200)
async def kapso_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    raw = await request.body()
    try:
        payloads = parse_webhook(
            raw, request.headers, request.app.state.settings.kapso_webhook_secret
        )
    except KapsoError as exc:
        raise HTTPException(status_code=400, detail="invalid webhook") from exc
    for payload in payloads:
        background_tasks.add_task(request.app.state.inbound.handle, payload)
    return Response(status_code=200)


@router.post("/webhook/calendly", status_code=200)
async def calendly_webhook(request: Request) -> Response:
    """Processed inline, not in the background: a 200 here means it landed.

    Calendly retries on anything else, and the service is idempotent, so an
    honest status is worth more than a fast one.
    """
    raw = await request.body()
    settings = request.app.state.settings
    if not verify_signature(
        raw,
        request.headers.get(CALENDLY_SIGNATURE_HEADER),
        settings.calendly_signing_key,
        now=datetime.now(UTC),
    ):
        log.warning("calendly_webhook_rejected")
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        body = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid webhook") from exc
    booking = getattr(request.app.state, "booking", None)
    if booking is None:
        log.error("calendly_webhook_unwired")
        return Response(status_code=200)
    await booking.handle(str(body.get("event") or ""), body.get("payload") or {})
    return Response(status_code=200)
