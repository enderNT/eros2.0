from datetime import UTC, datetime

import pytest

from agente.adapters.kapso.payloads import KapsoMessage, KapsoMessageText, WebhookPayload
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.domain.contacts import ContactKey
from agente.domain.crisis import CrisisVerdict
from agente.domain.errors import KapsoError, StoreError
from agente.services.inbound import FALLBACK, InboundService


class FakeChannel:
    def __init__(self, failures: int = 0) -> None:
        self.failures, self.sent = failures, []

    async def send_text(self, _phone_id: str, to: str, body: str) -> str:
        self.sent.append((to, body))
        if self.failures:
            self.failures -= 1
            raise KapsoError("failed")
        return f"out-{len(self.sent)}"


def _payload(message_id: str, text: str = "hola") -> WebhookPayload:
    return WebhookPayload(
        message=KapsoMessage(
            id=message_id,
            timestamp="2026-08-16T12:00:00Z",
            type="text",
            **{"from": "+12052943796"},
            text=KapsoMessageText(body=text),
        ),
        conversation={"id": "c1"},
        phone_number_id="1087343774471931",
    )


@pytest.mark.asyncio
async def test_duplicate_produces_one_reply(db_conn):
    channel = FakeChannel()
    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        debounce_seconds=0,
    )
    await service.handle(_payload("in-1"))
    await service.handle(_payload("in-1"))
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_muted_inbound_is_stored_without_send(db_conn):
    messages, mutes = SqliteMessagesRepository(db_conn), SqliteMutesRepository(db_conn)
    key = ContactKey("1087343774471931", "+12052943796")
    now = datetime(2026, 8, 16, tzinfo=UTC)
    mutes.set_mute(key, now, actor="test", reason="test")
    channel = FakeChannel()
    await InboundService(messages, mutes, channel, debounce_seconds=0).handle(_payload("in-2"))
    assert channel.sent == []
    assert len(messages.window(key, 10)) == 1


@pytest.mark.asyncio
async def test_send_failure_uses_single_fallback_without_retry(db_conn):
    channel = FakeChannel(failures=1)
    await InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        debounce_seconds=0,
    ).handle(_payload("in-3"))
    assert len(channel.sent) == 2
    assert channel.sent[-1][1] == FALLBACK


@pytest.mark.asyncio
async def test_three_message_burst_produces_one_reply(db_conn):
    import asyncio

    channel = FakeChannel()
    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        debounce_seconds=0.01,
    )
    await asyncio.gather(*(service.handle(_payload(f"burst-{index}")) for index in range(3)))
    assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_acute_crisis_mutes_and_skips_responder(db_conn):
    async def acute(_text):
        return CrisisVerdict.ACUTE

    channel = FakeChannel()
    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        crisis_classifier=acute,
        crisis_message="mensaje crisis",
        debounce_seconds=0,
    )
    await service.handle(_payload("acute"))
    assert channel.sent[-1][1] == "mensaje crisis"


@pytest.mark.asyncio
async def test_compaction_runs_after_the_reply_is_sent(db_conn):
    order = []
    channel = FakeChannel()

    async def compactor(_key):
        order.append(len(channel.sent))
        return True

    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        compactor=compactor,
        debounce_seconds=0,
    )
    await service.handle(_payload("m-compact"))
    assert order == [1]  # the reply was already out when compaction started


@pytest.mark.asyncio
async def test_compaction_failure_does_not_break_the_turn(db_conn):
    channel = FakeChannel()

    async def compactor(_key):
        raise StoreError("db down")

    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        channel,
        compactor=compactor,
        debounce_seconds=0,
    )
    await service.handle(_payload("m-compact-fail"))
    assert channel.sent
