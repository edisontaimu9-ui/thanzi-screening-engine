"""Risk model package: trees and exact explanations, model file refusal rules, features, metrics, dataset checks,
simulation, and the training script. Pure Python except the parity tests, which skip without scikit-learn or XGBoost."""
import copy
import itertools
import json
import random
import subprocess
import sys
from math import factorial
from pathlib import Path

import pytest

from thanzi_screen.ml.risk import RISK_FEATURES, RiskModel, RiskModelError, load_risk_model, risk_features, risk_vector
from thanzi_screen.ml.risk import evaluate as ev
from thanzi_screen.ml.risk.data import COLUMNS, load_dataset, write_dataset
from thanzi_screen.ml.risk.features import FORBIDDEN_PARTS, MONOTONE, Prior
from thanzi_screen.ml.risk.model import SCHEMA
from thanzi_screen.ml.risk.simulate import simulate_rows
from thanzi_screen.ml.risk.trees import TreeEnsemble, f32, logit, sigmoid
from thanzi_screen.rules import Appetite, ClinicalInputs

ROOT = Path(__file__).resolve().parents[2]
SIM_DIR = ROOT / "models" / "risk_sim"
FULL = ClinicalInputs(muac_cm=12.0, appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset())


def leaf(v, c):
    return {"v": v, "c": c}


T1 = {"f": 0, "t": 0.5, "c": 100, "l": {"f": 1, "t": 1.5, "c": 60, "l": leaf(1.0, 20), "r": leaf(-0.5, 40)},
      "r": {"f": 0, "t": 2.5, "c": 40, "l": leaf(0.3, 10), "r": {"f": 2, "t": 0.0, "c": 30, "l": leaf(2.0, 5), "r": leaf(0.1, 25)}}}
T2 = {"f": 2, "t": 0.1, "c": 100, "l": leaf(0.4, 70), "r": {"f": 1, "t": 0.2, "c": 30, "l": leaf(-1.0, 10), "r": leaf(0.7, 20)}}


def _brute_shapley(trees, x, n=3):
    """Exact Shapley values of the path-dependent value function, by enumerating feature subsets."""
    def val(node, S):
        if "v" in node:
            return node["v"]
        if node["f"] in S:
            return val(node["l"] if x[node["f"]] <= node["t"] else node["r"], S)
        return (node["l"]["c"] * val(node["l"], S) + node["r"]["c"] * val(node["r"], S)) / node["c"]
    phi = [0.0] * n
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for r in range(n):
            for S in itertools.combinations(others, r):
                w = factorial(r) * factorial(n - r - 1) / factorial(n)
                phi[i] += w * (sum(val(t, set(S) | {i}) for t in trees) - sum(val(t, set(S)) for t in trees))
    return phi


# ---------------------------------------------------------------- trees
@pytest.mark.parametrize("kind", ["gbm_logit", "rf_prob"])
def test_treeshap_equals_brute_force_shapley_and_adds_up(kind):
    trees = [copy.deepcopy(T1), copy.deepcopy(T2)]
    if kind == "rf_prob":                              # leaf values must be probabilities
        for t in trees:
            stack = [t]
            while stack:
                n = stack.pop()
                if "v" in n:
                    n["v"] = 1 / (1 + 2.718281828 ** -n["v"])
                else:
                    stack += [n["l"], n["r"]]
    E = TreeEnsemble(["a", "b", "c"], kind, "le", trees, base=-1.0 if kind == "gbm_logit" else 0.0)
    rng = random.Random(1)
    for _ in range(150):
        x = [rng.choice([0, 1, 2, 3, 0.25, 1.6]) for _ in range(3)]
        base, phi = E.contributions(x)
        bf = _brute_shapley(trees, [f32(v) for v in x])
        if kind == "rf_prob":
            bf = [b / 2 for b in bf]
        assert max(abs(a - b) for a, b in zip(phi, bf)) < 1e-9
        assert abs(base + sum(phi) - E.raw_output(x)) < 1e-9


def test_split_rules_differ_only_at_the_threshold():
    t = {"f": 0, "t": 1.0, "c": 2, "l": leaf(0.0, 1), "r": leaf(1.0, 1)}
    le = TreeEnsemble(["a"], "gbm_logit", "le", [copy.deepcopy(t)])
    lt = TreeEnsemble(["a"], "gbm_logit", "lt", [copy.deepcopy(t)])
    assert le.raw_output([1.0]) == 0.0 and lt.raw_output([1.0]) == 1.0
    assert le.raw_output([1.5]) == lt.raw_output([1.5]) == 1.0


