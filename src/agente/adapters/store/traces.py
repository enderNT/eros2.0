"""LLM call trace repository (SPEC §11). Implemented by T8."""

from __future__ import annotations

import json
import sqlite3

from ...domain.errors import StoreError
from ...ports.store import LlmTraceRow
from .db import parse_utc_iso, to_utc_iso


class SqliteTracesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, trace: LlmTraceRow) -> int:
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO llm_trace (turn_id, model, tokens_in, tokens_out,"
                    " cache_read_tokens,"
                    " cache_write_tokens, latency_ms, stop_reason, tools_called, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        trace.turn_id,
                        trace.model,
                        trace.tokens_in,
                        trace.tokens_out,
                        trace.cache_read_tokens,
                        trace.cache_write_tokens,
                        trace.latency_ms,
                        trace.stop_reason,
                        json.dumps(trace.tools_called),
                        to_utc_iso(trace.created_at),
                    ),
                )
            return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def recent(self, limit: int = 50) -> list[LlmTraceRow]:
        try:
            rows = self._conn.execute(
                "SELECT * FROM llm_trace ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return [
            LlmTraceRow(
                id=row["id"],
                turn_id=row["turn_id"],
                model=row["model"],
                tokens_in=row["tokens_in"],
                tokens_out=row["tokens_out"],
                cache_read_tokens=row["cache_read_tokens"],
                cache_write_tokens=row["cache_write_tokens"],
                latency_ms=row["latency_ms"],
                stop_reason=row["stop_reason"],
                tools_called=tuple(json.loads(row["tools_called"])),
                created_at=parse_utc_iso(row["created_at"]),
            )
            for row in rows
        ]
