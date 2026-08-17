"""Small async Calendly adapter; transport is injectable for tests."""

from __future__ import annotations

from datetime import datetime

import httpx

from ...domain.errors import CalendlyError
from ...ports.calendar import CalendarSlot


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
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            transport=transport,
        )

    async def availability(self, start: datetime, end: datetime) -> list[CalendarSlot]:
        try:
            response = await self._client.get(
                "/event_type_available_times",
                params={
                    "event_type": self._event_type_uri,
                    "start_time": start.isoformat(),
                    "end_time": end.isoformat(),
                },
            )
            response.raise_for_status()
            return [
                CalendarSlot(
                    item["start_time"],
                    datetime.fromisoformat(item["start_time"]),
                    datetime.fromisoformat(item["end_time"]),
                )
                for item in response.json()["collection"]
            ]
        except (httpx.HTTPError, KeyError, ValueError) as exc:
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
