"""Contact identity.

`ContactKey` is the stable unit of state (SPEC §1): a person identified by
`(phone_number_id, contact_phone)` — never by Kapso's 24h conversation id,
which dies and respawns daily. Phones are normalized to E.164 at
construction so the same person cannot fork two keys, and masked as
hash + last two digits wherever they reach a log (SPEC §11).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .errors import InvalidPhoneError

# Formatting characters tolerated while cleaning a phone number; anything
# else means the input is not a phone number at all.
_SEPARATORS = frozenset(" -.()/")

# E.164 bounds, country code included.
_MIN_DIGITS = 8
_MAX_DIGITS = 15


def normalize_phone(raw: str) -> str:
    """Return the E.164 form of `raw`: '+' followed by 8-15 digits.

    Strips formatting characters and the `00` international prefix, and
    drops the legacy `1` Mexico inserted between country code and number
    (`+52 1 55 ...` -> `+52 55 ...`). The input must already carry a
    country code — WhatsApp always delivers one; this cleans formatting,
    it does not guess country codes.
    """
    text = raw.strip()
    if text.startswith("+"):
        text = text[1:]
    if text.startswith("00"):
        text = text[2:]
    digits: list[str] = []
    for char in text:
        if char.isdigit():
            digits.append(char)
        elif char not in _SEPARATORS:
            raise InvalidPhoneError(f"not a phone number: {raw!r}")
    if len(digits) == _MAX_DIGITS - 2 and "".join(digits[:3]) == "521":
        digits[2:3] = []
    if not _MIN_DIGITS <= len(digits) <= _MAX_DIGITS:
        raise InvalidPhoneError(f"not a phone number: {raw!r}")
    return "+" + "".join(digits)


def mask_phone(raw: object) -> str:
    """Stable hash of the number plus its last two digits, and nothing else."""
    digits = "".join(char for char in str(raw) if char.isdigit())
    digest = hashlib.sha256(digits.encode("utf-8")).hexdigest()[:8]
    return f"{digest}:{digits[-2:]}"


@dataclass(frozen=True, slots=True)
class ContactKey:
    phone_number_id: str
    contact_phone: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "phone_number_id", self.phone_number_id.strip())
        object.__setattr__(self, "contact_phone", normalize_phone(self.contact_phone))
