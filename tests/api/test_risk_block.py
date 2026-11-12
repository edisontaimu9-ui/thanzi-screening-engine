"""Advisory risk block in the API: escalate only, never changes the rules, off by default, fails safe."""
import copy
import json
import logging
import random
from pathlib import Path

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE, need_api
from thanzi_screen.api import service
from thanzi_screen.ml import load_models
from thanzi_screen.ml.risk import RISK_FEATURES, RiskModel, load_risk_model
from thanzi_screen.ml.risk.model import SCHEMA

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / "models" / "risk_sim"
GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}
WEIGHT_SLIP = {**LOW_BASE, "weight_kg": 110.0}


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def sim():
    return load_risk_model(SIM_DIR, allow_simulated=True)


def _model(threshold, coef_by_name, kind="logistic", tree=None):
    """Hand-built model so a test controls exactly who is elevated."""
    names = list(RISK_FEATURES)
    if kind == "logistic":
        part = {"type": "logistic", "names": names, "mean": [0.0] * len(names), "std": [1.0] * len(names),
                "coef": [coef_by_name.get(n, 0.0) for n in names], "bias": 0.0}
    else:
        part = {"type": "tree_ensemble", "kind": "gbm_logit", "split": "lt", "names": names, "base": 0.0, "trees": [tree]}
    return RiskModel({"schema": SCHEMA, "version": "test-1", "kind": kind, "provenance": "simulated", "clinical_use": False,
                      "target": {"name": "t", "plain": "getting worse", "horizon_weeks": 8, "definition": "x"},
                      "calibration": {"a": 1.0, "b": 0.0}, "threshold": threshold,
                      "eligibility": {"age_months_min": 6.0, "age_months_max": 60.0}, "model": part})


ALWAYS = lambda: _model(0.01, {"wflh_z": -1.0})        # noqa: E731  elevated for almost everyone
NEVER = lambda: _model(0.999999, {"wflh_z": -1.0})     # noqa: E731


def _strip(out):
    out = json.loads(json.dumps(out))
    out.pop("ml_risk", None)
    return out


def _payloads():
    rng = random.Random(11)
    out = [MAM_BASE, SAM_BASE, LOW_BASE, WEIGHT_SLIP, {**LOW_BASE, "muac_cm": None}, {**MAM_BASE, "oedema": "++"},
           {**LOW_BASE, "age_days": 100, "muac_cm": None}, {**MAM_BASE, "previous_measurement": {"age_days": 460, "weight_kg": 11.4}}]
    for _ in range(60):
        out.append({**MAM_BASE, "sex": rng.choice(["male", "female"]), "age_days": rng.randint(30, 1800),
                    "weight_kg": round(rng.uniform(3, 20), 1), "length_height_cm": round(rng.uniform(50, 110), 1),
                    "measure_position": rng.choice(["length", "height"]), "muac_cm": rng.choice([None, 10.5, 11.8, 12.6, 14.0]),
                    "appetite": rng.choice(["passed", "failed", "not_done"]), "oedema": rng.choice(["none", "none", "+"])})
    return out


# ---- safety: the rules never move ----
@pytest.mark.parametrize("view", ["worker", "audit"])
@pytest.mark.parametrize("make", [ALWAYS, NEVER])
def test_risk_block_never_changes_anything_else(models, view, make):
    risk = make()
    for body in _payloads():
        try:
            without = service.screen(copy.deepcopy(body), view, models)
        except service.ApiError as exc:
            with pytest.raises(service.ApiError) as again:
                service.screen(copy.deepcopy(body), view, models, None, risk)
            assert again.value.code == exc.code
            continue
        with_risk = service.screen(copy.deepcopy(body), view, models, None, risk)
        assert _strip(with_risk) == _strip(without)


def test_without_a_risk_model_the_response_has_no_risk_key(models):
    assert "ml_risk" not in service.screen(MAM_BASE, "worker", models)


