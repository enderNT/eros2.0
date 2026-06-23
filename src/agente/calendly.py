"""Cliente de la Calendly Scheduling API (I.calendly / ADR 0001).

Flujo: get_event_types → available_times (máx 7 días) → crear_invitee.
V3: solo un 2xx de crear_invitee cuenta como reserva confirmada.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import httpx

from .config import settings
from .llm_logger import get_llm_logger, render_data_text

log = logging.getLogger(__name__)

BASE_URL = "https://api.calendly.com"

_REDACTED_HEADERS = {"authorization", "cookie", "set-cookie"}


@dataclass
class ResultadoReserva:
    status: str  # "ok" | "slot_taken" | "error"
    cancel_url: Optional[str] = None
    reschedule_url: Optional[str] = None
    invitee_uri: Optional[str] = None   # URI del invitee (clave para casar webhooks)
    event_uri: Optional[str] = None     # URI del scheduled_event
    detail: str = ""


def verificar_firma_webhook(signing_key: str, header: str, body: bytes) -> bool:
    """Valida el header `Calendly-Webhook-Signature` (formato 't=<ts>,v1=<hmac>').

    HMAC-SHA256 de '<t>.<body>' con la signing key registrada en la subscription.
    Si no hay signing key configurada, no se puede verificar → se rechaza.
    """
    if not signing_key or not header:
        return False
    partes = dict(
        p.split("=", 1) for p in header.split(",") if "=" in p
    )
    t, v1 = partes.get("t"), partes.get("v1")
    if not t or not v1:
        return False
    firmado = f"{t}.".encode() + body
    esperado = hmac.new(signing_key.encode(), firmado, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, v1)


class CalendlyClient:
    def __init__(self, token: str, http: Optional[httpx.Client] = None):
        self._http = http or httpx.Client(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def _headers(self, headers: httpx.Headers) -> dict[str, str]:
        return {
            key: ("***" if key.lower() in _REDACTED_HEADERS else value)
            for key, value in headers.items()
        }

    def _response_payload(self, response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:  # noqa: BLE001
            return response.text

    def _log_http(
        self,
        *,
        operation: str,
        stage: str,
        stage_label: str,
        stage_order: int,
        call_order: int,
        ctx: dict | None,
        response: httpx.Response | None = None,
        error: Exception | None = None,
        request_body: Any = None,
    ) -> None:
        if not ctx:
            return
        request = response.request if response is not None else None
        url = str(request.url) if request is not None else ""
        method = request.method if request is not None else operation.split(".")[-1].upper()
        headers = self._headers(request.headers) if request is not None else {}
        body = request_body if request_body is not None else {}
        semantic_request = {
            "method": method,
            "url": url,
            "headers": headers,
            "query": dict(request.url.params) if request is not None else {},
            "body": body,
        }

        if response is not None:
            response_body = self._response_payload(response)
            response_text = render_data_text(
                {
                    "status_code": response.status_code,
                    "reason": response.reason_phrase,
                    "body": response_body,
                }
            )
            status = "ok" if response.status_code < 400 else "error"
        else:
            response_text = render_data_text({"error": str(error)})
            status = "error"

        get_llm_logger().record(
            provider="calendly",
            operation=operation,
            model=None,
            status=status,
            conversation_id=ctx.get("conversation_id"),
            flow_id=ctx.get("flow_id"),
            message_id=ctx.get("message_id"),
            stage=stage,
            stage_label=stage_label,
            stage_order=stage_order,
            call_order=call_order,
            request_text=render_data_text(semantic_request),
            response_text=response_text,
            metadata={
                "purpose": "calendly.http",
                "calendly_http": True,
                "semantic_tab_label": "Semantico",
                "request_body_text": render_data_text(body),
                "http_method": method,
                "http_url": url,
                "http_status_code": response.status_code if response is not None else None,
            },
        )

    def available_times(self, event_type: str, start: str, end: str, ctx: dict | None = None) -> list[dict]:
        """Horarios disponibles. La API limita a 7 días por request."""
        params = {"event_type": event_type, "start_time": start, "end_time": end}
        try:
            r = self._http.get("/event_type_available_times", params=params)
        except Exception as e:  # noqa: BLE001
            self._log_http(
                operation="calendly.available_times",
                stage="calendly_available_times",
                stage_label="Calendly · consultar horarios",
                stage_order=32,
                call_order=1,
                ctx=ctx,
                error=e,
                request_body={},
            )
            raise
        self._log_http(
            operation="calendly.available_times",
            stage="calendly_available_times",
            stage_label="Calendly · consultar horarios",
            stage_order=32,
            call_order=1,
            ctx=ctx,
            response=r,
            request_body={},
        )
        r.raise_for_status()
        return r.json().get("collection", [])

    def crear_invitee(
        self,
        *,
        event_type: str,
        start_time: str,
        nombre: str,
        correo: str,
        timezone: str,
        location_kind: str,
        asunto: Optional[str] = None,
        ctx: dict | None = None,
        call_order: int = 1,
    ) -> ResultadoReserva:
        """POST /invitees. Mapea: 2xx→ok, 409/422→slot_taken, otro→error.

        Nota: el código exacto de "slot ocupado" puede afinarse; V3 se cumple
        igual porque solo `is_success` produce "ok".
        """
        payload: dict = {
            "event_type": event_type,
            "start_time": start_time,
            "invitee": {"name": nombre, "email": correo, "timezone": timezone},
            "location": {"kind": location_kind},
        }
        if asunto:
            payload["questions_and_answers"] = [
                {"question": "asunto", "answer": asunto, "position": 0}
            ]

        try:
            r = self._http.post("/invitees", json=payload)
        except Exception as e:  # noqa: BLE001
            self._log_http(
                operation="calendly.create_invitee",
                stage="calendly_create_invitee",
                stage_label="Calendly · crear invitee",
                stage_order=33,
                call_order=call_order,
                ctx=ctx,
                error=e,
                request_body=payload,
            )
            raise
        self._log_http(
            operation="calendly.create_invitee",
            stage="calendly_create_invitee",
            stage_label="Calendly · crear invitee",
            stage_order=33,
            call_order=call_order,
            ctx=ctx,
            response=r,
            request_body=payload,
        )
        if r.is_success:
            res = r.json().get("resource", {})
            return ResultadoReserva(
                "ok",
                cancel_url=res.get("cancel_url"),
                reschedule_url=res.get("reschedule_url"),
                invitee_uri=res.get("uri"),
                event_uri=res.get("event"),
            )
        if r.status_code in (409, 422):
            return ResultadoReserva("slot_taken", detail=r.text)
        return ResultadoReserva("error", detail=f"{r.status_code} {r.text}")


@lru_cache(maxsize=1)
def get_calendly() -> Optional[CalendlyClient]:
    """Cliente Calendly, o None si no hay token (el nodo degrada)."""
    if not settings.calendly_token:
        return None
    return CalendlyClient(settings.calendly_token)
