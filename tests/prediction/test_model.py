"""The shipped model, its safeguards, explanations and the card. Standard library only: no training library is needed here."""
import copy
import json
import math
import random
import subprocess
import sys
from pathlib import Path

import pytest

from thanzi_screen.prediction import (
    FEATURE_NAMES, Preprocessor, SimConfig, TargetConfig, build_examples, build_features, simulate_children,
)
from thanzi_screen.prediction import explain as ex
from thanzi_screen.prediction.errors import PredictionModelError
from thanzi_screen.prediction.model import SCHEMA, PredictionModel, load_prediction_model
from thanzi_screen.prediction.predict import ADVISORY, assess_child, assess_features
from thanzi_screen.prediction.features import FEATURES
from thanzi_screen.prediction.model import DEFAULT_REQUIRED
from thanzi_screen.prediction.status import input_status
from thanzi_screen.prediction.trees import TreeEnsemble

SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(scope="module")
def children():
    return simulate_children(SimConfig(n_children=300, seed=21))


@pytest.fixture(scope="module")
def pre(children):
    rows = [e.features for e in build_examples(children, TargetConfig()) if e.split == "train"]
    return Preprocessor.fit(rows)


def _spec(pre, kind="logistic", **over):
    cols = list(pre.columns)
    j = cols.index("whz")
    if kind == "logistic":
        coef = [0.0] * len(cols)
        coef[j] = -1.2
        coef[cols.index("muac_cm")] = -0.6
        coef[cols.index("fever_2wk")] = 0.5
        part = {"type": "logistic", "names": cols, "coef": coef, "bias": -1.5, "column_mean": [0.0] * len(cols)}
    else:       # two small trees on whz (lower is riskier). Covers add up. Left branch is x < t for "lt", x <= t for "le".
        def leaf(v, c):
            return {"v": v, "c": c}
        tree = {"f": j, "t": -0.5, "c": 100.0, "l": leaf(0.8 if kind == "gbm_logit" else 0.6, 40.0), "r": leaf(-0.4 if kind == "gbm_logit" else 0.1, 60.0)}
        part = {"type": "tree_ensemble", "kind": kind, "split": "lt" if kind == "gbm_logit" else "le", "names": cols,
                "base": -1.0 if kind == "gbm_logit" else 0.0, "trees": [copy.deepcopy(tree), copy.deepcopy(tree)]}
    spec = {"schema": SCHEMA, "version": "t-sim-0.1.0", "kind": kind, "provenance": "simulated", "clinical_use": False,
            "target": {"name": "future_wasting", "plain": "wasting", "definition": "test", "horizon_min_days": 28, "horizon_max_days": 180},
            "preprocessor": copy.deepcopy(pre.to_dict()), "model": part, "calibration": {"a": 1.0, "b": 0.0},
            "strata": {"cutoffs": {"elevated": 0.25, "high": 0.45}}, "eligibility": {"age_months_min": 6.0, "age_months_max": 60.0},
            "safeguards": {"max_missing_features": 20}, "acceptance": {"set": False, "passed": None, "checks": []}}
    spec.update(over)
    return spec


def _model(pre, kind="logistic", **over):
    return PredictionModel(_spec(pre, kind, **over))


def _row(children, pre):
    c = children[0]
    return build_features(c, len(c.observations) - 1)


# ---------- the file is refused unless every part is valid (fail closed) ----------
def test_a_simulated_model_can_never_be_marked_for_clinical_use(pre):
    with pytest.raises(PredictionModelError, match="never be marked for clinical use"):
        _model(pre, clinical_use=True)


def test_a_simulated_model_is_refused_by_the_loader_unless_allowed(pre, tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(_spec(pre), sort_keys=True))
    with pytest.raises(PredictionModelError, match="simulated"):
        load_prediction_model(p)
    assert load_prediction_model(p, allow_simulated=True).version == "t-sim-0.1.0"


