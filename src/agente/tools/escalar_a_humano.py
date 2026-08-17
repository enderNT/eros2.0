"""Mute a contact and return the patient-facing escalation wording."""

from __future__ import annotations

from datetime import datetime

from ..domain.contacts import ContactKey
from ..ports.store import MutesRepository


async def escalar_a_humano(
    mutes: MutesRepository, key: ContactKey, motivo: str, now: datetime
) -> str:
    mutes.set_mute(key, now, actor="agent", reason=motivo)
    return "Una persona del equipo dará seguimiento a tu mensaje."
