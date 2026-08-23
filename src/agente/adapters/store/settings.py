"""Global runtime controls that are safe to change from the panel."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.errors import StoreError
from .db import to_utc_iso

# Cero no vale: "ahora mismo" significaría escribirle otra vez en el mismo
# instante en que se le acaba de contestar. Un minuto es el mínimo con sentido,
# y el que permite probarlo de punta a punta sin esperar una hora.
MIN_INTEREST_FOLLOWUP_MINUTES = 1
MAX_INTEREST_FOLLOWUP_MINUTES = 90
MIN_APPOINTMENT_REMINDER_MINUTES = 1
MAX_APPOINTMENT_REMINDER_MINUTES = 10_080  # seven days


class SqliteRuntimeSettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def interest_followup_minutes(self, default: int) -> int:
        try:
            row = self._conn.execute(
                "SELECT interest_followup_minutes FROM app_setting WHERE id = 1"
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return int(row["interest_followup_minutes"]) if row else default

    def set_interest_followup_minutes(self, minutes: int, now: datetime) -> None:
        if not MIN_INTEREST_FOLLOWUP_MINUTES <= minutes <= MAX_INTEREST_FOLLOWUP_MINUTES:
            raise ValueError("interest follow-up minutes must be between 1 and 90")
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO app_setting (id, interest_followup_minutes, updated_at)"
                    " VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                    " interest_followup_minutes = excluded.interest_followup_minutes,"
                    " updated_at = excluded.updated_at",
                    (minutes, to_utc_iso(now)),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def interest_followup_enabled(self, default: bool) -> bool:
        return self._flag("interest_followup_enabled", default)

    def set_interest_followup_enabled(self, enabled: bool, now: datetime) -> None:
        self._set_flag("interest_followup_enabled", enabled, now)

    def appointment_reminder_enabled(self, default: bool) -> bool:
        return self._flag("appointment_reminder_enabled", default)

    def set_appointment_reminder_enabled(self, enabled: bool, now: datetime) -> None:
        self._set_flag("appointment_reminder_enabled", enabled, now)

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
                    "INSERT INTO app_setting (id, appointment_reminder_minutes, updated_at)"
                    " VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                    " appointment_reminder_minutes = excluded.appointment_reminder_minutes,"
                    " updated_at = excluded.updated_at",
                    (minutes, to_utc_iso(now)),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def _flag(self, column: str, default: bool) -> bool:
        """Read one on/off switch.

        `column` is never user input — it comes from the four call sites above —
        so interpolating it is safe here and buys one helper instead of four
        near-identical bodies.
        """
        try:
            row = self._conn.execute(
                f"SELECT {column} FROM app_setting WHERE id = 1"  # noqa: S608
            ).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return bool(row[column]) if row else default

    def _set_flag(self, column: str, enabled: bool, now: datetime) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    f"INSERT INTO app_setting (id, {column}, updated_at)"  # noqa: S608
                    " VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET"
                    f" {column} = excluded.{column}, updated_at = excluded.updated_at",
                    (int(enabled), to_utc_iso(now)),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
