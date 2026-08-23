"""El seguimiento tras el silencio: quien preguntó y se enfrió antes de agendar.

Comparte el outbox con el recordatorio de cita y no comparte nada más. Buena
parte de lo que se fija aquí es exactamente esa separación: que cancelar uno deje
al otro en pie, que ninguno responda por el otro, y que el plazo salga de su
propio ajuste.
"""

from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import KapsoError
from agente.services.interest_followup import FOLLOWUP_TEXT, InterestFollowups

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")


class FakeChannel:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        if self.fail:
            raise KapsoError("down")
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


@pytest.fixture()
def make(db_conn):
    def _make(channel=None, minutes: int = 60):
        SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
        return (
            InterestFollowups(
                outbox=SqliteOutboxRepository(db_conn),
                appointments=SqliteAppointmentsRepository(db_conn),
                messages=SqliteMessagesRepository(db_conn),
                mutes=SqliteMutesRepository(db_conn),
                channel=channel or FakeChannel(),
                delay_minutes=lambda: minutes,
                now=lambda: NOW,
            ),
            SqliteOutboxRepository(db_conn),
        )

    return _make


def _pending(outbox):
    return outbox.pending_interest_followup(KEY)


# --- programar ----------------------------------------------------------------


def test_speaking_to_someone_without_an_appointment_arms_the_follow_up(make):
    service, outbox = make(minutes=30)
    service.schedule_from_outbound(KEY, "lo que sea que haya dicho el bot", NOW)
    row = _pending(outbox)
    assert row is not None
    assert row.kind == "interest_followup"
    assert row.due_at == NOW + timedelta(minutes=30)
    assert row.text == FOLLOWUP_TEXT


def test_someone_who_already_booked_gets_nothing(make, db_conn):
    """Asking "¿sigues por ahí?" of a patient with a confirmed appointment is noise."""
    service, outbox = make()  # crea el contacto; la cita necesita que exista
    SqliteAppointmentsRepository(db_conn).add(KEY, "event-1", SLOT, NOW)
    service.schedule_from_outbound(KEY, "texto", NOW)
    assert _pending(outbox) is None


def test_speaking_again_reschedules_instead_of_queueing_another(make):
    """One nudge per silence, counted from the last thing said."""
    service, outbox = make(minutes=30)
    service.schedule_from_outbound(KEY, "primera", NOW)
    service.schedule_from_outbound(KEY, "segunda", NOW + timedelta(minutes=5))

    rows = [row for row in outbox.due(NOW + timedelta(days=1), kind="interest_followup")]
    assert len(rows) == 1
    assert rows[0].due_at == NOW + timedelta(minutes=35)


def test_the_delay_is_read_at_scheduling_time(make):
    """The panel slider moves this, so it cannot be captured at construction."""
    minutes = [90]
    service, outbox = make()
    service._delay_minutes = lambda: minutes[0]
    minutes[0] = 3
    service.schedule_from_outbound(KEY, "texto", NOW)
    assert _pending(outbox).due_at == NOW + timedelta(minutes=3)


# --- cancelar, sin llevarse por delante lo que no es suyo ---------------------


def test_the_patient_writing_back_cancels_it(make):
    service, outbox = make()
    service.schedule_from_outbound(KEY, "texto", NOW)
    service.cancel_for_contact(KEY)
    assert _pending(outbox) is None


def test_cancelling_leaves_the_reminder_alone(make, db_conn):
    """Los dos tipos comparten tabla; cada uno cancela sólo lo suyo.

    Es la regresión de OUTBOX-1: cancelar sin acotar por tipo se llevaba el
    recordatorio, así que a quien escribía un solo mensaje después de agendar no
    se le recordaba nunca.
    """
    outbox = SqliteOutboxRepository(db_conn)
    outbox.schedule_appointment_reminder(KEY, "event-1", SLOT, "recordatorio", SLOT)
    service, _ = make()
    service.schedule_from_outbound(KEY, "texto", NOW)

    service.cancel_for_contact(KEY)

    assert _pending(outbox) is None
    assert outbox.pending_appointment_reminder(KEY) is not None


