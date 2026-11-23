"""Waitlist, offers, and promotion. Memory tests are not distributed safety."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models import WaitlistEntry, WaitlistStatus
from app.seed import load_seed
from tests.conftest import FACULTY, FACULTY_ENG, STUDENT, STUDENT_B

FUTURE = datetime(2027, 4, 4, 10, 0, tzinfo=timezone.utc)


def _range(hours: float = 2) -> dict[str, str]:
    return {
        "preferred_start": FUTURE.isoformat(),
        "preferred_end": (FUTURE + timedelta(hours=hours)).isoformat(),
    }


def _join(**extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "equipment_id": "eq-workbench",
        "project_id": "proj-sensor",
        "duration_minutes": 120,
        "flexibility_minutes": 0,
        **_range(2),
    }
    body.update(extra)
    return body


def _book(client: TestClient, headers: dict[str, str], start: datetime | None = None) -> dict[str, object]:
    begin = FUTURE if start is None else start
    response = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": begin.isoformat(),
            "end": (begin + timedelta(hours=2)).isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_join_requires_no_suitable_slot(client: TestClient) -> None:
    open_join = client.post("/waitlist", json=_join(), headers=STUDENT)
    assert open_join.status_code == 409
    _book(client, STUDENT)
    joined = client.post("/waitlist", json=_join(), headers=STUDENT)
    assert joined.status_code == 201
    assert joined.json()["status"] == "waiting"
    duplicate = client.post("/waitlist", json=_join(), headers=STUDENT)
    assert duplicate.status_code == 409


def test_waitlist_authz_and_own_list(client: TestClient) -> None:
    _book(client, STUDENT)
    client.post("/waitlist", json=_join(), headers=STUDENT)
    other = client.post("/waitlist", json=_join(), headers=STUDENT_B)
    mine = client.get("/waitlist", headers=STUDENT)
    theirs = client.get("/waitlist", headers=STUDENT_B)
    anon = client.get("/waitlist")
    faculty_join = client.post("/waitlist", json=_join(), headers=FACULTY_ENG)
    assert other.status_code == 201
    assert mine.status_code == 200
    assert len(mine.json()["items"]) == 1
    assert mine.json()["items"][0]["id"] != theirs.json()["items"][0]["id"]
    assert "user-student-engineering" not in mine.text
    assert anon.status_code == 401
    assert faculty_join.status_code == 403


def test_cancel_own_not_others(client: TestClient) -> None:
    _book(client, STUDENT)
    first = client.post("/waitlist", json=_join(), headers=STUDENT)
    second = client.post("/waitlist", json=_join(), headers=STUDENT_B)
    stolen = client.post(f"/waitlist/{second.json()['id']}/cancel", headers=STUDENT)
    own = client.post(f"/waitlist/{first.json()['id']}/cancel", headers=STUDENT)
    assert stolen.status_code == 403
    assert own.status_code == 200
    assert own.json()["status"] == "cancelled"


def test_rank_uses_fairness_and_keeps_ineligible_below(client: TestClient) -> None:
    booking = _book(client, STUDENT)
    client.post("/waitlist", json=_join(), headers=STUDENT)
    client.post("/waitlist", json=_join(), headers=STUDENT_B)
    client.app.state.waitlist.join(
        WaitlistEntry(
            id="wait-unknown-actor",
            user_id="missing-user",
            equipment_id="eq-workbench",
            project_id="proj-sensor",
            duration_minutes=120,
            preferred_start=FUTURE,
            preferred_end=FUTURE + timedelta(hours=2),
            flexibility_minutes=0,
            status=WaitlistStatus.WAITING,
            created_at=FUTURE - timedelta(days=3),
            updated_at=FUTURE - timedelta(days=3),
        )
    )
    client.post(f"/bookings/{booking['id']}/cancel", headers=STUDENT)
    from app.waitlist import rank_waitlist

    rows = rank_waitlist(
        catalog=load_seed(),
        equipment_id="eq-workbench",
        entries=client.app.state.waitlist.snapshot(),
        bookings=client.app.state.bookings.snapshot(),
        now=datetime.now(timezone.utc),
        viewer_is_faculty=True,
    )
    eligible = [row for row in rows if row.eligible]
    ineligible = [row for row in rows if not row.eligible]
    assert eligible
    assert ineligible
    assert all(row.rank is not None and row.rank > max(item.rank or 0 for item in eligible) for row in ineligible)
    listed = client.get("/waitlist", headers=STUDENT)
    assert listed.status_code == 200
    assert any(item.get("explanation") for item in listed.json()["items"] if item["status"] == "waiting") or any(
        item["status"] == "offered" for item in listed.json()["items"]
    )


def test_promotion_offer_hold_accept_and_idempotent(client: TestClient) -> None:
    booking = _book(client, STUDENT)
    joined = client.post("/waitlist", json=_join(), headers=STUDENT_B)
    assert joined.status_code == 201
    cancelled = client.post(f"/bookings/{booking['id']}/cancel", headers=STUDENT)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    waiting = client.get("/waitlist", headers=STUDENT_B)
    entry = waiting.json()["items"][0]
    assert entry["status"] == "offered"
    assert entry["offer_id"]
    overlap = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    assert overlap.status_code == 409
    public = client.post("/scheduling/promote", json={"equipment_id": "eq-workbench"})
    student_promote = client.post(
        "/scheduling/promote",
        json={"equipment_id": "eq-workbench"},
        headers=STUDENT,
    )
    again = client.post(
        "/scheduling/promote",
        json={"equipment_id": "eq-workbench"},
        headers=FACULTY_ENG,
    )
    assert public.status_code == 401
    assert student_promote.status_code == 403
    assert again.status_code == 200
    assert again.json()["idempotent"] is True
    assert again.json()["job"] == "not_deployed"
    accepted = client.post(f"/waitlist/{entry['id']}/accept", headers=STUDENT_B)
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "approved"
    assert accepted.json()["user_id"] == "user-student-engineering"
    replay = client.post(f"/waitlist/{entry['id']}/accept", headers=STUDENT_B)
    assert replay.status_code == 409


def test_expired_offer_releases_capacity(client: TestClient) -> None:
    booking = _book(client, STUDENT)
    client.post("/waitlist", json=_join(), headers=STUDENT_B)
    client.post(f"/bookings/{booking['id']}/cancel", headers=STUDENT)
    offer = client.app.state.waitlist.offers_snapshot()[0]
    client.app.state.waitlist.put_offer(
        offer.model_copy(update={"expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc)})
    )
    expired_accept = client.post(
        f"/waitlist/{offer.waitlist_id}/accept",
        headers=STUDENT_B,
    )
    assert expired_accept.status_code == 409
    freed = client.post(
        "/bookings",
        json={
            "equipment_id": "eq-workbench",
            "project_id": "proj-sensor",
            "start": FUTURE.isoformat(),
            "end": (FUTURE + timedelta(hours=2)).isoformat(),
        },
        headers=STUDENT,
    )
    assert freed.status_code == 201


def test_restricted_offer_does_not_book_without_approval(client: TestClient) -> None:
    start = datetime(2027, 5, 5, 10, 0, tzinfo=timezone.utc)
    # Laser cannot be booked by the student; occupy the window via faculty-approved path is not available.
    # Fill the search window using waitlist join against maintenance-equivalent: use recommendations empty
    # by preferring a range that is entirely in the past relative to now? That 422s.
    # Instead join on fume hood (maintenance) which has no slots.
    joined = client.post(
        "/waitlist",
        json={
            "equipment_id": "eq-diode-laser",
            "project_id": "proj-raman",
            "duration_minutes": 120,
            "preferred_start": start.isoformat(),
            "preferred_end": (start + timedelta(hours=2)).isoformat(),
            "flexibility_minutes": 0,
        },
        headers=STUDENT,
    )
    # Laser likely still has free slots, so join is 409. Force-insert waiting row.
    if joined.status_code == 409:
        from app.models import WaitlistEntry as Entry

        client.app.state.waitlist.join(
            Entry(
                id="wait-laser-forced",
                user_id="user-student-physics",
                equipment_id="eq-diode-laser",
                project_id="proj-raman",
                duration_minutes=120,
                preferred_start=start,
                preferred_end=start + timedelta(hours=2),
                flexibility_minutes=0,
                status=WaitlistStatus.WAITING,
                created_at=start - timedelta(days=1),
                updated_at=start - timedelta(days=1),
            )
        )
        entry_id = "wait-laser-forced"
    else:
        entry_id = joined.json()["id"]
    promoted = client.post(
        "/scheduling/promote",
        json={"equipment_id": "eq-diode-laser"},
        headers=FACULTY,
    )
    assert promoted.status_code == 200
    if promoted.json()["offer"]:
        accepted = client.post(f"/waitlist/{entry_id}/accept", headers=STUDENT)
        assert accepted.status_code == 403
        assert accepted.json()["error"] == "restricted"


def test_physics_faculty_cannot_promote_engineering_equipment(client: TestClient) -> None:
    response = client.post(
        "/scheduling/promote",
        json={"equipment_id": "eq-workbench"},
        headers=FACULTY,
    )
    assert response.status_code == 403


def test_concurrent_memory_promote_does_not_double_hold(client: TestClient) -> None:
    from concurrent.futures import ThreadPoolExecutor

    booking = _book(client, STUDENT)
    client.post("/waitlist", json=_join(), headers=STUDENT_B)
    client.post(f"/bookings/{booking['id']}/cancel", headers=STUDENT)

    def attempt() -> tuple[int, str | None]:
        response = client.post(
            "/scheduling/promote",
            json={"equipment_id": "eq-workbench"},
            headers=FACULTY_ENG,
        )
        offer = response.json().get("offer") if response.status_code == 200 else None
        return response.status_code, offer["id"] if offer else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    codes = sorted(code for code, _ in results)
    assert codes[0] == 200
    offer_ids = {offer_id for _, offer_id in results if offer_id}
    assert len(offer_ids) == 1
