"""Appointment repository (SPEC §10). Implemented by T9 (scheduling)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import AppointmentRow
from .db import parse_utc_iso, to_utc_iso


class SqliteAppointmentsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self, key: ContactKey, calendly_event_id: str, slot_utc: datetime, now: datetime
    ) -> int:
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "INSERT INTO appointment (phone_number_id, contact_phone, calendly_event_id,"
                    " slot_utc, status, created_at) VALUES (?, ?, ?, ?, 'scheduled', ?)",
                    (
                        key.phone_number_id,
                        key.contact_phone,
                        calendly_event_id,
                        to_utc_iso(slot_utc),
                        to_utc_iso(now),
                    ),
                )
            return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def for_contact(self, key: ContactKey) -> list[AppointmentRow]:
        rows = self._conn.execute(
            "SELECT * FROM appointment WHERE phone_number_id = ? AND contact_phone = ?"
            " ORDER BY slot_utc",
            (key.phone_number_id, key.contact_phone),
        ).fetchall()
        return [
            AppointmentRow(
                row["id"],
                key,
                row["calendly_event_id"],
                parse_utc_iso(row["slot_utc"]),
                row["status"],
                parse_utc_iso(row["created_at"]),
            )
            for row in rows
        ]

    def update_status(self, calendly_event_id: str, status: str, now: datetime) -> bool:
        try:
            with self._conn:
                cursor = self._conn.execute(
                    "UPDATE appointment SET status = ? WHERE calendly_event_id = ?",
                    (status, calendly_event_id),
                )
            return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
