"""GET /health — version and database reachability."""

from __future__ import annotations

import importlib.metadata

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..adapters.store.db import probe

router = APIRouter()


def package_version() -> str:
    try:
        return importlib.metadata.version("agente")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    version = package_version()
    problem = probe(settings.db_path)
    if problem is not None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "version": version, "database": problem},
        )
    return {"status": "ok", "version": version, "database": "ok"}
