"""Window policy: what stays verbatim, what compacts, where the overlap sits (SPEC §9).

The trigger is a token budget, not a message count: ten one-word messages
and ten paragraphs are not the same context. Token estimation is injected
as a callable, so this module stays pure — the estimator belongs to whoever
talks to the model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class WindowPlan(Generic[T]):
    """One compaction decision over a window ordered oldest first.

    - `verbatim`: the window sent to the model, oldest first, with the
      overlap at its head.
    - `compacted`: the turns folded into the rolling summary this time,
      oldest first. Empty when the window fits the budget.
    - `overlap`: the last turns of `compacted`, also kept visible at the
      head of `verbatim` so the summary and the window connect.
    """

    verbatim: tuple[T, ...]
    compacted: tuple[T, ...]
    overlap: tuple[T, ...]

    @property
    def needs_compaction(self) -> bool:
        return bool(self.compacted)


def plan_window(
    turns: Sequence[T],
    *,
    token_budget: int,
    estimate_tokens: Callable[[T], int],
    overlap_turns: int = 1,
) -> WindowPlan[T]:
    """Split `turns` (oldest first) against `token_budget`.

    Keeps the newest turns verbatim while they fit the budget — always at
    least the newest one, even if it alone exceeds the budget, since a turn
    cannot be split — and compacts the rest. The last `overlap_turns`
    compacted turns stay in both places for continuity.
    """
    turns = tuple(turns)
    if not turns:
        return WindowPlan((), (), ())
    sizes = [estimate_tokens(turn) for turn in turns]
    if sum(sizes) <= token_budget:
        return WindowPlan(turns, (), ())
    kept_count, kept_tokens = 0, 0
    for size in reversed(sizes):
        if kept_count and kept_tokens + size > token_budget:
            break
        kept_count += 1
        kept_tokens += size
    compacted = turns[:-kept_count]
    overlap = compacted[-overlap_turns:] if overlap_turns > 0 else ()
    return WindowPlan(overlap + turns[-kept_count:], compacted, overlap)
