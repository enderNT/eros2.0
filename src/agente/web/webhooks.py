"""Kapso webhook edge: authenticate, acknowledge, process in background."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from ..adapters.kapso.payloads import parse_webhook
from ..domain.errors import KapsoError

router = APIRouter()


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
