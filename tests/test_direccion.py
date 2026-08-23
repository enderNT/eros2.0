"""La dirección de la sede llega a los dos mensajes donde hace falta.

Saber cuándo es la cita y no dónde es la mitad de un mensaje útil. La dirección
va en la confirmación —el mensaje que la persona guarda— y otra vez en el
recordatorio —el que tiene delante justo antes de salir de casa—, y se repite a
propósito: entre uno y otro pueden pasar días, y mandar a alguien a buscarla en
el historial es hacerle trabajo que nos toca a nosotros.

Lo que más importa fijar es lo contrario: sin dirección configurada no se
inventa ninguna. Quien lea una dirección se va a subir a un coche.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from agente.adapters.store.appointments import SqliteAppointmentsRepository
from agente.adapters.store.contacts import SqliteContactsRepository
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.adapters.store.outbox import SqliteOutboxRepository
from agente.domain.contacts import ContactKey
from agente.domain.scheduling import address_sentence
from agente.services.booking import BookingService, confirmation_text
from agente.services.reminders import AppointmentReminders, reminder_text
from agente.tools.agendar_cita import confirmed

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
SLOT = datetime(2026, 8, 18, 17, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")
EVENT = "https://api.calendly.com/scheduled_events/abc"
SEDE = "Sócrates 128, Polanco, Ciudad de México."
ZONA = ZoneInfo("America/Mexico_City")


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


# --- la frase suelta ----------------------------------------------------------


def test_no_address_means_no_sentence():
    assert address_sentence("") == ""
    assert address_sentence("   ") == ""


def test_the_address_sentence_never_doubles_a_period():
    """La escribe una persona, que puntúa como quiera."""
    assert address_sentence(SEDE).endswith("México.")
    assert ".." not in address_sentence(SEDE)
    assert address_sentence("Sócrates 128").endswith("128.")


# --- el recordatorio ----------------------------------------------------------


def test_the_reminder_says_where_as_well_as_when():
    texto = reminder_text(SLOT, ZONA, NOW, SEDE)
    assert "Sócrates 128" in texto
    assert "11:00 a. m." in texto
    assert "escríbeme por aquí" in texto


def test_a_reminder_without_a_configured_address_invents_nothing():
    texto = reminder_text(SLOT, ZONA, NOW, "")
    assert "dirección" not in texto
    assert "11:00 a. m." in texto


async def test_the_address_reaches_the_message_actually_sent(db_conn):
    """De punta a punta: no basta con que la sepa formatear, tiene que salir."""
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    channel = FakeChannel()
    service = AppointmentReminders(
        outbox=SqliteOutboxRepository(db_conn),
        appointments=SqliteAppointmentsRepository(db_conn),
        messages=SqliteMessagesRepository(db_conn),
        mutes=SqliteMutesRepository(db_conn),
        channel=channel,
        timezone="America/Mexico_City",
        minutes_before=lambda: 60,
        address=SEDE,
        now=lambda: NOW,
    )
    service.schedule(KEY, EVENT, SLOT, NOW)
    await service.send_due(SLOT)
    assert len(channel.sent) == 1
    assert "Sócrates 128" in channel.sent[0][1]


def test_moving_the_clinic_moves_the_reminder(db_conn):
    """Cambiar el ajuste reescribe los recordatorios que aún no han salido."""
    SqliteContactsRepository(db_conn).ensure_contact(KEY, NOW)
    SqliteAppointmentsRepository(db_conn).add(KEY, EVENT, SLOT, NOW)
    outbox = SqliteOutboxRepository(db_conn)
    comun = {
        "outbox": outbox,
        "appointments": SqliteAppointmentsRepository(db_conn),
        "messages": SqliteMessagesRepository(db_conn),
        "mutes": SqliteMutesRepository(db_conn),
        "channel": FakeChannel(),
        "timezone": "America/Mexico_City",
        "minutes_before": lambda: 60,
        "now": lambda: NOW,
    }
    AppointmentReminders(**comun, address=SEDE).schedule(KEY, EVENT, SLOT, NOW)
    assert "Sócrates 128" in outbox.pending_appointment_reminder(KEY).text

    AppointmentReminders(**comun, address="Otra calle 9").reschedule_pending(NOW)
    assert "Otra calle 9" in outbox.pending_appointment_reminder(KEY).text


# --- la confirmación al agendar -----------------------------------------------


def test_the_booking_result_quotes_the_address_verbatim():
    """Literal y no "búscala en la wiki": es el mensaje que la gente guarda."""
    for movida in (False, True):
        texto = confirmed("el jueves a las 4", movida, SEDE)
        assert f'"{SEDE}"' in texto
        assert "No la reformules" in texto


def test_the_booking_result_without_an_address_says_nothing_about_where():
    for movida in (False, True):
        texto = confirmed("el jueves a las 4", movida, "")
        assert "dirección" not in texto
        assert "el jueves a las 4" in texto


def test_the_rescheduled_result_still_carries_both_halves():
    """La dirección no puede desplazar lo que ya tenía que decir."""
    texto = confirmed("el jueves a las 4", True, SEDE)
    assert "cancelada" in texto
    assert "Sócrates 128" in texto


def test_the_tool_reads_the_address_from_the_booking_service(db_conn, contacts, messages):
    service = BookingService(
        appointments=SqliteAppointmentsRepository(db_conn),
        contacts=contacts,
        messages=messages,
        outbox=SqliteOutboxRepository(db_conn),
        channel=FakeChannel(),
        timezone="America/Mexico_City",
        address=SEDE,
    )
    assert service.address == SEDE


def test_the_webhook_confirmation_also_carries_it():
    """`confirmation_text` comparte la misma frase, no una copia suya."""
    assert address_sentence(SEDE) in confirmation_text(SLOT, "America/Mexico_City", NOW, SEDE)
