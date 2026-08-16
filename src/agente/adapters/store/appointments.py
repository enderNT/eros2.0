"""Appointment repository (SPEC §10). Implemented by T9 (scheduling)."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from ...domain.contacts import ContactKey
from ...ports.store import AppointmentRow


class SqliteAppointmentsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self, key: ContactKey, calendly_event_id: str, slot_utc: datetime, now: datetime
    ) -> int:
        raise NotImplementedError("T9 (scheduling) implements appointments")

    def for_contact(self, key: ContactKey) -> list[AppointmentRow]:
        raise NotImplementedError("T9 (scheduling) implements appointments")

    def update_status(self, calendly_event_id: str, status: str, now: datetime) -> bool:
        raise NotImplementedError("T9 (scheduling) implements appointments")