# --- enviar -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_due_follow_up_is_sent_once_and_consumed(make):
    channel = FakeChannel()
    service, outbox = make(channel=channel, minutes=1)
    service.schedule_from_outbound(KEY, "texto", NOW)

    later = NOW + timedelta(minutes=5)
    await service.send_due(later)
    await service.send_due(later)

    assert channel.sent == [(KEY.contact_phone, FOLLOWUP_TEXT)]
    assert _pending(outbox) is None


@pytest.mark.asyncio
async def test_a_muted_contact_is_not_written_to(make, db_conn):
    """Escalation and crisis both mute; neither wants a cheerful nudge after it."""
    channel = FakeChannel()
    service, _ = make(channel=channel, minutes=1)
    service.schedule_from_outbound(KEY, "texto", NOW)
    SqliteMutesRepository(db_conn).set_mute(KEY, NOW, actor="test", reason="test")

    await service.send_due(NOW + timedelta(minutes=5))
    assert channel.sent == []


@pytest.mark.asyncio
async def test_booking_between_scheduling_and_sending_cancels_the_nudge(make, db_conn):
    """The check has to happen at delivery: that is when it can be wrong."""
    channel = FakeChannel()
    service, _ = make(channel=channel, minutes=1)
    service.schedule_from_outbound(KEY, "texto", NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, "event-1", SLOT, NOW)

    await service.send_due(NOW + timedelta(minutes=5))
    assert channel.sent == []


@pytest.mark.asyncio
async def test_a_send_failure_does_not_leave_the_row_to_fire_again(make):
    channel = FakeChannel(fail=True)
    service, outbox = make(channel=channel, minutes=1)
    service.schedule_from_outbound(KEY, "texto", NOW)
    await service.send_due(NOW + timedelta(minutes=5))
    assert _pending(outbox) is None


# --- el botón del panel -------------------------------------------------------


@pytest.mark.asyncio
async def test_the_panel_button_sends_the_pending_follow_up_now(make):
    channel = FakeChannel()
    service, outbox = make(channel=channel, minutes=90)
    service.schedule_from_outbound(KEY, "texto", NOW)

    assert await service.send_now(KEY) == "sent"
    assert channel.sent == [(KEY.contact_phone, FOLLOWUP_TEXT)]
    assert _pending(outbox) is None


@pytest.mark.asyncio
async def test_the_panel_button_reports_when_there_is_nothing_pending(make):
    channel = FakeChannel()
    service, _ = make(channel=channel)
    assert await service.send_now(KEY) == "missing"
    assert channel.sent == []


@pytest.mark.asyncio
async def test_the_panel_button_refuses_for_someone_who_already_booked(make, db_conn):
    channel = FakeChannel()
    service, _ = make(channel=channel)
    service.schedule_from_outbound(KEY, "texto", NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, "event-1", SLOT, NOW)

    assert await service.send_now(KEY) == "booked"
    assert channel.sent == []


# --- el cableado de app.py ----------------------------------------------------


def test_the_app_wires_both_follow_ups_onto_the_same_hooks(settings):
    """Los dos seguimientos cuelgan de `on_inbound`/`on_outbound` a la vez.

    Se comprueba aquí porque esa composición está escrita a mano en `app.py`, y
    el modo de fallo es silencioso: si el nuevo servicio se queda fuera del
    gancho, nada revienta — sencillamente no se programa nunca nada y el hueco de
    C01 vuelve sin que ningún test unitario se entere.
    """
    from fastapi.testclient import TestClient

    from agente.app import create_app

    with TestClient(create_app(settings)) as client:
        app = client.app
        assert app.state.interest_followups is not None
        key = ContactKey(settings.kapso_phone_number_id, "+525512345678")
        SqliteContactsRepository(app.state.db).ensure_contact(key, NOW)
        outbox = SqliteOutboxRepository(app.state.db)

        app.state.inbound._on_outbound(key, "una respuesta cualquiera", NOW)
        assert outbox.pending_interest_followup(key) is not None

        app.state.inbound._on_inbound(key)
        assert outbox.pending_interest_followup(key) is None
