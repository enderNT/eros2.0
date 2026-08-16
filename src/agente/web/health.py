"""GET /health — version and database reachability."""

from __future__ import annotations

import importlib.metadata
import os
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


def package_version() -> str:
    try:
        return importlib.metadata.version("agente")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def probe_database(path: Path) -> str | None:
    """None when the SQLite file is reachable and writable, else the reason."""
    try:
        conn = sqlite3.connect(path)
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"unreachable ({exc.__class__.__name__})"
    if not os.access(path, os.W_OK):
        return "not writable"
    return None


@router.get("/health")
async def health(request: Request):
    settings = request.app.state.settings
    version = package_version()
    problem = probe_database(settings.db_path)
    if problem is not None:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "version": version, "database": problem},
        )
    return {"status": "ok", "version": version, "database": "ok"}
