"""The Calendly webhook turning a slot link into a real appointment (TASKS T9b)."""

from datetime import UTC, datetime

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.booking_tokens import SqliteBookingTokensRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import KapsoError
from agente.services.booking import BookingService, confirmation_text

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)  # 11:00 in Mexico City
KEY = ContactKey("1087343774471931", "+525512345678")
EVENT = "https://api.calendly.com/scheduled_events/abc"


class FakeChannel:
    def __init__(self, fail: bool = False) -> None:
        self.sent, self.fail = [], fail

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        if self.fail:
            raise KapsoError("down")
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"

    async def list_conversations(self, *_args, **_kwargs):  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture()
def booking(db_conn, contacts, messages):
    def _make(channel=None, address=""):
        return BookingService(
            tokens=SqliteBookingTokensRepository(db_conn),
            appointments=SqliteAppointmentsRepository(db_conn),
            contacts=contacts,
            messages=messages,
            outbox=SqliteOutboxRepository(db_conn),
            channel=channel or FakeChannel(),
            timezone="America/Mexico_City",
            address=address,
            now=lambda: NOW,
        )

    return _make


def _issue(db_conn, token: str = "tok-1") -> None:
    SqliteBookingTokensRepository(db_conn).issue(token, KEY, SLOT, NOW)


def _created(token: str = "tok-1", event: str = EVENT) -> dict:
    return {
        "event": event,
        "name": "Ana",
        "email": "ana@example.com",
        "tracking": {"utm_content": token},
        "scheduled_event": {"start_time": "2026-08-18T17:00:00Z"},
    }


@pytest.mark.asyncio
async def test_created_writes_one_appointment_and_one_message(db_conn, booking, contacts):
    _issue(db_conn)
    channel = FakeChannel()
    await booking(channel).handle("invitee.created", _created())
    rows = SqliteAppointmentsRepository(db_conn).for_contact(KEY)
    assert [(row.calendly_event_id, row.status) for row in rows] == [(EVENT, "scheduled")]
    assert len(channel.sent) == 1
    assert "11:00 a. m." in channel.sent[0][1]


@pytest.mark.asyncio
async def test_created_updates_the_durable_profile(db_conn, booking, contacts):
    _issue(db_conn)
    await booking().handle("invitee.created", _created())
    profile = contacts.get_profile(KEY)
    assert profile.next_appointment_utc == SLOT
    assert profile.appointment_count == 1
    assert profile.kind == "patient"
    assert (profile.name, profile.email) == ("Ana", "ana@example.com")


@pytest.mark.asyncio
async def test_the_same_delivery_twice_is_a_no_op(db_conn, booking):
    _issue(db_conn)
    channel = FakeChannel()
    service = booking(channel)
    await service.handle("invitee.created", _created())
    await service.handle("invitee.created", _created())
    assert len(SqliteAppointmentsRepository(db_conn).for_contact(KEY)) == 1
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_an_unknown_token_is_ignored(db_conn, booking):
    """A booking made straight from Calendly is not ours to confirm."""
    channel = FakeChannel()
    await booking(channel).handle("invitee.created", _created(token="nobody-issued-this"))
    assert SqliteAppointmentsRepository(db_conn).for_contact(KEY) == []
    assert channel.sent == []


@pytest.mark.asyncio
async def test_the_address_is_only_mentioned_when_configured(db_conn, booking):
    _issue(db_conn)
    channel = FakeChannel()
    await booking(channel, address="Av. Reforma 100").handle("invitee.created", _created())
    assert "Av. Reforma 100" in channel.sent[0][1]


@pytest.mark.asyncio
async def test_canceled_flips_the_status_and_clears_the_profile(db_conn, booking, contacts):
    _issue(db_conn)
    channel = FakeChannel()
    service = booking(channel)
    await service.handle("invitee.created", _created())
    await service.handle("invitee.canceled", {"event": EVENT})
    row = SqliteAppointmentsRepository(db_conn).find(EVENT)
    assert row.status == "canceled"
    assert contacts.get_profile(KEY).next_appointment_utc is None
    assert len(channel.sent) == 2


@pytest.mark.asyncio
async def test_a_repeated_cancel_notifies_once(db_conn, booking):
    _issue(db_conn)
    channel = FakeChannel()
    service = booking(channel)
    await service.handle("invitee.created", _created())
    await service.handle("invitee.canceled", {"event": EVENT})
    await service.handle("invitee.canceled", {"event": EVENT})
    assert len(channel.sent) == 2


@pytest.mark.asyncio
async def test_a_failed_notification_keeps_the_appointment(db_conn, booking):
    _issue(db_conn)
    await booking(FakeChannel(fail=True)).handle("invitee.created", _created())
    assert SqliteAppointmentsRepository(db_conn).find(EVENT) is not None


def test_the_confirmation_never_doubles_a_period():
    """The time label ends in "p. m." and the address may end in one too."""
    text = confirmation_text(SLOT, "America/Mexico_City", NOW, "Sócrates 128, Polanco.")
    assert ".." not in text


def test_the_confirmation_localizes_across_a_dst_transition():
    """The clinic zone has no DST, but the confirmation must not assume that.

    America/New_York springs forward on 2026-03-08: the same UTC hour is EST
    the day before and EDT the day after.
    """
    before = datetime(2026, 3, 7, 14, tzinfo=UTC)
    after = datetime(2026, 3, 8, 14, tzinfo=UTC)
    now = datetime(2026, 3, 1, 12, tzinfo=UTC)
    assert "9:00 a. m." in confirmation_text(before, "America/New_York", now, "")
    assert "10:00 a. m." in confirmation_text(after, "America/New_York", now, "")


@pytest.mark.asyncio
async def test_an_unrelated_event_does_nothing(db_conn, booking):
    _issue(db_conn)
    channel = FakeChannel()
    await booking(channel).handle("invitee_no_show.created", _created())
    assert channel.sent == []
