"""Message persistence: dedupe by Kapso id, window reads, UTC storage (SPEC §4, §10)."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from agente.domain.contacts import ContactKey

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")
OTHER_KEY = ContactKey("1087343774471931", "+525587654321")


def test_add_inbound_stores_the_message(messages):
    stored = messages.add_inbound(KEY, "wamid-1", "hola", NOW)
    assert stored is True
    rows = messages.window(KEY, 10)
    assert len(rows) == 1
    row = rows[0]
    assert row.direction == "inbound"
    assert row.kapso_message_id == "wamid-1"
    assert row.text == "hola"
    assert row.created_at == NOW
    assert row.sent_by_us is False


def test_add_inbound_creates_the_contact_row(messages, contacts):
    assert contacts.get_contact(KEY) is None
    messages.add_inbound(KEY, "wamid-1", "hola", NOW)
    contact = contacts.get_contact(KEY)
    assert contact is not None
    assert contact.created_at == NOW


def test_duplicate_kapso_id_is_rejected(messages):
    assert messages.add_inbound(KEY, "wamid-1", "hola", NOW) is True
    assert messages.add_inbound(KEY, "wamid-1", "hola again", NOW) is False
    assert len(messages.window(KEY, 10)) == 1


def test_duplicate_kapso_id_is_rejected_across_contacts(messages):
    assert messages.add_inbound(KEY, "wamid-1", "hola", NOW) is True
    assert messages.add_inbound(OTHER_KEY, "wamid-1", "otro", NOW) is False
    assert messages.window(OTHER_KEY, 10) == []


def test_window_returns_the_last_messages_oldest_first(messages):
    for index in range(5):
        messages.add_inbound(KEY, f"wamid-{index}", f"msg {index}", NOW + timedelta(seconds=index))
    rows = messages.window(KEY, 3)
    assert [row.text for row in rows] == ["msg 2", "msg 3", "msg 4"]
    assert [row.id for row in rows] == sorted(row.id for row in rows)


def test_window_mixes_directions_and_honours_sent_by_us(messages):
    messages.add_inbound(KEY, "wamid-1", "hola", NOW)
    messages.add_outbound(KEY, "wamid-2", "hola, ¿en qué te ayudo?", NOW + timedelta(seconds=2))
    # An outbound typed by a human in the Kapso Inbox, not by the bot.
    messages.add_outbound(
        KEY, "wamid-3", "te atiendo personalmente", NOW + timedelta(seconds=3), sent_by_us=False
    )
    rows = messages.window(KEY, 10)
    assert [row.direction for row in rows] == ["inbound", "outbound", "outbound"]
    assert [row.sent_by_us for row in rows] == [False, True, False]


def test_timestamps_are_stored_as_utc(messages):
    mexico_city = ZoneInfo("America/Mexico_City")
    local_time = datetime(2026, 8, 16, 7, 0, tzinfo=mexico_city)
    messages.add_inbound(KEY, "wamid-1", "hola", local_time)
    row = messages.window(KEY, 1)[0]
    assert row.created_at == local_time.astimezone(UTC)
    assert row.created_at.utcoffset() == timedelta(0)


def test_window_of_an_unknown_contact_is_empty(messages):
    assert messages.window(KEY, 10) == []
