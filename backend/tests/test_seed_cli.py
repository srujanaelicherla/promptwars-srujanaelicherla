from app.cli_seed import CONFIRM, main, should_write


def test_seed_refuses_without_confirmation() -> None:
    assert main(["--confirm", "nope"]) == 2


def test_seed_refuses_without_emulator_when_required(monkeypatch) -> None:
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    assert main(["--confirm", CONFIRM, "--emulator-only"]) == 2


def test_seed_write_policy_skips_bookings_and_user_created_records() -> None:
    assert should_write("equipment", None) is True
    assert should_write("equipment", {"synthetic": True}) is True
    assert should_write("equipment", {"synthetic": False, "name": "user asset"}) is False
    assert should_write("bookings", {"synthetic": True}) is False
    assert should_write("approvals", None) is True
    assert should_write("approvals", {"synthetic": True}) is False
    assert should_write("users", {"role": "faculty"}) is False
    assert should_write("users", {"synthetic": True}) is True
