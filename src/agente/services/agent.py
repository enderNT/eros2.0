"""Bounded ReAct loop over the model port."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..ports.model import Model

log = logging.getLogger(__name__)
FALLBACK = "Estoy teniendo un problema técnico. ¿Quieres que te conecte con una persona?"
ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]


class Agent:
    def __init__(self, model: Model, tools: dict[str, ToolHandler], *, max_iterations: int) -> None:
        self._model, self._tools, self._max_iterations = model, tools, max_iterations

    async def reply(
        self,
        system: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        definitions: list[dict[str, Any]],
        *,
        turn_id: str | None = None,
    ) -> str:
        for _ in range(self._max_iterations):
            response = await self._model.complete(system, messages, definitions, turn_id=turn_id)
            if response.stop_reason != "tool_use":
                return response.text.strip() or FALLBACK
            messages.append(
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": use.id, "name": use.name, "input": use.input}
                        for use in response.tool_uses
                    ],
                }
            )
            results = []
            for use in response.tool_uses:
                handler = self._tools.get(use.name)
                try:
                    content = await handler(use.input) if handler else "Herramienta no disponible."
                except (ValueError, RuntimeError) as exc:
                    content = f"La herramienta no pudo completarse: {type(exc).__name__}."
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content})
            messages.append({"role": "user", "content": results})
        log.error("agent_iteration_cap", extra={"turn_id": turn_id})
        return FALLBACK
