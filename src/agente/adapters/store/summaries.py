"""Rolling-summary repository (SPEC §9, §10). Implemented by T12."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...ports.store import SummaryRow


class SqliteSummariesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: ContactKey) -> SummaryRow | None:
        raise NotImplementedError("T12 (compaction) implements summaries")

    def save(self, key: ContactKey, text: str, watermark_message_id: int, now: datetime) -> None:
        raise NotImplementedError("T12 (compaction) implements summaries")
