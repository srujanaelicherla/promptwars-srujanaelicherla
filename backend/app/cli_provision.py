"""Provision faculty or admin from a trusted backend process.

Usage (emulator or ADC):

    python -m app.cli_provision --confirm SYNTHETIC-DEV-ONLY \\
        --user-id USER --role faculty --department dept-physics

There is no public self-service for this. POST /admin/users/{id}/role is
admin-authenticated and updates Firestore plus custom claims.
"""

from __future__ import annotations

import argparse
import os
import sys

from app.config import load_settings
from app.firebase_app import init_firebase
from app.models import Role, User

CONFIRM = "SYNTHETIC-DEV-ONLY"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assign an elevated LabLink role.")
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", required=True, choices=[item.value for item in Role])
    parser.add_argument("--department", required=True)
    args = parser.parse_args(argv)
    if args.confirm != CONFIRM:
        print("Refusing without SYNTHETIC-DEV-ONLY confirmation.", file=sys.stderr)
        return 2
    if not os.environ.get("FIRESTORE_EMULATOR_HOST") and os.environ.get("LABLINK_ALLOW_REMOTE_SEED") != "1":
        print("Remote provision blocked. Use the emulator or LABLINK_ALLOW_REMOTE_SEED=1.", file=sys.stderr)
        return 2
    settings = load_settings()
    if not init_firebase(settings):
        print("Firebase Admin is not configured.", file=sys.stderr)
        return 2
    from firebase_admin import auth
    from google.cloud import firestore

    role = Role(args.role)
    client = firestore.Client(project=settings.firebase_project_id or "demo-lablink")
    ref = client.collection("users").document(args.user_id)
    snap = ref.get()
    if not snap.exists:
        print("User document does not exist. Bootstrap the account first.", file=sys.stderr)
        return 2
    user = User(id=args.user_id, role=role, department_id=args.department)
    payload = user.model_dump(mode="json")
    payload["synthetic"] = False
    ref.set(payload, merge=True)
    auth.set_custom_user_claims(args.user_id, {"role": role.value, "department_id": args.department})
    print(f"Updated {args.user_id} to {role.value} in {args.department}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
