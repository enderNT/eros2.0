from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.booking_tokens import SqliteBookingTokensRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.services.followup import BookingFollowups

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


@pytest.fixture()
def followups(db_conn):
    channel = FakeChannel()
    service = BookingFollowups(
        outbox=SqliteOutboxRepository(db_conn),
        booking_tokens=SqliteBookingTokensRepository(db_conn),
        appointments=SqliteAppointmentsRepository(db_conn),
        messages=SqliteMessagesRepository(db_conn),
        mutes=SqliteMutesRepository(db_conn),
        channel=channel,
        timezone="America/Mexico_City",
        now=lambda: NOW,
    )
    return service, channel


def _issue(db_conn, token: str = "tok-1") -> str:
    SqliteBookingTokensRepository(db_conn).issue(token, KEY, SLOT, NOW)
    return f"https://calendly.com/clinic/slot?utm_content={token}"


@pytest.mark.asyncio
async def test_sends_one_followup_ninety_minutes_after_a_delivered_link(db_conn, followups):
    service, channel = followups
    service.schedule_from_outbound(KEY, f"Aquí está tu enlace: {_issue(db_conn)}.", NOW)

    await service.send_due(NOW + timedelta(minutes=89))
    assert channel.sent == []

    await service.send_due(NOW + timedelta(minutes=90))
    assert len(channel.sent) == 1
    assert "¿pudiste agendar tu cita" in channel.sent[0][1].lower()
    assert "11:00 a. m." in channel.sent[0][1]

    await service.send_due(NOW + timedelta(hours=3))
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_new_patient_message_cancels_the_followup(db_conn, followups):
    service, channel = followups
    service.schedule_from_outbound(KEY, _issue(db_conn), NOW)
    service.cancel_for_contact(KEY)

    await service.send_due(NOW + timedelta(hours=2))
    assert channel.sent == []


@pytest.mark.asyncio
async def test_confirmed_appointment_suppresses_the_followup(db_conn, followups):
    service, channel = followups
    service.schedule_from_outbound(KEY, _issue(db_conn), NOW)
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, "event-1", SLOT, NOW)

    await service.send_due(NOW + timedelta(hours=2))
    assert channel.sent == []
