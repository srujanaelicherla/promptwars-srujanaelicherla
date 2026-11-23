"""Equipment matching: spec comparison, ranking, and the project matches API."""

from fastapi.testclient import TestClient

from app.matching import rank_matches, requirement_matches, score_equipment
from app.models import (
    Equipment,
    EquipmentStatus,
    Requirement,
    ResourceKind,
    SpecComparison,
    Specification,
    Suitability,
)
from app.seed import load_seed


def _spec(name: str, value: str, unit: str | None = None) -> Specification:
    return Specification(name=name, value=value, unit=unit)


def _req(
    name: str,
    value: str,
    unit: str | None = None,
    *,
    mandatory: bool = True,
    comparison: SpecComparison = SpecComparison.EQUAL,
) -> Requirement:
    return Requirement(
        name=name,
        value=value,
        unit=unit,
        mandatory=mandatory,
        comparison=comparison,
    )


def _equipment(item_id: str, specs: list[Specification], department_id: str = "dept-physics") -> Equipment:
    return Equipment(
        id=item_id,
        name=item_id.replace("-", " "),
        category="test",
        lab_id="lab-optics",
        department_id=department_id,
        description="Synthetic fixture for matching tests.",
        specifications=specs,
        status=EquipmentStatus.AVAILABLE,
        safety_prerequisites=[],
    )


def test_exact_specification_match() -> None:
    spec = _spec("detector", "UV-Vis")
    required = _req("detector", "uv-vis")

    assert requirement_matches(required, spec) is True
    assert requirement_matches(_req("detector", "fluorescence"), spec) is False


def test_numeric_comparison_with_compatible_units() -> None:
    spec = _spec("bandwidth", "200", "MHz")

    assert requirement_matches(
        _req("bandwidth", "0.1", "GHz", comparison=SpecComparison.AT_LEAST),
        spec,
    )
    assert requirement_matches(_req("wavelength", "532", "nm"), _spec("wavelength", "532", "nm"))


def test_missing_units_and_specs_do_not_satisfy() -> None:
    laser = _equipment("eq-laser", [_spec("wavelength", "532", "nm")])

    missing_unit = score_equipment(laser, [_req("wavelength", "532")])
    assert missing_unit.suitability is Suitability.UNSUITABLE
    incompatible = score_equipment(laser, [_req("wavelength", "532", "mW")])
    assert incompatible.suitability is Suitability.UNSUITABLE
    missing_spec = score_equipment(laser, [_req("isolation", "pneumatic")])
    assert missing_spec.suitability is Suitability.UNSUITABLE
    assert missing_spec.unmet_requirements == ("isolation",)


def test_failed_hard_constraint_cannot_be_fully_suitable_or_outrank() -> None:
    required = [
        _req("wavelength", "532", "nm", mandatory=True),
        _req("isolation", "pneumatic", mandatory=False),
        _req("length", "2.4", "m", mandatory=False),
    ]
    failed_hard = _equipment(
        "eq-table",
        [_spec("isolation", "pneumatic"), _spec("length", "2.4", "m")],
    )
    passed_hard = _equipment("eq-laser", [_spec("wavelength", "532", "nm")])
    ranked = rank_matches([failed_hard, passed_hard], required)

    assert ranked[0].equipment.id == "eq-laser"
    assert ranked[0].mandatory_ok is True
    assert ranked[0].suitability is Suitability.PARTIALLY_SUITABLE
    assert ranked[1].equipment.id == "eq-table"
    assert ranked[1].mandatory_ok is False
    assert ranked[1].suitability is not Suitability.FULLY_SUITABLE
    assert ranked[1].score > ranked[0].score


def test_suitability_classes() -> None:
    required = [_req("wavelength", "532", "nm"), _req("length", "2.4", "m")]
    full = score_equipment(
        _equipment("eq-full", [_spec("wavelength", "532", "nm"), _spec("length", "2.4", "m")]),
        required,
    )
    partial = score_equipment(_equipment("eq-partial", [_spec("wavelength", "532", "nm")]), required)
    none = score_equipment(_equipment("eq-none", [_spec("detector", "UV-Vis")]), required)

    assert full.suitability is Suitability.FULLY_SUITABLE
    assert full.score == 1.0
    assert partial.suitability is Suitability.PARTIALLY_SUITABLE
    assert none.suitability is Suitability.UNSUITABLE
    assert none.score == 0.0


