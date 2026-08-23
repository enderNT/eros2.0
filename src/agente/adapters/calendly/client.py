"""Small async Calendly adapter; transport is injectable for tests.

Reading availability (`event_type_available_times`), two constraints confirmed
against the live API (2026-08-17):

* `start_time` must be **strictly** in the future — sending `now` is a 400.
  The caller keeps its injected clock; the adapter only pushes a start that
  is not future enough forward by `START_LEAD`.
* Each returned slot carries `start_time`, `status`, `invitees_remaining`
  and a slot-specific `scheduling_url` — **no `end_time`**. The duration
  comes from the event type and is fetched once per process.

Writing (`POST /invitees`, the Scheduling API), confirmed end to end against
the live account on 2026-08-22:

* `location` and `questions_and_answers` go at the **root** of the body, not
  inside `invitee` and not inside `event`. Getting this wrong produces
  `invalid_location_choice` naming `event.location_configuration.kind` — a
  parameter the API does not accept. The message is a red herring: it appears
  for any malformed body, for every `kind`, and with no location block at all.
  Do not chase the location when you see it; check the shape first.
* `location.location` is required for `physical`, `outbound_call`, `ask_invitee`
  and `custom`, but it does not always come from the same place: for
  `outbound_call` it is the number Calendly will ring — the patient's — and the
  event type leaves it blank on purpose.
* Booking a taken slot is a 400 with code `already_filled`. Calendly still
  arbitrates availability, so two patients cannot take the same hour.
* Cancelling twice is a 403 `Event is already canceled`; an unknown event is a
  404. The first is treated as success, because a retried cancellation must
  not fail the second time.

There is no reschedule endpoint. Rescheduling is `cancel` then `book`; the slot
freed by the cancellation is offered again immediately.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from ...domain.errors import CalendlyError, SlotTakenError
from ...ports.calendar import Booking, CalendarSlot

# Calendly rejects a start that is not strictly future; clock skew between us
# and their servers makes "now + a few seconds" unreliable.
START_LEAD = timedelta(minutes=5)
DEFAULT_DURATION_MINUTES = 60

# Who supplies the location value depends on the kind, and getting this backwards
# is easy: `outbound_call` means Calendly rings the *patient*, so the number is
# the patient's and the event type leaves it blank. The rest name a place the
# clinic owns. Video conferencing kinds need no value at all.
PATIENT_SUPPLIES = frozenset({"outbound_call"})
EVENT_TYPE_SUPPLIES = frozenset({"physical", "inbound_call", "custom"})
# The invitee is asked at booking time, so there is nothing for us to send.
UNSUPPORTED_KINDS = frozenset({"ask_invitee"})


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
        self._resource: dict[str, Any] | None = None
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def event_type(self) -> dict[str, Any]:
        """The event type, cached for the life of the process.

        It is the source of truth for three things a booking needs: how long the
        appointment lasts, where it happens, and which questions Calendly
        insists on. Reading them from here rather than from configuration means
        a change made in Calendly's UI cannot silently disagree with us.
        """
        if self._resource is None:
            try:
                response = await self._client.get(self._event_type_uri)
                response.raise_for_status()
                self._resource = dict(response.json()["resource"])
            except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
                raise CalendlyError("event type lookup failed") from exc
        return self._resource

    async def duration_minutes(self) -> int:
        """Length of the event type, cached for the life of the process."""
        try:
            return int((await self.event_type())["duration"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CalendlyError("event type lookup failed") from exc

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

    async def book(
        self,
        slot: CalendarSlot,
        *,
        name: str,
        email: str,
        timezone: str,
        phone: str,
    ) -> Booking:
        """Reserve the slot outright. No link, no token, no waiting on a webhook."""
        resource = await self.event_type()
        payload: dict[str, Any] = {
            "event_type": self._event_type_uri,
            "start_time": _stamp(slot.start_utc),
            "location": _location(resource, phone),
            "invitee": {"name": name, "email": email, "timezone": timezone},
        }
        answers = _answers(resource, phone)
        if answers:
            payload["questions_and_answers"] = answers
        try:
            response = await self._client.post("/invitees", json=payload)
        except httpx.HTTPError as exc:
            raise CalendlyError("booking failed") from exc
        if response.status_code == 400 and _has_code(response, "already_filled"):
            raise SlotTakenError("slot already booked")
        try:
            response.raise_for_status()
            created = response.json()["resource"]
            return Booking(
                event_id=str(created["event"]),
                invitee_id=str(created["uri"]),
                start_utc=slot.start_utc,
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise CalendlyError("booking failed") from exc

    async def cancel(self, event_id: str, *, reason: str = "") -> None:
        """Release a booking, tolerating a cancellation that already happened.

        A retry must not fail: Calendly answers 403 `Event is already canceled`
        the second time, and for our purposes that is the desired end state.
        """
        url = event_id if event_id.startswith("http") else f"/scheduled_events/{event_id}"
        try:
            response = await self._client.post(
                f"{url.rstrip('/')}/cancellation", json={"reason": reason} if reason else {}
            )
        except httpx.HTTPError as exc:
            raise CalendlyError("cancellation failed") from exc
        if response.status_code == 403 and "already canceled" in response.text.lower():
            return
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CalendlyError("cancellation failed") from exc

    async def create_invitee(self, slot: CalendarSlot, name: str, email: str) -> str:
        """Mint a booking page. Superseded by `book`; kept while the link flow lives."""
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


def _location(resource: dict[str, Any], phone: str) -> dict[str, str]:
    """Where the appointment happens, in the shape booking wants.

    The kind is read from the event type rather than from settings on purpose:
    the two can drift, and the API compares against what the event type
    declares. The *value* is a different question — see `PATIENT_SUPPLIES`.
    """
    locations = resource.get("locations") or []
    if not locations:
        raise CalendlyError("event type declares no location")
    first = locations[0] if isinstance(locations[0], dict) else {}
    kind = str(first.get("kind") or "")
    value = str(first.get("location") or "")
    if not kind:
        raise CalendlyError("event type location has no kind")
    if kind in UNSUPPORTED_KINDS:
        raise CalendlyError(f"location kind {kind!r} is answered by the invitee, not by us")
    if kind in PATIENT_SUPPLIES:
        if not phone:
            raise CalendlyError(f"location kind {kind!r} needs the patient's phone number")
        return {"kind": kind, "location": phone}
    if kind in EVENT_TYPE_SUPPLIES:
        if not value:
            raise CalendlyError(f"location kind {kind!r} needs a value the event type omits")
        return {"kind": kind, "location": value}
    return {"kind": kind}


def _answers(resource: dict[str, Any], phone: str) -> list[dict[str, Any]]:
    """Fill the questions Calendly refuses a booking without.

    Only a phone question can be answered from what we know. Anything else
    marked required is a question for the patient, and inventing an answer to it
    would put a fabricated sentence in the clinic's calendar — so this refuses
    loudly instead, and the fix is to make that question optional in Calendly.
    """
    answers: list[dict[str, Any]] = []
    for index, question in enumerate(resource.get("custom_questions") or []):
        if not isinstance(question, dict) or not question.get("required"):
            continue
        name = str(question.get("name") or "")
        if question.get("type") != "phone_number":
            raise CalendlyError(f"required question {name!r} cannot be answered automatically")
        answers.append(
            {"position": int(question.get("position", index)), "question": name, "answer": phone}
        )
    return answers


def _has_code(response: httpx.Response, code: str) -> bool:
    try:
        details = response.json().get("details") or []
    except ValueError:
        return False
    return any(isinstance(item, dict) and item.get("code") == code for item in details)


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
