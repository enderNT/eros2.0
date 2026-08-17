"""Summary maintenance outside the patient reply path."""

from __future__ import annotations

from datetime import datetime

from ..domain.contacts import ContactKey
from ..domain.memory import plan_window
from ..ports.store import MessagesRepository, SummariesRepository


def compact(
    key: ContactKey,
    messages: MessagesRepository,
    summaries: SummariesRepository,
    now: datetime,
    budget: int,
) -> bool:
    window = messages.window(key, 100)
    plan = plan_window(
        window,
        token_budget=budget,
        estimate_tokens=lambda item: len(item.text.split()),
    )
    if not plan.compacted:
        return False
    text = "\n".join(f"{item.direction}: {item.text}" for item in plan.compacted)
    summaries.save(key, text, plan.compacted[-1].id, now)
    return True
