"""Deep flag in the API (D153-D156): present beside the logistic flag, advisory, switchable, never breaks screening."""
import json
import logging
from pathlib import Path

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, need_api
from thanzi_screen.api import service
from thanzi_screen.ml import load_models
from thanzi_screen.ml.dl import load_deep_models

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG, HA = {"X-Gateway-Key": GW}, {"X-Audit-Key": AU}
WEIGHT_SLIP = {**LOW_BASE, "weight_kg": 110.0}        # 11.0 kg typed as 110: a decimal slip


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def deep():
    return load_deep_models()


def _strip(out):
    out = json.loads(json.dumps(out))
    out["ml_flags"].pop("deep_recording_error", None)
    return out


def test_deep_flag_appears_beside_the_logistic_flag(models, deep):
    out = service.screen(WEIGHT_SLIP, "worker", models, deep)
    f = out["ml_flags"]
    assert f["available"] and f["recording_error"]["flagged"]
    d = f["deep_recording_error"]
    assert d["flagged"] and d["suggested_field"] == "weight" and d["messages"]
    assert set(d) == {"flagged", "suggested_field", "messages"}          # same shape as recording_error, no probability


def test_normal_record_is_not_flagged_by_either(models, deep):
    f = service.screen(LOW_BASE, "worker", models, deep)["ml_flags"]
    assert not f["recording_error"]["flagged"] and not f["deep_recording_error"]["flagged"]


def test_probability_is_audit_view_only(models, deep):
    worker = service.screen(WEIGHT_SLIP, "worker", models, deep)["ml_flags"]["deep_recording_error"]
    audit = service.screen(WEIGHT_SLIP, "audit", models, deep)["ml_flags"]["deep_recording_error"]
    assert "probability" not in worker and 0.0 <= audit["probability"] <= 1.0


@pytest.mark.parametrize("view", ["worker", "audit"])
@pytest.mark.parametrize("body", [MAM_BASE, LOW_BASE, WEIGHT_SLIP, {**MAM_BASE, "muac_cm": 11.0}, {**LOW_BASE, "muac_cm": 140.0}])
def test_deep_flag_never_changes_the_rest_of_the_response(models, deep, body, view):
    with_deep = service.screen(body, view, models, deep)
    without = service.screen(body, view, models)
    assert "deep_recording_error" not in without["ml_flags"]
    assert _strip(with_deep) == _strip(without)                          # classification, tier, reasons, review, wording: identical


def test_without_deep_models_the_response_is_exactly_as_before(models):
    assert "deep_recording_error" not in service.screen(WEIGHT_SLIP, "worker", models)["ml_flags"]


def test_degraded_mode_has_no_deep_flag_either(deep):
    out = service.screen(WEIGHT_SLIP, "worker", None, deep)
    assert out["ml_flags"] == {"available": False, "recording_error": None, "review": out["ml_flags"]["review"]}


def test_a_failing_deep_model_does_not_touch_screening(models, deep, monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("secret patient detail 12345")
    monkeypatch.setattr(service, "flag_from_features", boom)
    with caplog.at_level(logging.WARNING, logger="thanzi.api"):
        out = service.screen(WEIGHT_SLIP, "worker", models, deep)
    assert "deep_recording_error" not in out["ml_flags"] and out["ml_flags"]["recording_error"]["flagged"]
    assert "RuntimeError" in caplog.text and "secret" not in caplog.text and "12345" not in caplog.text


def test_worker_view_still_has_no_hiv_information(models, deep):
    body = {**MAM_BASE, "hiv_positive": True}
    text = json.dumps(service.screen(body, "worker", models, deep)).lower()
    assert "hiv" not in text and "otp" not in text


def test_corrected_age_route_runs_no_ml_flag_at_all(models, deep):
    body = {**LOW_BASE, "age_days": 400, "gestational_age_weeks": 33, "birth_weight_g": 1800}
    out = service.screen(body, "worker", models, deep)
    assert out["ml_flags"]["available"] is False and "deep_recording_error" not in out["ml_flags"]


def test_version_info_names_the_deep_model_only_when_loaded(models, deep):
    assert service.version_info(models, deep)["deep_model_version"] == deep.version
    assert "deep_model_version" not in service.version_info(models)


# ---- HTTP edge ----
def _client(models=None, **kw):
    return TestClient(create_app(models=models, gateway_key=GW, audit_key=AU, **kw), raise_server_exceptions=False)


def test_http_loads_deep_models_by_default_and_reports_them(models, deep):
    c = _client(models)
    assert c.get("/version", headers=HG).json()["deep_model_version"] == deep.version
    r = c.post("/v1/screen", json=WEIGHT_SLIP, headers=HG)
    assert r.status_code == 200 and r.json()["ml_flags"]["deep_recording_error"]["flagged"]
    assert c.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("value", ["0", "false", "No", "OFF", " 0 "])
def test_switch_off_with_the_environment(models, monkeypatch, value):
    monkeypatch.setenv("THANZI_DEEP_ENABLED", value)
    c = _client(models)
    assert c.get("/version", headers=HG).json()["deep_model_version"] is None
    assert "deep_recording_error" not in c.post("/v1/screen", json=WEIGHT_SLIP, headers=HG).json()["ml_flags"]


def test_missing_deep_files_leave_screening_up_and_health_ok(models, tmp_path, caplog):
    for name in ("recording_error_lr.json", "recording_field_tree.json"):
        (tmp_path / name).write_text((ROOT / "models" / name).read_text())
    with caplog.at_level(logging.WARNING, logger="thanzi.api"):
        c = _client(models_dir=tmp_path)
    assert c.get("/health").json() == {"status": "ok"}
    r = c.post("/v1/screen", json=WEIGHT_SLIP, headers=HG)
    assert r.status_code == 200 and "deep_recording_error" not in r.json()["ml_flags"] and r.json()["ml_flags"]["recording_error"]["flagged"]
    assert "Deep models unavailable" in caplog.text


def test_mismatched_deep_files_are_ignored_not_fatal(models, tmp_path):
    for name in ("recording_error_lr.json", "recording_field_tree.json"):
        (tmp_path / name).write_text((ROOT / "models" / name).read_text())
    for name in ("recording_error_mlp.json", "recording_field_mlp.json"):
        obj = json.loads((ROOT / "models" / name).read_text())
        obj["metadata"]["feature_names"] = obj["metadata"]["feature_names"][:-1]
        (tmp_path / name).write_text(json.dumps(obj))
    c = _client(models_dir=tmp_path)
    assert c.post("/v1/screen", json=WEIGHT_SLIP, headers=HG).status_code == 200
    assert c.get("/version", headers=HG).json()["deep_model_version"] is None


def test_openapi_documents_the_new_fields(models):
    spec = json.loads((ROOT / "docs" / "api" / "openapi.json").read_text())
    assert "deep_recording_error" in spec["components"]["schemas"]["MlFlagsOut"]["properties"]
    assert "deep_model_version" in spec["components"]["schemas"]["VersionResponse"]["properties"]
