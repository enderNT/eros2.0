from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.booking_tokens import SqliteBookingTokensRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.domain.contacts import ContactKey
from agente.ports.calendar import CalendarSlot
from agente.tools.agendar_cita import ALREADY_BOOKED, NO_LINK, agendar_cita
from agente.tools.ver_horarios import ver_horarios

NOW = datetime(2026, 8, 16, 12, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+12052943796")


class FakeCalendar:
    async def availability(self, _start, _end):
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)
        return [CalendarSlot("a", now + timedelta(hours=2), now + timedelta(hours=3))]

    async def create_invitee(self, _slot, _name, _email):
        return "event-1"


def _slot(url: str = "") -> CalendarSlot:
    return CalendarSlot("a", NOW + timedelta(hours=2), NOW + timedelta(hours=3), booking_url=url)


def _repos(db_conn):
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    return SqliteAppointmentsRepository(db_conn), SqliteBookingTokensRepository(db_conn)


@pytest.mark.asyncio
async def test_lists_local_bookable_slot():
    text = await ver_horarios(FakeCalendar(), NOW, "America/Mexico_City")
    assert "—" in text


@pytest.mark.asyncio
async def test_booking_returns_the_link_without_claiming_a_confirmed_appointment(db_conn):
    appointments, tokens = _repos(db_conn)
    slot = _slot("https://calendly.com/x/new-meeting/2026-08-16T14:00:00Z")
    result = await agendar_cita(appointments, tokens, KEY, slot, NOW, make_token=lambda: "tok-1")
    assert slot.booking_url in result
    assert "NO está agendada" in result
    assert appointments.for_contact(KEY) == []


@pytest.mark.asyncio
async def test_the_link_carries_a_token_that_resolves_to_the_contact(db_conn):
    appointments, tokens = _repos(db_conn)
    slot = _slot("https://calendly.com/x/new-meeting/2026-08-16T14:00:00Z")
    result = await agendar_cita(appointments, tokens, KEY, slot, NOW, make_token=lambda: "tok-1")
    assert "utm_content=tok-1" in result
    record = tokens.resolve("tok-1")
    assert record is not None
    assert record.key == KEY
    assert record.slot_utc == slot.start_utc


@pytest.mark.asyncio
async def test_the_link_never_carries_the_phone_number(db_conn):
    """The URL leaves our control the moment it is sent; only the opaque id rides."""
    appointments, tokens = _repos(db_conn)
    result = await agendar_cita(appointments, tokens, KEY, _slot("https://calendly.com/x/y"), NOW)
    assert KEY.contact_phone not in result
    assert "12052943796" not in result


@pytest.mark.asyncio
async def test_an_existing_query_string_is_preserved(db_conn):
    appointments, tokens = _repos(db_conn)
    result = await agendar_cita(
        appointments,
        tokens,
        KEY,
        _slot("https://calendly.com/x/y?month=2026-08"),
        NOW,
        make_token=lambda: "tok-1",
    )
    assert "month=2026-08&utm_content=tok-1" in result


@pytest.mark.asyncio
async def test_slot_without_a_link_is_refused(db_conn):
    appointments, tokens = _repos(db_conn)
    assert await agendar_cita(appointments, tokens, KEY, _slot(), NOW) == NO_LINK


@pytest.mark.asyncio
async def test_a_confirmed_appointment_is_not_offered_again(db_conn):
    appointments, tokens = _repos(db_conn)
    slot = _slot("https://x/y")
    appointments.add(KEY, "event-1", slot.start_utc, NOW)
    assert await agendar_cita(appointments, tokens, KEY, slot, NOW) == ALREADY_BOOKED
