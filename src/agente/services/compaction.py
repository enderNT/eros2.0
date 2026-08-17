"""Rolling summary maintenance, off the patient reply path (SPEC §9).

Runs after the reply is already sent. It reads only what the current
summary does not yet cover (`watermark_message_id`), asks the cheap model
to fold the oldest turns into the summary, and moves the watermark to the
last turn that is no longer shown verbatim — the overlap stays visible in
the window *and* inside the summary, which is the point of the overlap.

A failure here is never a patient-facing failure: it logs and returns
False, and the next turn tries again over the same messages.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from ..domain.contacts import ContactKey
from ..domain.errors import DomainError
from ..domain.memory import plan_window
from ..ports.model import Model
from ..ports.store import MessageRow, MessagesRepository, SummariesRepository, SummaryRow

log = logging.getLogger(__name__)

Summarizer = Callable[[str], Awaitable[str]]

WINDOW_LIMIT = 100

SUMMARY_SYSTEM = (
    "Eres el archivista de un asistente de una clínica de psicología y neuromodulación."
    " Recibes el resumen previo (si existe) y los turnos más antiguos de una conversación"
    " de WhatsApp. Devuelve un resumen actualizado en español, en tercera persona, de 120"
    " palabras como máximo.\n"
    "Conserva: nombre, motivo de consulta, servicio de interés, datos que el paciente ya"
    " dio, precios o políticas que ya se le dijeron, y compromisos pendientes.\n"
    "No inventes nada, no interpretes clínicamente, no agregues consejos y no incluyas"
    " teléfonos ni correos. Devuelve sólo el resumen, sin preámbulo."
)


def make_summarizer(model: Model) -> Summarizer:
    """Bind the cheap model to the summary job."""

    async def summarize(transcript: str) -> str:
        reply = await model.complete(
            [{"type": "text", "text": SUMMARY_SYSTEM}],
            [{"role": "user", "content": transcript}],
            [],
        )
        return reply.text.strip()

    return summarize


async def compact(
    key: ContactKey,
    messages: MessagesRepository,
    summaries: SummariesRepository,
    summarize: Summarizer,
    now: datetime,
    *,
    budget: int,
    overlap_turns: int = 1,
) -> bool:
    """Fold everything above the token budget into the rolling summary."""
    try:
        previous = summaries.get(key)
        window = _uncovered(messages.window(key, WINDOW_LIMIT), previous)
    except DomainError:
        log.error("compaction_failed", extra={"stage": "read"})
        return False
    plan = plan_window(
        window,
        token_budget=budget,
        estimate_tokens=_estimate_tokens,
        overlap_turns=overlap_turns,
    )
    if not plan.needs_compaction:
        return False
    kept = {row.id for row in plan.verbatim}
    dropped = [row.id for row in plan.compacted if row.id not in kept]
    if not dropped:
        return False
    try:
        text = await summarize(_transcript(previous.text if previous else None, plan.compacted))
    except DomainError:
        log.error("compaction_failed", extra={"stage": "model"})
        return False
    if not text:
        return False
    try:
        summaries.save(key, text, max(dropped), now)
    except DomainError:
        log.error("compaction_failed", extra={"stage": "write"})
        return False
    log.info("compacted", extra={"turns": len(plan.compacted), "watermark": max(dropped)})
    return True


def _uncovered(window: list[MessageRow], previous: SummaryRow | None) -> list[MessageRow]:
    if previous is None:
        return window
    return [row for row in window if row.id > previous.watermark_message_id]


def _transcript(previous: str | None, turns: tuple[MessageRow, ...]) -> str:
    head = f"Resumen previo:\n{previous}\n\n" if previous else ""
    body = "\n".join(
        f"{'Paciente' if row.direction == 'inbound' else 'Asistente'}: {row.text}" for row in turns
    )
    return f"{head}Turnos a integrar:\n{body}"


def _estimate_tokens(row: MessageRow) -> int:
    return max(1, len(row.text) // 4)
