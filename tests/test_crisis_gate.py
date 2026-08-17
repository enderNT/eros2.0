"""The crisis pre-gate: verdicts, fail-closed behaviour and the branches (SPEC §7)."""

import asyncio
from datetime import UTC, datetime

import pytest

from agente.adapters.kapso.payloads import KapsoMessage, KapsoMessageText, WebhookPayload
from agente.adapters.store.messages import SqliteMessagesRepository
from agente.adapters.store.mutes import SqliteMutesRepository
from agente.domain.contacts import ContactKey
from agente.domain.crisis import CrisisVerdict
from agente.domain.errors import ModelError
from agente.ports.model import ModelReply, ToolUse
from agente.services.agent import system_blocks
from agente.services.crisis import TOOL_NAME, check, make_classifier
from agente.services.inbound import InboundService
from agente.services.knowledge import Knowledge

KEY = ContactKey("1087343774471931", "+12052943796")
CRISIS_TEXT = "Si estás en riesgo inmediato llama al 911 o acude a urgencias."


class FakeModel:
    """Answers with one tool call, the way the schema forces the real one to."""

    def __init__(self, verdict=None, *, raises=None, hangs=False, text_only=False) -> None:
        self.verdict, self.raises, self.hangs, self.text_only = verdict, raises, hangs, text_only
        self.calls = []

    async def complete(self, system, messages, tools, *, turn_id=None):
        self.calls.append((system, messages, tools))
        if self.hangs:
            await asyncio.sleep(10)
        if self.raises is not None:
            raise self.raises
        if self.text_only:
            return ModelReply("no puedo", "end_turn")
        return ModelReply(
            "",
            "tool_use",
            (ToolUse("u1", TOOL_NAME, {"verdicto": self.verdict}),),
        )


class FakeChannel:
    def __init__(self) -> None:
        self.sent = []

    async def send_text(self, _phone_id, to, body) -> str:
        self.sent.append((to, body))
        return f"out-{len(self.sent)}"


def _payload(message_id: str, text: str = "ya no quiero seguir aquí") -> WebhookPayload:
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
@pytest.mark.parametrize("value", ["none", "possible", "acute"])
async def test_each_verdict_is_parsed_from_the_tool_schema(value):
    assert await make_classifier(FakeModel(value))("hola") is CrisisVerdict(value)


@pytest.mark.asyncio
async def test_an_unknown_verdict_string_becomes_possible():
    assert await make_classifier(FakeModel("catastrophic"))("hola") is CrisisVerdict.POSSIBLE


@pytest.mark.asyncio
async def test_an_answer_without_the_tool_call_becomes_possible():
    classifier = make_classifier(FakeModel(text_only=True))
    assert await classifier("hola") is CrisisVerdict.POSSIBLE


@pytest.mark.asyncio
async def test_a_model_failure_becomes_possible_not_none():
    classifier = make_classifier(FakeModel(raises=ModelError("down")))
    assert await check(classifier, "hola") is CrisisVerdict.POSSIBLE


@pytest.mark.asyncio
async def test_a_timeout_becomes_possible_not_none():
    classifier = make_classifier(FakeModel("none", hangs=True))
    assert await check(classifier, "hola", timeout=0.01) is CrisisVerdict.POSSIBLE


@pytest.mark.asyncio
async def test_acute_sends_the_clinic_text_verbatim_and_runs_no_agent(db_conn):
    async def responder(*_args):  # pragma: no cover - must never run
        raise AssertionError("the agent ran on an acute turn")

    channel = FakeChannel()
    mutes = SqliteMutesRepository(db_conn)
    service = InboundService(
        SqliteMessagesRepository(db_conn),
        mutes,
        channel,
        responder=responder,
        crisis_classifier=make_classifier(FakeModel("acute")),
        crisis_message=CRISIS_TEXT,
        debounce_seconds=0,
    )
    await service.handle(_payload("acute-1"))
    assert channel.sent == [(KEY.contact_phone, CRISIS_TEXT)]
    assert mutes.is_bot_muted(KEY, datetime(2026, 8, 16, 12, tzinfo=UTC))


@pytest.mark.asyncio
async def test_acute_writes_an_urgent_audit_entry(db_conn):
    mutes = SqliteMutesRepository(db_conn)
    service = InboundService(
        SqliteMessagesRepository(db_conn),
        mutes,
        FakeChannel(),
        crisis_classifier=make_classifier(FakeModel("acute")),
        crisis_message=CRISIS_TEXT,
        debounce_seconds=0,
    )
    await service.handle(_payload("acute-2"))
    entry = mutes.audit_trail()[0]
    assert (entry.actor, entry.urgent) == ("crisis", True)


@pytest.mark.asyncio
async def test_possible_hands_the_playbook_directives_to_the_agent(db_conn):
    seen = []

    async def responder(_key, _text, directives, _turn_id):
        seen.append(directives)
        return "te escucho"

    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        FakeChannel(),
        responder=responder,
        crisis_classifier=make_classifier(FakeModel("possible")),
        crisis_message=CRISIS_TEXT,
        crisis_directives="# Crisis y riesgo\nEscala de inmediato.",
        debounce_seconds=0,
    )
    await service.handle(_payload("possible-1"))
    assert seen == ["# Crisis y riesgo\nEscala de inmediato."]


@pytest.mark.asyncio
async def test_none_proceeds_without_directives(db_conn):
    seen = []

    async def responder(_key, _text, directives, _turn_id):
        seen.append(directives)
        return "claro"

    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        FakeChannel(),
        responder=responder,
        crisis_classifier=make_classifier(FakeModel("none")),
        crisis_message=CRISIS_TEXT,
        crisis_directives="# Crisis y riesgo\nEscala de inmediato.",
        debounce_seconds=0,
    )
    await service.handle(_payload("none-1", text="¿cuánto cuesta la consulta?"))
    assert seen == [None]


@pytest.mark.asyncio
async def test_the_crisis_call_and_the_agent_share_one_turn_id(db_conn):
    """Correlation is the point: both model calls of a turn must be joinable."""
    seen = {}

    async def classifier(_text, turn_id):
        seen["crisis"] = turn_id
        return CrisisVerdict.NONE

    async def responder(_key, _text, _directives, turn_id):
        seen["agent"] = turn_id
        return "hola"

    service = InboundService(
        SqliteMessagesRepository(db_conn),
        SqliteMutesRepository(db_conn),
        FakeChannel(),
        responder=responder,
        crisis_classifier=classifier,
        crisis_message=CRISIS_TEXT,
        debounce_seconds=0,
    )
    await service.handle(_payload("turn-1"))
    assert seen["crisis"] and seen["crisis"] == seen["agent"]


def test_directives_become_a_fourth_system_block_without_a_cache_breakpoint():
    blocks = system_blocks(Knowledge("guia", []), None, None, "directivas de crisis")
    assert len(blocks) == 3
    assert blocks[-1] == {"type": "text", "text": "directivas de crisis"}


def test_the_playbook_crisis_section_is_what_gets_injected():
    knowledge = Knowledge("# Tono\nbreve\n\n# Crisis y riesgo\nEscala de inmediato.", [])
    assert knowledge.crisis_directives() == "Crisis y riesgo\nEscala de inmediato."


def test_a_playbook_without_a_crisis_section_injects_nothing():
    assert Knowledge("# Tono\nbreve", []).crisis_directives() == ""
