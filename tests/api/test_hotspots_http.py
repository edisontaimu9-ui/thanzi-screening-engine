"""POST /v1/surveillance/hotspots: behind the gateway key, strict contract, no child-level or fine-geography fields."""
import pytest

from tests.api._support import need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}
URL = "/v1/surveillance/hotspots"
ROW = {"district": "Mangochi", "period": "2026-10", "screened": 300, "sam": 15, "mam": 35}
OTHER = {"district": "Zomba", "period": "2026-10", "screened": 300, "sam": 5, "mam": 10}


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(gateway_key=GW, models=None))


def test_requires_gateway_key(client):
    assert client.post(URL, json={"rows": [ROW]}).status_code == 401


def test_happy_path(client):
    r = client.post(URL, json={"rows": [ROW, OTHER]}, headers=HG)
    assert r.status_code == 200
    body = r.json()
    assert body["areas"][0]["district"] == "Mangochi" and body["areas"][0]["status"] == "hotspot"
    assert "advisory" in body and body["period"] == "2026-10"


@pytest.mark.parametrize("extra", ["child_id", "name", "date_of_birth", "latitude", "facility", "community"])
def test_identifier_and_fine_geography_fields_rejected(client, extra):
    r = client.post(URL, json={"rows": [{**ROW, extra: "x"}]}, headers=HG)
    assert r.status_code == 422 and r.json()["code"] == "unknown_field"


def test_top_level_unknown_field_rejected(client):
    assert client.post(URL, json={"rows": [ROW], "child_id": "1"}, headers=HG).status_code == 422


def test_engine_error_is_422_without_echo(client):
    r = client.post(URL, json={"rows": [{**ROW, "period": "bad-value-xyz"}]}, headers=HG)
    assert r.status_code == 422 and "bad-value-xyz" not in r.text and r.json()["code"] == "invalid_period"


def test_empty_rows_rejected(client):
    assert client.post(URL, json={"rows": []}, headers=HG).status_code == 422


def test_large_batch_allowed_but_screen_body_limit_unchanged(client):
    rows = [{**OTHER, "district": f"District {chr(65 + i % 26)}{chr(65 + i // 26)}"} for i in range(400)]
    assert client.post(URL, json={"rows": rows}, headers=HG).status_code == 200
    big = {"sex": "male", "pad": "x" * 20_000}
    assert client.post("/v1/screen", json=big, headers=HG).status_code == 413


def test_screen_endpoint_unaffected_by_hotspots(client):
    payload = {"sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0, "measure_position": "length",
               "oedema": "none", "muac_cm": 12.0, "appetite": "passed", "danger_signs": [], "complications": [],
               "clinically_well_and_alert": True}
    a = client.post("/v1/screen", json=payload, headers=HG).json()
    client.post(URL, json={"rows": [ROW, OTHER]}, headers=HG)
    assert client.post("/v1/screen", json=payload, headers=HG).json() == a
