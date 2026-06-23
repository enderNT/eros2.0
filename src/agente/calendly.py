"""Cliente de la Calendly Scheduling API (I.calendly / ADR 0001).

Flujo: get_event_types → available_times (máx 7 días) → crear_invitee.
V3: solo un 2xx de crear_invitee cuenta como reserva confirmada.
"""

import hashlib
import hmac
import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

import httpx

from .config import settings

log = logging.getLogger(__name__)

BASE_URL = "https://api.calendly.com"


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

    def available_times(self, event_type: str, start: str, end: str) -> list[dict]:
        """Horarios disponibles. La API limita a 7 días por request."""
        r = self._http.get(
            "/event_type_available_times",
            params={"event_type": event_type, "start_time": start, "end_time": end},
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

        r = self._http.post("/invitees", json=payload)
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
