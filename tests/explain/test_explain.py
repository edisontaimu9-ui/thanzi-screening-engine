import json
import math
import re
from pathlib import Path

import pytest

from thanzi_screen.anthro import compute_anthropometry
from thanzi_screen.data import GenConfig, generate
from thanzi_screen.data.schema import row_to_inputs
from thanzi_screen.explain import Explanation, explain
from thanzi_screen.explain import messages as M
from thanzi_screen.explain.ml_explain import contributions, sigmoid, tree_path
from thanzi_screen.explain.trace import build_trace
from thanzi_screen.ml import flag_record, load_models
from thanzi_screen.ml.features import FEATURES, features_from_inputs, vector
from thanzi_screen.rules import Appetite, ClinicalInputs, OedemaGrade, classify, review
from thanzi_screen.rules import rules_v2016 as R
from thanzi_screen.rules.review import MESSAGES as REVIEW_MESSAGES

ROOT = Path(__file__).resolve().parents[2]
FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(), clinically_well_and_alert=True)
RECORD = ("male", 500, 11.0, 80.0, "length", ClinicalInputs(muac_cm=14.0, **FULL))


@pytest.fixture(scope="module")
def models():
    return load_models()


@pytest.fixture(scope="module")
def rows():
    rows = generate(GenConfig(seed=5, n=1200))
    return rows


def _inputs(row):
    return (row["sex"], int(row["age_days"]), float(row["weight_kg"]), float(row["length_height_cm"]),
            row["measure_position"], row_to_inputs(row))


def _csv_row(r):
    """Rows from generate() hold python values. Encode them the way the CSV writer does, as strings."""
    from thanzi_screen.data.io import _fmt
    return {k: _fmt(k, v) for k, v in r.items()}


def _cases(rows):
    return [_inputs(_csv_row(r)) for r in rows]


# ---- catalogue completeness ----
def test_every_rule_has_worker_text_and_no_hiv_wording():
    assert set(M.RULE_WORKER) == set(R.RULES)
    for rid, text in M.RULE_WORKER.items():
        assert "hiv" not in text.lower(), rid


def test_every_classify_reason_code_has_text():
    src = (ROOT / "src/thanzi_screen/rules/classify.py").read_text()
    codes = set(re.findall(r'(?:reasons|missing)\.append\("([a-z_]+)"\)', src))
    assert codes and codes <= set(M.REASON_TEXT), codes - set(M.REASON_TEXT)


def test_every_review_code_has_evidence_label():
    assert set(REVIEW_MESSAGES) == set(M.REVIEW_EVIDENCE_LABEL)


def test_every_feature_has_phrase():
    f = {n: 1.0 for n in FEATURES}
    g = {n: 0.0 for n in FEATURES}
    assert set(M.FEATURE_TEXT) == set(FEATURES)
    for n in FEATURES:
        assert isinstance(M.feature_phrase(n, f), str) and M.feature_phrase(n, f)
        assert isinstance(M.feature_phrase(n, g), str) and M.feature_phrase(n, g)


def test_missing_values_are_not_shown_as_zero():
    f = {n: 0.0 for n in FEATURES}
    f.update(muac_missing=1.0, wfa_missing=1.0)
    assert M.feature_phrase("muac_cm", f) == "MUAC was not recorded"
    assert "could not be computed" in M.feature_phrase("wfa_z", f)


def test_age_caveat_text_present():
    f = {n: 0.0 for n in FEATURES}
    f["age_heap_exact"] = 1.0
    assert "date of birth is known" in M.feature_phrase("age_heap_exact", f)


# ---- faithfulness of the ML explanation ----
def test_logistic_contributions_sum_to_logit_exactly(models, rows):
    for case in _cases(rows)[:200]:
        f, _, _ = features_from_inputs(*case)
        x = vector(f)
        logit, cs = contributions(models.error, x, f)
        assert math.isclose(logit, models.error.bias + sum(c.contribution for c in cs), abs_tol=1e-12)
        assert math.isclose(sigmoid(logit), models.error.predict_proba(x), abs_tol=1e-12)
        assert len(cs) == len(FEATURES)


