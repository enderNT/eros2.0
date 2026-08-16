"""LLM call trace repository (SPEC §11). Implemented by T8."""

from __future__ import annotations

import sqlite3

from ...ports.store import LlmTraceRow


class SqliteTracesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, trace: LlmTraceRow) -> int:
        raise NotImplementedError("T8 (agent loop) implements traces")

    def recent(self, limit: int = 50) -> list[LlmTraceRow]:
        raise NotImplementedError("T8 (agent loop) implements traces")
