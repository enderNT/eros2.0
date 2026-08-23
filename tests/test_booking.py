"""El webhook de Calendly: reservas que no hicimos nosotros."""

from datetime import UTC, datetime

import pytest

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import KapsoError
from agente.ports.store import Profile
from agente.services.booking import BookingService, confirmation_text
from agente.services.reminders import AppointmentReminders

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
    def _make(channel=None, address="", reminders=None, phone_number_id=KEY.phone_number_id):
        return BookingService(
            appointments=SqliteAppointmentsRepository(db_conn),
            contacts=contacts,
            messages=messages,
            outbox=SqliteOutboxRepository(db_conn),
            channel=channel or FakeChannel(),
            reminders=reminders,
            phone_number_id=phone_number_id,
            timezone="America/Mexico_City",
            address=address,
            now=lambda: NOW,
        )

    return _make


def _conocido(db_conn) -> None:
    """La precondición de una reserva atribuible: que ya tengamos perfil suyo.

    Sin token, el único asidero es el teléfono, y el listón es deliberadamente
    alto: tiene que ser alguien de quien ya sabemos algo. Quien reserve desde la
    página pública sin haber hablado nunca con nosotros se descarta en silencio,
    que es justo lo que protege de confirmarle una cita al paciente equivocado.
    """
    repo = SqliteContactsRepository(db_conn)
    repo.ensure_contact(KEY, NOW)
    repo.save_profile(
        Profile(
            key=KEY,
            name=None,
            email=None,
            kind="prospect",
            timezone=None,
            appointment_count=0,
            last_appointment_utc=None,
            next_appointment_utc=None,
            handoff_state="bot",
            updated_at=NOW,
        )
    )


def _created(token: str = "tok-1", event: str = EVENT) -> dict:
    return {
        "event": event,
        "name": "Ana",
        "email": "ana@example.com",
        "questions_and_answers": [{"question": "Número de teléfono", "answer": KEY.contact_phone}],
        "scheduled_event": {"start_time": "2026-08-18T17:00:00Z"},
    }


@pytest.mark.asyncio
async def test_created_writes_one_appointment_and_one_message(db_conn, booking, contacts):
    _conocido(db_conn)
    channel = FakeChannel()
    await booking(channel).handle("invitee.created", _created())
    rows = SqliteAppointmentsRepository(db_conn).for_contact(KEY)
    assert [(row.calendly_event_id, row.status) for row in rows] == [(EVENT, "scheduled")]
    assert len(channel.sent) == 1
    assert "11:00 a. m." in channel.sent[0][1]


@pytest.mark.asyncio
async def test_created_updates_the_durable_profile(db_conn, booking, contacts):
    _conocido(db_conn)
    await booking().handle("invitee.created", _created())
    profile = contacts.get_profile(KEY)
    assert profile.next_appointment_utc == SLOT
    assert profile.appointment_count == 1
    assert profile.kind == "patient"
    assert (profile.name, profile.email) == ("Ana", "ana@example.com")


@pytest.mark.asyncio
async def test_the_same_delivery_twice_is_a_no_op(db_conn, booking):
    _conocido(db_conn)
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
async def test_a_phone_answer_that_does_not_match_is_not_linked(db_conn, booking):
    _conocido(db_conn)
    channel = FakeChannel()
    payload = _created()
    payload["questions_and_answers"][0]["answer"] = "+52 55 0000 0000"
    await booking(channel).handle("invitee.created", payload)
    assert SqliteAppointmentsRepository(db_conn).for_contact(KEY) == []
    assert channel.sent == []


@pytest.mark.asyncio
async def test_canceled_flips_the_status_and_clears_the_profile(db_conn, booking, contacts):
    _conocido(db_conn)
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
    _conocido(db_conn)
    channel = FakeChannel()
    service = booking(channel)
    await service.handle("invitee.created", _created())
    await service.handle("invitee.canceled", {"event": EVENT})
    await service.handle("invitee.canceled", {"event": EVENT})
    assert len(channel.sent) == 2