def test_cross_department_seed_recommendation(client: TestClient) -> None:
    response = client.get("/projects/proj-hplc-method/equipment-matches")
    project = next(item for item in load_seed().projects if item.id == "proj-hplc-method")
    items = {item["equipment_id"]: item for item in response.json()["items"]}
    hplc = items["eq-hplc"]
    spectrometer = items["eq-spectrometer"]

    assert response.status_code == 200
    assert hplc["suitability"] == "fully_suitable"
    assert hplc["department_id"] == project.department_id
    assert spectrometer["department_id"] != project.department_id
    assert spectrometer["suitability"] == "partially_suitable"
    assert "detector" in spectrometer["matched_requirements"]
    assert "flow rate" in spectrometer["unmet_requirements"]


def test_ranking_is_deterministic(client: TestClient) -> None:
    catalog = load_seed()
    project = next(item for item in catalog.projects if item.id == "proj-raman")
    forward = rank_matches(catalog.equipment, project.required_specifications)
    reverse = rank_matches(list(reversed(catalog.equipment)), project.required_specifications)
    first = client.get("/projects/proj-raman/equipment-matches", params={"limit": 200})
    second = client.get("/projects/proj-raman/equipment-matches", params={"limit": 200})
    ranked_ids = [item.equipment.id for item in forward]
    scored = [item for item in forward if item.score > 0]
    zero_aux = [
        item
        for item in forward
        if item.equipment.kind is not ResourceKind.EQUIPMENT and item.score == 0
    ]

    assert ranked_ids == [item.equipment.id for item in reverse]
    assert first.status_code == 200
    assert first.json()["total"] == 110
    assert first.json()["items"] == second.json()["items"]
    assert ranked_ids == [item["equipment_id"] for item in first.json()["items"]]
    assert scored
    assert zero_aux
    assert max(ranked_ids.index(item.equipment.id) for item in scored) < min(
        ranked_ids.index(item.equipment.id) for item in zero_aux
    )
    assert ranked_ids.index("eq-diode-laser") < ranked_ids.index("eq-optics-bench")
    assert ranked_ids.index("eq-optical-table") < ranked_ids.index("eq-optics-kit")


def test_unknown_project_and_invalid_limit(client: TestClient) -> None:
    missing = client.get("/projects/proj-missing/equipment-matches")
    invalid_id = client.get("/projects/Not-Valid/equipment-matches")
    bad_limit = client.get("/projects/proj-sensor/equipment-matches", params={"limit": 0})

    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"
    assert invalid_id.status_code == 422
    assert bad_limit.status_code == 422
    assert "Not-Valid" not in invalid_id.text


def test_biology_project_matches_thermocycler(client: TestClient) -> None:
    response = client.get("/projects/proj-amplicon/equipment-matches", params={"limit": 5})
    items = response.json()["items"]
    top = items[0]
    thermocycler = next(item for item in load_seed().equipment if item.id == "eq-pcr-thermocycler")

    assert response.status_code == 200
    assert top["equipment_id"] == "eq-pcr-thermocycler"
    assert top["department_id"] == "dept-biology"
    assert top["suitability"] == "fully_suitable"
    assert top["score"] == 1.0
    assert "well format" in top["matched_requirements"]
    assert "heated lid" in top["matched_requirements"]
    assert thermocycler.status.value == "available"
    assert response.json()["source"] == "synthetic"


def test_seed_matches_use_recorded_specs(client: TestClient) -> None:
    response = client.get("/projects/proj-sensor/equipment-matches", params={"limit": 1})
    scope = next(item for item in load_seed().equipment if item.id == "eq-oscilloscope")
    body = response.json()["items"][0]
    bandwidth = next(spec for spec in scope.specifications if spec.name == "bandwidth")

    assert response.status_code == 200
    assert body["equipment_id"] == "eq-oscilloscope"
    assert body["suitability"] == "fully_suitable"
    assert body["score"] == 1.0
    assert body["matched_requirements"] == ["bandwidth", "channels"]
    assert bandwidth.value == "200"
    assert bandwidth.unit == "MHz"
    assert requirement_matches(
        _req("bandwidth", "100", "MHz", comparison=SpecComparison.AT_LEAST),
        bandwidth,
    )
    assert "live availability" in body["explanation"]
    assert response.json()["source"] == "synthetic"
