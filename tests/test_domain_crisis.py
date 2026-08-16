"""Crisis verdict type and escalation rules (SPEC §7)."""

import pytest

from agente.domain.crisis import CrisisVerdict, adds_crisis_directives, agent_runs, escalates


def test_the_verdict_is_a_strict_enum_of_three_values():
    assert [verdict.value for verdict in CrisisVerdict] == ["none", "possible", "acute"]
    assert CrisisVerdict("none") is CrisisVerdict.NONE


def test_unknown_verdict_values_are_rejected():
    with pytest.raises(ValueError):
        CrisisVerdict("sí")


def test_the_agent_runs_unless_the_verdict_is_acute():
    assert agent_runs(CrisisVerdict.NONE) is True
    assert agent_runs(CrisisVerdict.POSSIBLE) is True
    assert agent_runs(CrisisVerdict.ACUTE) is False


def test_only_possible_appends_the_crisis_directives_block():
    assert adds_crisis_directives(CrisisVerdict.NONE) is False
    assert adds_crisis_directives(CrisisVerdict.POSSIBLE) is True
    assert adds_crisis_directives(CrisisVerdict.ACUTE) is False


def test_only_acute_escalates():
    assert escalates(CrisisVerdict.NONE) is False
    assert escalates(CrisisVerdict.POSSIBLE) is False
    assert escalates(CrisisVerdict.ACUTE) is True
