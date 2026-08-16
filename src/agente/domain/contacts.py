"""Contact identity.

`ContactKey` is the stable unit of state (SPEC §1): a person identified by
`(phone_number_id, contact_phone)` — never by Kapso's 24h conversation id,
which dies and respawns daily. Phone normalization to E.164 and log masking
land here in T3.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ContactKey:
    phone_number_id: str
    contact_phone: str
