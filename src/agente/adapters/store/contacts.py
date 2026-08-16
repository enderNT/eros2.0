"""Contact and profile repository (SPEC §9, §10)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import ContactRow, Profile
from .db import optional_utc_iso, parse_utc_iso, to_utc_iso


class SqliteContactsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def ensure_contact(
        self,
        key: ContactKey,
        now: datetime,
        *,
        display_name: str | None = None,
        timezone: str | None = None,
    ) -> None:
        """Create the contact if new; refresh name/timezone when provided."""
        stamp = to_utc_iso(now)
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO contact"
                    " (phone_number_id, contact_phone, display_name, timezone,"
                    " created_at, updated_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (phone_number_id, contact_phone) DO UPDATE SET"
                    " display_name = COALESCE(excluded.display_name, contact.display_name),"
                    " timezone = COALESCE(excluded.timezone, contact.timezone),"
                    " updated_at = excluded.updated_at",
                    (key.phone_number_id, key.contact_phone, display_name, timezone, stamp, stamp),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def get_contact(self, key: ContactKey) -> ContactRow | None:
        row = self._fetch_one(
            "SELECT display_name, timezone, created_at, updated_at FROM contact"
            " WHERE phone_number_id = ? AND contact_phone = ?",
            (key.phone_number_id, key.contact_phone),
        )
        if row is None:
            return None
        return ContactRow(
            key=key,
            display_name=row["display_name"],
            timezone=row["timezone"],
            created_at=parse_utc_iso(row["created_at"]),
            updated_at=parse_utc_iso(row["updated_at"]),
        )

    def get_profile(self, key: ContactKey) -> Profile | None:
        row = self._fetch_one(
            "SELECT name, email, kind, timezone, appointment_count, last_appointment_utc,"
            " next_appointment_utc, handoff_state, updated_at FROM profile"
            " WHERE phone_number_id = ? AND contact_phone = ?",
            (key.phone_number_id, key.contact_phone),
        )
        if row is None:
            return None
        return Profile(
            key=key,
            name=row["name"],
            email=row["email"],
            kind=row["kind"],
            timezone=row["timezone"],
            appointment_count=row["appointment_count"],
            last_appointment_utc=_optional_dt(row["last_appointment_utc"]),
            next_appointment_utc=_optional_dt(row["next_appointment_utc"]),
            handoff_state=row["handoff_state"],
            updated_at=parse_utc_iso(row["updated_at"]),
        )

    def save_profile(self, profile: Profile) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO profile (phone_number_id, contact_phone, name, email, kind,"
                    " timezone, appointment_count, last_appointment_utc, next_appointment_utc,"
                    " handoff_state, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT (phone_number_id, contact_phone) DO UPDATE SET"
                    " name = excluded.name, email = excluded.email, kind = excluded.kind,"
                    " timezone = excluded.timezone,"
                    " appointment_count = excluded.appointment_count,"
                    " last_appointment_utc = excluded.last_appointment_utc,"
                    " next_appointment_utc = excluded.next_appointment_utc,"
                    " handoff_state = excluded.handoff_state,"
                    " updated_at = excluded.updated_at",
                    (
                        profile.key.phone_number_id,
                        profile.key.contact_phone,
                        profile.name,
                        profile.email,
                        profile.kind,
                        profile.timezone,
                        profile.appointment_count,
                        optional_utc_iso(profile.last_appointment_utc),
                        optional_utc_iso(profile.next_appointment_utc),
                        profile.handoff_state,
                        to_utc_iso(profile.updated_at),
                    ),
                )
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def _fetch_one(self, sql: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            return self._conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc


def _optional_dt(value: str | None) -> datetime | None:
    return parse_utc_iso(value) if value is not None else None