def test_real_data_needs_governance_and_acceptance(pre):
    base = dict(provenance="real", clinical_use=True)
    with pytest.raises(PredictionModelError, match="ethics"):
        _model(pre, **base)
    gov = {"ethics_ref": "E1", "data_agreement_ref": "D1", "clinical_signoff": "S1"}
    with pytest.raises(PredictionModelError, match="acceptance"):
        _model(pre, governance=gov, **base)
    assert _model(pre, governance=gov, acceptance={"set": True, "passed": True, "checks": []}, **base).clinical_use is True
    with pytest.raises(PredictionModelError, match="ethics"):
        _model(pre, governance={**gov, "clinical_signoff": " "}, acceptance={"set": True, "passed": True}, **base)


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s.update(schema="x"), "not a prediction model"),
    (lambda s: s.pop("strata"), "missing a required part"),
    (lambda s: s.update(calibration={"a": -1.0, "b": 0.0}), "positive slope"),
    (lambda s: s.update(calibration={"a": float("nan"), "b": 0.0}), "positive slope"),
    (lambda s: s["strata"]["cutoffs"].update(elevated=0.6, high=0.4), "strata cut-offs"),
    (lambda s: s["strata"]["cutoffs"].update(high=1.0), "strata cut-offs"),
    (lambda s: s.update(eligibility={"age_months_min": 30.0, "age_months_max": 12.0}), "eligibility"),
    (lambda s: s.update(kind="forest"), "unknown model kind"),
    (lambda s: s["target"].pop("horizon_min_days"), "horizon"),
    (lambda s: s["model"]["coef"].pop(), "logistic model is invalid"),
    (lambda s: s["model"]["names"].reverse(), "do not match the preprocessor"),
    (lambda s: s["model"].update(bias=float("inf")), "logistic model is invalid"),
    (lambda s: s["safeguards"].update(max_missing_features=-1), "max_missing_features"),
    (lambda s: s["preprocessor"]["features"].pop("whz"), "required input is not one of the model's inputs"),
])
def test_a_bad_model_file_is_refused(pre, mutate, message):
    spec = _spec(pre)
    mutate(spec)
    with pytest.raises(PredictionModelError, match=message):
        PredictionModel(spec)


def test_an_unreadable_or_oversized_file_is_refused(tmp_path):
    with pytest.raises(PredictionModelError, match="missing or unreadable"):
        load_prediction_model(tmp_path / "none.json")
    (tmp_path / "bad.json").write_text("{not json")
    with pytest.raises(PredictionModelError, match="missing or unreadable"):
        load_prediction_model(tmp_path / "bad.json", allow_simulated=True)


def test_tree_model_with_the_wrong_kind_or_columns_is_refused(pre):
    spec = _spec(pre, "gbm_logit")
    spec["model"]["kind"] = "rf_prob"
    with pytest.raises(PredictionModelError, match="does not match kind"):
        PredictionModel(spec)
    spec = _spec(pre, "rf_prob")
    spec["model"]["names"] = spec["model"]["names"][:-1]
    with pytest.raises(PredictionModelError):
        PredictionModel(spec)


# ---------- columns keep their order through JSON written with sorted keys (a real bug caught during export) ----------
def test_columns_do_not_depend_on_the_key_order_of_the_preprocessor_file(pre, children):
    shuffled = json.loads(json.dumps(pre.to_dict(), sort_keys=True))
    again = Preprocessor.from_dict(shuffled)
    assert again.columns == pre.columns
    row = _row(children, pre)
    assert again.transform(row) == pre.transform(row)


# ---------- strata, escalate-only wording and safeguards ----------
def test_strata_have_no_low_risk_label_and_the_order_is_kept(pre):
    m = _model(pre)
    assert [m.stratum(p) for p in (0.0, 0.24, 0.25, 0.44, 0.45, 0.99)] == [None, None, "elevated", "elevated", "high", "high"]
    ps = [m.probability(m.vectorise({**{n: 0.0 for n in FEATURE_NAMES}, "whz": z}))[1] for z in (-3, -2, -1, 0, 1)]
    assert ps == sorted(ps, reverse=True)


def _features(children, pre, **over):
    f = dict(_row(children, pre))
    f.update(over)
    return f


def test_a_child_with_extra_concern_gets_a_message_drivers_and_the_advisory(children, pre):
    m = _model(pre)
    out = assess_features(m, _features(children, pre, whz=-3.0, muac_cm=10.5, fever_2wk=1.0))
    assert out["scored"] and out["elevated"] is True and out["stratum"] in ("elevated", "high")
    assert "closer follow-up" in out["message"] and out["advisory"] == ADVISORY and out["non_clinical"] is True
    assert out["drivers"] and all(d["direction"] == "raises" for d in out["drivers"]) and len(out["drivers"]) <= 3
    assert "low risk" not in json.dumps(out).lower()


