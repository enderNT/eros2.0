from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.domain.contacts import ContactKey
from agente.ports.calendar import CalendarSlot
from agente.tools.agendar_cita import agendar_cita
from agente.tools.ver_horarios import ver_horarios


class FakeCalendar:
    async def availability(self, _start, _end):
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)
        return [CalendarSlot("a", now + timedelta(hours=2), now + timedelta(hours=3))]

    async def create_invitee(self, _slot, _name, _email):
        return "event-1"


@pytest.mark.asyncio
async def test_lists_local_bookable_slot():
    text = await ver_horarios(
        FakeCalendar(), datetime(2026, 8, 16, 12, tzinfo=UTC), "America/Mexico_City"
    )
    assert "—" in text


@pytest.mark.asyncio
async def test_booking_writes_appointment(db_conn):
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    slot = CalendarSlot("a", now + timedelta(hours=2), now + timedelta(hours=3))
    key = ContactKey("1087343774471931", "+12052943796")
    SqliteContactsRepository(db_conn).ensure_contact(key, now)
    result = await agendar_cita(
        FakeCalendar(),
        SqliteAppointmentsRepository(db_conn),
        key,
        slot,
        "Ana",
        "ana@example.com",
        now,
    )
    assert "registrada" in result
