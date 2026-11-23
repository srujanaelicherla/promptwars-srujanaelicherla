"""Discrete slot reservations for overlap-safe bookings.

Invariant
---------
A booking occupies every 15-minute half-open slot in [start, end).
Adjacent bookings are allowed: a booking that ends at T does not take the
slot that starts at T. Any partial overlap shares at least one slot key.

Contention
----------
Each slot is a document id `slot_locks/{equipment_id}_{YYYYMMDDTHHMMSSZ}`.
A transaction must read every key in the range before writing the booking
and the lock documents. Query-then-write of overlapping booking rows is not
the contention point; these lock documents are.

Capacity is one active booking per slot. Memory tests use the same keys
under a process lock. Firestore uses a transaction with bounded retries.
Distributed safety is verified only by emulator tests.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

SLOT = timedelta(minutes=15)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("slot bounds must be timezone-aware")
    return value.astimezone(timezone.utc)


def floor_slot(value: datetime) -> datetime:
    instant = _as_utc(value)
    discard = instant.minute % 15
    return instant.replace(minute=instant.minute - discard, second=0, microsecond=0)


def slot_keys(equipment_id: str, start: datetime, end: datetime) -> tuple[str, ...]:
    """Return ordered lock ids covering [start, end)."""

    cursor = floor_slot(start)
    finish = _as_utc(end)
    keys: list[str] = []
    while cursor < finish:
        keys.append(f"{equipment_id}_{cursor.strftime('%Y%m%dT%H%M%SZ')}")
        cursor += SLOT
    return tuple(keys)