def test_no_extra_concern_means_no_message_and_never_low_risk(children, pre):
    m = _model(pre)
    out = assess_features(m, _features(children, pre, whz=2.0, muac_cm=16.0, fever_2wk=0.0))
    assert out["scored"] and out["elevated"] is False and out["stratum"] is None
    assert out["message"] is None and out["drivers"] == []
    assert "low" not in json.dumps({k: v for k, v in out.items() if k != "advisory"}).lower()


@pytest.mark.parametrize("age", [5.9, 60.0, 80.0, None])
def test_a_child_outside_the_age_range_is_not_scored(children, pre, age):
    out = assess_features(_model(pre), _features(children, pre, age_months=age))
    assert out["scored"] is False and out["not_scored_reason"] == "age_outside_model_range" and out["message"] is None


def test_a_missing_essential_input_is_not_scored_and_not_imputed(children, pre):
    for n in ("whz", "oedema_present"):
        f = _features(children, pre)
        f[n] = None
        out = assess_features(_model(pre), f)
        assert out["not_scored_reason"] == "essential_input_unavailable" and out["scored"] is False


def test_missing_non_essential_inputs_do_not_stop_the_check_and_are_reported(children, pre):
    m = _model(pre)
    f = _features(children, pre)
    for n in FEATURE_NAMES:
        if n not in m.required_features and FEATURES[n].group in ("clinical", "feeding", "maternal", "socioeconomic"):
            f[n] = None
    assert m.check_inputs(f) is None
    st = assess_features(m, f)["inputs"]
    assert "clinical" in st["not_assessed"] and set(st) == {"not_assessed", "not_applicable", "unavailable"}


def test_input_states_are_kept_apart():
    f = dict.fromkeys(FEATURE_NAMES)
    f.update(age_months=8.0, birth_order=1)
    none_, bad = input_status(f), input_status(f, "unavailable")
    assert "longitudinal" in none_["not_applicable"] and "longitudinal" in bad["unavailable"]
    assert "demographic" in none_["not_assessed"] and "feeding" in none_["not_assessed"]


def test_pathway_required_features_must_be_known(pre):
    with pytest.raises(PredictionModelError, match="required_features"):
        _model(pre, pathway={"name": "x", "required_features": ["nope"]})


def test_a_gap_never_seen_in_training_is_refused(children, pre):
    never = next(n for n in FEATURE_NAMES if not pre.spec["features"][n]["indicator"] and n not in DEFAULT_REQUIRED)      # essential inputs have their own check
    out = assess_features(_model(pre), _features(children, pre, **{never: None}))
    assert out["not_scored_reason"] == "gap_never_seen_in_training" and out["scored"] is False


def test_the_assessment_never_raises_and_logs_no_data(children, pre, caplog):
    m = _model(pre)
    f = _features(children, pre)
    f["whz"] = "abc"                                # malformed row
    out = assess_features(m, f)
    assert out["scored"] is False and out["not_scored_reason"] == "model_error"
    assert "whz" not in caplog.text and str(f["age_months"]) not in caplog.text
    out = assess_features(m, {"age_months": "abc"})
    assert out["scored"] is False


def test_assess_child_uses_only_visits_up_to_the_index(children, pre):
    m = _model(pre)
    c = next(c for c in children if len(c.observations) >= 4)
    from dataclasses import replace
    later = tuple(replace(o, visit=replace(o.visit, weight_kg=o.visit.weight_kg * 0.5)) if k > 1 else o for k, o in enumerate(c.observations))
    changed = replace(c, observations=later)
    assert assess_child(m, c, 1, audit=True) == assess_child(m, changed, 1, audit=True)


def test_the_classification_is_not_an_input(pre):
    assert not any(any(w in n for w in ("cmam", "tier", "class", "referral")) for n in pre.names)


# ---------- explanations are exact ----------
@pytest.mark.parametrize("kind", ["logistic", "gbm_logit", "rf_prob"])
def test_baseline_plus_contributions_equals_the_model_output(children, pre, kind):
    m = _model(pre, kind)
    rng = random.Random(0)
    for _ in range(25):
        f = _features(children, pre, whz=rng.uniform(-4, 2), muac_cm=rng.uniform(10, 17), fever_2wk=float(rng.random() < .5))
        x = m.vectorise(f)
        base, phi, unit = m.contributions(x)
        assert abs(base + sum(phi) - m.raw_output(x)) < 1e-9
        assert unit == ("probability" if kind == "rf_prob" else "logit")


