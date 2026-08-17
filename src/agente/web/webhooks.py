"""Kapso webhook edge: authenticate, acknowledge, process in background."""

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from ..adapters.kapso.payloads import parse_webhook
from ..adapters.store.messages import SqliteMessagesRepository
from ..adapters.store.mutes import SqliteMutesRepository
from ..domain.errors import KapsoError
from ..services.inbound import InboundService

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
    service = InboundService(
        SqliteMessagesRepository(request.app.state.db),
        SqliteMutesRepository(request.app.state.db),
        request.app.state.channel,
    )
    for payload in payloads:
        background_tasks.add_task(service.handle, payload)
    return Response(status_code=200)
