"""Bounded ReAct loop over the model port."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Any

from ..domain.contacts import ContactKey
from ..ports.model import Model
from ..ports.store import (
    ContactsRepository,
    MessageRow,
    MessagesRepository,
    Profile,
    SummariesRepository,
    SummaryRow,
)
from .knowledge import Knowledge

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


class AgentResponder:
    """Adapts a contact/text inbound turn to the model-facing agent.

    The verbatim window and the rolling summary come from the store, so the
    turn the model sees is the whole conversation minus what compaction
    already folded away (SPEC §9). Without `messages` it degrades to the
    single current turn.
    """

    def __init__(
        self,
        agent: Agent,
        knowledge: Knowledge,
        contacts: ContactsRepository,
        tools_for_contact,
        *,
        messages: MessagesRepository | None = None,
        summaries: SummariesRepository | None = None,
        window_limit: int = 40,
    ) -> None:
        self._agent, self._knowledge, self._contacts, self._tools_for_contact = (
            agent,
            knowledge,
            contacts,
            tools_for_contact,
        )
        self._messages, self._summaries, self._window_limit = messages, summaries, window_limit

    async def __call__(self, key: ContactKey, text: str, directives: str | None = None) -> str:
        definitions, handlers = self._tools_for_contact(key)
        summary = self._summaries.get(key) if self._summaries is not None else None
        previous_tools = self._agent._tools
        self._agent._tools = handlers
        try:
            return await self._agent.reply(
                system_blocks(
                    self._knowledge, self._contacts.get_profile(key), summary, directives
                ),
                self._history(key, summary, text),
                definitions,
            )
        finally:
            self._agent._tools = previous_tools

    def _history(
        self, key: ContactKey, summary: SummaryRow | None, text: str
    ) -> list[dict[str, Any]]:
        if self._messages is None:
            return [{"role": "user", "content": text}]
        rows = self._messages.window(key, self._window_limit)
        if summary is not None:
            rows = [row for row in rows if row.id > summary.watermark_message_id]
        turns = merge_turns(rows)
        # The inbound message is stored before the reply is built, so the last
        # user turn already carries it; only a missing or stale tail is added.
        if not turns or turns[-1]["role"] != "user":
            turns.append({"role": "user", "content": text})
        return turns


def merge_turns(rows: Iterable[MessageRow]) -> list[dict[str, Any]]:
    """Store rows to Anthropic messages: roles must alternate and start with the patient."""
    turns: list[dict[str, Any]] = []
    for row in rows:
        role = "user" if row.direction == "inbound" else "assistant"
        if not turns and role == "assistant":
            continue
        if turns and turns[-1]["role"] == role:
            turns[-1]["content"] = f"{turns[-1]['content']}\n{row.text}"
            continue
        turns.append({"role": role, "content": row.text})
    return turns


def system_blocks(
    knowledge: Knowledge,
    profile: Profile | None,
    summary: SummaryRow | None,
    directives: str | None = None,
) -> list[dict[str, Any]]:
    blocks = [
        {
            "type": "text",
            "text": f"{knowledge.playbook}\n\nWiki disponible:\n{knowledge.table_of_contents()}",
            "cache_control": {"type": "ephemeral"},
        },
        {"type": "text", "text": _profile_text(profile), "cache_control": {"type": "ephemeral"}},
    ]
    if summary is not None:
        blocks.append(
            {"type": "text", "text": summary.text, "cache_control": {"type": "ephemeral"}}
        )
    if directives:
        # Fourth block, only on a `possible` crisis turn (SPEC §7). No cache
        # breakpoint: it is present for this turn alone, and caching it would
        # invalidate the three stable blocks above on every other turn.
        blocks.append({"type": "text", "text": directives})
    return blocks


def _profile_text(profile: Profile | None) -> str:
    if profile is None:
        return "Perfil del contacto: todavía no hay datos estructurados."
    return (
        f"Perfil del contacto: nombre={profile.name or 'desconocido'}, "
        f"correo={profile.email or 'desconocido'}, estado={profile.handoff_state}."
    )