@pytest.mark.asyncio
async def test_a_failed_notification_keeps_the_appointment(db_conn, booking):
    _conocido(db_conn)
    await booking(FakeChannel(fail=True)).handle("invitee.created", _created())
    assert SqliteAppointmentsRepository(db_conn).find(EVENT) is not None


@pytest.mark.asyncio
async def test_confirmed_booking_schedules_and_cancel_removes_its_reminder(db_conn, booking):
    _conocido(db_conn)
    channel = FakeChannel()
    reminders = AppointmentReminders(
        outbox=SqliteOutboxRepository(db_conn),
        appointments=SqliteAppointmentsRepository(db_conn),
        messages=SqliteMessagesRepository(db_conn),
        mutes=SqliteMutesRepository(db_conn),
        channel=channel,
        timezone="America/Mexico_City",
        minutes_before=lambda: 60,
        now=lambda: NOW,
    )
    service = booking(channel, reminders=reminders)
    await service.handle("invitee.created", _created())
    assert SqliteOutboxRepository(db_conn).pending_appointment_reminder(KEY) is not None
    await service.handle("invitee.canceled", {"event": EVENT})
    assert SqliteOutboxRepository(db_conn).pending_appointment_reminder(KEY) is None


def test_the_address_is_only_mentioned_when_configured():
    """OJO: hoy ningún camino de producción llama a `confirmation_text`.

    Lo que el webhook manda es `moved_text`, y lo nuestro se confirma desde
    `agendar_cita`. Esta prueba dejó de poder pasar por el webhook cuando el
    agendamiento por enlace desapareció, así que ejerce la función directamente
    y queda como constancia de que la dirección se sabe formatear — no de que
    alguien se la esté diciendo al paciente.
    """
    assert "Av. Reforma 100" in confirmation_text(
        SLOT, "America/Mexico_City", NOW, "Av. Reforma 100"
    )
    assert "dirección" not in confirmation_text(SLOT, "America/Mexico_City", NOW, "")


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
    _conocido(db_conn)
    channel = FakeChannel()
    await booking(channel).handle("invitee_no_show.created", _created())
    assert channel.sent == []


# --- reagendado hecho por la clínica, sin token nuestro -----------------------


def _rescheduled(phone: str) -> dict:
    """`invitee.created` como lo emite Calendly cuando reagenda el anfitrión."""
    return {
        "event": "https://api.calendly.com/scheduled_events/movido",
        "name": "Paciente",
        "email": "citas@clinica.test",
        "questions_and_answers": [{"question": "Numero de telefono", "answer": phone}],
        "scheduled_event": {"start_time": SLOT.isoformat().replace("+00:00", "Z")},
    }


@pytest.mark.asyncio
async def test_a_host_reschedule_is_attributed_by_the_phone_we_wrote(booking, contacts, db_conn):
    """We wrote that number into Calendly ourselves, so reading it back is not guessing."""
    _conocido(db_conn)
    channel = FakeChannel()
    service = booking(channel=channel, phone_number_id=KEY.phone_number_id)
    await service.handle("invitee.created", _created())  # la cita que luego se mueve
    await service.handle("invitee.canceled", {"event": EVENT})

    await service.handle("invitee.created", _rescheduled(KEY.contact_phone))

    vigentes = [
        row
        for row in SqliteAppointmentsRepository(db_conn).for_contact(KEY)
        if row.status == "scheduled"
    ]
    assert [row.slot_utc for row in vigentes] == [SLOT]
    assert any("mover tu cita" in body for _to, body in channel.sent)


@pytest.mark.asyncio
async def test_a_booking_from_an_unknown_number_is_still_discarded(booking, contacts, db_conn):
    """An unknown number booked from the public page: not ours to confirm.

    The bar is a contact with a profile — somebody we have actually booked for.
    Attributing anything else would confirm a stranger's appointment to a patient.
    """
    _conocido(db_conn)
    service = booking(phone_number_id=KEY.phone_number_id)
    await service.handle("invitee.created", _created())
    await service.handle("invitee.canceled", {"event": EVENT})

    await service.handle("invitee.created", _rescheduled("+525599990000"))

    vigentes = [
        row
        for row in SqliteAppointmentsRepository(db_conn).for_contact(KEY)
        if row.status == "scheduled"
    ]
    assert vigentes == []