def test_lt_thresholds_are_rounded_to_32_bit_like_xgboost():
    t = {"f": 0, "t": 2.857143, "c": 2, "l": leaf(0.0, 1), "r": leaf(1.0, 1)}   # decimal text of a float32 cut
    lt = TreeEnsemble(["a"], "gbm_logit", "lt", [t])
    assert lt.raw_output([f32(2.857143)]) == 1.0          # equal to the cut goes right, as in XGBoost


def test_ensemble_round_trips_and_is_deterministic():
    E = TreeEnsemble(["a", "b", "c"], "gbm_logit", "le", [copy.deepcopy(T1), copy.deepcopy(T2)], base=0.2)
    E2 = TreeEnsemble.from_dict(json.loads(json.dumps(E.to_dict())))
    x = [0.0, 2.0, 1.0]
    assert E.raw_output(x) == E2.raw_output(x) and E.contributions(x) == E2.contributions(x)


@pytest.mark.parametrize("mutate,why", [
    (lambda t: t["l"].update(c=0), "zero cover"),
    (lambda t: t["l"].update(c=1), "covers do not add up"),
    (lambda t: t.update(f=9), "feature index"),
    (lambda t: t.update(t=float("inf")), "threshold"),
    (lambda t: t["l"]["l"].update(v=float("nan")), "leaf value"),
])
def test_bad_trees_are_refused(mutate, why):
    t = copy.deepcopy(T1)
    mutate(t)
    with pytest.raises(RiskModelError):
        TreeEnsemble(["a", "b", "c"], "gbm_logit", "le", [t])


def test_too_deep_trees_are_refused():
    node = leaf(0.0, 1)
    for _ in range(12):
        node = {"f": 0, "t": 0.5, "c": 2, "l": node, "r": leaf(0.0, 1)}
        node["c"] = node["l"]["c"] + 1
    with pytest.raises(RiskModelError):
        TreeEnsemble(["a"], "gbm_logit", "le", [node])


def _random_data(n=600, d=len(RISK_FEATURES), seed=0):
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(seed)
    X = rng.normal(size=(n, d)).round(2)
    y = (X[:, 2] * -1.2 + X[:, 5] * 0.8 + rng.normal(size=n) > 0.8).astype(int)
    return X, y


def test_random_forest_export_matches_scikit_learn():
    pytest.importorskip("sklearn")
    from sklearn.ensemble import RandomForestClassifier
    from thanzi_screen.ml.risk.export import from_sklearn_forest
    X, y = _random_data()
    rf = RandomForestClassifier(n_estimators=15, max_depth=4, min_samples_leaf=20, random_state=0, n_jobs=1).fit(X, y)
    E = from_sklearn_forest(rf, list(RISK_FEATURES))
    assert max(abs(E.probability(list(x)) - p) for x, p in zip(X, rf.predict_proba(X)[:, 1])) < 1e-9
    base, phi = E.contributions(list(X[0]))
    assert abs(base + sum(phi) - E.raw_output(list(X[0]))) < 1e-9


def test_xgboost_export_matches_the_library():
    xgb = pytest.importorskip("xgboost")
    from thanzi_screen.ml.risk.export import from_xgboost
    X, y = _random_data()
    m = xgb.XGBClassifier(n_estimators=30, max_depth=3, learning_rate=0.2, tree_method="hist", random_state=0, n_jobs=1).fit(X, y)
    E = from_xgboost(m.get_booster(), list(RISK_FEATURES), list(X[0]))
    assert max(abs(E.probability(list(x)) - p) for x, p in zip(X, m.predict_proba(X)[:, 1])) < 1e-5
    base, phi = E.contributions(list(X[5]))
    assert abs(base + sum(phi) - E.raw_output(list(X[5]))) < 1e-9


# ---------------------------------------------------------------- model file
def _spec():
    return json.loads((SIM_DIR / "risk_model.json").read_text())


def test_shipped_simulated_model_is_refused_unless_allowed():
    with pytest.raises(RiskModelError, match="simulated"):
        load_risk_model(SIM_DIR)
    m = load_risk_model(SIM_DIR, allow_simulated=True)
    assert m.simulated and not m.clinical_use and m.provenance == "simulated"


@pytest.mark.parametrize("edit", [
    lambda s: s.update(schema="other"),
    lambda s: s.pop("threshold"),
    lambda s: s.update(threshold=1.5),
    lambda s: s["calibration"].update(a=-1.0),
    lambda s: s["calibration"].update(b=float("nan")),
    lambda s: s.update(clinical_use=True),                       # simulated can never be clinical
    lambda s: s.update(kind="rf_prob"),
    lambda s: s["model"].update(names=list(reversed(s["model"]["names"]))),
    lambda s: s["target"].pop("plain"),
    lambda s: s["eligibility"].update(age_months_min=30.0, age_months_max=10.0),
    lambda s: s.update(provenance="unknown"),
])
def test_bad_model_files_are_refused(edit):
    s = _spec()
    edit(s)
    with pytest.raises(RiskModelError):
        RiskModel(s)


