from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.domain.contacts import ContactKey
from agente.ports.calendar import CalendarSlot
from agente.tools.agendar_cita import ALREADY_BOOKED, NO_LINK, agendar_cita
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
async def test_booking_returns_the_link_without_claiming_a_confirmed_appointment(db_conn):
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    slot = CalendarSlot(
        "a",
        now + timedelta(hours=2),
        now + timedelta(hours=3),
        booking_url="https://calendly.com/x/new-meeting/2026-08-16T14:00:00Z",
    )
    key = ContactKey("1087343774471931", "+12052943796")
    SqliteContactsRepository(db_conn).ensure_contact(key, now)
    appointments = SqliteAppointmentsRepository(db_conn)
    result = await agendar_cita(appointments, key, slot, now)
    assert slot.booking_url in result
    assert "NO está agendada" in result
    assert appointments.for_contact(key) == []


@pytest.mark.asyncio
async def test_slot_without_a_link_is_refused(db_conn):
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    slot = CalendarSlot("a", now + timedelta(hours=2), now + timedelta(hours=3))
    key = ContactKey("1087343774471931", "+12052943796")
    SqliteContactsRepository(db_conn).ensure_contact(key, now)
    assert await agendar_cita(SqliteAppointmentsRepository(db_conn), key, slot, now) == NO_LINK


@pytest.mark.asyncio
async def test_a_confirmed_appointment_is_not_offered_again(db_conn):
    now = datetime(2026, 8, 16, 12, tzinfo=UTC)
    slot = CalendarSlot(
        "a", now + timedelta(hours=2), now + timedelta(hours=3), booking_url="https://x/y"
    )
    key = ContactKey("1087343774471931", "+12052943796")
    SqliteContactsRepository(db_conn).ensure_contact(key, now)
    appointments = SqliteAppointmentsRepository(db_conn)
    appointments.add(key, "event-1", slot.start_utc, now)
    assert await agendar_cita(appointments, key, slot, now) == ALREADY_BOOKED