def test_explanation_probability_matches_flag(models, rows):
    for case in _cases(rows)[:100]:
        e = explain(*case, models)
        flags = flag_record(*case, models)
        assert e.flag_trace.probability == flags.recording_error.probability
        assert e.flag_trace.flagged == flags.recording_error.flagged
        assert math.isclose(sigmoid(e.flag_trace.logit), e.flag_trace.probability, abs_tol=1e-12)


def test_tree_path_ends_at_the_models_own_leaf(models, rows):
    for case in _cases(rows)[:150]:
        f, _, _ = features_from_inputs(*case)
        x = vector(f)
        steps, leaf, _ = tree_path(models.field, x, f)
        assert leaf == models.field.predict_dist(x)
        for s in steps:
            assert (s.value <= s.threshold) == (s.went == "<=")


def test_flag_suggested_field_is_argmax_of_leaf(models, rows):
    seen = 0
    for case in _cases(rows):
        e = explain(*case, models)
        if e.flag_trace.flagged:
            seen += 1
            assert e.flag_trace.suggested_field == max(e.flag_trace.leaf_distribution.items(), key=lambda kv: kv[1])[0]
            assert e.flag_trace.top_raising and all(c.direction == "raises" for c in e.flag_trace.top_raising)
    assert seen > 0


# ---- classification trace matches the rules ----
def test_trace_rules_equal_rules_fired_and_bands_agree(models, rows):
    for case in _cases(rows):
        sex, age, w, l, pos, cl = case
        e = explain(*case, models)
        a = compute_anthropometry(sex=sex, weight_kg=w, length_height_cm=l, measure_position=pos, age_days=age,
                                  oedema=cl.oedema != OedemaGrade.NONE)
        r = classify(a, cl)
        t = e.classification_trace
        assert tuple(x.id for x in t.rules) == r.rules_fired
        assert (t.classification, t.tier, t.programme) == (r.classification.value, r.tier.value, r.programme)
        by = {c.code: c for c in t.criteria}
        if t.pathway == "child":
            if by["muac"].used and by["muac"].status == "severe":
                assert "SAM.MUAC" in r.rules_fired
            if by["muac"].used and by["muac"].status == "moderate" and not r.classification.value.startswith("SAM"):
                assert "MAM.MUAC" in r.rules_fired
            if by["wflh_z"].used and by["wflh_z"].status == "severe":
                assert "SAM.WFLH" in r.rules_fired
            if not by["wflh_z"].used:
                assert "SAM.WFLH" not in r.rules_fired and "MAM.WFLH" not in r.rules_fired
        else:
            if by["wflh_z"].used and by["wflh_z"].status == "severe":
                assert "INF.WFL" in r.rules_fired
            if not by["wflh_z"].used:
                assert "INF.WFL" not in r.rules_fired


def _muac_criterion(m):
    a = compute_anthropometry(sex="male", weight_kg=9.0, length_height_cm=75.0, measure_position="length",
                              age_days=400, oedema=False)
    cl = ClinicalInputs(muac_cm=m)
    return {c.code: c for c in build_trace(a, cl, classify(a, cl)).criteria}["muac"]


@pytest.mark.parametrize("m,status,cutoff,margin", [
    (11.4, "severe", 11.5, -0.1), (11.5, "moderate", 11.5, 0.0),
    (12.4, "moderate", 12.5, -0.1), (12.5, "normal", 12.5, 0.0)])
def test_muac_margins_at_exact_cutoffs(m, status, cutoff, margin):
    c = _muac_criterion(m)
    assert (c.status, c.nearest_cutoff) == (status, cutoff)
    assert c.margin == pytest.approx(margin, abs=1e-9)


def test_z_margins_on_boundary_records(models, rows):
    b = [r for r in rows if r["record_type"] == "boundary"]
    assert b
    hits = 0
    for r in b:
        case = _inputs(_csv_row(r))
        if case[5].oedema != OedemaGrade.NONE:
            continue
        t = explain(*case, models).classification_trace
        z = {c.code: c for c in t.criteria}.get("wflh_z")
        if z and z.used and z.nearest_cutoff in (-3.0, -2.0) and abs(z.margin) <= 0.02:
            hits += 1
            assert z.status == ("severe" if z.value < -3 else "moderate" if z.value < -2 else "normal")
    assert hits >= 3


