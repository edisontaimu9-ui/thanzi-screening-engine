"""Anthropometric pathway: measurements only, so empty history, feeding, birth and household answers never stop a score."""
import json

import pytest

from thanzi_screen.prediction import FEATURE_NAMES, FEATURES, SimConfig, TargetConfig, build_examples, simulate_children
from thanzi_screen.prediction.errors import PredictionModelError
from thanzi_screen.prediction.model import PredictionModel
from thanzi_screen.prediction.pathways import PATHWAYS, apply_pathway, feature_names, withhold_history
from thanzi_screen.prediction.predict import assess_features
from thanzi_screen.prediction.preprocess import Preprocessor


@pytest.fixture(scope="module")
def examples():
    return build_examples(simulate_children(SimConfig(n_children=300, seed=21)), TargetConfig())


def test_a_pathway_keeps_only_its_own_inputs(examples):
    rows = apply_pathway(examples, "anthropometric")
    allowed = set(feature_names("anthropometric"))
    assert all(set(e.features) == allowed for e in rows)
    assert not allowed & {n for n in FEATURE_NAMES if FEATURES[n].group in ("clinical", "feeding", "maternal", "socioeconomic", "demographic")}


def test_history_is_withheld_for_a_repeatable_share_and_looks_like_a_first_visit(examples):
    a, b = apply_pathway(examples, "anthropometric"), apply_pathway(examples, "anthropometric")
    assert [e.features for e in a] == [e.features for e in b]
    none_hist = [e for e in a if e.features["n_prior_visits"] == 0.0]
    assert 0.2 < len(none_hist) / len(a) < 0.6 and all(e.features["d_whz"] is None for e in none_hist)
    f = withhold_history(examples[0].features)
    assert f["n_prior_visits"] == 0.0 and f["d_waz"] is None and f["whz"] == examples[0].features["whz"]


def test_full_pathway_is_unchanged(examples):
    assert [e.features for e in apply_pathway(examples, "full")] == [e.features for e in examples]


def _spec(examples, required=None):
    pre = Preprocessor.fit([e.features for e in apply_pathway(examples, "anthropometric") if e.split == "train"])
    cols = list(pre.columns)
    coef = [0.0] * len(cols)
    coef[cols.index("whz")] = -1.0
    return {"schema": "thanzi.prediction_model.v1", "version": "t-anthro-sim", "kind": "logistic", "provenance": "simulated", "clinical_use": False,
            "target": {"name": "future_wasting", "plain": "wasting", "definition": "t", "horizon_min_days": 28, "horizon_max_days": 180},
            "preprocessor": pre.to_dict(), "model": {"type": "logistic", "names": cols, "coef": coef, "bias": -1.0, "column_mean": [0.0] * len(cols)},
            "calibration": {"a": 1.0, "b": 0.0}, "strata": {"cutoffs": {"elevated": 0.25, "high": 0.45}},
            "eligibility": {"age_months_min": 6.0, "age_months_max": 60.0}, "safeguards": {"max_missing_features": 10},
            "pathway": {"name": "anthropometric", "required_features": required or list(PATHWAYS["anthropometric"]["required"])},
            "acceptance": {"set": False, "passed": None, "checks": []}}


def test_a_pathway_model_scores_a_full_row_with_everything_else_empty_and_no_history(examples):
    from thanzi_screen.prediction.model import SCHEMA
    spec = _spec(examples)
    spec["schema"] = SCHEMA
    m = PredictionModel(json.loads(json.dumps(spec, sort_keys=True)))
    f = dict.fromkeys(FEATURE_NAMES)                    # every input empty ...
    f.update(age_months=14.0, sex_male=1.0, waz=-1.5, haz=-1.0, whz=-1.8, muac_cm=12.8, oedema_present=0.0, n_prior_visits=0.0)
    out = assess_features(m, f)
    assert out["scored"] is True and out["pathway"] == "anthropometric"
    assert {"clinical", "feeding", "maternal", "socioeconomic"} <= set(out["inputs"]["not_assessed"])
    assert "longitudinal" in out["inputs"]["not_applicable"]
    f["whz"] = None                                      # ... but an essential one is still never filled in
    assert assess_features(m, f)["not_scored_reason"] == "essential_input_unavailable"


def test_a_required_input_must_belong_to_the_pathway(examples):
    from thanzi_screen.prediction.model import SCHEMA
    spec = _spec(examples, required=["age_months", "wealth_quintile"])
    spec["schema"] = SCHEMA
    with pytest.raises(PredictionModelError):
        PredictionModel(spec)
