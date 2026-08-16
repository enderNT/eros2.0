"""Pure token-budget memory policy tests (SPEC §9)."""

from agente.domain.memory import plan_window


def test_a_window_within_budget_stays_verbatim():
    plan = plan_window(("one", "two"), token_budget=2, estimate_tokens=lambda _: 1)

    assert plan.verbatim == ("one", "two")
    assert plan.compacted == ()
    assert plan.overlap == ()
    assert plan.needs_compaction is False


def test_long_turns_compact_while_ten_one_word_turns_do_not():
    short_turns = ("ok",) * 10
    long_turns = ("a much longer message",) * 10

    def estimate(turn: str) -> int:
        return len(turn.split())

    short_plan = plan_window(short_turns, token_budget=10, estimate_tokens=estimate)
    long_plan = plan_window(long_turns, token_budget=10, estimate_tokens=estimate)

    assert short_plan.needs_compaction is False
    assert long_plan.needs_compaction is True


def test_compaction_keeps_the_requested_overlap_at_the_window_head():
    plan = plan_window(
        ("oldest", "older", "recent", "newest"),
        token_budget=2,
        estimate_tokens=lambda _: 1,
        overlap_turns=1,
    )

    assert plan.compacted == ("oldest", "older")
    assert plan.overlap == ("older",)
    assert plan.verbatim == ("older", "recent", "newest")


def test_an_oversized_newest_turn_remains_visible():
    plan = plan_window(
        ("old", "very long newest"),
        token_budget=1,
        estimate_tokens=lambda turn: 3 if turn.startswith("very") else 1,
    )

    assert plan.compacted == ("old",)
    assert plan.verbatim == ("old", "very long newest")
