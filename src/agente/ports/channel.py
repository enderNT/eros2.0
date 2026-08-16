"""Channel port: the messaging interface services depend on (SPEC §2.3, §3).

The Kapso adapter satisfies this Protocol; services never import httpx
or know about Kapso's API shape. `ConversationRow` carries the real
contact phone (needed for mute keying) — it is masked at the logging
and display layers, never inside the row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ConversationRow:
    conversation_id: str
    contact_name: str | None
    contact_phone: str | None
    last_message_text: str | None
    last_activity_at: datetime | None
    status: str | None


@dataclass(frozen=True, slots=True)
class ConversationList:
    conversations: list[ConversationRow]
    next_cursor: str | None


class Channel(Protocol):
    async def send_text(self, phone_number_id: str, to: str, body: str) -> str:
        """Send a text message; return the Kapso message id."""
        ...

    async def list_conversations(
        self, phone_number_id: str, *, cursor: str | None = None, limit: int = 20
    ) -> ConversationList:
        """List conversations with cursor pagination."""
        ...
