"""Durable, one-shot booking follow-ups."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import OutboxRow
from .db import parse_utc_iso, to_utc_iso


class SqliteOutboxRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def schedule_booking_followup(
        self,
        key: ContactKey,
        booking_token: str,
        slot_utc: datetime,
        text: str,
        due_at: datetime,
    ) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO outbox (phone_number_id, contact_phone, text, due_at,"
                    " booking_token, slot_utc) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(booking_token) WHERE booking_token IS NOT NULL DO NOTHING",
                    (
                        key.phone_number_id,
                        key.contact_phone,
                        text,
                        to_utc_iso(due_at),
                        booking_token,
                        to_utc_iso(slot_utc),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def due(self, now: datetime, limit: int = 20) -> list[OutboxRow]:
        try:
            rows = self._conn.execute(
                "SELECT id, phone_number_id, contact_phone, text, due_at, booking_token, slot_utc"
                " FROM outbox WHERE sent_at IS NULL AND due_at <= ? ORDER BY due_at, id LIMIT ?",
                (to_utc_iso(now), limit),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return [
            OutboxRow(
                id=row["id"],
                key=ContactKey(row["phone_number_id"], row["contact_phone"]),
                text=row["text"],
                due_at=parse_utc_iso(row["due_at"]),
                booking_token=row["booking_token"],
                slot_utc=parse_utc_iso(row["slot_utc"]) if row["slot_utc"] else None,
            )
            for row in rows
        ]

    def consume(self, row_id: int, now: datetime) -> bool:
        """Claim a row before sending: sends are deliberately never retried blindly."""
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "UPDATE outbox SET sent_at = ? WHERE id = ? AND sent_at IS NULL",
                    (to_utc_iso(now), row_id),
                )
            return cursor.rowcount == 1
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def cancel_for_contact(self, key: ContactKey) -> None:
        self._cancel(
            "phone_number_id = ? AND contact_phone = ?",
            (key.phone_number_id, key.contact_phone),
        )

    def cancel_for_token(self, booking_token: str) -> None:
        self._cancel("booking_token = ?", (booking_token,))

    def _cancel(self, predicate: str, values: tuple[str, ...]) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    f"DELETE FROM outbox WHERE sent_at IS NULL AND {predicate}", values
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
