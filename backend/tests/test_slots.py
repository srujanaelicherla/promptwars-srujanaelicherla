"""Slot-key overlap math. Independent of Firestore."""

from datetime import datetime, timedelta, timezone

from app.slots import slot_keys

START = datetime(2026, 12, 20, 10, 0, tzinfo=timezone.utc)


def test_partial_overlap_shares_a_key() -> None:
    first = slot_keys("eq-workbench", START, START + timedelta(hours=2))
    second = slot_keys("eq-workbench", START + timedelta(hours=1), START + timedelta(hours=3))
    assert set(first) & set(second)


def test_adjacent_slots_do_not_share_keys() -> None:
    first = slot_keys("eq-workbench", START, START + timedelta(hours=2))
    second = slot_keys("eq-workbench", START + timedelta(hours=2), START + timedelta(hours=4))
    assert set(first).isdisjoint(second)


def test_different_equipment_keys_differ() -> None:
    first = slot_keys("eq-workbench", START, START + timedelta(hours=1))
    second = slot_keys("eq-oscilloscope", START, START + timedelta(hours=1))
    assert set(first).isdisjoint(second)
