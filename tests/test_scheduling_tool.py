from datetime import UTC, datetime, timedelta

import pytest

from agente.ports.calendar import CalendarSlot
from agente.tools.ver_horarios import ver_horarios


class FakeCalendar:
    async def availability(self, _start, _end):
        now = datetime(2026, 8, 16, 12, tzinfo=UTC)
        return [CalendarSlot("a", now + timedelta(hours=2), now + timedelta(hours=3))]


@pytest.mark.asyncio
async def test_lists_local_bookable_slot():
    text = await ver_horarios(
        FakeCalendar(), datetime(2026, 8, 16, 12, tzinfo=UTC), "America/Mexico_City"
    )
    assert "—" in text
