"""Calendar boundary used by scheduling tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CalendarSlot:
    id: str
    start_utc: datetime
    end_utc: datetime


class Calendar(Protocol):
    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]: ...
    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str: ...
