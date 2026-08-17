"""The crisis pre-gate (SPEC §7): one Haiku call before the agent runs.

The verdict comes back through a tool schema with an `enum`, not as free
text, so there is nothing to string-match and nothing to misparse. Anything
that is not one of the three verdicts — a missing tool call, an unknown
string, a timeout, a model failure — becomes `possible`.

**Fail closed, always.** `possible` costs a slightly more careful answer;
`none` on a message that was actually a crisis costs something we cannot
take back. The asymmetry is the whole design.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from ..domain.crisis import CrisisVerdict
from ..domain.errors import DomainError
from ..ports.model import Model

log = logging.getLogger(__name__)

Classifier = Callable[[str, str | None], Awaitable[CrisisVerdict]]

TIMEOUT_SECONDS = 8.0
TOOL_NAME = "clasificar_riesgo"

SYSTEM = (
    "Clasificas el riesgo del mensaje de un paciente que escribe a una clínica de"
    " psicología. No conversas, no aconsejas, no consuelas: sólo clasificas, siempre"
    " llamando a la herramienta clasificar_riesgo.\n\n"
    "- acute: hay riesgo para la vida ahora — ideación suicida, plan o intención de"
    " suicidio, autolesión en curso, sobredosis, violencia inminente contra sí mismo"
    " o contra alguien más.\n"
    "- possible: sufrimiento intenso, desesperanza, crisis emocional o mención de"
    " ideas de muerte sin plan ni inminencia; también cuando el mensaje es ambiguo"
    " y podrías estar leyendo de menos.\n"
    "- none: todo lo demás — preguntas de precios, horarios, servicios, logística,"
    " o malestar cotidiano sin señales de riesgo.\n\n"
    "Ante la duda entre dos categorías, elige siempre la más grave."
)

TOOL: dict[str, Any] = {
    "name": TOOL_NAME,
    "description": "Devuelve el nivel de riesgo del mensaje.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdicto": {
                "type": "string",
                "enum": [verdict.value for verdict in CrisisVerdict],
            }
        },
        "required": ["verdicto"],
    },
}


def make_classifier(model: Model) -> Classifier:
    """Bind the pre-gate to a model port (a Haiku client in the composition root)."""

    async def classify(text: str, turn_id: str | None = None) -> CrisisVerdict:
        reply = await model.complete(
            [{"type": "text", "text": SYSTEM}],
            [{"role": "user", "content": text}],
            [TOOL],
            turn_id=turn_id,
        )
        for use in reply.tool_uses:
            if use.name == TOOL_NAME:
                return parse_verdict(use.input.get("verdicto"))
        return CrisisVerdict.POSSIBLE

    return classify


def parse_verdict(value: Any) -> CrisisVerdict:
    try:
        return CrisisVerdict(str(value).strip().lower())
    except ValueError:
        return CrisisVerdict.POSSIBLE


async def check(
    classifier: Classifier | None,
    text: str,
    *,
    turn_id: str | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> CrisisVerdict:
    if classifier is None:
        return CrisisVerdict.NONE
    try:
        return await asyncio.wait_for(classifier(text, turn_id), timeout)
    except (DomainError, TimeoutError, RuntimeError, ValueError):
        log.error("crisis_check_failed", extra={"turn_id": turn_id})
        return CrisisVerdict.POSSIBLE
