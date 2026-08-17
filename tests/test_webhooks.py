import hashlib
import hmac
import json

from fastapi.testclient import TestClient

from agente.app import create_app


class FakeInbound:
    def __init__(self) -> None:
        self.received = []

    async def handle(self, payload) -> None:
        self.received.append(payload)


def _body() -> bytes:
    return json.dumps(
        {
            "message": {
                "id": "m1",
                "timestamp": "2026-08-16T12:00:00Z",
                "type": "text",
                "from": "+12052943796",
                "text": {"body": "hola"},
            },
            "conversation": {"id": "c1"},
            "phone_number_id": "1087343774471931",
        }
    ).encode()


def test_webhook_rejects_forged_signature(settings):
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/webhook/kapso", content=_body(), headers={"X-Webhook-Signature": "bad"}
        )
    assert response.status_code == 400


def test_webhook_acks_and_dispatches_signed_payload(settings):
    body = _body()
    signature = hmac.new(settings.kapso_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    with TestClient(create_app(settings)) as client:
        fake = FakeInbound()
        client.app.state.inbound = fake
        response = client.post(
            "/webhook/kapso", content=body, headers={"X-Webhook-Signature": signature}
        )
    assert response.status_code == 200
    assert len(fake.received) == 1
