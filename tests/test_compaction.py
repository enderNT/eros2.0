from datetime import UTC, datetime, timedelta

import pytest

from agente.adapters.store.summaries import SqliteSummariesRepository
from agente.domain.contacts import ContactKey
from agente.domain.errors import ModelError
from agente.ports.model import ModelReply
from agente.services.compaction import compact, make_summarizer

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
KEY = ContactKey("1087343774471931", "+525512345678")


class RecordingSummarizer:
    def __init__(self, text="Ana pregunta por la valoración."):
        self.text, self.prompts = text, []

    async def __call__(self, transcript):
        self.prompts.append(transcript)
        return self.text


def _conversation(messages, turns, *, size=200, prefix="a"):
    for index in range(turns):
        stamp = NOW + timedelta(minutes=index)
        messages.add_inbound(KEY, f"{prefix}-in-{index}", "x" * size, stamp)
        messages.add_outbound(KEY, f"{prefix}-out-{index}", "y" * size, stamp)


@pytest.mark.asyncio
async def test_short_conversation_is_not_compacted(db_conn, messages):
    _conversation(messages, 1)
    summaries = SqliteSummariesRepository(db_conn)
    assert not await compact(KEY, messages, summaries, RecordingSummarizer(), NOW, budget=2000)
    assert summaries.get(KEY) is None


@pytest.mark.asyncio
async def test_long_conversation_is_summarized_and_watermarked(db_conn, messages):
    _conversation(messages, 8)
    summaries = SqliteSummariesRepository(db_conn)
    summarizer = RecordingSummarizer()
    assert await compact(KEY, messages, summaries, summarizer, NOW, budget=200)
    stored = summaries.get(KEY)
    assert stored.text == summarizer.text
    assert stored.watermark_message_id > 0
    assert "Paciente:" in summarizer.prompts[0]


@pytest.mark.asyncio
async def test_second_pass_only_sees_uncovered_messages(db_conn, messages):
    _conversation(messages, 8)
    summaries = SqliteSummariesRepository(db_conn)
    summarizer = RecordingSummarizer()
    await compact(KEY, messages, summaries, summarizer, NOW, budget=200)
    first_watermark = summaries.get(KEY).watermark_message_id
    _conversation(messages, 8, prefix="b")
    await compact(KEY, messages, summaries, summarizer, NOW, budget=200)
    assert summaries.get(KEY).watermark_message_id > first_watermark
    assert "Resumen previo:" in summarizer.prompts[-1]


@pytest.mark.asyncio
async def test_model_failure_leaves_the_summary_untouched(db_conn, messages):
    _conversation(messages, 8)
    summaries = SqliteSummariesRepository(db_conn)

    async def failing(_transcript):
        raise ModelError("down")

    assert not await compact(KEY, messages, summaries, failing, NOW, budget=200)
    assert summaries.get(KEY) is None


@pytest.mark.asyncio
async def test_summarizer_asks_the_model_without_tools():
    seen = {}

    class Model:
        async def complete(self, system, messages, tools, *, turn_id=None):
            seen.update(system=system, messages=messages, tools=tools)
            return ModelReply("  resumen  ", "end_turn")

    assert await make_summarizer(Model())("transcripción") == "resumen"
    assert seen["tools"] == []
    assert seen["messages"][0]["content"] == "transcripción"
