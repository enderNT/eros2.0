"""Domain exception types.

Adapters translate their library errors into these at the boundary
(SPEC §2.5); services never see a driver-level database or HTTP error.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every domain error."""


class StoreError(DomainError):
    """Persistence failed. The underlying sqlite error is chained as cause."""
