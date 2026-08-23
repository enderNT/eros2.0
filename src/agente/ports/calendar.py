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
    # Slot-specific booking page, when the calendar offers one. Kept for the
    # link-based path that predates `book`; a calendar that books directly has
    # no use for it.
    booking_url: str = ""


@dataclass(frozen=True, slots=True)
class Booking:
    """An appointment the calendar has actually confirmed.

    `event_id` is the handle everything else hangs off: it is what `cancel`
    takes, and it is the same identifier the webhook reports as `event`, so a
    booking made here and one made from a link are indistinguishable downstream.
    """

    event_id: str
    invitee_id: str
    start_utc: datetime


class Calendar(Protocol):
    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]: ...

    async def book(
        self,
        slot: CalendarSlot,
        *,
        name: str,
        email: str,
        timezone: str,
        phone: str,
    ) -> Booking:
        """Reserve `slot` outright, raising `SlotTakenError` if someone else got it."""
        ...

    async def cancel(self, event_id: str, *, reason: str = "") -> None:
        """Release a booking. The slot becomes available again immediately."""
        ...

    # Mints a booking page instead of booking. Superseded by `book`; kept while
    # the link-based flow is still wired.
    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str: ...