def test_elevated_adds_a_concern_with_reasons_and_never_reassures(models):
    r = service.screen({**MAM_BASE, "weight_kg": 9.0}, "worker", models, None, ALWAYS())["ml_risk"]
    assert r["scored"] and r["elevated"] is True and r["message"] and 1 <= len(r["drivers"]) <= 3
    assert all(d["direction"] == "raises" and d["text"] for d in r["drivers"])
    q = service.screen(MAM_BASE, "worker", models, None, NEVER())["ml_risk"]
    assert q["scored"] and q["elevated"] is False and q["message"] is None and q["drivers"] == []
    assert "does not mean the child is well" in q["advisory"]


def test_worker_view_hides_probabilities_audit_shows_exact_contributions(models):
    w = service.screen(MAM_BASE, "worker", models, None, ALWAYS())["ml_risk"]
    a = service.screen(MAM_BASE, "audit", models, None, ALWAYS())["ml_risk"]
    assert not {"probability", "raw_probability", "threshold", "explanation"} & set(w)
    ex = a["explanation"]
    assert 0 < a["probability"] < 1 and ex["unit"] == "logit"
    assert abs(ex["baseline"] + sum(c["contribution"] for c in ex["contributions"]) - _logit(a["raw_probability"])) < 1e-4


def _logit(p):
    import math
    return math.log(p / (1 - p))


@pytest.mark.parametrize("body,reason", [
    ({**LOW_BASE, "muac_cm": None}, "muac_missing"),
    ({**LOW_BASE, "age_days": 100, "weight_kg": 6.0, "length_height_cm": 60.0, "muac_cm": None}, "age_outside_model_range"),
    (WEIGHT_SLIP, "possible_recording_error"),
])
def test_children_who_cannot_be_scored_say_why(models, body, reason):
    r = service.screen(body, "worker", models, None, ALWAYS())["ml_risk"]
    assert r["scored"] is False and r["not_scored_reason"] == reason and r["elevated"] is None and r["message"] is None


def test_not_scored_when_the_recording_check_did_not_run():
    r = service.screen(LOW_BASE, "worker", None, None, ALWAYS())["ml_risk"]
    assert r["scored"] is False and r["not_scored_reason"] == "data_quality_check_unavailable"


@pytest.mark.parametrize("extra", [{"gestational_age_weeks": 33, "birth_weight_g": 1800, "age_days": 400},
                                   {"gestational_age_weeks": 30, "birth_weight_g": 1200, "age_days": 20, "weight_kg": 1.5, "length_height_cm": 40.0, "muac_cm": None}])
def test_no_risk_block_on_preterm_or_corrected_age_routes(models, extra):
    assert "ml_risk" not in service.screen({**LOW_BASE, **extra}, "worker", models, None, ALWAYS())


def test_a_failing_model_does_not_touch_screening_or_leak_input(models, monkeypatch, caplog):
    def boom(self, x):
        raise RuntimeError("secret patient detail 12345")
    monkeypatch.setattr(RiskModel, "elevated", boom)
    with caplog.at_level(logging.WARNING, logger="thanzi.api"):
        out = service.screen(MAM_BASE, "worker", models, None, ALWAYS())
    assert out["ml_risk"]["not_scored_reason"] == "model_error" and out["ml_risk"]["scored"] is False
    assert _strip(out) == _strip(service.screen(MAM_BASE, "worker", models))
    assert "RuntimeError" in caplog.text and "secret" not in caplog.text and "12345" not in caplog.text


def test_worker_view_has_no_hiv_content_and_marks_simulated_models(models, sim):
    out = service.screen({**MAM_BASE, "hiv_positive": True}, "worker", models, None, sim)
    text = json.dumps(out).lower()
    assert "hiv" not in text and out["ml_risk"]["non_clinical"] is True


