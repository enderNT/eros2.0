"""The tool surface the conversational agent sees (SPEC §6).

One place builds both halves of the contract — the JSON schemas the model
reads and the handlers that run — so a tool cannot be described without
being wired. Handlers translate every domain failure into a sentence the
model can act on: the agent loop only rescues `ValueError`/`RuntimeError`,
and a `CalendlyError` reaching it would drop the patient's turn.

Time is injected (`now`), never read inside a handler, so scheduling stays
testable with a fixed clock.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ..domain.contacts import ContactKey
from ..domain.errors import CalendlyError, DomainError
from ..ports.calendar import Calendar, CalendarSlot
from ..ports.store import MutesRepository
from ..services.booking import BookingService
from ..services.knowledge import Knowledge
from .agendar_cita import agendar_cita
from .buscar_wiki import buscar_wiki
from .cancelar_cita import cancelar_cita
from .escalar_a_humano import escalar_a_humano
from .ver_horarios import ver_horarios

log = logging.getLogger(__name__)

ToolHandler = Callable[[dict[str, Any]], Awaitable[str]]

AVAILABILITY_DAYS = 14
CALENDAR_DOWN = "No puedo consultar la agenda ahora mismo. Ofrece continuar con una persona."
UNKNOWN_SLOT = "Ese horario ya no está disponible. Ofrece otro de los horarios vigentes."
STORE_DOWN = "No pude guardar el dato. No confirmes nada al paciente."
CANCEL_DOWN = (
    "No pude cancelar la cita ahora mismo y sigue agendada. NO le digas que quedó"
    " cancelada: dile que hubo un problema y pásalo a una persona del equipo."
)

DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "buscar_wiki",
        "description": (
            "Devuelve el texto confirmado de la clínica. Consulta con el título de la"
            " sección del índice (por ejemplo 'Precios y formas de pago'), no con la"
            " frase del paciente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "consulta": {
                    "type": "string",
                    "description": "Título o palabras clave de la sección del índice.",
                }
            },
            "required": ["consulta"],
        },
    },
    {
        "name": "ver_horarios",
        "description": (
            "Horarios disponibles para la cita de valoración. Cada línea trae primero"
            " un identificador ISO que debes copiar tal cual en agendar_cita, y"
            " después la etiqueta legible que puedes decirle al paciente."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "dias": {
                    "type": "integer",
                    "description": (
                        f"Días hacia adelante a consultar, 1-30. Default {AVAILABILITY_DAYS}."
                    ),
                }
            },
            "required": [],
        },
    },
    {
        "name": "agendar_cita",
        "description": (
            "Reserva de verdad un horario que ya le ofreciste con ver_horarios. La cita"
            " queda agendada y confirmada al usar esta herramienta: el paciente no tiene"
            " que entrar a ningún enlace ni rellenar nada. Si ya tenía otra cita, ésta la"
            " sustituye y la anterior se cancela sola. Úsala sólo cuando el paciente haya"
            " aceptado un horario concreto."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "inicio": {
                    "type": "string",
                    "description": "Identificador ISO exacto devuelto por ver_horarios.",
                }
            },
            "required": ["inicio"],
        },
    },
    {
        "name": "cancelar_cita",
        "description": (
            "Cancela la cita del paciente y libera su horario. Se usa en DOS pasos:"
            " llámala primero sin confirmado para saber qué cita es y pregúntale al"
            " paciente si quiere cancelarla; sólo cuando responda que sí de forma clara,"
            " vuelve a llamarla con confirmado=true. Que dude sobre si podrá asistir"
            " ('creo que no llego', 'se me complicó') NO es pedir una cancelación:"
            " ofrécele cancelar o reagendar y espera su respuesta. Para mover una cita"
            " no hace falta cancelar: usa agendar_cita con el horario nuevo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "confirmado": {
                    "type": "boolean",
                    "description": (
                        "true SÓLO si el paciente ya dijo explícitamente que sí quiere"
                        " cancelar. Nunca lo pongas por iniciativa propia."
                    ),
                },
                "motivo": {
                    "type": "string",
                    "description": "Motivo breve, en las palabras del paciente.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "escalar_a_humano",
        "description": (
            "Silencia al bot y deja la conversación a una persona del equipo. Úsala"
            " cuando el dato no exista, no te corresponda, o el paciente pida un humano."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"motivo": {"type": "string"}},
            "required": ["motivo"],
        },
    },
]


def build_tools(
    *,
    knowledge: Knowledge,
    mutes: MutesRepository,
    calendar: Calendar,
    booking: BookingService,
    key: ContactKey,
    timezone: str,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> tuple[list[dict[str, Any]], dict[str, ToolHandler]]:
    """The definitions and handlers for one contact's turn."""

    async def _buscar_wiki(data: dict[str, Any]) -> str:
        return await buscar_wiki(knowledge, str(data.get("consulta", "")))

    async def _ver_horarios(data: dict[str, Any]) -> str:
        days = _days(data.get("dias"))
        try:
            return await ver_horarios(calendar, now(), timezone, days=days)
        except CalendlyError:
            log.warning("tool_failed", extra={"tool": "ver_horarios"})
            return CALENDAR_DOWN

    async def _agendar_cita(data: dict[str, Any]) -> str:
        moment = now()
        try:
            slot = await _resolve_slot(calendar, str(data.get("inicio", "")), moment)
        except CalendlyError:
            log.warning("tool_failed", extra={"tool": "agendar_cita", "stage": "availability"})
            return CALENDAR_DOWN
        if slot is None:
            return UNKNOWN_SLOT
        try:
            return await agendar_cita(booking, key, slot, moment, timezone)
        except CalendlyError:
            log.error("tool_failed", extra={"tool": "agendar_cita", "stage": "book"})
            return CALENDAR_DOWN
        except DomainError:
            log.error("tool_failed", extra={"tool": "agendar_cita", "stage": "store"})
            return STORE_DOWN

    async def _cancelar_cita(data: dict[str, Any]) -> str:
        try:
            return await cancelar_cita(
                booking,
                key,
                now(),
                timezone,
                confirmado=bool(data.get("confirmado")),
                motivo=str(data.get("motivo", "")),
            )
        except CalendlyError:
            log.error("tool_failed", extra={"tool": "cancelar_cita", "stage": "calendar"})
            return CANCEL_DOWN
        except DomainError:
            log.error("tool_failed", extra={"tool": "cancelar_cita", "stage": "store"})
            return STORE_DOWN

    async def _escalar_a_humano(data: dict[str, Any]) -> str:
        try:
            return await escalar_a_humano(mutes, key, str(data.get("motivo", "")), now())
        except DomainError:
            log.error("tool_failed", extra={"tool": "escalar_a_humano"})
            return STORE_DOWN

    return list(DEFINITIONS), {
        "buscar_wiki": _buscar_wiki,
        "ver_horarios": _ver_horarios,
        "agendar_cita": _agendar_cita,
        "cancelar_cita": _cancelar_cita,
        "escalar_a_humano": _escalar_a_humano,
    }


async def _resolve_slot(calendar: Calendar, inicio: str, now: datetime) -> CalendarSlot | None:
    """Match the model-supplied identifier against live availability.

    The model can only book something the calendar still offers: a stale or
    invented `inicio` finds no slot and the tool says so.
    """
    wanted = _parse_utc(inicio)
    if wanted is None:
        return None
    slots = await calendar.availability(now, now + timedelta(days=AVAILABILITY_DAYS))
    return next((slot for slot in slots if slot.start_utc == wanted), None)


def _parse_utc(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _days(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError):
        return AVAILABILITY_DAYS
    return min(max(days, 1), 30)
