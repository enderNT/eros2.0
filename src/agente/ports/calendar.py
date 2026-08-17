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
    # Slot-specific booking page, when the calendar offers one. Calendly has no
    # API to book on the patient's behalf, so this link is how a slot actually
    # becomes an appointment.
    booking_url: str = ""


class Calendar(Protocol):
    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]: ...
    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str: ...
