"""Pydantic models for Kapso webhook payloads and authenticity verification
(SPEC §15).

Two forms arrive at ``POST /webhook/kapso``:

* **Single** — the unbuffered body, one message.
* **Batched** — ``X-Webhook-Batch: true`` header and
  ``{batch: true, data: [...]}`` body, each item shaped like the single form.

Field names are verbatim from Kapso's documentation; nested shapes are
summarized (SPEC §15 caveat: **verify against a real delivery in T6**).
Every model uses ``extra="allow"`` so undocumented fields do not reject a
valid delivery.

Authenticity is verified with HMAC-SHA256 of the raw body keyed by the
webhook secret.  The exact header Kapso uses is undocumented (SPEC §15);
``X-Webhook-Signature`` is the secure default — confirm and adjust in T6.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ...domain.errors import KapsoError

_SIGNATURE_HEADER = "X-Webhook-Signature"
_BATCH_HEADER = "X-Webhook-Batch"


class KapsoMessageText(BaseModel):
    model_config = ConfigDict(extra="allow")
    body: str | None = None


class KapsoMessageKapsoMeta(BaseModel):
    model_config = ConfigDict(extra="allow")
    direction: str | None = None
    status: str | None = None
    processing_status: str | None = None
    origin: str | None = None
    has_media: bool = False
    content: str | None = None


class KapsoMessage(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    timestamp: str
    type: str
    from_: str = Field(alias="from")
    text: KapsoMessageText | None = None
    kapso: KapsoMessageKapsoMeta | None = None


class KapsoConversation(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str


class WebhookPayload(BaseModel):
    """Single-form ``whatsapp.message.received`` payload."""

    model_config = ConfigDict(extra="allow")
    message: KapsoMessage
    conversation: KapsoConversation
    is_new_conversation: bool = False
    phone_number_id: str


class BatchedWebhookPayload(BaseModel):
    """Batched form (``X-Webhook-Batch: true``)."""

    model_config = ConfigDict(extra="allow")
    type: str
    batch: bool
    data: list[WebhookPayload]


def verify_webhook_signature(
    raw_body: bytes, headers: Mapping[str, str], webhook_secret: str
) -> bool:
    """Return ``True`` only if the HMAC-SHA256 signature matches the body."""
    signature = _header_value(headers, _SIGNATURE_HEADER)
    if signature is None:
        return False
    expected = hmac.new(
        webhook_secret.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


def parse_webhook(
    raw_body: bytes, headers: Mapping[str, str], webhook_secret: str
) -> list[WebhookPayload]:
    """Verify authenticity, then parse single or batched payloads.

    Raises :class:`~agente.domain.errors.KapsoError` on a bad signature or
    a malformed body.
    """
    if not verify_webhook_signature(raw_body, headers, webhook_secret):
        raise KapsoError("webhook signature verification failed")
    try:
        parsed: object = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise KapsoError(f"invalid webhook body: {exc}") from exc
    if not isinstance(parsed, dict):
        raise KapsoError("webhook body is not a JSON object")
    is_batched = _header_value(headers, _BATCH_HEADER) == "true" or parsed.get("batch") is True
    model = BatchedWebhookPayload if is_batched else WebhookPayload
    try:
        result = model.model_validate(parsed)
    except ValidationError as exc:
        raise KapsoError(f"invalid webhook payload: {exc}") from exc
    return result.data if is_batched else [result]


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup."""
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None
