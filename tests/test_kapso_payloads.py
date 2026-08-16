"""Kapso webhook payload parsing and authenticity verification (SPEC §15)."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from pydantic import ValidationError

from agente.adapters.kapso.payloads import (
    BatchedWebhookPayload,
    WebhookPayload,
    parse_webhook,
    verify_webhook_signature,
)
from agente.domain.errors import KapsoError

SECRET = "whsec-test"

# --- single-form payload (SPEC §15, unbuffered body) -----------------------

SINGLE_BODY = {
    "message": {
        "id": "msg_001",
        "timestamp": "2026-08-16T12:00:00Z",
        "type": "text",
        "from": "+525512345678",
        "text": {"body": "Hola, necesito información"},
        "kapso": {
            "direction": "inbound",
            "status": "delivered",
            "processing_status": "done",
            "origin": "customer",
            "has_media": False,
            "content": "Hola, necesito información",
        },
    },
    "conversation": {"id": "conv_001", "kapso": {"messages_count": 5}},
    "is_new_conversation": False,
    "phone_number_id": "1087343774471931",
}

# --- batched payload (X-Webhook-Batch: true) --------------------------------

BATCH_BODY = {
    "type": "whatsapp.message.received",
    "batch": True,
    "batch_info": {"count": 2},
    "data": [SINGLE_BODY, {**SINGLE_BODY, "message": {**SINGLE_BODY["message"], "id": "msg_002"}}],
}


def _sign(body: bytes, secret: str = SECRET) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _headers(body: bytes, *, batch: bool = False, secret: str = SECRET) -> dict[str, str]:
    headers = {"X-Webhook-Signature": _sign(body, secret)}
    if batch:
        headers["X-Webhook-Batch"] = "true"
    return headers


# --- model tests ------------------------------------------------------------


def test_single_payload_parses_all_fields():
    payload = WebhookPayload.model_validate(SINGLE_BODY)
    msg = payload.message
    assert msg.id == "msg_001"
    assert msg.timestamp == "2026-08-16T12:00:00Z"
    assert msg.type == "text"
    assert msg.from_ == "+525512345678"
    assert msg.text is not None
    assert msg.text.body == "Hola, necesito información"
    assert msg.kapso is not None
    assert msg.kapso.direction == "inbound"
    assert msg.kapso.has_media is False
    assert msg.kapso.content == "Hola, necesito información"
    assert payload.conversation.id == "conv_001"
    assert payload.is_new_conversation is False
    assert payload.phone_number_id == "1087343774471931"


def test_single_payload_preserves_extra_fields():
    body = {**SINGLE_BODY, "extra_field": "extra_value"}
    payload = WebhookPayload.model_validate(body)
    assert payload.__pydantic_extra__.get("extra_field") == "extra_value"


def test_batched_payload_parses_envelope_and_items():
    batch = BatchedWebhookPayload.model_validate(BATCH_BODY)
    assert batch.batch is True
    assert batch.type == "whatsapp.message.received"
    assert len(batch.data) == 2
    assert batch.data[0].message.id == "msg_001"
    assert batch.data[1].message.id == "msg_002"


def test_missing_from_field_is_rejected():
    stripped_msg = {k: v for k, v in SINGLE_BODY["message"].items() if k != "from"}
    body = {**SINGLE_BODY, "message": stripped_msg}
    with pytest.raises(ValidationError):
        WebhookPayload.model_validate(body)


# --- verification tests -----------------------------------------------------


def test_valid_signature_is_accepted():
    body = json.dumps(SINGLE_BODY).encode()
    assert verify_webhook_signature(body, _headers(body), SECRET) is True


def test_forged_signature_is_rejected():
    body = json.dumps(SINGLE_BODY).encode()
    headers = {"X-Webhook-Signature": "deadbeef"}
    assert verify_webhook_signature(body, headers, SECRET) is False


def test_missing_signature_header_is_rejected():
    body = json.dumps(SINGLE_BODY).encode()
    assert verify_webhook_signature(body, {}, SECRET) is False


def test_wrong_secret_is_rejected():
    body = json.dumps(SINGLE_BODY).encode()
    headers = {"X-Webhook-Signature": _sign(body, "other-secret")}
    assert verify_webhook_signature(body, headers, SECRET) is False


def test_signature_header_lookup_is_case_insensitive():
    body = json.dumps(SINGLE_BODY).encode()
    headers = {"x-webhook-signature": _sign(body)}
    assert verify_webhook_signature(body, headers, SECRET) is True


# --- parse_webhook tests ----------------------------------------------------


def test_parse_single_webhook_returns_one_payload():
    body = json.dumps(SINGLE_BODY).encode()
    payloads = parse_webhook(body, _headers(body), SECRET)
    assert len(payloads) == 1
    assert payloads[0].message.id == "msg_001"


def test_parse_batched_webhook_returns_all_payloads():
    body = json.dumps(BATCH_BODY).encode()
    payloads = parse_webhook(body, _headers(body, batch=True), SECRET)
    assert len(payloads) == 2
    assert {p.message.id for p in payloads} == {"msg_001", "msg_002"}


def test_parse_batched_via_body_flag_without_header():
    body = json.dumps(BATCH_BODY).encode()
    # No X-Webhook-Batch header, but body has batch: true
    payloads = parse_webhook(body, _headers(body), SECRET)
    assert len(payloads) == 2


def test_parse_forged_webhook_raises_kapso_error():
    body = json.dumps(SINGLE_BODY).encode()
    headers = {"X-Webhook-Signature": "forged"}
    with pytest.raises(KapsoError, match="signature"):
        parse_webhook(body, headers, SECRET)


def test_parse_malformed_body_raises_kapso_error():
    body = b"not json"
    with pytest.raises(KapsoError, match="invalid webhook body"):
        parse_webhook(body, _headers(body), SECRET)


def test_parse_non_object_body_raises_kapso_error():
    body = b"[1, 2, 3]"
    with pytest.raises(KapsoError, match="not a JSON object"):
        parse_webhook(body, _headers(body), SECRET)
