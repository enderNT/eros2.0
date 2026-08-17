"""Rolling-summary repository (SPEC §9, §10). Implemented by T12."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import SummaryRow
from .db import parse_utc_iso, to_utc_iso


class SqliteSummariesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: ContactKey) -> SummaryRow | None:
        try:
            row = self._conn.execute(
                "SELECT text, watermark_message_id, updated_at FROM summary"
                " WHERE phone_number_id = ? AND contact_phone = ?",
                (key.phone_number_id, key.contact_phone),
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return (
            SummaryRow(
                key, row["text"], row["watermark_message_id"], parse_utc_iso(row["updated_at"])
            )
            if row
            else None
        )

    def save(self, key: ContactKey, text: str, watermark_message_id: int, now: datetime) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO summary (phone_number_id, contact_phone, text,"
                    " watermark_message_id, updated_at) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT(phone_number_id, contact_phone)"
                    " DO UPDATE SET text=excluded.text,"
                    " watermark_message_id=excluded.watermark_message_id,"
                    " updated_at=excluded.updated_at",
                    (
                        key.phone_number_id,
                        key.contact_phone,
                        text,
                        watermark_message_id,
                        to_utc_iso(now),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
