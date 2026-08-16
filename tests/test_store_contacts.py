"""Contact rows and durable profiles (SPEC §9, §10)."""

from datetime import UTC, datetime, timedelta

from agente.domain.contacts import ContactKey
from agente.ports.store import Profile

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")


def test_get_contact_of_an_unknown_key_is_none(contacts):
    assert contacts.get_contact(KEY) is None


def test_ensure_contact_creates_the_row(contacts):
    contacts.ensure_contact(KEY, NOW, display_name="María")
    row = contacts.get_contact(KEY)
    assert row is not None
    assert row.key == KEY
    assert row.display_name == "María"
    assert row.timezone is None
    assert row.created_at == NOW
    assert row.updated_at == NOW


def test_ensure_contact_keeps_known_fields_when_not_provided(contacts):
    contacts.ensure_contact(KEY, NOW, display_name="María", timezone="America/Mexico_City")
    contacts.ensure_contact(KEY, NOW + timedelta(minutes=5))
    row = contacts.get_contact(KEY)
    assert row.display_name == "María"
    assert row.timezone == "America/Mexico_City"
    assert row.created_at == NOW
    assert row.updated_at == NOW + timedelta(minutes=5)


def test_profile_round_trip(contacts):
    assert contacts.get_profile(KEY) is None
    contacts.ensure_contact(KEY, NOW)
    profile = Profile(
        key=KEY,
        name="María López",
        email=None,
        kind="prospect",
        timezone="America/Mexico_City",
        appointment_count=0,
        last_appointment_utc=None,
        next_appointment_utc=None,
        handoff_state="bot",
        updated_at=NOW,
    )
    contacts.save_profile(profile)
    assert contacts.get_profile(KEY) == profile


def test_save_profile_upserts_a_single_row(contacts):
    contacts.ensure_contact(KEY, NOW)
    first = Profile(
        key=KEY,
        name="María",
        email="maria@example.com",
        kind="prospect",
        timezone=None,
        appointment_count=0,
        last_appointment_utc=None,
        next_appointment_utc=None,
        handoff_state="bot",
        updated_at=NOW,
    )
    contacts.save_profile(first)
    slot = NOW + timedelta(days=2)
    second = Profile(
        key=KEY,
        name="María López",
        email="maria@example.com",
        kind="patient",
        timezone="America/Mexico_City",
        appointment_count=1,
        last_appointment_utc=None,
        next_appointment_utc=slot,
        handoff_state="bot",
        updated_at=NOW + timedelta(minutes=10),
    )
    contacts.save_profile(second)
    assert contacts.get_profile(KEY) == second
