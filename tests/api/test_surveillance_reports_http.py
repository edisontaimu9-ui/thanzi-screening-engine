"""POST /v1/surveillance/report and /v1/surveillance/dhis2: off by default, behind the gateway key, strict contract."""
import pytest

from tests.api._support import need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}
REPORT, DHIS2 = "/v1/surveillance/report", "/v1/surveillance/dhis2"
ORG = [{"code": "MW", "name": "Malawi", "level": "national"},
       {"code": "D1", "name": "Zomba", "level": "district", "parent": "MW"},
       {"code": "D2", "name": "Mangochi", "level": "district", "parent": "MW"},
       {"code": "F1", "name": "Zomba Central Hospital", "level": "facility", "parent": "D1"},
       {"code": "F2", "name": "Mangochi District Hospital", "level": "facility", "parent": "D2"}]
ROWS = [{"org_unit": "F1", "period": "2026-10", "screened": 300, "sam": 5, "mam": 10},
        {"org_unit": "F2", "period": "2026-10", "screened": 300, "sam": 15, "mam": 35}]
BODY = {"org_units": ORG, "rows": ROWS}
MAPPING = {"elements": {"screened": "THZ_SCREENED", "sam": "THZ_SAM", "mam": "THZ_MAM"}}


@pytest.fixture(scope="module")
def on():
    return TestClient(create_app(gateway_key=GW, models=None, surveillance_reports=True))


def test_off_by_default_and_switched_on_by_the_environment(monkeypatch):
    monkeypatch.delenv("THANZI_SURVEILLANCE_REPORTS_ENABLED", raising=False)
    off = TestClient(create_app(gateway_key=GW, models=None))
    for url, body in ((REPORT, BODY), (DHIS2, {**BODY, "mapping": MAPPING})):
        r = off.post(url, json=body, headers=HG)
        assert r.status_code == 404 and r.json()["code"] == "surveillance_reports_off"
    monkeypatch.setenv("THANZI_SURVEILLANCE_REPORTS_ENABLED", "1")          # Phase 11: the switch alone is not enough
    monkeypatch.delenv("THANZI_REVIEW_SIGNOFF_DIR", raising=False)
    assert TestClient(create_app(gateway_key=GW, models=None)).post(REPORT, json=BODY, headers=HG).status_code == 404
    from tests.review.test_gate import SURV, signed
    from thanzi_screen.review import SUBJECTS, pack
    import json as _json
    import pathlib, tempfile
    with tempfile.TemporaryDirectory() as d:
        (pathlib.Path(d) / SUBJECTS[SURV].filename).write_text(_json.dumps(signed(SURV)), encoding="utf-8")
        monkeypatch.setenv("THANZI_REVIEW_SIGNOFF_DIR", d)
        assert TestClient(create_app(gateway_key=GW, models=None)).post(REPORT, json=BODY, headers=HG).status_code == 404   # still PLACEHOLDER settings
        monkeypatch.setattr(pack, "_surv_placeholder", lambda: False)                                                        # Ministry values are in
        assert TestClient(create_app(gateway_key=GW, models=None)).post(REPORT, json=BODY, headers=HG).status_code == 200


def test_both_routes_need_the_gateway_key(on):
    assert on.post(REPORT, json=BODY).status_code == 401
    assert on.post(DHIS2, json={**BODY, "mapping": MAPPING}).status_code == 401
    assert on.post(REPORT, json=BODY, headers={"X-Gateway-Key": GW[::-1]}).status_code == 401


def test_report_happy_path(on):
    r = on.post(REPORT, json=BODY, headers=HG)
    assert r.status_code == 200
    b = r.json()
    assert b["period"] == "2026-10" and b["national"]["screened"] == 600 and b["national"]["sam"] == 20
    assert b["districts"][0]["org_unit"] == "D2" and b["districts"][0]["hotspot_status"] == "hotspot"
    assert {f["org_unit"] for f in b["facilities"]} == {"F1", "F2"} and b["summary"]["reporting_rate"] == 1.0
    assert "advisory" in b and b["limits"]


def test_dhis2_happy_path(on):
    r = on.post(DHIS2, json={**BODY, "mapping": MAPPING}, headers=HG)
    assert r.status_code == 200
    b = r.json()
    assert b["data_value_set"]["period"] == "202610" and len(b["data_value_set"]["dataValues"]) == 6
    assert b["import_parameters"]["dryRun"] == "true" and b["summary"]["facilities_exported"] == 2


@pytest.mark.parametrize("extra", ["child_id", "date_of_birth", "latitude", "village"])
def test_identifier_and_fine_geography_fields_rejected(on, extra):
    assert on.post(REPORT, json={**BODY, "rows": [{**ROWS[0], extra: "x"}, ROWS[1]]}, headers=HG).json()["code"] == "unknown_field"
    assert on.post(REPORT, json={**BODY, extra: "x"}, headers=HG).status_code == 422
    org = [{**ORG[0], extra: "x"}, *ORG[1:]]
    assert on.post(REPORT, json={**BODY, "org_units": org}, headers=HG).json()["code"] == "unknown_field"


def test_engine_errors_are_422_without_echo(on):
    r = on.post(REPORT, json={**BODY, "rows": [{**ROWS[0], "org_unit": "SECRET-xyz"}]}, headers=HG)
    assert r.status_code == 422 and r.json()["code"] == "unknown_org_unit" and "SECRET-xyz" not in r.text
    r = on.post(DHIS2, json={**BODY, "mapping": {"elements": {"screened": "A"}}}, headers=HG)
    assert r.status_code == 422 and r.json()["code"] == "mapping_incomplete"


def test_empty_and_missing_parts_rejected(on):
    assert on.post(REPORT, json={"org_units": ORG, "rows": []}, headers=HG).status_code == 422
    assert on.post(DHIS2, json=BODY, headers=HG).status_code == 422                 # mapping is required


def test_body_limits_are_separate(on):
    facilities = [{"code": f"FAC{i}", "name": f"Facility number {i}", "level": "facility", "parent": "D1"} for i in range(1000)]
    rows = [{"org_unit": f"FAC{i}", "period": "2026-10", "screened": 40, "sam": 0, "mam": 6} for i in range(1000)]
    big = {"org_units": ORG[:3] + facilities, "rows": rows}
    r = on.post(REPORT, json=big, headers=HG)
    assert r.status_code == 200 and r.json()["national"]["screened"] == 40_000       # far over the 16 KB screen limit
    assert on.post(REPORT, json={**BODY, "pad": "x" * 2_000_000}, headers=HG).status_code == 413
    assert on.post("/v1/screen", json={"sex": "male", "pad": "x" * 20_000}, headers=HG).status_code == 413
    assert on.post("/v1/surveillance/hotspots", json={"rows": [], "pad": "x" * 300_000}, headers=HG).status_code == 413


def test_routes_are_listed_and_counted(on):
    paths = on.get("/v1/about", headers=HG).json()["routes"]
    assert REPORT in paths and DHIS2 in paths
    on.post(REPORT, json=BODY, headers=HG)
    assert on.get("/v1/metrics", headers=HG).json()["by_route"].get(REPORT, 0) >= 1
