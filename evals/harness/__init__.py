"""Arnés de pruebas conversacionales: la app real, sin Kapso y sin Calendly."""

from .fakes import FakeCalendar, RecordingChannel, SentMessage
from .judge import (
    ROL_CLINICA,
    caso_conversacional,
    coherente,
    judge,
    no_inventa,
    reconduce,
    rubric,
    sin_diagnostico,
    tono_clinico,
)
from .report import Criterio, Medida, Report, cerrar
from .texto import dice, dice_todo, normaliza, respuestas
from .world import (
    CONTACT,
    PHONE_NUMBER_ID,
    RUNS_DIR,
    Appointment,
    Exchange,
    Pending,
    Reserva,
    Snapshot,
    World,
    world,
)

__all__ = [
    "CONTACT",
    "ROL_CLINICA",
    "PHONE_NUMBER_ID",
    "RUNS_DIR",
    "Appointment",
    "Criterio",
    "Exchange",
    "FakeCalendar",
    "Medida",
    "Pending",
    "RecordingChannel",
    "Report",
    "Reserva",
    "SentMessage",
    "Snapshot",
    "World",
    "caso_conversacional",
    "cerrar",
    "dice",
    "dice_todo",
    "normaliza",
    "respuestas",
    "coherente",
    "judge",
    "no_inventa",
    "reconduce",
    "rubric",
    "sin_diagnostico",
    "tono_clinico",
    "world",
]
