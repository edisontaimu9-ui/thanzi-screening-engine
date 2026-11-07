import json
from pathlib import Path

import pytest

from thanzi_screen.anthro import compute_anthropometry
from thanzi_screen.data import DataError, GenConfig, generate, load_dataset, write_dataset
from thanzi_screen.ml import flag_record, load_models
from thanzi_screen.ml import evaluate as ev
from thanzi_screen.ml.features import FEATURES, FORBIDDEN_FEATURE_PARTS, features_from_inputs, row_inputs, vector
from thanzi_screen.ml.flags import FIELD_MESSAGES
from thanzi_screen.ml.models import LogisticModel, TreeModel, auc
from thanzi_screen.ml.train import STATEMENT, train_all
from thanzi_screen.rules import Appetite, ClinicalInputs, OedemaGrade, classify, review

ROOT = Path(__file__).resolve().parents[2]
FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(), clinically_well_and_alert=True)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    d = tmp_path_factory.mktemp("ml")
    cfg = GenConfig(seed=11, n=6000)
    write_dataset(generate(cfg), cfg, d / "data")
    summary = train_all(d / "data" / "synthetic_children.csv", d / "models", seed=0, epochs=8)
    return d, summary


# ---- no leakage ----
def test_feature_names_have_no_forbidden_parts():
    assert len(FEATURES) == len(set(FEATURES))
    for n in FEATURES:
        assert not any(p in n for p in FORBIDDEN_FEATURE_PARTS), n


def test_features_ignore_truth_and_label_columns(trained):
    d, _ = trained
    row = load_dataset(d / "data" / "synthetic_children.csv")[5]
    f1 = vector(features_from_inputs(*row_inputs(row))[0])
    tampered = dict(row, true_weight_kg="99.99", true_wflh_z="9.9", injected_error="muac_unit_error",
                    review_needed="true", review_reasons="x", split="test", child_id="zzz")
    assert vector(features_from_inputs(*row_inputs(tampered))[0]) == f1


# ---- trained artifacts ----
def test_training_is_deterministic(trained, tmp_path):
    d, _ = trained
    train_all(d / "data" / "synthetic_children.csv", tmp_path, seed=0, epochs=8)
    for name in ("recording_error_lr.json", "recording_field_tree.json", "review_replica_diagnostic.json", "MODEL_CARD.md"):
        assert (tmp_path / name).read_bytes() == (d / "models" / name).read_bytes()


def test_training_refuses_unverified_data(trained, tmp_path):
    d, _ = trained
    (tmp_path / "x.csv").write_bytes((d / "data" / "synthetic_children.csv").read_bytes())
    with pytest.raises(DataError):
        train_all(tmp_path / "x.csv", tmp_path / "m")


def test_operating_point_and_quality(trained):
    _, s = trained
    assert s["operating_point"]["operating_point_met"]
    t = s["test"]
    assert t["ml"]["alert_rate"] <= 0.10
    assert t["ml_recall_on_missed_by_phase1"] >= 0.7
    assert t["ml"]["recall"] > t["phase1_only"]["recall"]
    assert t["auc"] > 0.9
    assert s["field"]["test_accuracy_on_error_records"] >= 0.8


def test_report_contents(trained):
    _, s = trained
    t = s["test"]
    assert set(t["by_sex"]) >= {"male", "female", "_max_recall_gap"}
    assert set(t["by_age_band"]) >= {"0-5m", "6-23m", "24-59m"}
    assert len([k for k in t["by_district"] if not k.startswith("_")]) == 28
    assert t["by_error_type"] and t["calibration"]
    assert s["boundary"]["n"] == 16


def test_model_files_labels_and_card(trained):
    d, _ = trained
    a = json.loads((d / "models" / "recording_error_lr.json").read_text())
    b = json.loads((d / "models" / "review_replica_diagnostic.json").read_text())
    assert a["production"] is True and b["production"] is False
    assert a["metadata"]["validated_on_real_data"] is False
    assert "diagnostic" in b["role"] and "Diagnostic only" in b["metrics"]["note"]
    card = (d / "models" / "MODEL_CARD.md").read_text()
    assert STATEMENT in card and "Limits" in card


def test_json_roundtrip_same_predictions(trained):
    d, _ = trained
    m = load_models(d / "models")
    a = json.loads((d / "models" / "recording_error_lr.json").read_text())["model"]
    again = LogisticModel.from_dict(json.loads(json.dumps(a)))
    x = [0.5] * len(FEATURES)
    assert again.predict_proba(x) == m.error.predict_proba(x)