# ---- never changes anything ----
def test_explain_does_not_change_results(models, rows):
    for case in _cases(rows)[:80]:
        sex, age, w, l, pos, cl = case
        a = compute_anthropometry(sex=sex, weight_kg=w, length_height_cm=l, measure_position=pos, age_days=age,
                                  oedema=cl.oedema != OedemaGrade.NONE)
        before_c, before_f = classify(a, cl), flag_record(*case, models)
        explain(*case, models)
        assert classify(a, cl) == before_c
        assert flag_record(*case, models) == before_f


def test_review_reasons_equal_rules_review(models, rows):
    for case in _cases(rows)[:300]:
        sex, age, w, l, pos, cl = case
        e = explain(*case, models)
        f, a, r = features_from_inputs(*case)
        rv = review(a, r, cl.muac_cm, cl.oedema.value != "none")
        assert tuple(x.code for x in e.review_trace.reasons) == rv.reasons
        assert all(x.evidence for x in e.review_trace.reasons)


# ---- worker summary safety ----
BANNED = ("diagnosed", "has severe", "has moderate", "is malnourished", "suffers", "suffering from")


def test_summary_shape_and_wording(models, rows):
    for case in _cases(rows):
        e = explain(*case, models)
        assert 2 <= len(e.summary) <= 3 and all(line.strip() for line in e.summary)
        text = " ".join(e.summary).lower()
        assert not any(b in text for b in BANNED)
        assert R.PLACEHOLDER.lower() not in text
        cls, tier = e.classification_trace.classification, e.classification_trace.tier
        if tier == "urgent":
            assert any(k in e.summary[1].lower() for k in ("urgent", "refer", "assessment"))
            assert "Meets the criterion for severe acute malnutrition in the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016" in e.summary[0]
        if cls == "MAM":
            assert "refer" in e.summary[1].lower()
        if tier == "recheck":
            assert "recheck" in e.summary[1].lower()


def test_hiv_wording_only_in_audit(models):
    cl = ClinicalInputs(muac_cm=12.0, hiv_positive=True, **FULL)
    e = explain("female", 400, 9.0, 74.0, "length", cl, models)
    assert "MAM.HIV_OTP" in [r.id for r in e.classification_trace.rules]
    assert "hiv" not in " ".join(e.summary).lower()
    assert "OTP" in " ".join(e.summary)
    assert any("HIV" in n for n in e.classification_trace.audit_notes)


def test_unable_to_classify_says_what_is_missing(models):
    e = explain("male", 90, 5.5, 58.0, "length", ClinicalInputs(), models)
    assert e.classification_trace.classification == "UNABLE_TO_CLASSIFY"
    assert "Needed:" in e.summary[0] and "not assessed" in e.summary[0]


def test_sam_assess_says_what_is_missing(models):
    e = explain("male", 400, 8.0, 72.0, "length", ClinicalInputs(muac_cm=11.4), models)
    assert e.classification_trace.classification == "SAM_ASSESS"
    assert "appetite test not done" in e.summary[0]


def test_age_heaping_flag_carries_the_caveat(models):
    e = explain("female", 365, 9.0, 74.0, "length", ClinicalInputs(muac_cm=12.0, **FULL), models)
    if any(c.feature == "age_heap_exact" for c in e.flag_trace.top_raising[:2]):
        assert "date of birth is known" in " ".join(e.summary)


# ---- output form ----
def test_determinism_and_json_round_trip(models):
    a, b = explain(*RECORD, models), explain(*RECORD, models)
    assert a == b and a.to_json(sort_keys=True) == b.to_json(sort_keys=True)
    d = json.loads(a.to_json())
    assert d["summary"] == list(a.summary)
    assert d["classification_trace"]["rules"][0]["source"] == "Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016"
    assert set(d) >= {"summary", "classification_trace", "flag_trace", "review_trace", "limits"}


def test_limits_state_synthetic_and_advisory(models):
    e = explain(*RECORD, models)
    text = " ".join(e.limits).lower()
    assert "synthetic" in text and "advisory" in text and "not a diagnosis" in text
    assert isinstance(e, Explanation)
