from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import CalendlyError
from agente.ports.calendar import Booking, CalendarSlot
from agente.services.booking import BookingService
from agente.services.knowledge import Knowledge, Section
from agente.tools.registry import CALENDAR_DOWN, UNKNOWN_SLOT, build_tools

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")
SLOT = CalendarSlot(
    "a",
    NOW + timedelta(days=1),
    NOW + timedelta(days=1, hours=1),
    booking_url="https://calendly.com/x/new-meeting/2026-08-18T12:00:00Z",
)


class FakeCalendar:
    def __init__(self, slots=(SLOT,), fail=False, fail_book=False):
        self.slots, self.fail, self.fail_book = list(slots), fail, fail_book
        self.booked, self.canceled = [], []

    async def availability(self, _start, _end):
        if self.fail:
            raise CalendlyError("down")
        return self.slots

    async def book(self, slot, *, name, email, timezone, phone):
        if self.fail_book:
            raise CalendlyError("down")
        self.booked.append((slot.start_utc, name, email, phone))
        return Booking("event-1", "invitee-1", slot.start_utc)

    async def cancel(self, event_id, *, reason=""):
        self.canceled.append(event_id)

    async def create_invitee(self, slot, name, email):
        return "event-1"


class SilentChannel:
    async def send_text(self, *_args, **_kwargs) -> str:
        return "out-1"


@pytest.fixture()
def tools(db_conn, mutes):
    def _build(calendar=None):
        SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
        return build_tools(
            knowledge=Knowledge("guia", [Section("Precios y formas de pago", "$1,000 MXN")]),
            mutes=mutes,
            calendar=calendar or FakeCalendar(),
            booking=BookingService(
                appointments=SqliteAppointmentsRepository(db_conn),
                contacts=SqliteContactsRepository(db_conn),
                messages=SqliteMessagesRepository(db_conn),
                outbox=SqliteOutboxRepository(db_conn),
                channel=SilentChannel(),
                calendar=calendar or FakeCalendar(),
                invitee_email="citas@clinica.test",
                timezone="America/Mexico_City",
                now=lambda: NOW,
            ),
            key=KEY,
            timezone="America/Mexico_City",
            now=lambda: NOW,
        )

    return _build


def test_every_defined_tool_has_a_handler(tools):
    definitions, handlers = tools()
    assert {item["name"] for item in definitions} == set(handlers)
    assert set(handlers) == {
        "buscar_wiki",
        "ver_horarios",
        "agendar_cita",
        "cancelar_cita",
        "escalar_a_humano",
    }


@pytest.mark.asyncio
async def test_availability_is_listed_with_a_bookable_identifier(tools):
    _, handlers = tools()
    text = await handlers["ver_horarios"]({})
    assert SLOT.start_utc.isoformat() in text


@pytest.mark.asyncio
async def test_booking_reserves_the_slot_and_records_the_appointment(tools, db_conn):
    calendar = FakeCalendar()
    _, handlers = tools(calendar)
    result = await handlers["agendar_cita"]({"inicio": SLOT.start_utc.isoformat()})
    assert "agendada y confirmada" in result
    filas = SqliteAppointmentsRepository(db_conn).for_contact(KEY)
    assert [fila.slot_utc for fila in filas] == [SLOT.start_utc]
    assert calendar.booked and calendar.booked[0][0] == SLOT.start_utc


@pytest.mark.asyncio
async def test_the_patient_phone_is_what_reaches_the_calendar(tools):
    """Reserving ourselves means we set the number, instead of checking it after."""
    calendar = FakeCalendar()
    _, handlers = tools(calendar)
    await handlers["agendar_cita"]({"inicio": SLOT.start_utc.isoformat()})
    assert calendar.booked[0][3] == KEY.contact_phone


@pytest.mark.asyncio
async def test_cancelling_needs_a_second_call_with_confirmation(tools):
    calendar = FakeCalendar()
    _, handlers = tools(calendar)
    await handlers["agendar_cita"]({"inicio": SLOT.start_utc.isoformat()})

    primera = await handlers["cancelar_cita"]({})
    assert "NO se ha cancelado nada" in primera
    assert not calendar.canceled

    segunda = await handlers["cancelar_cita"]({"confirmado": True})
    assert "cancelada" in segunda.lower()
    assert calendar.canceled == ["event-1"]


@pytest.mark.asyncio
async def test_invented_slot_is_refused_without_touching_the_calendar(tools):
    calendar = FakeCalendar()
    _, handlers = tools(calendar)
    assert await handlers["agendar_cita"]({"inicio": "2026-09-01T10:00:00+00:00"}) == UNKNOWN_SLOT
    assert not calendar.booked


@pytest.mark.asyncio
async def test_malformed_slot_identifier_is_refused(tools):
    _, handlers = tools()
    assert await handlers["agendar_cita"]({"inicio": "el jueves"}) == UNKNOWN_SLOT


@pytest.mark.asyncio
async def test_calendar_failure_degrades_instead_of_raising(tools):
    _, handlers = tools(FakeCalendar(fail=True))
    assert await handlers["ver_horarios"]({}) == CALENDAR_DOWN
    assert await handlers["agendar_cita"]({"inicio": SLOT.start_utc.isoformat()}) == CALENDAR_DOWN


@pytest.mark.asyncio
async def test_a_booking_failure_never_reads_as_a_confirmed_appointment(tools, db_conn):
    """The calendar answering badly must not become "tu cita quedó confirmada"."""
    _, handlers = tools(FakeCalendar(fail_book=True))
    resultado = await handlers["agendar_cita"]({"inicio": SLOT.start_utc.isoformat()})
    assert resultado == CALENDAR_DOWN
    assert SqliteAppointmentsRepository(db_conn).for_contact(KEY) == []


@pytest.mark.asyncio
async def test_escalation_mutes_the_contact(tools, mutes):
    _, handlers = tools()
    await handlers["escalar_a_humano"]({"motivo": "pidió hablar con alguien"})
    assert mutes.is_bot_muted(KEY, NOW)


@pytest.mark.asyncio
async def test_wiki_lookup_returns_confirmed_text(tools):
    _, handlers = tools()
    assert "$1,000" in await handlers["buscar_wiki"]({"consulta": "Precios"})
