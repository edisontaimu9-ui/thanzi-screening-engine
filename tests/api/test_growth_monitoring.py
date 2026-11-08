"""Growth monitoring in the API (D157-D162): optional earlier visit, advisory result, strict input, route handling."""
import json

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, need_api
from thanzi_screen.api import service
from thanzi_screen.api.service import ApiError
from thanzi_screen.ml import load_models
from thanzi_screen.ml.dl import load_deep_models

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG = {"X-Gateway-Key": GW}
# A boy of 10 months, healthy by every CMAM measure, who gained 50 g in 31 days.
NOW = {**LOW_BASE, "age_days": 305, "weight_kg": 8.55, "length_height_cm": 72.0}
SLOW = {"age_days": 274, "weight_kg": 8.5}
FINE = {"age_days": 274, "weight_kg": 8.2}


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def deep():
    return load_deep_models()


def _scrub(out):
    out = json.loads(json.dumps(out))
    out.pop("growth_monitoring", None)
    return out


def test_slow_gain_is_flagged_and_explained(models, deep):
    g = service.screen({**NOW, "previous_measurement": SLOW}, "worker", models, deep)["growth_monitoring"]
    assert g["assessed"] and g["status"] == "below_range" and g["flagged"] and not g["weight_loss"]
    assert g["interval_days"] == 31 and g["weight_change_g"] == 50.0 and g["rate_g_per_day"] == 1.61
    assert (g["reference_low"], g["reference_high"]) == (4.0, 12.0)
    assert "faltering" in g["messages"][0] and g["reference"] == "R19" and "does not change" in g["advisory"]


def test_normal_gain_is_not_flagged(models, deep):
    g = service.screen({**NOW, "previous_measurement": FINE}, "worker", models, deep)["growth_monitoring"]
    assert g["status"] == "within_range" and not g["flagged"] and g["messages"] == []


def test_absent_without_the_earlier_visit(models, deep):
    assert "growth_monitoring" not in service.screen(NOW, "worker", models, deep)
    assert "growth_monitoring" not in service.screen({**NOW, "previous_measurement": None}, "worker", models, deep)


@pytest.mark.parametrize("view", ["worker", "audit"])
@pytest.mark.parametrize("body", [NOW, {**NOW, "muac_cm": 11.0}, {**NOW, "muac_cm": 12.0}, {**NOW, "weight_kg": 85.5}])
@pytest.mark.parametrize("previous", [SLOW, FINE, {"age_days": 300, "weight_kg": 8.5}, {"age_days": 274, "weight_kg": 8.9}])
def test_the_rest_of_the_response_is_identical_with_and_without_it(models, deep, body, view, previous):
    """Advisory only (D9): classification, tier, reasons, review, ML flags and wording never depend on growth."""
    with_growth = service.screen({**body, "previous_measurement": previous}, view, models, deep)
    without = service.screen(body, view, models, deep)
    assert _scrub(with_growth) == _scrub(without)


def test_a_child_can_be_low_risk_and_still_be_flagged_for_growth(models, deep):
    out = service.screen({**NOW, "previous_measurement": SLOW}, "worker", models, deep)
    assert out["classification"] == "low_risk" and out["growth_monitoring"]["flagged"]


def test_it_works_in_degraded_mode_because_it_is_rules_based():
    out = service.screen({**NOW, "previous_measurement": SLOW}, "worker", None)
    assert out["ml_flags"]["available"] is False and out["growth_monitoring"]["status"] == "below_range"


def test_worker_view_has_no_hiv_or_programme_leak(models, deep):
    body = {**NOW, "muac_cm": 12.0, "hiv_positive": True, "previous_measurement": SLOW}
    out = service.screen(body, "worker", models, deep)
    assert "hiv" not in json.dumps(out).lower() and out["programme"] is None


def test_worker_and_audit_carry_the_same_growth_result(models, deep):
    body = {**NOW, "previous_measurement": SLOW}
    assert (service.screen(body, "worker", models, deep)["growth_monitoring"]
            == service.screen(body, "audit", models, deep)["growth_monitoring"])


def test_not_assessed_cases_say_why(models, deep):
    short = service.screen({**NOW, "previous_measurement": {"age_days": 290, "weight_kg": 8.5}}, "worker", models, deep)
    assert short["growth_monitoring"]["reason"] == "interval_too_short" and short["growth_monitoring"]["status"] is None
    girl = {**NOW, "sex": "female", "age_days": 140, "weight_kg": 6.2, "length_height_cm": 62.0}
    g = service.screen({**girl, "previous_measurement": {"age_days": 100, "weight_kg": 5.5}}, "worker", models, deep)
    assert g["growth_monitoring"]["reason"] == "reference_unverified" and not g["growth_monitoring"]["flagged"]