def test_audit_lists_every_feature_with_the_missing_flag_folded_in(children, pre):
    m = _model(pre)
    out = assess_features(m, _features(children, pre, whz=-3.0), audit=True)
    audit = out["explanation"]
    assert {c["feature"] for c in audit["contributions"]} == set(FEATURE_NAMES)
    assert abs(audit["baseline"] + sum(c["contribution"] for c in audit["contributions"]) - math.log(out["raw_probability"] / (1 - out["raw_probability"]))) < 1e-4


def test_every_feature_has_text_or_is_deliberately_hidden():
    for n in FEATURE_NAMES:
        shown = ex.phrase(n, 1.0) or ex.phrase(n, 0.0)
        assert shown or n in ex.NOT_SHOWN, n
    assert ex.phrase("sex_male", 1.0) is None
    assert ex.phrase("whz", None) == "weight-for-height z-score: not recorded"


def test_a_missing_flag_that_raises_risk_is_shown_as_not_recorded(children, pre):
    flagged = next((n for n in FEATURE_NAMES if pre.spec["features"][n]["indicator"] and n not in ex.NOT_SHOWN), None)
    if flagged is None:
        pytest.skip("no feature had gaps in this sample")
    spec = _spec(pre)
    cols = spec["model"]["names"]
    spec["model"]["coef"][cols.index(flagged + "_missing")] = 5.0
    m = PredictionModel(spec)
    f = _features(children, pre, **{flagged: None})
    drivers, _ = ex.explain(m, m.vectorise(f), f)
    assert drivers and drivers[0]["text"].endswith("not recorded")


# ---------- the tree evaluator here and the one in ml.risk agree exactly ----------
def _random_tree(rng, n_features, depth, cover):
    if depth == 0 or rng.random() < 0.2:
        return {"v": rng.uniform(-1, 1), "c": cover}
    k = rng.uniform(0.3, 0.7)
    return {"f": rng.randrange(n_features), "t": rng.uniform(-1, 1), "c": cover,
            "l": _random_tree(rng, n_features, depth - 1, cover * k), "r": _random_tree(rng, n_features, depth - 1, cover * (1 - k))}


@pytest.mark.parametrize("kind,split", [("gbm_logit", "lt"), ("rf_prob", "le")])
def test_the_copied_tree_code_matches_ml_risk_exactly(kind, split):
    from thanzi_screen.ml.risk.trees import TreeEnsemble as Ref
    rng = random.Random(4)
    names = [f"f{i}" for i in range(6)]
    trees = [_random_tree(rng, 6, 4, 100.0) for _ in range(5)]
    if kind == "rf_prob":
        trees = [json.loads(json.dumps(t).replace('"v"', '"v"')) for t in trees]
    a, b = TreeEnsemble(names, kind, split, copy.deepcopy(trees), 0.3), Ref(names, kind, split, copy.deepcopy(trees), 0.3)
    for _ in range(40):
        x = [rng.uniform(-1.5, 1.5) for _ in names]
        assert a.raw_output(x) == b.raw_output(x)
        assert a.contributions(x) == b.contributions(x)


# ---------- the runtime stays standard library and independent of the screening and ml packages ----------
def test_runtime_modules_load_no_training_library_and_no_screening_module():
    code = ("import sys; import thanzi_screen.prediction, thanzi_screen.prediction.model, thanzi_screen.prediction.predict, "
            "thanzi_screen.prediction.explain, thanzi_screen.prediction.card, thanzi_screen.prediction.export, thanzi_screen.prediction.trees;"
            "print('\\n'.join(sorted(m.split('.')[0] if not m.startswith('thanzi_screen') else m for m in sys.modules)))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONPATH": str(SRC)}, check=True)
    mods = set(out.stdout.split())
    assert not mods & {"numpy", "sklearn", "xgboost", "scipy"}, mods
    assert not any(m.startswith(("thanzi_screen.under5", "thanzi_screen.report", "thanzi_screen.ml", "thanzi_screen.growth")) for m in mods)
