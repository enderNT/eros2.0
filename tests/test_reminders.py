from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.services.reminders import AppointmentReminders

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")
EVENT = "https://api.calendly.com/scheduled_events/abc"


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


@pytest.fixture()
def reminders(db_conn):
    channel = FakeChannel()
    service = AppointmentReminders(
        outbox=SqliteOutboxRepository(db_conn),
        appointments=SqliteAppointmentsRepository(db_conn),
        messages=SqliteMessagesRepository(db_conn),
        mutes=SqliteMutesRepository(db_conn),
        channel=channel,
        timezone="America/Mexico_City",
        minutes_before=lambda: 60,
        now=lambda: NOW,
    )
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    return service, channel


@pytest.mark.asyncio
async def test_sends_once_an_hour_before_a_confirmed_appointment(reminders):
    service, channel = reminders
    service.schedule(KEY, EVENT, SLOT, NOW)
    await service.send_due(SLOT - timedelta(minutes=61))
    assert channel.sent == []
    await service.send_due(SLOT - timedelta(minutes=60))
    assert len(channel.sent) == 1
    assert "te recordamos" in channel.sent[0][1].lower()


@pytest.mark.asyncio
async def test_manual_send_runs_only_the_pending_reminder_for_that_contact(reminders):
    service, channel = reminders
    service.schedule(KEY, EVENT, SLOT, NOW)
    assert await service.send_now(KEY) == "sent"
    assert len(channel.sent) == 1
    assert await service.send_now(KEY) == "missing"


@pytest.mark.asyncio
async def test_a_canceled_appointment_does_not_send_its_reminder(db_conn, reminders):
    service, channel = reminders
    service.schedule(KEY, EVENT, SLOT, NOW)
    SqliteAppointmentsRepository(db_conn).update_status(EVENT, "canceled", NOW)
    await service.send_due(SLOT)
    assert channel.sent == []


def test_recalculating_global_timing_moves_unsent_future_reminders(db_conn, reminders):
    service, _ = reminders
    service.schedule(KEY, EVENT, SLOT, NOW)
    service._minutes_before = lambda: 2  # test-only replacement of the runtime control
    service.reschedule_pending(NOW)
    rows = SqliteOutboxRepository(db_conn).due(
        SLOT - timedelta(minutes=2), kind="appointment_reminder"
    )
    assert len(rows) == 1
