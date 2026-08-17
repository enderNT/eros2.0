"""Fail-closed crisis classification seam."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..domain.crisis import CrisisVerdict

Classifier = Callable[[str], Awaitable[CrisisVerdict]]


async def check(classifier: Classifier | None, text: str) -> CrisisVerdict:
    if classifier is None:
        return CrisisVerdict.NONE
    try:
        return await classifier(text)
    except (RuntimeError, ValueError):
        return CrisisVerdict.POSSIBLE
