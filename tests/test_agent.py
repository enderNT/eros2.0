import pytest

from agente.ports.model import ModelReply, ToolUse
from agente.services.agent import FALLBACK, Agent, system_blocks
from agente.services.knowledge import Knowledge, Section


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
