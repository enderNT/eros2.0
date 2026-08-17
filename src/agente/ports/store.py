"""Repository protocols for the SQLite store (SPEC §10).

Services depend on these protocols alone; the implementations live in
`adapters/store/` and share one connection. Times cross the boundary as
aware datetimes — the store persists them as UTC ISO-8601 strings and
services never see the string form.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..domain.contacts import ContactKey

Direction = Literal["inbound", "outbound"]
ProfileKind = Literal["patient", "prospect"]


@dataclass(frozen=True, slots=True)
class ContactRow:
    key: ContactKey
    display_name: str | None
    timezone: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Profile:
    key: ContactKey
    name: str | None
    email: str | None
    kind: ProfileKind
    timezone: str | None
    appointment_count: int
    last_appointment_utc: datetime | None
    next_appointment_utc: datetime | None
    handoff_state: str
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MessageRow:
    id: int
    key: ContactKey
    direction: Direction
    kapso_message_id: str
    text: str
    created_at: datetime
    sent_by_us: bool


@dataclass(frozen=True, slots=True)
class SummaryRow:
    key: ContactKey
    text: str
    watermark_message_id: int
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class MuteState:
    muted_at: datetime
    muted_until: datetime | None


@dataclass(frozen=True, slots=True)
class AuditEntry:
    created_at: datetime
    actor: str
    action: str
    reason: str
    phone_number_id: str | None = None
    contact_phone: str | None = None
    urgent: bool = False


@dataclass(frozen=True, slots=True)
class AppointmentRow:
    id: int
    key: ContactKey
    calendly_event_id: str
    slot_utc: datetime
    status: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BookingTokenRow:
    """What a Calendly `utm_content` value resolves back to."""

    token: str
    key: ContactKey
    slot_utc: datetime
    created_at: datetime


@dataclass(frozen=True, slots=True)
class OutboxRow:
    """One pending outbound follow-up, consumed before it is sent."""

    id: int
    key: ContactKey
    text: str
    due_at: datetime
    booking_token: str | None
    slot_utc: datetime | None


@dataclass(frozen=True, slots=True)
class LlmTraceRow:
    turn_id: str | None
    model: str
    tokens_in: int
    tokens_out: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int
    stop_reason: str | None
    tools_called: tuple[str, ...]
    created_at: datetime
    id: int | None = None


class ContactsRepository(Protocol):
    def ensure_contact(
        self,
        key: ContactKey,
        now: datetime,
        *,
        display_name: str | None = None,
        timezone: str | None = None,
    ) -> None: ...

    def get_contact(self, key: ContactKey) -> ContactRow | None: ...

    def get_profile(self, key: ContactKey) -> Profile | None: ...

    def save_profile(self, profile: Profile) -> None: ...


class MessagesRepository(Protocol):
    def add_inbound(
        self, key: ContactKey, kapso_message_id: str, text: str, created_at: datetime
    ) -> bool: ...

    def add_outbound(
        self,
        key: ContactKey,
        kapso_message_id: str,
        text: str,
        created_at: datetime,
        *,
        sent_by_us: bool = True,
    ) -> bool: ...

    def window(self, key: ContactKey, limit: int) -> list[MessageRow]: ...


class SummariesRepository(Protocol):
    def get(self, key: ContactKey) -> SummaryRow | None: ...

    def save(
        self, key: ContactKey, text: str, watermark_message_id: int, now: datetime
    ) -> None: ...


class MutesRepository(Protocol):
    def is_bot_muted(self, key: ContactKey, now: datetime) -> bool: ...

    def set_mute(
        self,
        key: ContactKey,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
        urgent: bool = False,
    ) -> None: ...

    def clear_mute(self, key: ContactKey, now: datetime, *, actor: str, reason: str) -> None: ...

    def set_number_mute(
        self,
        phone_number_id: str,
        muted: bool,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
    ) -> None: ...

    def set_global(
        self,
        muted: bool,
        now: datetime,
        *,
        actor: str,
        reason: str,
        until: datetime | None = None,
    ) -> None: ...

    def contact_mute(self, key: ContactKey) -> MuteState | None: ...

    def number_mute(self, phone_number_id: str) -> MuteState | None: ...

    def global_mute(self) -> MuteState | None: ...

    def audit_trail(self, limit: int = 100) -> list[AuditEntry]: ...


class AppointmentsRepository(Protocol):
    def add(
        self, key: ContactKey, calendly_event_id: str, slot_utc: datetime, now: datetime
    ) -> int: ...

    def for_contact(self, key: ContactKey) -> list[AppointmentRow]: ...

    def find(self, calendly_event_id: str) -> AppointmentRow | None: ...

    def update_status(self, calendly_event_id: str, status: str, now: datetime) -> bool: ...


class BookingTokensRepository(Protocol):
    def issue(self, token: str, key: ContactKey, slot_utc: datetime, now: datetime) -> None: ...

    def resolve(self, token: str) -> BookingTokenRow | None: ...


class OutboxRepository(Protocol):
    def schedule_booking_followup(
        self,
        key: ContactKey,
        booking_token: str,
        slot_utc: datetime,
        text: str,
        due_at: datetime,
    ) -> None: ...

    def due(self, now: datetime, limit: int = 20) -> list[OutboxRow]: ...

    def consume(self, row_id: int, now: datetime) -> bool: ...

    def cancel_for_contact(self, key: ContactKey) -> None: ...

    def cancel_for_token(self, booking_token: str) -> None: ...


class PurgeRepository(Protocol):
    def contact(
        self, key: ContactKey, now: datetime, *, actor: str, reason: str
    ) -> dict[str, int]: ...


class TracesRepository(Protocol):
    def add(self, trace: LlmTraceRow) -> int: ...

    def recent(self, limit: int = 50) -> list[LlmTraceRow]: ...
