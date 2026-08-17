"""Language-model port used by the agent service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class ToolUse:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ModelReply:
    text: str
    stop_reason: str
    tool_uses: tuple[ToolUse, ...] = ()


class Model(Protocol):
    async def complete(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        turn_id: str | None = None,
    ) -> ModelReply: ...
