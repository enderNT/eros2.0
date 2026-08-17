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
                    " booking_token, slot_utc, kind) VALUES (?, ?, ?, ?, ?, ?, 'booking_followup')"
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

    def schedule_appointment_reminder(
        self,
        key: ContactKey,
        calendly_event_id: str,
        slot_utc: datetime,
        text: str,
        due_at: datetime,
        *,
        replace_pending: bool = False,
    ) -> None:
        """Create one reminder per Calendly event, optionally moving an unsent one.

        The replacement path is used only after a global timing change. A sent
        reminder is never resurrected just because someone moves the slider.
        """
        try:
            with self._conn:
                if replace_pending:
                    self._conn.execute(
                        "UPDATE outbox SET text = ?, due_at = ?, slot_utc = ?"
                        " WHERE appointment_event_id = ? AND sent_at IS NULL",
                        (text, to_utc_iso(due_at), to_utc_iso(slot_utc), calendly_event_id),
                    )
                self._conn.execute(
                    "INSERT INTO outbox (phone_number_id, contact_phone, text, due_at, slot_utc,"
                    " kind, appointment_event_id) VALUES (?, ?, ?, ?, ?, 'appointment_reminder', ?)"
                    " ON CONFLICT(appointment_event_id) WHERE appointment_event_id IS NOT NULL"
                    " DO NOTHING",
                    (
                        key.phone_number_id,
                        key.contact_phone,
                        text,
                        to_utc_iso(due_at),
                        to_utc_iso(slot_utc),
                        calendly_event_id,
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def due(self, now: datetime, limit: int = 20, *, kind: str | None = None) -> list[OutboxRow]:
        try:
            filter_sql = " AND kind = ?" if kind else ""
            values: tuple[str | int, ...] = (to_utc_iso(now),)
            if kind:
                values += (kind,)
            values += (limit,)
            rows = self._conn.execute(
                "SELECT id, phone_number_id, contact_phone, text, due_at, booking_token, slot_utc,"
                " kind, appointment_event_id FROM outbox WHERE sent_at IS NULL AND due_at <= ?"
                f"{filter_sql} ORDER BY due_at, id LIMIT ?",
                values,
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
                kind=row["kind"],
                appointment_event_id=row["appointment_event_id"],
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

    def cancel_for_appointment(self, calendly_event_id: str) -> None:
        self._cancel("appointment_event_id = ?", (calendly_event_id,))

    def pending_appointment_reminder(self, key: ContactKey) -> OutboxRow | None:
        try:
            row = self._conn.execute(
                "SELECT id, phone_number_id, contact_phone, text, due_at, booking_token, slot_utc,"
                " kind, appointment_event_id FROM outbox"
                " WHERE phone_number_id = ? AND contact_phone = ?"
                " AND kind = 'appointment_reminder' AND sent_at IS NULL"
                " ORDER BY slot_utc, id LIMIT 1",
                (key.phone_number_id, key.contact_phone),
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        if row is None:
            return None
        return OutboxRow(
            id=row["id"],
            key=ContactKey(row["phone_number_id"], row["contact_phone"]),
            text=row["text"],
            due_at=parse_utc_iso(row["due_at"]),
            booking_token=row["booking_token"],
            slot_utc=parse_utc_iso(row["slot_utc"]) if row["slot_utc"] else None,
            kind=row["kind"],
            appointment_event_id=row["appointment_event_id"],
        )

    def _cancel(self, predicate: str, values: tuple[str, ...]) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    f"DELETE FROM outbox WHERE sent_at IS NULL AND {predicate}", values
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
