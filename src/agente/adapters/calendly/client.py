"""Small async Calendly adapter; transport is injectable for tests.

Two constraints of `event_type_available_times`, both confirmed against the
live API (2026-08-17):

* `start_time` must be **strictly** in the future — sending `now` is a 400.
  The caller keeps its injected clock; the adapter only pushes a start that
  is not future enough forward by `START_LEAD`.
* Each returned slot carries `start_time`, `status`, `invitees_remaining`
  and a slot-specific `scheduling_url` — **no `end_time`**. The duration
  comes from the event type and is fetched once per process.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from ...domain.errors import CalendlyError
from ...ports.calendar import CalendarSlot

# Calendly rejects a start that is not strictly future; clock skew between us
# and their servers makes "now + a few seconds" unreliable.
START_LEAD = timedelta(minutes=5)
DEFAULT_DURATION_MINUTES = 60


class CalendlyClient:
    def __init__(
        self,
        token: str,
        event_type_uri: str,
        *,
        base_url: str = "https://api.calendly.com",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._event_type_uri = event_type_uri
        self._duration: int | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def duration_minutes(self) -> int:
        """Length of the event type, cached for the life of the process."""
        if self._duration is None:
            try:
                response = await self._client.get(self._event_type_uri)
                response.raise_for_status()
                self._duration = int(response.json()["resource"]["duration"])
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise CalendlyError("event type lookup failed") from exc
        return self._duration

    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]:
        duration = timedelta(minutes=await self.duration_minutes())
        window_start = max(start, datetime.now(UTC) + START_LEAD)
        if end <= window_start:
            return []
        try:
            response = await self._client.get(
                "/event_type_available_times",
                params={
                    "event_type": self._event_type_uri,
                    "start_time": _stamp(window_start),
                    "end_time": _stamp(end),
                },
            )
            response.raise_for_status()
            return [
                _slot(item, duration)
                for item in response.json()["collection"]
                if item.get("status", "available") == "available"
            ]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise CalendlyError("availability failed") from exc

    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str:
        try:
            response = await self._client.post(
                "/scheduling_links",
                json={
                    "max_event_count": 1,
                    "owner": self._event_type_uri,
                    "owner_type": "EventType",
                },
            )
            response.raise_for_status()
            return str(response.json()["resource"]["booking_url"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise CalendlyError("invitee creation failed") from exc


def _slot(item: dict, duration: timedelta) -> CalendarSlot:
    start = datetime.fromisoformat(item["start_time"].replace("Z", "+00:00"))
    return CalendarSlot(
        item["start_time"],
        start,
        start + duration,
        booking_url=str(item.get("scheduling_url", "")),
    )


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).replace(microsecond=0).isoformat()
