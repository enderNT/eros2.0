"""Crisis verdict and escalation rules (SPEC §7).

The pre-gate classifies the merged inbound text into a strict enum; these
rules say what each verdict means for the pipeline. Parsing the verdict out
of the model output and the fail-closed fallback live in the service layer.
"""

from __future__ import annotations

from enum import StrEnum


class CrisisVerdict(StrEnum):
    NONE = "none"
    POSSIBLE = "possible"
    ACUTE = "acute"


def agent_runs(verdict: CrisisVerdict) -> bool:
    """The agent loop runs unless the verdict is acute."""
    return verdict is not CrisisVerdict.ACUTE


def adds_crisis_directives(verdict: CrisisVerdict) -> bool:
    """`possible` appends the playbook crisis directives as a fourth system block."""
    return verdict is CrisisVerdict.POSSIBLE


def escalates(verdict: CrisisVerdict) -> bool:
    """`acute`: crisis message verbatim, mute the contact, urgent audit entry."""
    return verdict is CrisisVerdict.ACUTE
