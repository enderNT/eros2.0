"""Signature verification and the Calendly webhook edge (TASKS T9b)."""

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agente.adapters.calendly.signature import sign, verify_signature
from agente.app import create_app

NOW = datetime(2026, 8, 17, 12, tzinfo=UTC)
KEY = "calendly-signing-key"
BODY = json.dumps({"event": "invitee.created", "payload": {}}).encode()


class FakeBooking:
    def __init__(self) -> None:
        self.calls = []

    async def handle(self, event, payload) -> None:
        self.calls.append((event, payload))


def test_signature_over_timestamp_and_body_is_accepted():
    assert verify_signature(BODY, sign(BODY, KEY, NOW), KEY, now=NOW)


def test_signature_over_the_body_alone_is_rejected():
    """The old, wrong scheme: signing the body only would let a delivery replay forever."""
    import hashlib
    import hmac

    body_only = hmac.new(KEY.encode(), BODY, hashlib.sha256).hexdigest()
    assert not verify_signature(BODY, f"t={int(NOW.timestamp())},v1={body_only}", KEY, now=NOW)


def test_stale_timestamp_is_rejected():
    stale = sign(BODY, KEY, NOW - timedelta(minutes=10))
    assert not verify_signature(BODY, stale, KEY, now=NOW)


def test_tampered_body_is_rejected():
    assert not verify_signature(b'{"event":"other"}', sign(BODY, KEY, NOW), KEY, now=NOW)


def test_missing_header_or_key_is_rejected():
    assert not verify_signature(BODY, None, KEY, now=NOW)
    assert not verify_signature(BODY, sign(BODY, KEY, NOW), "", now=NOW)
    assert not verify_signature(BODY, "garbage", KEY, now=NOW)


def test_route_rejects_a_forged_delivery(make_settings):
    settings = make_settings(calendly_signing_key=KEY)
    with TestClient(create_app(settings)) as client:
        fake = FakeBooking()
        client.app.state.booking = fake
        response = client.post(
            "/webhook/calendly", content=BODY, headers={"Calendly-Webhook-Signature": "t=1,v1=bad"}
        )
    assert response.status_code == 401
    assert fake.calls == []


def test_route_dispatches_a_valid_delivery(make_settings):
    settings = make_settings(calendly_signing_key=KEY)
    signature = sign(BODY, KEY, datetime.now(UTC))
    with TestClient(create_app(settings)) as client:
        fake = FakeBooking()
        client.app.state.booking = fake
        response = client.post(
            "/webhook/calendly", content=BODY, headers={"Calendly-Webhook-Signature": signature}
        )
    assert response.status_code == 200
    assert fake.calls == [("invitee.created", {})]