def test_tree_ensemble_model_works_end_to_end_with_exact_explanations(models):
    leaf = lambda v, c: {"v": v, "c": c}  # noqa: E731
    i = {n: k for k, n in enumerate(RISK_FEATURES)}
    tree = {"f": i["wflh_z"], "t": -1.0, "c": 100, "l": {"f": i["appetite_failed"], "t": 0.5, "c": 30, "l": leaf(1.0, 20), "r": leaf(2.5, 10)},
            "r": leaf(-2.0, 70)}
    risk = _model(0.5, {}, kind="gbm_logit", tree=tree)
    body = {**MAM_BASE, "weight_kg": 9.0, "appetite": "failed"}
    a = service.screen(body, "audit", models, None, risk)["ml_risk"]
    assert a["scored"] and a["elevated"] is True and a["model_kind"] == "gbm_logit"
    c = a["explanation"]
    assert abs(c["baseline"] + sum(x["contribution"] for x in c["contributions"]) - _logit(a["raw_probability"])) < 1e-4
    assert a["drivers"][0]["feature"] in ("wflh_z", "appetite_failed")


# ---- HTTP edge ----
def _client(models=None, **kw):
    return TestClient(create_app(models=models, gateway_key=GW, **kw), raise_server_exceptions=False)


def test_risk_is_off_by_default(models, monkeypatch):
    monkeypatch.delenv("THANZI_RISK_ENABLED", raising=False)
    c = _client(models)
    assert "ml_risk" not in c.post("/v1/screen", json=MAM_BASE, headers=HG).json()
    assert c.get("/version", headers=HG).json()["risk_model_version"] is None
    comp = {x["name"]: x for x in c.get("/v1/about", headers=HG).json()["components"]}
    assert comp["ml_risk"]["state"] == "off" and comp["ml_risk"]["version"] is None


def test_switched_on_with_a_model(models, sim):
    c = _client(models, risk_model=sim)
    r = c.post("/v1/screen", json=MAM_BASE, headers=HG).json()
    assert r["ml_risk"]["model_version"] == sim.version and r["ml_risk"]["non_clinical"] is True
    assert c.get("/version", headers=HG).json()["risk_model_version"] == sim.version
    comp = {x["name"]: x for x in c.get("/v1/about", headers=HG).json()["components"]}
    assert comp["ml_risk"]["state"] == "ok" and "SIMULATED" in comp["ml_risk"]["detail"]
    assert c.get("/health").json() == {"status": "ok"}


def test_environment_switch_refuses_simulated_models_unless_allowed(models, monkeypatch):
    monkeypatch.setenv("THANZI_RISK_ENABLED", "1")
    monkeypatch.setenv("THANZI_RISK_MODEL_DIR", str(SIM_DIR))
    monkeypatch.delenv("THANZI_RISK_ALLOW_SIMULATED", raising=False)
    c = _client(models)
    assert "ml_risk" not in c.post("/v1/screen", json=MAM_BASE, headers=HG).json()
    assert {x["name"]: x for x in c.get("/v1/about", headers=HG).json()["components"]}["ml_risk"]["state"] == "degraded"
    assert c.get("/health").json() == {"status": "ok"}              # a refused risk model never degrades screening
    monkeypatch.setenv("THANZI_RISK_ALLOW_SIMULATED", "1")
    assert "ml_risk" in _client(models).post("/v1/screen", json=MAM_BASE, headers=HG).json()


def test_missing_risk_directory_starts_cleanly(models, monkeypatch, tmp_path):
    monkeypatch.setenv("THANZI_RISK_ENABLED", "1")
    monkeypatch.setenv("THANZI_RISK_MODEL_DIR", str(tmp_path))
    c = _client(models)
    assert c.post("/v1/screen", json=MAM_BASE, headers=HG).status_code == 200


def test_openapi_documents_the_risk_block(models):
    schemas = create_app(models=models, gateway_key=GW).openapi()["components"]["schemas"]
    assert "RiskOut" in schemas and "ml_risk" in schemas["WorkerResponse"]["properties"]
    assert "risk_model_version" in schemas["VersionResponse"]["properties"]