# ---- inference ----
def _flags(models, weight=8.6, length=70.0, age=300, muac=13.5, **kw):
    clin = ClinicalInputs(muac_cm=muac, **{**FULL, **kw})
    return flag_record("male", age, weight, length, "length", clin, models)


def test_flags_normal_record_not_flagged(trained):
    m = load_models(trained[0] / "models")
    f = _flags(m)
    assert not f.recording_error.flagged and not f.review.needed and f.model_version


def test_flags_catch_typical_errors(trained):
    m = load_models(trained[0] / "models")
    f = _flags(m, weight=86.0)
    assert f.recording_error.flagged and f.recording_error.suggested_field == "weight"
    assert f.recording_error.messages == (FIELD_MESSAGES["weight"],)
    f = _flags(m, muac=135.0)
    assert f.recording_error.flagged and f.recording_error.suggested_field == "muac"
    assert f.recording_error.top_signals


def test_flags_with_missing_inputs_work(trained):
    m = load_models(trained[0] / "models")
    f = flag_record("female", 400, 9.0, 72.0, "length", ClinicalInputs(), m)
    assert 0.0 <= f.recording_error.probability <= 1.0 and f.review is not None


def test_flags_never_change_classification(trained):
    m = load_models(trained[0] / "models")
    for muac, w in ((11.0, 8.0), (12.0, 8.6), (13.5, 86.0), (13.5, 8.6)):
        clin = ClinicalInputs(muac_cm=muac, **FULL)
        a = compute_anthropometry(sex="male", weight_kg=w, length_height_cm=70.0, measure_position="length", age_days=300)
        before = classify(a, clin)
        flag_record("male", 300, w, 70.0, "length", clin, m)
        after = classify(a, clin)
        assert before == after


def test_mlflags_separate_from_classification_result():
    from thanzi_screen.rules import ClassificationResult
    assert "recording_error" not in ClassificationResult.__dataclass_fields__
    assert "review" not in ClassificationResult.__dataclass_fields__


# ---- rules-based review (target B) ----
def test_review_rules_reasons_and_messages():
    a = compute_anthropometry(sex="male", weight_kg=8.6, length_height_cm=70.0, measure_position="length", age_days=300)
    clin = ClinicalInputs(muac_cm=11.6, **FULL)
    r = review(a, classify(a, clin), 11.6, False)
    assert r.needed and "near_threshold_muac" in r.reasons and len(r.messages) == len(r.reasons)
    assert r.source == "rules_review_v1"
    clean = review(a, classify(a, ClinicalInputs(muac_cm=14.0, **FULL)), 14.0, False)
    assert not clean.needed and clean.reasons == ()


def test_review_matches_dataset_labels(trained):
    d, _ = trained
    for row in load_dataset(d / "data" / "synthetic_children.csv")[::40]:
        f, a, res = features_from_inputs(*row_inputs(row))
        muac = None if row["muac_cm"] == "" else float(row["muac_cm"])
        r = review(a, res, muac, row["oedema"] != "none", 0.2, 0.1)
        assert (row["review_needed"] == "true") == r.needed
        assert row["review_reasons"] == ";".join(r.reasons)


# ---- model code ----
def test_logistic_learns_simple_rule():
    import random
    rng = random.Random(1)
    X = [[rng.random(), rng.random()] for _ in range(600)]
    y = [int(x[0] > 0.6) for x in X]
    m = LogisticModel(["a", "b"]).fit(X, y, seed=1, epochs=20)
    assert auc([m.predict_proba(x) for x in X], y) > 0.95


def test_tree_learns_and_roundtrips():
    X = [[i % 10, (i * 7) % 5] for i in range(300)]
    y = ["a" if x[0] < 5 else "b" for x in X]
    t = TreeModel(["p", "q"], ["a", "b"]).fit(X, y, max_depth=2, min_leaf=5)
    assert t.predict_dist([2, 1])["a"] > 0.9 and t.predict_dist([8, 1])["b"] > 0.9
    t2 = TreeModel.from_dict(json.loads(json.dumps(t.to_dict())))
    assert t2.predict_dist([8, 1]) == t.predict_dist([8, 1])


def test_choose_threshold_respects_alert_budget():
    probs = [i / 100 for i in range(100)]
    err = [p > 0.9 for p in probs]
    op = ev.choose_threshold(probs, err, [False] * 100)
    assert op["alert_rate"] <= 0.10 and op["operating_point_met"]


# ---- shipped models ----
def test_committed_models_exist_and_load():
    m = load_models(ROOT / "models")
    assert m.version == "0.4.0"
    card = (ROOT / "models" / "MODEL_CARD.md").read_text()
    assert "Not validated on real children" in card
