"""Anthropic Messages adapter behind the model port."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic

from ...domain.errors import ModelError
from ...ports.model import ModelReply, ToolUse
from ...ports.store import LlmTraceRow


class AnthropicClient:
    def __init__(
        self, api_key: str, model: str, max_tokens: int, traces, *, client: Any | None = None
    ) -> None:
        self._model, self._max_tokens, self._traces = model, max_tokens, traces
        self._client = client or AsyncAnthropic(api_key=api_key)

    async def complete(self, system, messages, tools, *, turn_id=None) -> ModelReply:
        started = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            raise ModelError("Anthropic completion failed") from exc
        uses = tuple(
            ToolUse(block.id, block.name, dict(block.input))
            for block in response.content
            if block.type == "tool_use"
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        self._traces.add(
            LlmTraceRow(
                turn_id=turn_id,
                model=self._model,
                tokens_in=usage.input_tokens,
                tokens_out=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                latency_ms=int((time.monotonic() - started) * 1000),
                stop_reason=response.stop_reason,
                tools_called=tuple(use.name for use in uses),
                created_at=datetime.now(UTC),
            )
        )
        return ModelReply(text, response.stop_reason, uses)
