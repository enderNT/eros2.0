from datetime import UTC, datetime

import pytest

from agente.adapters.store.summaries import SqliteSummariesRepository
from agente.domain.contacts import ContactKey
from agente.ports.model import ModelReply, ToolUse
from agente.services.agent import FALLBACK, Agent, AgentResponder, system_blocks
from agente.services.knowledge import Knowledge, Section

KEY = ContactKey("1087343774471931", "+525512345678")
NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)

    async def complete(self, *_args, **_kwargs):
        return next(self.replies)


@pytest.mark.asyncio
async def test_two_round_tool_conversation():
    async def tool(_input):
        return "resultado"

    agent = Agent(
        ScriptedModel(
            [
                ModelReply("", "tool_use", (ToolUse("1", "buscar", {}),)),
                ModelReply("Listo", "end_turn"),
            ]
        ),
        {"buscar": tool},
        max_iterations=2,
    )
    assert await agent.reply([], [], []) == "Listo"


@pytest.mark.asyncio
async def test_iteration_cap_returns_fallback():
    model = ScriptedModel([ModelReply("", "tool_use", ())])
    assert await Agent(model, {}, max_iterations=1).reply([], [], []) == FALLBACK


def test_system_blocks_start_with_playbook_and_wiki_toc():
    blocks = system_blocks(Knowledge("instrucciones", [Section("Servicios", "x")]), None, None)
    assert "instrucciones" in blocks[0]["text"]
    assert "Servicios" in blocks[0]["text"]
    assert len(blocks) == 2


class Recorder:
    """Captures the messages the agent was asked to answer."""

    def __init__(self):
        self.messages = None

    async def complete(self, _system, messages, _tools, *, turn_id=None):
        self.messages = [dict(item) for item in messages]
        return ModelReply("ok", "end_turn")


class FakeContacts:
    def get_profile(self, _key):
        return None


def _responder(model, messages=None, summaries=None):
    return AgentResponder(
        Agent(model, {}, max_iterations=2),
        Knowledge("guia", [Section("Servicios", "x")]),
        FakeContacts(),
        lambda _key: ([], {}),
        messages=messages,
        summaries=summaries,
    )


@pytest.mark.asyncio
async def test_history_comes_from_the_stored_window(db_conn, messages):
    messages.add_inbound(KEY, "in-1", "hola", NOW)
    messages.add_outbound(KEY, "out-1", "¿en qué te ayudo?", NOW)
    messages.add_inbound(KEY, "in-2", "cuanto cuesta", NOW)
    model = Recorder()
    await _responder(model, messages)(KEY, "cuanto cuesta")
    assert [item["role"] for item in model.messages] == ["user", "assistant", "user"]
    assert model.messages[-1]["content"] == "cuanto cuesta"


@pytest.mark.asyncio
async def test_history_skips_what_the_summary_already_covers(db_conn, messages):
    messages.add_inbound(KEY, "in-1", "viejo", NOW)
    messages.add_outbound(KEY, "out-1", "respuesta vieja", NOW)
    summaries = SqliteSummariesRepository(db_conn)
    summaries.save(KEY, "Ana pregunta por precios.", 2, NOW)
    messages.add_inbound(KEY, "in-2", "nuevo", NOW)
    model = Recorder()
    await _responder(model, messages, summaries)(KEY, "nuevo")
    assert [item["content"] for item in model.messages] == ["nuevo"]


@pytest.mark.asyncio
async def test_consecutive_patient_messages_merge_into_one_turn(db_conn, messages):
    messages.add_inbound(KEY, "in-1", "hola", NOW)
    messages.add_inbound(KEY, "in-2", "quiero agendar", NOW)
    model = Recorder()
    await _responder(model, messages)(KEY, "hola\nquiero agendar")
    assert model.messages == [{"role": "user", "content": "hola\nquiero agendar"}]
