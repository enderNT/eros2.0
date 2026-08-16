"""Message repository: append-only truth, dedupe and window reads (SPEC §4, §10)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import MessageRow
from .db import parse_utc_iso, to_utc_iso


class SqliteMessagesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add_inbound(
        self, key: ContactKey, kapso_message_id: str, text: str, created_at: datetime
    ) -> bool:
        return self._add(key, "inbound", kapso_message_id, text, created_at, sent_by_us=False)

    def add_outbound(
        self,
        key: ContactKey,
        kapso_message_id: str,
        text: str,
        created_at: datetime,
        *,
        sent_by_us: bool = True,
    ) -> bool:
        return self._add(key, "outbound", kapso_message_id, text, created_at, sent_by_us=sent_by_us)

    def window(self, key: ContactKey, limit: int) -> list[MessageRow]:
        """The last `limit` messages of the contact, oldest first."""
        try:
            rows = self._conn.execute(
                "SELECT id, phone_number_id, contact_phone, direction, kapso_message_id,"
                " text, created_at, sent_by_us FROM message"
                " WHERE phone_number_id = ? AND contact_phone = ?"
                " ORDER BY created_at DESC, id DESC LIMIT ?",
                (key.phone_number_id, key.contact_phone, limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return [
            MessageRow(
                id=row["id"],
                key=ContactKey(row["phone_number_id"], row["contact_phone"]),
                direction=row["direction"],
                kapso_message_id=row["kapso_message_id"],
                text=row["text"],
                created_at=parse_utc_iso(row["created_at"]),
                sent_by_us=bool(row["sent_by_us"]),
            )
            for row in reversed(rows)
        ]

    def _add(
        self,
        key: ContactKey,
        direction: str,
        kapso_message_id: str,
        text: str,
        created_at: datetime,
        *,
        sent_by_us: bool,
    ) -> bool:
        """Store the message; False when the Kapso id is already stored (dedupe)."""
        stamp = to_utc_iso(created_at)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO contact"
                    " (phone_number_id, contact_phone, created_at, updated_at)"
                    " VALUES (?, ?, ?, ?)",
                    (key.phone_number_id, key.contact_phone, stamp, stamp),
                )
                try:
                    self._conn.execute(
                        "INSERT INTO message (phone_number_id, contact_phone, direction,"
                        " kapso_message_id, text, created_at, sent_by_us)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            key.phone_number_id,
                            key.contact_phone,
                            direction,
                            kapso_message_id,
                            text,
                            stamp,
                            int(sent_by_us),
                        ),
                    )
                except sqlite3.IntegrityError as exc:
                    # The contact row was just ensured, so the only integrity
                    # failure left is the dedupe unique index.
                    if "message.kapso_message_id" in str(exc):
                        return False
                    raise
            return True
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
