"""Domain exception types.

Adapters translate their library errors into these at the boundary
(SPEC §2.5); services never see a driver-level database or HTTP error.
"""

from __future__ import annotations


class DomainError(Exception):
    """Base class for every domain error."""


class StoreError(DomainError):
    """Persistence failed. The underlying sqlite error is chained as cause."""


class InvalidPhoneError(DomainError, ValueError):
    """A phone number could not be normalized to E.164."""


class KapsoError(DomainError):
    """Kapso channel (HTTP or webhook) failed. The underlying error is chained."""


class ModelError(DomainError):
    """Language model adapter failed."""


class CalendlyError(DomainError):
    """Calendly adapter failed."""
