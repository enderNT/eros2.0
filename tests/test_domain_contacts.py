"""Phone normalization to E.164, contact identity and log masking (SPEC §1, §11)."""

import pytest

from agente.domain.contacts import ContactKey, mask_phone, normalize_phone
from agente.domain.errors import DomainError, InvalidPhoneError


def test_normalizes_formatted_numbers_to_e164():
    assert normalize_phone("+52 55 1234 5678") == "+525512345678"
    assert normalize_phone("+52-55-1234-5678") == "+525512345678"
    assert normalize_phone("(55) 1234 5678 / 52") == "+551234567852"
    assert normalize_phone("+1 205-294-3796") == "+12052943796"


def test_strips_the_double_zero_international_prefix():
    assert normalize_phone("0052 55 1234 5678") == "+525512345678"


def test_drops_the_legacy_mexican_mobile_one():
    assert normalize_phone("5215512345678") == "+525512345678"
    assert normalize_phone("+52 1 55 1234 5678") == "+525512345678"
    # Thirteen digits that are not the legacy form stay untouched.
    assert normalize_phone("+1234567890123") == "+1234567890123"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "1234567",  # too short for E.164
        "1234567890123456",  # too long for E.164
        "55abc12345678",
        "++525512345678",
    ],
)
def test_rejects_input_that_is_not_a_phone(raw):
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_invalid_phone_is_a_value_error_and_a_domain_error():
    assert issubclass(InvalidPhoneError, ValueError)
    assert issubclass(InvalidPhoneError, DomainError)


def test_contact_key_normalizes_the_phone_at_construction():
    key = ContactKey("1087343774471931", "+52 55 1234 5678")
    assert key.contact_phone == "+525512345678"


def test_contact_key_is_identity_under_formatting():
    key_a = ContactKey("1087343774471931", "+52 55 1234 5678")
    key_b = ContactKey("1087343774471931", "00525512345678")
    assert key_a == key_b
    assert hash(key_a) == hash(key_b)


def test_contact_key_rejects_a_non_phone():
    with pytest.raises(InvalidPhoneError):
        ContactKey("1087343774471931", "not-a-phone")


def test_mask_phone_keeps_only_hash_and_last_two_digits():
    masked = mask_phone("+1 205-294-3796")
    assert masked == mask_phone("+12052943796")
    assert masked.endswith(":96")
    assert "2052943796" not in masked


def test_mask_phone_differs_per_number():
    assert mask_phone("+525512345678") != mask_phone("+525587654321")
