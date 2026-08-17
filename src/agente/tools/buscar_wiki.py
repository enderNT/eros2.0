"""Model-facing wrapper around deterministic clinic wiki lookup."""

from __future__ import annotations

from ..services.knowledge import Knowledge


async def buscar_wiki(knowledge: Knowledge, consulta: str) -> str:
    return knowledge.find_sections(consulta)
