"""Global runtime controls that are safe to change from the panel."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.errors import StoreError
from .db import to_utc_iso

MIN_BOOKING_FOLLOWUP_MINUTES = 0
MAX_BOOKING_FOLLOWUP_MINUTES = 90
MIN_APPOINTMENT_REMINDER_MINUTES = 1
MAX_APPOINTMENT_REMINDER_MINUTES = 10_080  # seven days


class SqliteRuntimeSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def booking_followup_minutes(self, default: int) -> int:
        try:
            row = self._conn.execute(
                "SELECT booking_followup_minutes FROM app_setting WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return int(row["booking_followup_minutes"]) if row else default

    def set_booking_followup_minutes(self, minutes: int, now: datetime) -> None:
        if not MIN_BOOKING_FOLLOWUP_MINUTES <= minutes <= MAX_BOOKING_FOLLOWUP_MINUTES:
            raise ValueError("booking follow-up minutes must be between 0 and 90")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO app_setting (id, booking_followup_minutes, updated_at)"
                    " VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                    " booking_followup_minutes = excluded.booking_followup_minutes,"
                    " updated_at = excluded.updated_at",
                    (minutes, to_utc_iso(now)),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def appointment_reminder_minutes(self, default: int) -> int:
        try:
            row = self._conn.execute(
                "SELECT appointment_reminder_minutes FROM app_setting WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return int(row["appointment_reminder_minutes"]) if row else default

    def set_appointment_reminder_minutes(self, minutes: int, now: datetime) -> None:
        if not MIN_APPOINTMENT_REMINDER_MINUTES <= minutes <= MAX_APPOINTMENT_REMINDER_MINUTES:
            raise ValueError("appointment reminder minutes must be between 1 and 10080")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO app_setting (id, booking_followup_minutes,"
                    " appointment_reminder_minutes, updated_at) VALUES (1, 90, ?, ?)"
                    " ON CONFLICT(id) DO UPDATE SET"
                    " appointment_reminder_minutes = excluded.appointment_reminder_minutes,"
                    " updated_at = excluded.updated_at",
                    (minutes, to_utc_iso(now)),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
