"""Kapso HTTP client tests — MockTransport, no network (SPEC §3, §11).

Every ``httpx`` failure is translated into :class:`~agente.domain.errors.KapsoError`.
Tests verify timeout, server error, and successful sends plus paginated conversation
listing. Message bodies and full phone numbers never reach a log line.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from agente.adapters.kapso.client import KapsoClient
from agente.domain.errors import KapsoError

# ---- helpers -----------------------------------------------------------------


def _json_response(body: dict[str, Any]) -> httpx.Response:
    """Return a successful ``httpx.Response`` whose body is *body* as JSON."""
    return httpx.Response(200, json=body, request=httpx.Request("GET", "https://dummy"))


def _timeout_response(_: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("read timed out")


def _server_error(_: httpx.Request) -> httpx.Response:
    return httpx.Response(
        500, json={"error": "internal"}, request=httpx.Request("POST", "https://dummy")
    )


BASE_URL = "https://api.kapso.ai/platform/v1"
PHONE_NUMBER_ID = "1087343774471931"
DEST_PHONE = "+525512345678"


# --- fixture ------------------------------------------------------------------


@pytest.fixture()
def client() -> KapsoClient:
    return KapsoClient(BASE_URL, api_key="test-key", timeout=2.0)


# --- send_text ----------------------------------------------------------------


async def test_send_text_returns_message_id(client: KapsoClient) -> None:
    """A happy-path POST returns the Kapso-assigned message id."""
    expected_id = "kps_msg_abc123"
    transport = httpx.MockTransport(lambda req: _json_response({"messages": [{"id": expected_id}]}))
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    result = await client.send_text(PHONE_NUMBER_ID, DEST_PHONE, "Hello")
    assert result == expected_id


async def test_send_text_timeout_raises_kapso_error(client: KapsoClient) -> None:
    """A read timeout bubbles up as KapsoError."""
    transport = httpx.MockTransport(_timeout_response)
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(0.01),
        transport=transport,
    )
    with pytest.raises(KapsoError, match="send_text failed"):
        await client.send_text(PHONE_NUMBER_ID, DEST_PHONE, "Hello")


async def test_send_text_server_error_raises_kapso_error(client: KapsoClient) -> None:
    """A non-2xx response surfaces as KapsoError via raise_for_status."""
    transport = httpx.MockTransport(_server_error)
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    with pytest.raises(KapsoError, match="send_text failed"):
        await client.send_text(PHONE_NUMBER_ID, DEST_PHONE, "Hello")


# --- list_conversations -------------------------------------------------------


def _conversation_item(
    conv_id: str,
    contact_name: str | None = "Ana García",
    contact_phone: str = "525512345678",
    last_text: str | None = "Hola",
    last_activity: str = "2026-08-16T12:00:00-04:00",
    status: str = "active",
) -> dict[str, Any]:
    """One row exactly as the live API returns it (confirmed 2026-08-17)."""
    return {
        "id": conv_id,
        "contact_name": contact_name,
        "phone_number": contact_phone,
        "phone_number_id": PHONE_NUMBER_ID,
        "kapso": {
            "contact_name": contact_name,
            "last_message_text": last_text,
            "last_message_timestamp": "2026-08-16T16:00:00Z",
        },
        "last_active_at": last_activity,
        "status": status,
    }


def _conversations_body(
    items: list[dict[str, Any]] | None = None,
    next_cursor: str | None = None,
) -> dict[str, Any]:
    data = items if items is not None else []
    return {"data": data, "paging": {"cursors": {}, "next": next_cursor, "previous": None}}


CONV_ITEM_A = _conversation_item("conv_a")
CONV_ITEM_B = _conversation_item("conv_b", contact_name="Bob Smith", last_text="¿Horario?")


async def test_list_conversations_returns_rows(client: KapsoClient) -> None:
    """Success yields populated ConversationRow objects."""
    transport = httpx.MockTransport(
        lambda req: _json_response(_conversations_body([CONV_ITEM_A])),
    )
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    result = await client.list_conversations(PHONE_NUMBER_ID)
    assert len(result.conversations) == 1
    row = result.conversations[0]
    assert row.conversation_id == "conv_a"
    assert row.contact_name == "Ana García"
    assert row.contact_phone == "+525512345678"  # normalized from the bare form
    assert row.last_message_text == "Hola"
    assert row.status == "active"
    assert result.next_cursor is None


async def test_list_conversations_has_next_cursor(client: KapsoClient) -> None:
    """Pagination lives in ``paging.next`` and goes back as the ``after`` param."""
    transport = httpx.MockTransport(
        lambda req: _json_response(_conversations_body([CONV_ITEM_A], next_cursor="abc123")),
    )
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    result = await client.list_conversations(PHONE_NUMBER_ID)
    assert result.next_cursor == "abc123"


async def test_list_conversations_empty(client: KapsoClient) -> None:
    """No conversations still returns an empty list, not ``None``."""
    transport = httpx.MockTransport(
        lambda req: _json_response(_conversations_body([])),
    )
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    result = await client.list_conversations(PHONE_NUMBER_ID)
    assert result.conversations == []
    assert result.next_cursor is None


async def test_list_conversations_timeout_raises_kapso_error(client: KapsoClient) -> None:
    transport = httpx.MockTransport(_timeout_response)
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(0.01),
        transport=transport,
    )
    with pytest.raises(KapsoError, match="list_conversations failed"):
        await client.list_conversations(PHONE_NUMBER_ID)


async def test_list_conversations_with_cursor_and_limit(client: KapsoClient) -> None:
    """The cursor travels as ``after`` — Kapso's own pagination param."""
    captured: list[httpx.Request] = []

    def capture(req: httpx.Request) -> httpx.Response:
        captured.append(req)
        return _json_response(_conversations_body([CONV_ITEM_A]))

    transport = httpx.MockTransport(capture)
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    await client.list_conversations(PHONE_NUMBER_ID, cursor="prev", limit=5)
    assert len(captured) == 1
    url = str(captured[0].url)
    assert f"/{PHONE_NUMBER_ID}/conversations" in url
    assert "after=prev" in url
    assert "limit=5" in url


async def test_list_conversations_server_error_raises_kapso_error(client: KapsoClient) -> None:
    transport = httpx.MockTransport(_server_error)
    client._client = httpx.AsyncClient(
        timeout=httpx.Timeout(2.0),
        transport=transport,
    )
    with pytest.raises(KapsoError, match="list_conversations failed"):
        await client.list_conversations(PHONE_NUMBER_ID)


async def test_aclose_is_idempotent(client: KapsoClient) -> None:
    """Calling aclose twice must be safe."""
    await client.aclose()
    await client.aclose()  # should not raise
