"""The scheduling tools now that the calendar can be written to (SPEC §6).

`agendar_cita` books outright and `cancelar_cita` releases in two steps. The
rules worth pinning here are the ones that stop being the model's job and become
the code's: booking replaces, and cancelling waits for a yes.
"""

from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import SlotTakenError
from agente.ports.calendar import Booking, CalendarSlot
from agente.services.booking import BookingService
from agente.tools.agendar_cita import EXPIRED, TAKEN, agendar_cita
from agente.tools.cancelar_cita import SIN_CITA, cancelar_cita
from agente.tools.ver_horarios import ver_horarios

NOW = datetime(2026, 8, 16, 12, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+12052943796")
TZ = "America/Mexico_City"


def _slot(hours: int = 2) -> CalendarSlot:
    return CalendarSlot("a", NOW + timedelta(hours=hours), NOW + timedelta(hours=hours + 1))


class FakeCalendar:
    """Books, cancels and refuses a taken slot, like the real one."""

    def __init__(self, *, taken: bool = False) -> None:
        self.taken = taken
        self.booked: list[datetime] = []
        self.canceled: list[str] = []
        self._n = 0

    async def availability(self, _start, _end):
        return [_slot()]

    async def book(self, slot, *, name, email, timezone, phone) -> Booking:
        if self.taken:
            raise SlotTakenError("slot already booked")
        self._n += 1
        self.booked.append(slot.start_utc)
        return Booking(f"event-{self._n}", f"invitee-{self._n}", slot.start_utc)

    async def cancel(self, event_id: str, *, reason: str = "") -> None:
        self.canceled.append(event_id)

    async def create_invitee(self, _slot, _name, _email):
        return "event-1"


class SilentChannel:
    async def send_text(self, *_args, **_kwargs) -> str:
        return "out-1"


def _service(db_conn, calendar) -> BookingService:
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    return BookingService(
        appointments=SqliteAppointmentsRepository(db_conn),
        contacts=SqliteContactsRepository(db_conn),
        messages=SqliteMessagesRepository(db_conn),
        outbox=SqliteOutboxRepository(db_conn),
        channel=SilentChannel(),
        calendar=calendar,
        invitee_email="citas@clinica.test",
        timezone=TZ,
        now=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_lists_local_bookable_slot():
    text = await ver_horarios(FakeCalendar(), NOW, TZ)
    assert "—" in text


@pytest.mark.asyncio
async def test_booking_confirms_the_appointment_and_records_it(db_conn):
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    result = await agendar_cita(booking, KEY, _slot(), NOW, TZ)
    assert "agendada y confirmada" in result
    assert "enlace" not in result.lower() or "ningún enlace" in result
    assert [row.slot_utc for row in booking.scheduled_for(KEY)] == [_slot().start_utc]
    assert calendar.booked == [_slot().start_utc]


@pytest.mark.asyncio
async def test_booking_again_replaces_the_previous_appointment(db_conn):
    """The old C09 hueco, closed in code: moving must not leave two."""
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    await agendar_cita(booking, KEY, _slot(2), NOW, TZ)
    result = await agendar_cita(booking, KEY, _slot(5), NOW, TZ)

    assert "reagendada" in result
    vigentes = booking.scheduled_for(KEY)
    assert [row.slot_utc for row in vigentes] == [_slot(5).start_utc]
    assert calendar.canceled == ["event-1"]


@pytest.mark.asyncio
async def test_moving_does_not_count_as_a_second_appointment(db_conn):
    booking = _service(db_conn, FakeCalendar())
    await agendar_cita(booking, KEY, _slot(2), NOW, TZ)
    await agendar_cita(booking, KEY, _slot(5), NOW, TZ)
    profile = SqliteContactsRepository(db_conn).get_profile(KEY)
    assert profile is not None and profile.appointment_count == 1


@pytest.mark.asyncio
async def test_a_slot_taken_in_the_meantime_is_reported_not_claimed(db_conn):
    booking = _service(db_conn, FakeCalendar(taken=True))
    result = await agendar_cita(booking, KEY, _slot(), NOW, TZ)
    assert result == TAKEN
    assert booking.scheduled_for(KEY) == []


@pytest.mark.asyncio
async def test_a_slot_in_the_past_is_refused_before_calling_the_calendar(db_conn):
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    past = CalendarSlot("a", NOW - timedelta(hours=1), NOW)
    assert await agendar_cita(booking, KEY, past, NOW, TZ) == EXPIRED
    assert calendar.booked == []


# --- cancelar_cita ------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelling_asks_before_it_acts(db_conn):
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    await agendar_cita(booking, KEY, _slot(), NOW, TZ)

    result = await cancelar_cita(booking, KEY, NOW, TZ)
    assert "NO se ha cancelado nada" in result
    assert len(booking.scheduled_for(KEY)) == 1
    assert calendar.canceled == []


@pytest.mark.asyncio
async def test_cancelling_confirmed_releases_the_appointment(db_conn):
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    await agendar_cita(booking, KEY, _slot(), NOW, TZ)

    result = await cancelar_cita(booking, KEY, NOW, TZ, confirmado=True)
    assert "cancelada" in result.lower()
    assert booking.scheduled_for(KEY) == []
    assert calendar.canceled == ["event-1"]
    profile = SqliteContactsRepository(db_conn).get_profile(KEY)
    assert profile is not None and profile.next_appointment_utc is None


@pytest.mark.asyncio
async def test_cancelling_without_an_appointment_says_so(db_conn):
    """Nobody's Thursday appointment gets invented so it can be cancelled."""
    calendar = FakeCalendar()
    booking = _service(db_conn, calendar)
    assert await cancelar_cita(booking, KEY, NOW, TZ) == SIN_CITA
    assert await cancelar_cita(booking, KEY, NOW, TZ, confirmado=True) == SIN_CITA
    assert calendar.canceled == []