@pytest.mark.parametrize("bad,code", [
    ({"age_days": 305, "weight_kg": 8.5}, "invalid_input"),          # same day
    ({"age_days": 400, "weight_kg": 8.5}, "invalid_input"),          # later than this visit
    ({"age_days": -5, "weight_kg": 8.5}, "invalid_input"),
    ({"age_days": 274, "weight_kg": 0}, "invalid_input"),
    ({"age_days": 274, "weight_kg": -3.0}, "invalid_input"),
    ({"age_days": 274}, "missing_field"),
    ({"weight_kg": 8.5}, "missing_field"),
    ({"age_days": 274, "weight_kg": 8.5, "name": "x"}, "unknown_field"),
    ({"age_days": 274, "weight_kg": 8.5, "date_of_birth": "2026-01-01"}, "unknown_field"),
    ({"age_days": 274.5, "weight_kg": 8.5}, "invalid_request"),
    ({"age_days": True, "weight_kg": 8.5}, "invalid_request"),
    ({"age_days": 274, "weight_kg": "8.5"}, "invalid_request"),
    ({"age_days": 274, "weight_kg": float("nan")}, "invalid_request"),
    ("274:8.5", "invalid_request"),
    ([274, 8.5], "invalid_request"),
])
def test_bad_earlier_visits_are_rejected_without_echoing_values(models, deep, bad, code):
    with pytest.raises(ApiError) as e:
        service.screen({**NOW, "previous_measurement": bad}, "worker", models, deep)
    assert e.value.status == 422 and e.value.code == code
    assert "8.5" not in e.value.message and "274" not in e.value.message and "x" != e.value.message


def test_preterm_route_ignores_it_with_a_warning(models, deep):
    body = {**NOW, "age_days": 20, "weight_kg": 2.2, "length_height_cm": 46.0, "gestational_age_weeks": 33, "birth_weight_g": 1900,
            "previous_measurement": {"age_days": 2, "weight_kg": 1.9}}
    out = service.screen(body, "worker", models, deep)
    assert out["route"] == "preterm" and "growth_monitoring" not in out
    assert any("Growth monitoring was not run" in w for w in out["warnings"])


def test_corrected_age_route_ignores_it_with_a_warning(models, deep):
    body = {**NOW, "age_days": 400, "weight_kg": 6.0, "length_height_cm": 63.0, "gestational_age_weeks": 33, "birth_weight_g": 1800,
            "previous_measurement": {"age_days": 360, "weight_kg": 5.6}}
    out = service.screen(body, "worker", models, deep)
    assert out["route"] == "under5_corrected_age" and "growth_monitoring" not in out
    assert any("Growth monitoring was not run" in w for w in out["warnings"])


def test_preterm_route_without_it_is_unchanged(models, deep):
    body = {**NOW, "age_days": 20, "weight_kg": 2.2, "length_height_cm": 46.0, "gestational_age_weeks": 33, "birth_weight_g": 1900}
    out = service.screen(body, "worker", models, deep)
    assert not any("Growth monitoring" in w for w in out["warnings"])


# ---- HTTP edge ----
def _client(models, deep):
    return TestClient(create_app(models=models, deep_models=deep, gateway_key=GW, audit_key=AU), raise_server_exceptions=False)


def test_http_round_trip(models, deep):
    c = _client(models, deep)
    r = c.post("/v1/screen", json={**NOW, "previous_measurement": SLOW}, headers=HG)
    assert r.status_code == 200 and r.json()["growth_monitoring"]["status"] == "below_range"
    assert "growth_monitoring" not in c.post("/v1/screen", json=NOW, headers=HG).json()


@pytest.mark.parametrize("bad", [{"age_days": 274}, {"age_days": 274, "weight_kg": 8.5, "name": "x"}, {"age_days": "274", "weight_kg": 8.5},
                                 {"age_days": 305, "weight_kg": 8.5}, "text", 5])
def test_http_rejects_bad_earlier_visits_with_422(models, deep, bad):
    r = _client(models, deep).post("/v1/screen", json={**NOW, "previous_measurement": bad}, headers=HG)
    assert r.status_code == 422 and "8.5" not in r.text and "name" not in r.json().get("message", "")


def test_http_still_needs_the_gateway_key(models, deep):
    assert _client(models, deep).post("/v1/screen", json={**NOW, "previous_measurement": SLOW}).status_code == 401


def test_openapi_documents_the_new_fields():
    from pathlib import Path
    spec = json.loads((Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json").read_text())
    schemas = spec["components"]["schemas"]
    assert "previous_measurement" in schemas["ScreenRequest"]["properties"] and "PreviousMeasurement" in schemas
    assert "growth_monitoring" in schemas["WorkerResponse"]["properties"] and "GrowthMonitoring" in schemas
