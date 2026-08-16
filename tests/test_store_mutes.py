"""Three-level mute resolution, expiry and the audit trail (SPEC §10, PROJECT.md)."""

from datetime import UTC, datetime, timedelta

from agente.domain.contacts import ContactKey

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
NUMBER = "1087343774471931"
KEY = ContactKey(NUMBER, "+525512345678")
OTHER_KEY = ContactKey(NUMBER, "+525587654321")
OTHER_NUMBER_KEY = ContactKey("999", "+525512345678")
ACTOR = {"actor": "panel:maria", "reason": "human takeover"}


def test_nobody_is_muted_by_default(mutes):
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_contact_mute_and_clear(mutes):
    mutes.set_mute(KEY, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True
    assert mutes.is_bot_muted(OTHER_KEY, NOW) is False
    mutes.clear_mute(KEY, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_number_mute_covers_every_contact_of_that_number(mutes):
    mutes.set_number_mute(NUMBER, True, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True
    assert mutes.is_bot_muted(OTHER_KEY, NOW) is True
    assert mutes.is_bot_muted(OTHER_NUMBER_KEY, NOW) is False
    mutes.set_number_mute(NUMBER, False, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_global_mute_covers_every_number(mutes):
    mutes.set_global(True, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True
    assert mutes.is_bot_muted(OTHER_NUMBER_KEY, NOW) is True
    mutes.set_global(False, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_levels_resolve_global_then_number_then_contact(mutes):
    mutes.set_mute(KEY, NOW, **ACTOR)
    mutes.set_number_mute(NUMBER, True, NOW, **ACTOR)
    mutes.set_global(True, NOW, **ACTOR)
    # Clearing the contact level changes nothing while higher levels hold.
    mutes.clear_mute(KEY, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True
    mutes.set_number_mute(NUMBER, False, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True  # global still holds
    mutes.set_global(False, NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_mute_with_expiry_in_the_future_is_active(mutes):
    mutes.set_mute(KEY, NOW, until=NOW + timedelta(hours=1), **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True


def test_expired_mute_is_inactive(mutes):
    mutes.set_mute(KEY, NOW, until=NOW - timedelta(seconds=1), **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False


def test_mute_expires_at_exactly_muted_until(mutes):
    mutes.set_mute(KEY, NOW, until=NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False
    assert mutes.is_bot_muted(KEY, NOW - timedelta(seconds=1)) is True


def test_expiry_applies_to_number_and_global_levels(mutes):
    mutes.set_number_mute(NUMBER, True, NOW, until=NOW, **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is False
    mutes.set_global(True, NOW, until=NOW + timedelta(hours=1), **ACTOR)
    assert mutes.is_bot_muted(KEY, NOW) is True
    assert mutes.is_bot_muted(KEY, NOW + timedelta(hours=2)) is False


def test_getters_report_the_raw_state_even_when_expired(mutes):
    assert mutes.contact_mute(KEY) is None
    assert mutes.number_mute(NUMBER) is None
    assert mutes.global_mute() is None
    until = NOW + timedelta(hours=2)
    mutes.set_mute(KEY, NOW, until=until, **ACTOR)
    state = mutes.contact_mute(KEY)
    assert state is not None
    assert state.muted_at == NOW
    assert state.muted_until == until


def test_every_mutation_writes_exactly_one_audit_row(mutes):
    mutes.set_mute(KEY, NOW, **ACTOR)
    mutes.clear_mute(KEY, NOW + timedelta(seconds=1), **ACTOR)
    mutes.set_number_mute(NUMBER, True, NOW + timedelta(seconds=2), **ACTOR)
    mutes.set_number_mute(NUMBER, False, NOW + timedelta(seconds=3), **ACTOR)
    mutes.set_global(True, NOW + timedelta(seconds=4), **ACTOR)
    mutes.set_global(False, NOW + timedelta(seconds=5), **ACTOR)
    trail = mutes.audit_trail()
    assert len(trail) == 6
    # Newest first.
    assert [entry.action for entry in trail] == [
        "global_unmuted",
        "global_muted",
        "number_unmuted",
        "number_muted",
        "contact_unmuted",
        "contact_muted",
    ]
    first = trail[-1]
    assert first.actor == "panel:maria"
    assert first.reason == "human takeover"
    assert first.phone_number_id == NUMBER
    assert first.contact_phone == KEY.contact_phone
    assert first.created_at == NOW
    assert first.urgent is False


def test_remuting_updates_state_without_duplicating_it(mutes):
    mutes.set_mute(KEY, NOW, **ACTOR)
    later = NOW + timedelta(seconds=1)
    mutes.set_mute(KEY, later, reason="still needs a human", actor="panel:maria")
    assert len(mutes.audit_trail()) == 2
    state = mutes.contact_mute(KEY)
    assert state is not None
    assert state.muted_at == NOW + timedelta(seconds=1)
