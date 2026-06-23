"""Recordatorios de cita: cola durable en Postgres + despacho por plantilla WhatsApp.

Flujo:
  - Al agendar (tools.agendar_cita) o al recibir `invitee.created` (webhook Calendly)
    se insertan filas en `recordatorios`, una por cada lead (minutos antes).
  - Un poller in-process (app.py) llama `despachar_due()` cada N segundos: reclama
    los vencidos y los manda como PLANTILLA por Chatwoot (texto libre no se entrega
    fuera de la ventana de 24h de WhatsApp).

El recordatorio es DETERMINISTA: no pasa por el LLM. Si la persona responde, ese
mensaje entrante entra por el webhook normal y ahí sí corre el agente.
"""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .chatwoot import get_chatwoot
from .config import settings
from .llm_logger import get_llm_logger, render_data_text
from .store import get_store

log = logging.getLogger(__name__)

# --- Plantilla WhatsApp (fija, no en env) ------------------------------------
# Plantilla aprobada: dos variables posicionales → {{1}}=nombre, {{2}}=date_day.
TEMPLATE_NOMBRE = "saludos_confirmar_cita"
TEMPLATE_IDIOMA = "es_MX"  # si tu plantilla quedó como es_MX/es_ES, ajústalo aquí
# WhatsApp rechaza variables vacías o solo-espacios; si no hay nombre, mandamos esto.
NOMBRE_FALLBACK = "👋"

_DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
_MESES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def leads_minutes() -> list[int]:
    """Lee settings.recordatorio_lead_minutes ('1440,10') → [1440, 10]."""
    out = []
    for parte in (settings.recordatorio_lead_minutes or "").split(","):
        parte = parte.strip()
        if parte.isdigit():
            out.append(int(parte))
    return out


def _en_zona(slot: datetime) -> datetime:
    return slot.astimezone(ZoneInfo(settings.calendly_timezone))


def _fmt_fecha(slot_local: datetime) -> str:
    return f"{_DIAS[slot_local.weekday()]} {slot_local.day} de {_MESES[slot_local.month]}"


def _fmt_hora(slot_local: datetime) -> str:
    h = slot_local.hour % 12 or 12
    ampm = "a.m." if slot_local.hour < 12 else "p.m."
    return f"{h}:{slot_local.minute:02d} {ampm}"


def construir_params(nombre: str | None, slot: datetime) -> dict:
    """Variables de la plantilla: {{1}}=nombre (con fallback), {{2}}=date_day."""
    local = _en_zona(slot)
    return {
        "1": (nombre or "").strip() or NOMBRE_FALLBACK,
        "2": _fmt_fecha(local),
    }


def _fallback(nombre: str | None, slot: datetime) -> str:
    local = _en_zona(slot)
    saludo = f"Hola {nombre}, " if nombre else "Hola, "
    return f"{saludo}te recordamos tu cita el {_fmt_fecha(local)} a las {_fmt_hora(local)}."


def despachar_due(limite: int = 20) -> int:
    """Reclama recordatorios vencidos y los envía como plantilla. Devuelve cuántos
    se enviaron. Pensado para correr en threadpool desde el poller."""
    cw = get_chatwoot()
    if cw is None:
        log.warning("recordatorios: Chatwoot no configurado; no se envía nada")
        return 0

    store = get_store()
    pendientes = store.reclamar_recordatorios_vencidos(limite)
    logger = get_llm_logger()
    enviados = 0
    for r in pendientes:
        # Cada recordatorio es un flujo aparte, rastreable en el mismo listado/tabla.
        flow_id = f"recordatorio:{r['id']}"
        params = construir_params(r["nombre"], r["slot"])
        fallback = _fallback(r["nombre"], r["slot"])
        slot_iso = r["slot"].isoformat() if hasattr(r["slot"], "isoformat") else str(r["slot"])

        # Etapa 1: el recordatorio fue encontrado/reclamado para envío.
        logger.record(
            provider="recordatorio",
            operation="recordatorio.encontrado",
            model=None,
            status="ok",
            conversation_id=r["conversation_id"],
            flow_id=flow_id,
            stage="recordatorio_encontrado",
            stage_label="Recordatorio encontrado",
            stage_order=10,
            call_order=1,
            request_text=render_data_text(
                {
                    "recordatorio_id": r["id"],
                    "conversation_id": r["conversation_id"],
                    "nombre": r["nombre"],
                    "cita": slot_iso,
                    "lead_minutes": r["lead_minutes"],
                }
            ),
            response_text=render_data_text(
                {
                    "estado": "reclamado para envío",
                    "plantilla": TEMPLATE_NOMBRE,
                    "idioma": TEMPLATE_IDIOMA,
                    "variables": params,
                }
            ),
            metadata={"purpose": "recordatorio", "etapa": "encontrado"},
        )

        # Etapa 2: envío por Chatwoot (plantilla WhatsApp).
        req = {
            "conversation_id": r["conversation_id"],
            "plantilla": TEMPLATE_NOMBRE,
            "idioma": TEMPLATE_IDIOMA,
            "processed_params": params,
            "fallback": fallback,
        }
        try:
            resp = cw.enviar_plantilla(
                r["conversation_id"],
                nombre_plantilla=TEMPLATE_NOMBRE,
                idioma=TEMPLATE_IDIOMA,
                processed_params=params,
                fallback=fallback,
            )
            store.marcar_recordatorio_enviado(r["id"])
            enviados += 1
            log.info("recordatorio %s enviado (conv=%s)", r["id"], r["conversation_id"])
            logger.record(
                provider="recordatorio",
                operation="recordatorio.envio",
                model=None,
                status="ok",
                conversation_id=r["conversation_id"],
                flow_id=flow_id,
                stage="recordatorio_envio",
                stage_label="Envío por Chatwoot",
                stage_order=20,
                call_order=1,
                request_text=render_data_text(req),
                response_text=render_data_text(resp),
                metadata={"purpose": "recordatorio", "etapa": "envio"},
            )
        except Exception as e:  # noqa: BLE001
            log.error("recordatorio %s falló: %s", r["id"], e)
            store.marcar_recordatorio_fallido(r["id"], str(e))
            logger.record(
                provider="recordatorio",
                operation="recordatorio.envio",
                model=None,
                status="error",
                conversation_id=r["conversation_id"],
                flow_id=flow_id,
                stage="recordatorio_envio",
                stage_label="Envío por Chatwoot",
                stage_order=20,
                call_order=1,
                request_text=render_data_text(req),
                response_text=str(e),
                metadata={"purpose": "recordatorio", "etapa": "envio"},
            )
    return enviados