def test_real_models_need_governance_and_a_passed_acceptance_check():
    s = _spec()
    s.update(provenance="real", clinical_use=False)
    with pytest.raises(RiskModelError, match="ethics"):
        RiskModel(s)
    s["governance"] = {"ethics_ref": "E-1", "data_agreement_ref": "D-1", "clinical_signoff": "S-1"}
    with pytest.raises(RiskModelError, match="acceptance"):
        RiskModel(s)
    s["acceptance"] = {"set": True, "passed": False}
    with pytest.raises(RiskModelError, match="acceptance"):
        RiskModel(s)
    s["acceptance"] = {"set": True, "passed": True}
    assert RiskModel(s).provenance == "real"


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(RiskModelError):
        load_risk_model(tmp_path, allow_simulated=True)


def test_calibration_keeps_the_order_of_risks():
    m = load_risk_model(SIM_DIR, allow_simulated=True)
    ps = sorted(m.probability([0.0] * 0 + [30.0, 1.0, z, z, z, 12.0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0])[1] for z in (-3, -2, -1, 0, 1))
    raws = sorted(m.probability([30.0, 1.0, z, z, z, 12.0, 0, 0, 0, 0, 0, 0, 0, 0, 0.0])[0] for z in (-3, -2, -1, 0, 1))
    assert ps == sorted(ps) and raws == sorted(raws)


def test_contributions_add_up_for_the_logistic_model():
    m = load_risk_model(SIM_DIR, allow_simulated=True)
    x = [20.0, 1.0, -1.5, -2.0, -2.2, 11.9, 0, 1, 0, 1, 0, 0, 0, 1, -3.0]
    base, parts, unit = m.contributions(x)
    assert unit == "logit" and abs(base + sum(parts) - logit(m.model.predict_proba(x))) < 1e-9


# ---------------------------------------------------------------- features
def test_feature_names_are_leak_free_and_independent_of_the_rules():
    for n in RISK_FEATURES:
        assert not any(p in n for p in FORBIDDEN_PARTS), n
    assert set(MONOTONE) <= set(RISK_FEATURES)


@pytest.mark.parametrize("args,reason", [
    (("male", 100, 5.5, 60.0, "length", FULL), "age_outside_model_range"),                      # 3 months
    (("male", 1900, 14.0, 105.0, "height", FULL), "age_outside_model_range"),                   # over 60 months
    (("male", 500, 9.5, 75.0, "length", ClinicalInputs(appetite=Appetite.PASSED)), "muac_missing"),
    (("male", 500, 95.0, 75.0, "length", FULL), "measurement_not_assessable"),                  # decimal slip
    (("male", 500, -1.0, 75.0, "length", FULL), "invalid_input"),
])
def test_children_who_cannot_be_scored_get_a_reason_not_a_guess(args, reason):
    f, why = risk_features(*args)
    assert f is None and why == reason


def test_unassessed_danger_signs_are_flagged_not_assumed_absent():
    f, _ = risk_features("male", 500, 9.5, 75.0, "length", ClinicalInputs(muac_cm=12.0))
    assert f["danger_unknown"] == 1.0 and f["compl_unknown"] == 1.0 and f["appetite_not_done"] == 1.0
    g, _ = risk_features("male", 500, 9.5, 75.0, "length", FULL)
    assert g["danger_unknown"] == 0.0 and g["appetite_failed"] == 0.0


def test_previous_visit_is_used_only_when_the_interval_is_sensible():
    base = ("male", 500, 9.5, 75.0, "length", FULL)
    assert risk_features(*base, Prior(470, 9.8))[0]["weight_rate_g_per_day"] == pytest.approx(-10.0)
    for prior in (None, Prior(495, 9.0), Prior(300, 8.0), Prior(470, 0.0)):       # none, too short, too long, bad weight
        f, _ = risk_features(*base, prior)
        assert f["has_previous"] == 0.0 and f["weight_rate_g_per_day"] == 0.0


def test_vector_follows_the_declared_order():
    f, _ = risk_features("female", 500, 9.5, 75.0, "length", FULL)
    assert risk_vector(f) == [f[n] for n in RISK_FEATURES]


# ---------------------------------------------------------------- metrics
def test_metrics_known_values():
    assert ev.auroc([.1, .4, .35, .8], [0, 0, 1, 1]) == 0.75
    assert ev.auprc([.1, .4, .35, .8], [0, 0, 1, 1]) == pytest.approx(5 / 6)
    assert ev.brier([0.0, 1.0], [0, 1]) == 0.0
    t = ev.at_threshold([.9, .8, .2, .1], [1, 0, 1, 0], 0.5)
    assert (t["tp"], t["fp"], t["fn"], t["tn"]) == (1, 1, 1, 1) and t["alert_rate"] == 0.5


