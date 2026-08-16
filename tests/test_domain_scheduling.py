"""Slot labels, part-of-day buckets, sampling and bookability (SPEC §6).

Frozen clocks throughout (SPEC §2.6), with explicit DST transitions of the
clinic timezone — America/Mexico_City's last ones happened in 2022, it has
been fixed at UTC-6 since — and of a still-DST zone, since the clinic
timezone is configuration.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from agente.domain.scheduling import (
    PartOfDay,
    Slot,
    is_bookable,
    part_of_day,
    sample_slots,
    slot_label,
)

CDMX = ZoneInfo("America/Mexico_City")
NEW_YORK = ZoneInfo("America/New_York")
NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)  # Sunday, 06:00 in Mexico City
BUFFER = timedelta(minutes=30)


def utc(year, month, day, hour=0, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def slot(start, hours=0, minutes=30):
    return Slot(start, start + timedelta(hours=hours, minutes=minutes))


def test_slots_must_be_timezone_aware_and_ordered():
    with pytest.raises(ValueError):
        Slot(datetime(2026, 8, 19, 15, 30), utc(2026, 8, 19, 16))
    with pytest.raises(ValueError):
        Slot(utc(2026, 8, 19, 16), utc(2026, 8, 19, 15))


def test_label_is_local_day_and_time_never_utc():
    # 15:30 UTC is 09:30 in Mexico City (fixed UTC-6 since 2023).
    label = slot_label(slot(utc(2026, 8, 19, 15, 30)), CDMX, NOW)
    assert label == "miércoles 19 de agosto, 9:30 a. m."


def test_label_says_hoy_and_mañana_on_the_local_date():
    assert slot_label(slot(utc(2026, 8, 16, 20)), CDMX, NOW) == "hoy, 2:00 p. m."
    assert slot_label(slot(utc(2026, 8, 17, 16)), CDMX, NOW) == "mañana, 10:00 a. m."


def test_hoy_and_mañana_follow_the_local_midnight_not_the_utc_one():
    # Sunday 23:00 local; the slot is Monday 01:00 UTC but still Sunday local.
    now = utc(2026, 8, 16, 23)  # local 17:00 Sunday
    late_local = slot(utc(2026, 8, 17, 1))  # local 19:00 Sunday
    assert slot_label(late_local, CDMX, now) == "hoy, 7:00 p. m."
    # Local Sunday 20:00 (Monday 02:00 UTC); a Monday-morning slot is mañana.
    evening = utc(2026, 8, 17, 2)
    assert slot_label(slot(utc(2026, 8, 17, 16)), CDMX, evening) == "mañana, 10:00 a. m."


def test_noon_and_midnight_render_in_twelve_hour_form():
    assert slot_label(slot(utc(2026, 8, 19, 18)), CDMX, NOW) == (
        "miércoles 19 de agosto, 12:00 p. m."
    )
    assert slot_label(slot(utc(2026, 8, 19, 6)), CDMX, NOW) == (
        "miércoles 19 de agosto, 12:00 a. m."
    )


def test_dst_fall_back_labels_both_sides_of_the_last_mexican_transition():
    # 2022-10-30: 01:59 CDT (-05:00) was followed by 01:00 CST (-06:00).
    before = slot(utc(2022, 10, 30, 6, 30)).start_utc.astimezone(CDMX)
    after = slot(utc(2022, 10, 30, 7, 30)).start_utc.astimezone(CDMX)
    assert before.utcoffset() == timedelta(hours=-5)
    assert after.utcoffset() == timedelta(hours=-6)
    assert before.hour == 1 and after.hour == 1
    assert slot_label(slot(utc(2022, 10, 30, 6, 30)), CDMX, NOW) == (
        "domingo 30 de octubre, 1:30 a. m."
    )
    assert slot_label(slot(utc(2022, 10, 30, 7, 30)), CDMX, NOW) == (
        "domingo 30 de octubre, 1:30 a. m."
    )
    assert part_of_day(before.hour) is PartOfDay.EVENING


def test_dst_spring_forward_skips_the_nonexistent_local_hour():
    # 2022-04-03: Mexico City jumped 01:59 CST (-06:00) to 03:00 CDT (-05:00).
    before = slot(utc(2022, 4, 3, 7, 30)).start_utc.astimezone(CDMX)
    after = slot(utc(2022, 4, 3, 8, 30)).start_utc.astimezone(CDMX)
    assert (before.hour, before.utcoffset()) == (1, timedelta(hours=-6))
    assert (after.hour, after.utcoffset()) == (3, timedelta(hours=-5))
    assert slot_label(slot(utc(2022, 4, 3, 8, 30)), CDMX, NOW) == "domingo 3 de abril, 3:30 a. m."


def test_mexico_city_has_had_no_dst_since_2022():
    january = slot(utc(2026, 1, 15, 18)).start_utc.astimezone(CDMX)
    august = slot(utc(2026, 8, 19, 18)).start_utc.astimezone(CDMX)
    assert january.utcoffset() == august.utcoffset() == timedelta(hours=-6)
    assert slot_label(slot(utc(2026, 1, 15, 18)), CDMX, NOW) == "jueves 15 de enero, 12:00 p. m."


def test_the_clinic_timezone_is_configuration_not_a_constant():
    same_slot = slot(utc(2026, 8, 19, 15, 30))
    assert slot_label(same_slot, NEW_YORK, NOW) == "miércoles 19 de agosto, 11:30 a. m."


def test_a_live_dst_transition_in_a_zone_that_still_shifts():
    # America/New_York springs forward on 2026-03-08: 01:59 EST -> 03:00 EDT.
    before = slot(utc(2026, 3, 8, 6, 59)).start_utc.astimezone(NEW_YORK)
    after = slot(utc(2026, 3, 8, 7, 30)).start_utc.astimezone(NEW_YORK)
    assert (before.hour, before.utcoffset()) == (1, timedelta(hours=-5))
    assert (after.hour, after.utcoffset()) == (3, timedelta(hours=-4))
    assert slot_label(slot(utc(2026, 3, 8, 7, 30)), NEW_YORK, NOW) == (
        "domingo 8 de marzo, 3:30 a. m."
    )


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (0, PartOfDay.EVENING),
        (4, PartOfDay.EVENING),
        (5, PartOfDay.MORNING),
        (11, PartOfDay.MORNING),
        (12, PartOfDay.AFTERNOON),
        (18, PartOfDay.AFTERNOON),
        (19, PartOfDay.EVENING),
        (23, PartOfDay.EVENING),
    ],
)
def test_part_of_day_buckets(hour, expected):
    assert part_of_day(hour) is expected


def test_bookable_rejects_past_slots_and_slots_inside_the_buffer():
    assert is_bookable(slot(utc(2026, 8, 16, 13)), NOW, BUFFER) is True
    assert is_bookable(slot(utc(2026, 8, 16, 12, 29)), NOW, BUFFER) is False
    assert is_bookable(slot(utc(2026, 8, 16, 11)), NOW, BUFFER) is False


def test_a_slot_exactly_at_the_buffer_edge_is_bookable():
    assert is_bookable(slot(utc(2026, 8, 16, 12, 30)), NOW, BUFFER) is True
    one_second_less = Slot(utc(2026, 8, 16, 12, 30), utc(2026, 8, 16, 13))
    assert is_bookable(one_second_less, NOW + timedelta(seconds=1), BUFFER) is False


def test_bookable_rejects_a_naive_clock():
    with pytest.raises(ValueError):
        is_bookable(slot(utc(2026, 8, 16, 13)), datetime(2026, 8, 16, 12), BUFFER)


def local_slot(day, hour, minute=0):
    start = datetime(2026, 8, day, hour, minute, tzinfo=CDMX)
    return Slot(start.astimezone(UTC), start.astimezone(UTC) + timedelta(minutes=30))


def week_of_slots():
    # Five days x three morning, three afternoon and one evening local slot.
    slots = []
    for day in range(17, 22):
        for hour, minute in [(9, 0), (9, 30), (10, 0), (13, 0), (13, 30), (14, 0), (20, 0)]:
            slots.append(local_slot(day, hour, minute))
    return slots


def test_sampling_spreads_across_days_and_caps_parts_of_day():
    picked = sample_slots(week_of_slots(), CDMX)
    assert len(picked) == 12
    assert [s.start_utc for s in picked] == sorted(s.start_utc for s in picked)
    days = {s.start_utc.astimezone(CDMX).date().day for s in picked}
    assert days == {17, 18, 19}  # day 20-21 never needed to reach the cap
    per_bucket: dict[tuple, int] = {}
    for s in picked:
        local = s.start_utc.astimezone(CDMX)
        key = (local.date(), part_of_day(local.hour))
        per_bucket[key] = per_bucket.get(key, 0) + 1
    assert max(per_bucket.values()) <= 2


def test_sampling_is_deterministic_and_input_order_does_not_matter():
    forward = sample_slots(week_of_slots(), CDMX)
    backward = sample_slots(list(reversed(week_of_slots())), CDMX)
    assert forward == backward


def test_sampling_returns_everything_when_under_the_cap():
    sparse = [local_slot(17, 9), local_slot(18, 13), local_slot(19, 20)]
    assert sample_slots(sparse, CDMX) == sorted(sparse, key=lambda s: s.start_utc)


def test_sampling_respects_the_per_part_of_day_limit():
    five_mornings = [local_slot(17, 9, minute) for minute in range(5)]
    assert len(sample_slots(five_mornings, CDMX)) == 2


def test_sampling_of_no_slots_is_empty():
    assert sample_slots([], CDMX) == []
