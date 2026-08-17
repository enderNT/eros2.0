"""Erase everything we hold about one contact.

Deliberately its own repository rather than a method on each of the others:
the delete has to be **one transaction**. A half-purged contact — messages
gone but the rolling summary still there — would leave the agent talking
about a conversation the patient cannot see, which is worse than not purging
at all.

Destructive and irreversible, so it writes an `audit_log` row like every
other switch in the panel. It does not touch Calendly: a booked appointment
stays booked on their side, and only a human can cancel it.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from .db import to_utc_iso

# Children before parents: `summary` points at `message`, and `message`,
# `appointment` and `profile` all point at `contact`.
_TABLES = (
    "summary",
    "booking_token",
    "appointment",
    "message",
    "mute",
    "profile",
    "contact",
)


class SqlitePurgeRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def contact(self, key: ContactKey, now: datetime, *, actor: str, reason: str) -> dict[str, int]:
        """Delete every row we hold for the contact; return what was removed."""
        removed: dict[str, int] = {}
        try:
            with self._conn:
                for table in _TABLES:
                    cursor = self._conn.execute(
                        f"DELETE FROM {table} WHERE phone_number_id = ? AND contact_phone = ?",
                        (key.phone_number_id, key.contact_phone),
                    )
                    if cursor.rowcount:
                        removed[table] = cursor.rowcount
                self._conn.execute(
                    "INSERT INTO audit_log (created_at, actor, action, phone_number_id,"
                    " contact_phone, reason, urgent) VALUES (?, ?, 'contact_purged', ?, ?, ?, 0)",
                    (
                        to_utc_iso(now),
                        actor,
                        key.phone_number_id,
                        key.contact_phone,
                        reason,
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return removed
