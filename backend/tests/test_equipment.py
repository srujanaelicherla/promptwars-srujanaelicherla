"""Equipment discovery against the synthetic catalog."""

from fastapi.testclient import TestClient

from app.seed import load_seed

_CATALOG_IDS = tuple(sorted(item.id for item in load_seed().equipment))


def test_lists_all_equipment(client: TestClient) -> None:
    response = client.get("/equipment")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "synthetic"
    assert body["total"] == 110
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert [item["id"] for item in body["items"]] == list(_CATALOG_IDS[:20])


def test_search_by_name(client: TestClient) -> None:
    response = client.get("/equipment", params={"search": "DIODE"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["eq-diode-laser"]
    assert "laser" in items[0]["name"].casefold()


def test_search_by_description(client: TestClient) -> None:
    response = client.get("/equipment", params={"search": "chromatography"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["eq-hplc"]
    assert "chromatography" in items[0]["description"].casefold()


def test_department_filter(client: TestClient) -> None:
    response = client.get("/equipment", params={"department": "dept-physics"})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 23
    assert {item["department_id"] for item in body["items"]} == {"dept-physics"}


def test_category_filter(client: TestClient) -> None:
    response = client.get("/equipment", params={"category": "optics"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert "eq-diode-laser" in [item["id"] for item in items]
    assert "eq-optical-table" in [item["id"] for item in items]
    assert {item["category"] for item in items} == {"optics"}


def test_status_filter(client: TestClient) -> None:
    response = client.get("/equipment", params={"status": "maintenance"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == ["eq-fume-hood"]
    assert items[0]["status"] == "maintenance"


def test_combined_filters(client: TestClient) -> None:
    response = client.get(
        "/equipment",
        params={"department": "dept-chemistry", "category": "safety", "status": "maintenance"},
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body["items"]] == ["eq-fume-hood"]
    assert body["total"] == 1


def test_pagination(client: TestClient) -> None:
    first = client.get("/equipment", params={"limit": 3, "offset": 0})
    second = client.get("/equipment", params={"limit": 3, "offset": 3})

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["total"] == second_body["total"] == 110
    assert first_body["items"][0]["id"] == _CATALOG_IDS[0]
    assert [item["id"] for item in first_body["items"]] + [
        item["id"] for item in second_body["items"]
    ] == list(_CATALOG_IDS[:6])
    assert first_body["items"][0]["id"] != second_body["items"][0]["id"]


def test_invalid_query_parameters(client: TestClient) -> None:
    limit = client.get("/equipment", params={"limit": 0})
    offset = client.get("/equipment", params={"offset": -1})
    status = client.get("/equipment", params={"status": "in_use"})
    department = client.get("/equipment", params={"department": "Not An Id"})

    for response in (limit, offset, status, department):
        assert response.status_code == 422
        body = response.json()
        assert body["error"] == "invalid_request"
        assert "in_use" not in response.text
        assert "Not An Id" not in response.text


def test_equipment_detail(client: TestClient) -> None:
    response = client.get("/equipment/eq-diode-laser")

    assert response.status_code == 200
    body = response.json()
    expected = next(item for item in load_seed().equipment if item.id == "eq-diode-laser")
    assert body == expected.model_dump(mode="json")


def test_unknown_equipment_id(client: TestClient) -> None:
    response = client.get("/equipment/eq-missing")

    assert response.status_code == 404
    assert response.json() == {
        "error": "not_found",
        "message": "The requested resource does not exist.",
    }


def test_department_counts_unique_ids_and_names() -> None:
    catalog = load_seed()
    by_dept: dict[str, list[str]] = {}
    ids = [item.id for item in catalog.equipment]
    assert len(ids) == len(set(ids)) == 110
    for item in catalog.equipment:
        by_dept.setdefault(item.department_id, []).append(item.name)
    assert {dept.id for dept in catalog.departments} == set(by_dept)
    assert len(by_dept["dept-chemistry"]) == 27
    assert len(by_dept["dept-physics"]) == 23
    assert len(by_dept["dept-engineering"]) == 33
    assert len(by_dept["dept-biology"]) == 27
    for department_id, names in by_dept.items():
        assert len(names) == len({name.casefold() for name in names}), department_id


def test_biology_equipment_is_visible(client: TestClient) -> None:
    response = client.get("/equipment", params={"department": "dept-biology", "limit": 100})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 27
    assert body["items"]
    assert {item["department_id"] for item in body["items"]} == {"dept-biology"}
    assert "eq-pcr-thermocycler" in {item["id"] for item in body["items"]}


def test_kind_filter_lists_stations_and_kits(client: TestClient) -> None:
    stations = client.get("/equipment", params={"kind": "lab-station", "limit": 200})
    kits = client.get("/equipment", params={"kind": "kit", "limit": 200})

    assert stations.status_code == 200
    assert kits.status_code == 200
    station_ids = {item["id"] for item in stations.json()["items"]}
    kit_ids = {item["id"] for item in kits.json()["items"]}
    assert "eq-workbench" in station_ids
    assert "eq-assembly-bench" in station_ids
    assert "eq-electronics-kit" in kit_ids
    assert "eq-laser-kit" in kit_ids
    assert stations.json()["total"] == 5
    assert kits.json()["total"] == 5


def test_unknown_department_filter_is_empty(client: TestClient) -> None:
    response = client.get("/equipment", params={"department": "dept-missing"})

    assert response.status_code == 200
    assert response.json()["total"] == 0
    assert response.json()["items"] == []
