"""Mute repository: the three-level switch and its audit trail.

Resolution order for `is_bot_muted` is global, then number, then contact
(PROJECT.md, "Human handoff"). A row present means muted; `muted_until`
NULL means indefinitely, and the mute stops being active at exactly that
instant. Every mutation writes exactly one `audit_log` row in the same
transaction as the state change.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...domain.errors import StoreError
from ...ports.store import AuditEntry, MuteState
from .db import optional_utc_iso, parse_utc_iso, to_utc_iso


class SqliteMutesRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def is_bot_muted(self, key: ContactKey, now: datetime) -> bool:
        return (
            self._level_active("SELECT muted_until FROM global_state WHERE id = 1", (), now)
            or self._level_active(
                "SELECT muted_until FROM number_mute WHERE phone_number_id = ?",
                (key.phone_number_id,),
                now,
            )
            or self._level_active(
                "SELECT muted_until FROM mute"
                " WHERE phone_number_id = ? AND contact_phone = ?",
                (key.phone_number_id, key.contact_phone),
                now,
            )
        )

    def set_mute(
        self,
        key: ContactKey,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
    ) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO mute (phone_number_id, contact_phone, muted_at, muted_until)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (phone_number_id, contact_phone)"
                    " DO UPDATE SET muted_at = excluded.muted_at,"
                    " muted_until = excluded.muted_until",
                    (
                        key.phone_number_id,
                        key.contact_phone,
                        to_utc_iso(now),
                        optional_utc_iso(until),
                    ),
                )
                self._audit(now, actor, "contact_muted", reason, key=key)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def clear_mute(self, key: ContactKey, now: datetime, *, actor: str, reason: str) -> None:
        try:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM mute WHERE phone_number_id = ? AND contact_phone = ?",
                    (key.phone_number_id, key.contact_phone),
                )
                self._audit(now, actor, "contact_unmuted", reason, key=key)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def set_number_mute(
        self,
        phone_number_id: str,
        muted: bool,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
    ) -> None:
        try:
            with self._conn:
                if muted:
                    self._conn.execute(
                        "INSERT INTO number_mute (phone_number_id, muted_at, muted_until)"
                        " VALUES (?, ?, ?)"
                        " ON CONFLICT (phone_number_id)"
                        " DO UPDATE SET muted_at = excluded.muted_at,"
                        " muted_until = excluded.muted_until",
                        (phone_number_id, to_utc_iso(now), optional_utc_iso(until)),
                    )
                else:
                    self._conn.execute(
                        "DELETE FROM number_mute WHERE phone_number_id = ?", (phone_number_id,)
                    )
                action = "number_muted" if muted else "number_unmuted"
                self._audit(now, actor, action, reason, phone_number_id=phone_number_id)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def set_global(
        self,
        muted: bool,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
    ) -> None:
        try:
            with self._conn:
                if muted:
                    self._conn.execute(
                        "INSERT INTO global_state (id, muted_at, muted_until) VALUES (1, ?, ?)"
                        " ON CONFLICT (id)"
                        " DO UPDATE SET muted_at = excluded.muted_at,"
                        " muted_until = excluded.muted_until",
                        (to_utc_iso(now), optional_utc_iso(until)),
                    )
                else:
                    self._conn.execute("DELETE FROM global_state WHERE id = 1")
                action = "global_muted" if muted else "global_unmuted"
                self._audit(now, actor, action, reason)
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def contact_mute(self, key: ContactKey) -> MuteState | None:
        row = self._fetch_one(
            "SELECT muted_at, muted_until FROM mute"
            " WHERE phone_number_id = ? AND contact_phone = ?",
            (key.phone_number_id, key.contact_phone),
        )
        return _mute_state(row)

    def number_mute(self, phone_number_id: str) -> MuteState | None:
        row = self._fetch_one(
            "SELECT muted_at, muted_until FROM number_mute WHERE phone_number_id = ?",
            (phone_number_id,),
        )
        return _mute_state(row)

    def global_mute(self) -> MuteState | None:
        row = self._fetch_one("SELECT muted_at, muted_until FROM global_state WHERE id = 1", ())
        return _mute_state(row)

    def audit_trail(self, limit: int = 100) -> list[AuditEntry]:
        try:
            rows = self._conn.execute(
                "SELECT created_at, actor, action, phone_number_id, contact_phone, reason,"
                " urgent FROM audit_log ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc
        return [
            AuditEntry(
                created_at=parse_utc_iso(row["created_at"]),
                actor=row["actor"],
                action=row["action"],
                reason=row["reason"],
                phone_number_id=row["phone_number_id"],
                contact_phone=row["contact_phone"],
                urgent=bool(row["urgent"]),
            )
            for row in rows
        ]

    def _level_active(self, sql: str, params: tuple[object, ...], now: datetime) -> bool:
        row = self._fetch_one(sql, params)
        if row is None:
            return False
        until = row["muted_until"]
        return until is None or parse_utc_iso(until) > now

    def _fetch_one(self, sql: str, params: tuple[object, ...]) -> sqlite3.Row | None:
        try:
            return self._conn.execute(sql, params).fetchone()
        except sqlite3.Error as exc:
            raise StoreError(str(exc)) from exc

    def _audit(
        self,
        now: datetime,
        actor: str,
        action: str,
        reason: str,
        *,
        key: ContactKey | None = None,
        phone_number_id: str | None = None,
        urgent: bool = False,
    ) -> None:
        target_key = key.phone_number_id if key is not None else phone_number_id
        self._conn.execute(
            "INSERT INTO audit_log (created_at, actor, action, phone_number_id,"
            " contact_phone, reason, urgent) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                to_utc_iso(now),
                actor,
                action,
                target_key,
                key.contact_phone if key is not None else None,
                reason,
                int(urgent),
            ),
        )


def _mute_state(row: sqlite3.Row | None) -> MuteState | None:
    if row is None:
        return None
    until = row["muted_until"]
    return MuteState(
        muted_at=parse_utc_iso(row["muted_at"]),
        muted_until=parse_utc_iso(until) if until is not None else None,
    )
