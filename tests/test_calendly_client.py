"""Calendly write path — MockTransport, no network (SPEC §3, §11).

The shapes asserted here are not guesses: every one was confirmed against the
live account on 2026-08-22, including the misleading `invalid_location_choice`
error that made the body look like a location problem when it was a nesting
problem. These tests exist so that discovery does not have to be repeated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest

from agente.adapters.calendly.client import CalendlyClient
from agente.domain.errors import CalendlyError, SlotTakenError
from agente.ports.calendar import CalendarSlot

EVENT_TYPE = "https://api.calendly.com/event_types/0b092d16"
SCHEDULED = "https://api.calendly.com/scheduled_events/8d01516b"
SLOT_START = datetime(2026, 8, 23, 15, 0, tzinfo=UTC)

PHYSICAL = {
    "duration": 15,
    "locations": [{"kind": "physical", "location": "Sócrates 128, Polanco."}],
    "custom_questions": [{"name": "Numero de teléfono", "type": "phone_number", "required": True}],
}
# Una llamada saliente: Calendly marca al paciente, así que el event type deja
# el número en blanco a propósito y lo pone la reserva.
CALL = {
    "duration": 30,
    "locations": [{"kind": "outbound_call"}],
    "custom_questions": [],
}


def _slot() -> CalendarSlot:
    return CalendarSlot("id", SLOT_START, SLOT_START + timedelta(minutes=15))


def _client(handler, resource: dict[str, Any] = PHYSICAL) -> CalendlyClient:
    """A client whose event-type lookup is already answered, so tests assert on the POST."""

    def route(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"resource": resource}, request=request)
        return handler(request)

    return CalendlyClient("token", EVENT_TYPE, transport=httpx.MockTransport(route))


async def _book(client: CalendlyClient):
    return await client.book(
        _slot(),
        name="Ana",
        email="ana@example.com",
        timezone="America/Mexico_City",
        phone="+525599998888",
    )


# --- book ---------------------------------------------------------------------


async def test_book_puts_location_and_answers_at_the_root() -> None:
    """The nesting that cost an hour: both live beside `invitee`, not inside it."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(
            201,
            json={"resource": {"event": SCHEDULED, "uri": f"{SCHEDULED}/invitees/4dfa"}},
            request=request,
        )

    await _book(_client(handler))
    assert seen["location"] == {"kind": "physical", "location": "Sócrates 128, Polanco."}
    assert seen["questions_and_answers"] == [
        {"position": 0, "question": "Numero de teléfono", "answer": "+525599998888"}
    ]
    assert seen["invitee"] == {
        "name": "Ana",
        "email": "ana@example.com",
        "timezone": "America/Mexico_City",
    }
    assert "location" not in seen["invitee"] and "event" not in seen


async def test_book_returns_the_scheduled_event_as_the_handle() -> None:
    """`event_id` must be the scheduled event, the same id the webhook reports."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"resource": {"event": SCHEDULED, "uri": f"{SCHEDULED}/invitees/4dfa"}},
            request=request,
        )

    booking = await _book(_client(handler))
    assert booking.event_id == SCHEDULED
    assert booking.invitee_id == f"{SCHEDULED}/invitees/4dfa"
    assert booking.start_utc == SLOT_START


async def test_book_omits_answers_when_no_question_is_required() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(
            201, json={"resource": {"event": SCHEDULED, "uri": "u"}}, request=request
        )

    await _book(_client(handler, CALL))
    assert "questions_and_answers" not in seen
    assert seen["location"] == {"kind": "outbound_call", "location": "+525599998888"}


async def test_book_raises_slot_taken_on_already_filled() -> None:
    """The one calendar failure with a useful answer: offer another time."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "title": "Invalid Argument",
                "details": [{"parameter": "event.start_time", "code": "already_filled"}],
            },
            request=request,
        )

    with pytest.raises(SlotTakenError):
        await _book(_client(handler))


async def test_book_raises_plain_calendly_error_on_other_400() -> None:
    """A 400 that is not `already_filled` is not a slot problem and must not read as one."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"details": [{"code": "invalid_location_choice"}]},
            request=request,
        )

    with pytest.raises(CalendlyError) as caught:
        await _book(_client(handler))
    assert not isinstance(caught.value, SlotTakenError)


async def test_book_refuses_to_invent_a_required_question() -> None:
    """Only a phone question can be answered from what we know; the rest is the patient's."""
    resource = {
        "duration": 15,
        "locations": [{"kind": "physical", "location": "Sócrates 128."}],
        "custom_questions": [{"name": "¿Motivo de consulta?", "type": "text", "required": True}],
    }

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        raise AssertionError("must not POST when an answer would have to be invented")

    with pytest.raises(CalendlyError, match="Motivo de consulta"):
        await _book(_client(handler, resource))


async def test_book_ignores_optional_questions() -> None:
    resource = dict(CALL) | {
        "custom_questions": [{"name": "Algo que ayude", "type": "text", "required": False}]
    }
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(
            201, json={"resource": {"event": SCHEDULED, "uri": "u"}}, request=request
        )

    await _book(_client(handler, resource))
    assert "questions_and_answers" not in seen


async def test_book_fails_when_the_event_type_declares_no_location() -> None:
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        raise AssertionError("must not POST without a location")

    with pytest.raises(CalendlyError, match="no location"):
        await _book(_client(handler, {"duration": 15, "locations": []}))


async def test_book_translates_transport_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out")

    with pytest.raises(CalendlyError):
        await _book(_client(handler))


# --- cancel -------------------------------------------------------------------


async def test_cancel_posts_the_reason_to_the_cancellation_path() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(201, json={"resource": {}}, request=request)

    await _client(handler).cancel(SCHEDULED, reason="el paciente no puede")
    assert seen["url"] == f"{SCHEDULED}/cancellation"
    assert seen["body"] == {"reason": "el paciente no puede"}


async def test_cancel_accepts_a_bare_uuid() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(201, json={"resource": {}}, request=request)

    await _client(handler).cancel("8d01516b")
    assert seen["url"] == "https://api.calendly.com/scheduled_events/8d01516b/cancellation"


async def test_cancel_twice_is_not_a_failure() -> None:
    """Calendly answers 403 the second time, and that is the state we wanted."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"title": "Permission Denied", "message": "Event is already canceled"},
            request=request,
        )

    await _client(handler).cancel(SCHEDULED)


async def test_cancel_of_an_unknown_event_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"title": "Resource Not Found"}, request=request)

    with pytest.raises(CalendlyError):
        await _client(handler).cancel(SCHEDULED)


async def test_book_uses_the_patient_phone_for_an_outbound_call() -> None:
    """`outbound_call` means Calendly rings the patient: the event type leaves it blank."""
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.update(json.loads(request.content))
        return httpx.Response(
            201, json={"resource": {"event": SCHEDULED, "uri": "u"}}, request=request
        )

    await _book(_client(handler, CALL))
    assert seen["location"]["location"] == "+525599998888"


async def test_book_refuses_a_location_only_the_invitee_can_give() -> None:
    resource = {"duration": 15, "locations": [{"kind": "ask_invitee"}], "custom_questions": []}

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        raise AssertionError("must not POST a location we cannot know")

    with pytest.raises(CalendlyError, match="answered by the invitee"):
        await _book(_client(handler, resource))
