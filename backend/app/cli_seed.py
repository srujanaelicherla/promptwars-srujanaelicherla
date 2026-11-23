"""Idempotent synthetic Firestore seed. Never auto-runs. Never overwrites live users."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime

from app.firebase_app import init_firebase
from app.config import load_settings
from app.seed import load_seed

CONFIRM = "SYNTHETIC-DEV-ONLY"
_IMMUTABLE = frozenset(
    {"bookings", "access_requests", "approvals", "allocation_decisions"}
)


def should_write(collection: str, existing: dict[str, object] | None) -> bool:
    """Create missing docs. Never overwrite bookings, approvals, or user-created records."""

    if existing is None:
        return True
    if collection in _IMMUTABLE:
        return False
    return existing.get("synthetic") is True


def _dump(model: object) -> dict[str, object]:
    if hasattr(model, "model_dump_json"):
        payload = json.loads(model.model_dump_json())  # type: ignore[attr-defined]
    else:
        raise TypeError("unsupported record")
    payload["synthetic"] = True
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed synthetic LabLink records into Firestore.")
    parser.add_argument("--confirm", required=True, help=f"Must be {CONFIRM}")
    parser.add_argument("--emulator-only", action="store_true", help="Refuse unless FIRESTORE_EMULATOR_HOST is set.")
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print("Refusing to seed without explicit SYNTHETIC-DEV-ONLY confirmation.", file=sys.stderr)
        return 2
    if args.emulator_only and not os.environ.get("FIRESTORE_EMULATOR_HOST"):
        print("FIRESTORE_EMULATOR_HOST is not set.", file=sys.stderr)
        return 2
    if not os.environ.get("FIRESTORE_EMULATOR_HOST") and os.environ.get("LABLINK_ALLOW_REMOTE_SEED") != "1":
        print("Remote seed blocked. Use the emulator or set LABLINK_ALLOW_REMOTE_SEED=1.", file=sys.stderr)
        return 2
    settings = load_settings()
    if not init_firebase(settings):
        print("Firebase Admin is not configured.", file=sys.stderr)
        return 2
    from google.cloud import firestore

    client = firestore.Client(project=settings.firebase_project_id or "demo-lablink")
    catalog = load_seed()
    planned: list[tuple[str, str, dict[str, object]]] = []
    for name, records in (
        ("departments", catalog.departments),
        ("labs", catalog.labs),
        ("equipment", catalog.equipment),
        ("projects", catalog.projects),
        ("bookings", catalog.bookings),
        ("access_requests", catalog.access_requests),
        ("approvals", catalog.approvals),
        ("allocation_decisions", catalog.allocation_decisions),
        ("users", catalog.users),
    ):
        for item in records:
            planned.append((name, item.id, _dump(item)))
    batch = client.batch()
    count = 0
    for collection, doc_id, payload in planned:
        snap = client.collection(collection).document(doc_id).get()
        existing = snap.to_dict() if snap.exists else None
        if not should_write(collection, existing):
            continue
        payload["updated_at"] = datetime.now().isoformat()
        batch.set(client.collection(collection).document(doc_id), payload, merge=True)
        count += 1
        if count % 400 == 0:
            batch.commit()
            batch = client.batch()
    if count:
        batch.commit()
    print(f"Seeded {count} synthetic documents.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
