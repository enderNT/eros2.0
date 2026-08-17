"""Calendar availability rendered as compact clinic-local slot labels."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain.scheduling import Slot, is_bookable, sample_slots, slot_label
from ..ports.calendar import Calendar


async def ver_horarios(calendar: Calendar, now: datetime, timezone: str, *, days: int = 14) -> str:
    slots = await calendar.availability(now, now + timedelta(days=days))
    candidates = [Slot(slot.start_utc, slot.end_utc) for slot in slots]
    selected = [
        slot
        for slot in sample_slots(candidates, ZoneInfo(timezone))
        if is_bookable(slot, now, timedelta(minutes=10))
    ]
    if not selected:
        return "No hay horarios disponibles por ahora."
    return "\n".join(
        f"{slot.start_utc.isoformat()} — {slot_label(slot, ZoneInfo(timezone), now)}"
        for slot in selected
    )
