"""Los dos avisos automáticos se pueden apagar, y apagados no hacen nada.

Un interruptor es fácil de implementar a medias: se deja de encolar pero lo ya
encolado sigue vivo, o se deja de mandar pero se sigue encolando y todo sale de
golpe al volver a encender. Lo que se fija aquí es la conducta completa —
apagado no encola, no manda, y vacía lo pendiente— y que cada interruptor sea
suyo: apagar los recordatorios no puede apagar el seguimiento, ni al revés.
"""

from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.adapters.store.settings import SqliteRuntimeSettingsRepository
from agente.domain.contacts import ContactKey
from agente.services.interest_followup import InterestFollowups
from agente.services.reminders import AppointmentReminders

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")
EVENT = "https://api.calendly.com/scheduled_events/ev-1"


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


class Switch:
    """Un interruptor movible, que es como lo ve el servicio: se relee cada vez."""

    def __init__(self, on: bool = True) -> None:
        self.on = on

    def __call__(self) -> bool:
        return self.on


@pytest.fixture()
def wired(db_conn):
    def _wired(interest_on: bool = True, reminder_on: bool = True):
        SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
        channel = FakeChannel()
        outbox = SqliteOutboxRepository(db_conn)
        interest_switch, reminder_switch = Switch(interest_on), Switch(reminder_on)
        common = {
            "outbox": outbox,
            "appointments": SqliteAppointmentsRepository(db_conn),
            "messages": SqliteMessagesRepository(db_conn),
            "mutes": SqliteMutesRepository(db_conn),
            "channel": channel,
        }
        interest = InterestFollowups(
            **common, delay_minutes=lambda: 1, enabled=interest_switch, now=lambda: NOW
        )
        reminders = AppointmentReminders(
            **common,
            timezone="America/Mexico_City",
            minutes_before=lambda: 30,
            enabled=reminder_switch,
            now=lambda: NOW,
        )
        return channel, outbox, interest, reminders, interest_switch, reminder_switch

    return _wired


def _kinds(outbox, kind):
    return [row for row in outbox.due(NOW + timedelta(days=2), kind=kind)]


# --- seguimiento de interés ---------------------------------------------------


def test_disabled_interest_follow_up_is_never_armed(wired):
    _, outbox, interest, _, _, _ = wired(interest_on=False)
    interest.schedule_from_outbound(KEY, "hola", NOW)
    assert outbox.pending_interest_followup(KEY) is None


async def test_disabling_after_arming_stops_the_send(wired):
    """El caso que importa: ya estaba programado cuando se apagó el interruptor."""
    channel, outbox, interest, _, switch, _ = wired()
    interest.schedule_from_outbound(KEY, "hola", NOW)
    assert outbox.pending_interest_followup(KEY) is not None

    switch.on = False
    await interest.send_due(NOW + timedelta(minutes=5))
    assert channel.sent == []


def test_dropping_pending_empties_the_queue(wired):
    _, outbox, interest, _, _, _ = wired()
    interest.schedule_from_outbound(KEY, "hola", NOW)
    interest.drop_pending()
    assert outbox.pending_interest_followup(KEY) is None


async def test_the_panel_button_refuses_while_disabled(wired):
    channel, _, interest, _, switch, _ = wired()
    interest.schedule_from_outbound(KEY, "hola", NOW)
    switch.on = False
    assert await interest.send_now(KEY) == "disabled"
    assert channel.sent == []


# --- recordatorio de cita -----------------------------------------------------


def test_disabled_reminder_is_never_armed(wired):
    _, outbox, _, reminders, _, _ = wired(reminder_on=False)
    reminders.schedule(KEY, EVENT, SLOT, NOW)
    assert outbox.pending_appointment_reminder(KEY) is None


async def test_disabling_after_booking_stops_the_reminder(wired, db_conn):
    channel, outbox, _, reminders, _, switch = wired()
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    reminders.schedule(KEY, EVENT, SLOT, NOW)
    assert outbox.pending_appointment_reminder(KEY) is not None

    switch.on = False
    reminders.drop_pending()
    await reminders.send_due(SLOT)
    assert channel.sent == []
    assert outbox.pending_appointment_reminder(KEY) is None


def test_re_enabling_rebuilds_reminders_for_future_appointments(wired, db_conn):
    """Vuelta atrás: la cita sobrevive al apagado, así que el recordatorio se rehace.

    Sin esto, quien agendó mientras estuvo apagado no recibiría nunca su
    recordatorio aunque la clínica volviera a encenderlo el mismo día.
    """
    _, outbox, _, reminders, _, switch = wired(reminder_on=False)
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    reminders.schedule(KEY, EVENT, SLOT, NOW)
    assert outbox.pending_appointment_reminder(KEY) is None

    switch.on = True
    reminders.reschedule_pending(NOW)
    row = outbox.pending_appointment_reminder(KEY)
    assert row is not None
    assert row.due_at == SLOT - timedelta(minutes=30)


async def test_the_reminder_button_refuses_while_disabled(wired, db_conn):
    channel, _, _, reminders, _, switch = wired()
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    reminders.schedule(KEY, EVENT, SLOT, NOW)
    switch.on = False
    assert await reminders.send_now(KEY) == "disabled"
    assert channel.sent == []


# --- que sean dos interruptores, no uno ---------------------------------------


async def test_each_switch_leaves_the_other_alone(wired, db_conn):
    """Apagar el seguimiento no puede llevarse por delante los recordatorios."""
    channel, outbox, interest, reminders, interest_switch, _ = wired()
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    reminders.schedule(KEY, EVENT, SLOT, NOW)
    interest.schedule_from_outbound(KEY, "hola", NOW)

    interest_switch.on = False
    interest.drop_pending()

    assert outbox.pending_interest_followup(KEY) is None
    assert outbox.pending_appointment_reminder(KEY) is not None
    await reminders.send_due(SLOT)
    assert len(channel.sent) == 1


def test_the_two_settings_are_stored_apart(db_conn):
    runtime = SqliteRuntimeSettingsRepository(db_conn)
    runtime.set_interest_followup_enabled(False, NOW)
    assert runtime.interest_followup_enabled(default=True) is False
    assert runtime.appointment_reminder_enabled(default=True) is True

    runtime.set_appointment_reminder_enabled(False, NOW)
    runtime.set_interest_followup_enabled(True, NOW)
    assert runtime.interest_followup_enabled(default=True) is True
    assert runtime.appointment_reminder_enabled(default=True) is False


def test_a_fresh_database_has_both_switched_on(db_conn):
    """Nadie hereda un aviso apagado por una migración."""
    runtime = SqliteRuntimeSettingsRepository(db_conn)
    runtime.set_interest_followup_minutes(5, NOW)  # crea la fila sin tocar los flags
    assert runtime.interest_followup_enabled(default=False) is True
    assert runtime.appointment_reminder_enabled(default=False) is True
