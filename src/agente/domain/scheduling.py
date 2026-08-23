"""Slot math, timezone rules and human-readable labels (SPEC §6, §10).

Calendly speaks UTC, the patient speaks the clinic's timezone, and the
conversion happens here and nowhere else (SPEC §10). Every function takes
the clock it needs as an argument (SPEC §2.6); nothing reads the wall
clock, which is what makes DST behaviour testable.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


# Local hours: morning 05:00-11:59, afternoon 12:00-18:59, evening 19:00-04:59.
class PartOfDay(StrEnum):
    MORNING = "mañana"
    AFTERNOON = "tarde"
    EVENING = "noche"


_PART_ORDER = (PartOfDay.MORNING, PartOfDay.AFTERNOON, PartOfDay.EVENING)

_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)


@dataclass(frozen=True, slots=True)
class Slot:
    start_utc: datetime
    end_utc: datetime

    def __post_init__(self) -> None:
        if self.start_utc.tzinfo is None or self.end_utc.tzinfo is None:
            raise ValueError("slot times must be timezone-aware")
        if self.end_utc < self.start_utc:
            raise ValueError("slot ends before it starts")


def part_of_day(hour: int) -> PartOfDay:
    if 5 <= hour < 12:
        return PartOfDay.MORNING
    if 12 <= hour < 19:
        return PartOfDay.AFTERNOON
    return PartOfDay.EVENING


def slot_label(slot: Slot, tz: ZoneInfo, now: datetime) -> str:
    """Patient-facing label in the clinic timezone, never UTC.

    'hoy, 3:30 p. m.', 'mañana, 10:00 a. m.' or
    'miércoles 19 de agosto, 9:30 a. m.' — hoy/mañana are decided on the
    clinic's local date, not the UTC one.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    local = slot.start_utc.astimezone(tz)
    return f"{_day_label(local.date(), now.astimezone(tz).date())}, {_time_label(local)}"


def end_sentence(text: str) -> str:
    """Cerrar la frase sin duplicar el punto.

    Las dos mitades pueden traerlo ya puesto: la etiqueta de hora acaba en
    "p. m." y la dirección la escribe una persona que puntúa como quiera.
    """
    return text if text.rstrip().endswith((".", "!", "?")) else f"{text}."


def address_sentence(address: str) -> str:
    """La dirección como frase suelta, o cadena vacía si no hay ninguna.

    Vacía y no un texto por defecto: una dirección inventada es peor que
    ninguna, y quien la lea va a subirse a un coche.
    """
    return end_sentence(f"La dirección es {address}") if address.strip() else ""


def is_bookable(slot: Slot, now: datetime, buffer: timedelta) -> bool:
    """A slot is bookable when it starts at or after `now + buffer`.

    The buffer covers the time the patient spends choosing and typing, so a
    slot that becomes past while the message travels is never offered. A
    slot starting exactly at the buffer edge is bookable.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return slot.start_utc >= now + buffer


def sample_slots(
    slots: Sequence[Slot],
    tz: ZoneInfo,
    *,
    cap: int = 12,
    per_part_of_day: int = 2,
) -> list[Slot]:
    """The broad sampling rule of SPEC §6.

    Walk the days in order, take at most `per_part_of_day` earliest slots
    from each part of day, stop at `cap`. The sample stays spread across
    days, keeps chronological order, and is deterministic for a given input.
    """
    buckets: dict[date, dict[PartOfDay, list[Slot]]] = {}
    for slot in sorted(slots, key=lambda candidate: candidate.start_utc):
        local = slot.start_utc.astimezone(tz)
        buckets.setdefault(local.date(), {}).setdefault(part_of_day(local.hour), []).append(slot)
    picked: list[Slot] = []
    for day in sorted(buckets):
        for part in _PART_ORDER:
            picked.extend(buckets[day].get(part, ())[:per_part_of_day])
            if len(picked) >= cap:
                return picked[:cap]
    return picked


def _day_label(local_day: date, today: date) -> str:
    if local_day == today:
        return "hoy"
    if local_day == today + timedelta(days=1):
        return "mañana"
    return f"{_WEEKDAYS[local_day.weekday()]} {local_day.day} de {_MONTHS[local_day.month - 1]}"


def _time_label(local: datetime) -> str:
    suffix = "a. m." if local.hour < 12 else "p. m."
    return f"{local.hour % 12 or 12}:{local.minute:02d} {suffix}"