def test_platt_recovers_a_known_miscalibration():
    rng = random.Random(3)
    zs = [rng.gauss(0, 1.5) for _ in range(20000)]
    y = [1 if rng.random() < sigmoid(2 * z - 1) else 0 for z in zs]
    a, b = ev.fit_platt([sigmoid(z) for z in zs], y)
    assert a == pytest.approx(2.0, abs=0.12) and b == pytest.approx(-1.0, abs=0.12)


def test_alert_rate_threshold_never_exceeds_the_rate():
    rng = random.Random(4)
    p = [round(rng.random(), 2) for _ in range(2000)]          # many ties
    t = ev.threshold_for_alert_rate(p, 0.10)
    assert sum(1 for v in p if v >= t) <= 0.10 * len(p)


def test_bootstrap_is_seeded():
    rng = random.Random(5)
    p = [rng.random() for _ in range(300)]
    y = [1 if rng.random() < v else 0 for v in p]
    assert ev.bootstrap_ci(ev.auroc, p, y, seed=1) == ev.bootstrap_ci(ev.auroc, p, y, seed=1)


# ---------------------------------------------------------------- simulation and dataset
def test_simulation_is_deterministic_and_marked_non_clinical():
    a, ea = simulate_rows(1500, 3)
    b, eb = simulate_rows(1500, 3)
    assert a == b and ea == eb
    assert ea["provenance"] == "simulated" and ea["non_clinical"] is True
    assert 0.05 < ea["observed_prevalence"] < 0.15
    assert all(set(r) == set(COLUMNS) for r in a)


def test_dataset_loader_refuses_unverified_tampered_or_identifying_data(tmp_path):
    rows, extra = simulate_rows(800, 3)
    write_dataset(rows, extra, tmp_path)
    csv_path = tmp_path / "risk_dataset.csv"
    with pytest.raises(RiskModelError, match="simulated"):
        load_dataset(csv_path)
    loaded, manifest = load_dataset(csv_path, allow_simulated=True)
    assert len(loaded) == len(rows) and manifest["provenance"] == "simulated"
    original = csv_path.read_text()
    csv_path.write_text(original.replace("syn-", "syx-", 1))
    with pytest.raises(RiskModelError, match="checksum"):
        load_dataset(csv_path, allow_simulated=True)
    csv_path.write_text(original)
    (tmp_path / "MANIFEST.json").unlink()
    with pytest.raises(RiskModelError, match="manifest"):
        load_dataset(csv_path, allow_simulated=True)


def test_dataset_with_an_identifier_column_is_refused(tmp_path):
    rows, extra = simulate_rows(500, 3)
    write_dataset(rows, extra, tmp_path)
    p = tmp_path / "risk_dataset.csv"
    p.write_text(p.read_text().replace("district", "village", 1))
    import hashlib
    m = json.loads((tmp_path / "MANIFEST.json").read_text())
    m["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (tmp_path / "MANIFEST.json").write_text(json.dumps(m))
    with pytest.raises(RiskModelError, match="identifier"):
        load_dataset(p, allow_simulated=True)


def test_real_dataset_needs_governance_fields(tmp_path):
    rows, extra = simulate_rows(500, 3)
    write_dataset(rows, {**extra, "provenance": "real"}, tmp_path)
    with pytest.raises(RiskModelError, match="real dataset"):
        load_dataset(tmp_path / "risk_dataset.csv")


# ---------------------------------------------------------------- training script
def _train(out, data, *extra):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "train_risk.py"), "--data", str(data / "risk_dataset.csv"),
                           "--out", str(out), "--candidates", "lr", *extra], capture_output=True, text=True, cwd=ROOT)


def test_training_refuses_simulated_data_without_the_flag_and_is_reproducible(tmp_path):
    rows, extra = simulate_rows(4500, 5)
    data = tmp_path / "data"
    write_dataset(rows, extra, data)
    refused = _train(tmp_path / "x", data)
    assert refused.returncode == 2 and "refused" in refused.stderr
    a = _train(tmp_path / "a", data, "--allow-simulated")
    b = _train(tmp_path / "b", data, "--allow-simulated")
    assert a.returncode == 0 and b.returncode == 0, a.stderr + b.stderr
    assert (tmp_path / "a" / "risk_model.json").read_bytes() == (tmp_path / "b" / "risk_model.json").read_bytes()
    model = load_risk_model(tmp_path / "a", allow_simulated=True)
    assert model.simulated and model.kind == "logistic" and 0 < model.threshold < 1
    card = (tmp_path / "a" / "RISK_MODEL_CARD.md").read_text()
    assert "SIMULATED OUTCOMES. NOT CLINICAL" in card and "Acceptance thresholds NOT SET" in card
