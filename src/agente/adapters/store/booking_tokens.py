"""Booking-token repository: the link between a slot link and a contact."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import BookingTokenRow
from .db import parse_utc_iso, to_utc_iso


class SqliteBookingTokensRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def issue(self, token: str, key: ContactKey, slot_utc: datetime, now: datetime) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO booking_token (token, phone_number_id, contact_phone,"
                    " slot_utc, created_at) VALUES (?, ?, ?, ?, ?)"
                    " ON CONFLICT (token) DO NOTHING",
                    (
                        token,
                        key.phone_number_id,
                        key.contact_phone,
                        to_utc_iso(slot_utc),
                        to_utc_iso(now),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def resolve(self, token: str) -> BookingTokenRow | None:
        try:
            row = self._conn.execute(
                "SELECT token, phone_number_id, contact_phone, slot_utc, created_at"
                " FROM booking_token WHERE token = ?",
                (token,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        if row is None:
            return None
        return BookingTokenRow(
            token=row["token"],
            key=ContactKey(row["phone_number_id"], row["contact_phone"]),
            slot_utc=parse_utc_iso(row["slot_utc"]),
            created_at=parse_utc_iso(row["created_at"]),
        )
