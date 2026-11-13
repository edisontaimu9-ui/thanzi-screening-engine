"""The child report: the rules result is copied and never changed, findings only escalate, nothing reassures, no HIV, fails closed."""
import copy
import json

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE
from thanzi_screen.api import service
from thanzi_screen.childreport import REPORT_VERSION, build_child_report

PRETERM = {"sex": "male", "age_days": 10, "weight_kg": 1.8, "length_height_cm": 42.0, "measure_position": "length",
           "oedema": "none", "gestational_age_weeks": 32, "birth_weight_g": 1700}
RANK = {"routine": 0, "raised": 1, "recheck": 2, "urgent": 3}
COPIED = ("classification", "tier", "programme", "rules_fired", "rule_set_version", "preterm_level")


def worker(body):
    return service.screen(body, "worker")


def prediction(**kw):
    base = {"available": True, "scored": True, "elevated": False, "stratum": None, "message": None, "drivers": [], "concerns": [],
            "not_scored": [], "inputs": None, "targets_scored": ["future_sam"], "non_clinical": True, "advisory": "a", "authority": "b",
            "model_versions": ["m"]}
    return {**base, **kw}


CONCERN = prediction(elevated=True, stratum="high", message="The prediction models estimate one of the highest chances of severe wasting.",
                     concerns=[{"target": "future_sam", "plain": "severe wasting", "stratum": "high", "horizon_days": [28, 180], "pathway": "full"}],
                     drivers=[{"feature": "weight_kg", "text": "Weight is low", "direction": "raises"}])
GROWTH = {"assessed": True, "reason": None, "status": "low", "flagged": True, "weight_loss": False, "messages": ["Weight gain is low."],
          "trends": {"wfa": {"flagged": True, "messages": ["Weight-for-age fell."]}}, "review_suggested": True,
          "review_note": "A clinician should review growth."}


def report_of(body, **extra):
    return build_child_report({**worker(body), **extra})


# ---- fails closed ----
def test_audit_view_is_refused():
    with pytest.raises(ValueError):
        build_child_report(service.screen(MAM_BASE, "audit"))


@pytest.mark.parametrize("bad", [None, [], "x", {}, {"view": "worker"}, {"view": "audit", "tier": "urgent"},
                                 {"view": "worker", "tier": "urgent", "worker_summary": []}])
def test_anything_that_is_not_a_worker_screening_result_is_refused(bad):
    with pytest.raises(ValueError):
        build_child_report(bad)


def test_hiv_text_anywhere_makes_it_refuse():
    w = worker(MAM_BASE)
    w["warnings"] = [*w["warnings"], "Child is HIV positive."]
    with pytest.raises(ValueError):
        build_child_report(w)


# ---- the screening result is copied, never recomputed ----
@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE, PRETERM], ids=["sam", "mam", "low", "preterm"])
def test_result_is_the_screening_result(body):
    w = worker(body)
    before = copy.deepcopy(w)
    r = build_child_report(w)
    assert w == before                                              # input untouched
    assert r["report_version"] == REPORT_VERSION and r["attention"]["changes_classification"] is False
    for k in COPIED:
        if k in w:
            assert r["result"][k] == w[k], k
    assert r["result"]["summary"] == w["worker_summary"]
    assert r["result"]["tier"] == w["tier"]


def test_a_moderate_report_is_the_same_whatever_the_hidden_programme():
    """The worker view hides the programme (and so any HIV inference). The report must not bring it back."""
    a, b = report_of({**MAM_BASE, "hiv_positive": True}), report_of({**MAM_BASE, "hiv_positive": False})
    assert a == b and a["result"]["programme"] is None
    assert "hiv" not in json.dumps(a).lower()


@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE, PRETERM, {**MAM_BASE, "hiv_positive": True}])
def test_no_report_mentions_hiv(body):
    assert "hiv" not in json.dumps(report_of(body)).lower()


# ---- levels ----
@pytest.mark.parametrize("body,level", [(SAM_BASE, "urgent"), (MAM_BASE, "raised"), (LOW_BASE, "routine")])
def test_level_follows_the_screening_tier(body, level):
    r = report_of(body)
    assert r["attention"]["level"] == level and r["attention"]["raised_by_findings"] is False


def test_recheck_tier_says_to_recheck():
    w = {**worker(LOW_BASE), "tier": "recheck", "classification": "UNABLE_TO_CLASSIFY"}
    r = build_child_report(w)
    assert r["attention"]["level"] == "recheck" and "Recheck" in r["action"]["statement"]


def test_an_unknown_tier_is_never_read_as_routine():
    r = build_child_report({**worker(LOW_BASE), "tier": "something_new"})
    assert r["attention"]["level"] == "raised" and "could not be placed" in r["action"]["statement"]


def test_preterm_follow_up_has_no_tier_but_a_level():
    w = worker(PRETERM)
    assert w["tier"] is None
    r = build_child_report(w)
    assert r["attention"]["level"] in ("routine", "raised", "urgent") and r["action"]["steps"] == w["actions"]
    assert r["sources"][0].startswith("Care of the Infant and Newborn")


# ---- escalate only (the central property) ----
FINDINGS = [{}, {"growth_monitoring": GROWTH}, {"ml_prediction": prediction()}, {"ml_prediction": CONCERN},
            {"ml_prediction": prediction(scored=False, elevated=None, not_scored=[{"target": "future_sam", "pathway": "full",
                                                                                   "reason": "essential_input_unavailable", "message": "m"}])},
            {"growth_monitoring": GROWTH, "ml_prediction": CONCERN}]


@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE], ids=["sam", "mam", "low"])
@pytest.mark.parametrize("extra", FINDINGS, ids=range(len(FINDINGS)))
def test_findings_never_change_the_result_and_never_lower_the_level(body, extra):
    plain, with_findings = report_of(body), report_of(body, **extra)
    assert with_findings["result"] == plain["result"] and with_findings["action"] == plain["action"]
    assert RANK[with_findings["attention"]["level"]] >= RANK[plain["attention"]["level"]]
    assert with_findings["attention"]["changes_classification"] is False


def test_a_finding_can_lift_routine_to_raised_but_urgent_stays_urgent():
    lifted = report_of(LOW_BASE, ml_prediction=CONCERN)
    assert lifted["attention"] == {"level": "raised", "label": "Closer follow-up", "raised_by_findings": True,
                                   "changes_classification": False}
    assert report_of(LOW_BASE, growth_monitoring=GROWTH)["attention"]["level"] == "raised"
    assert report_of(SAM_BASE, ml_prediction=prediction())["attention"]["level"] == "urgent"
    assert report_of(LOW_BASE, ml_prediction=prediction())["attention"]["level"] == "routine"


# ---- prediction is never reassurance ----
def test_prediction_statuses():
    assert report_of(LOW_BASE)["prediction"]["status"] == "not_run"
    assert report_of(LOW_BASE, ml_prediction=prediction())["prediction"]["status"] == "no_concern"
    p = report_of(LOW_BASE, ml_prediction=CONCERN)["prediction"]
    assert p["status"] == "concern" and p["elevated"] and p["message"] == CONCERN["message"]
    assert p["concerns"] == [{"plain": "severe wasting", "stratum": "high"}] and p["drivers"] == ["Weight is low"]
    ns = report_of(LOW_BASE, ml_prediction=prediction(scored=False, elevated=None))["prediction"]
    assert ns["status"] == "not_scored" and not ns["elevated"]


@pytest.mark.parametrize("extra", [{}, {"ml_prediction": prediction()},
                                   {"ml_prediction": prediction(scored=False, elevated=None)}])
def test_no_concern_always_says_it_is_not_reassurance(extra):
    stmt = report_of(LOW_BASE, **extra)["prediction"]["statement"]
    assert "not reassurance" in stmt


def test_partly_scored_says_so():
    p = report_of(LOW_BASE, ml_prediction=prediction(not_scored=[{"target": "future_wasting", "pathway": "full", "reason": "x", "message": "m"}]))["prediction"]
    assert p["status"] == "no_concern" and "could not be made" in p["statement"] and p["not_scored"][0]["target"] == "future_wasting"


# ---- check before acting ----
def test_recording_error_review_assessment_and_warnings_are_listed_once():
    w = worker(LOW_BASE)
    w["ml_flags"] = {"available": True, "advisory": "a", "review": {"needed": True, "reasons": [{"code": "x", "message": "Review the case."}]},
                     "recording_error": {"flagged": True, "suggested_field": "length_height_cm", "messages": ["Length may be mistyped."]}}
    w["clinical_assessment"] = {"needed": True, "reasons": [{"code": "y", "message": "Assess if preterm."}]}
    w["warnings"] = ["Review the case.", "Be careful."]
    items = build_child_report(w)["check_before_acting"]["items"]
    texts = [i["text"] for i in items]
    assert "Length may be mistyped." in texts and "Assess if preterm." in texts and "Be careful." in texts
    assert texts.count("Review the case.") == 1
    assert {i["source"] for i in items} >= {"recording_error", "review", "clinical_assessment", "warning"}


def test_nothing_to_check_means_no_section():
    w = worker(LOW_BASE)
    assert not w["warnings"] and not w["ml_flags"]["review"]["needed"]        # the premise: nothing to check on this child
    assert build_child_report(w)["check_before_acting"] is None


def test_growth_section_copies_the_messages():
    g = report_of(LOW_BASE, growth_monitoring=GROWTH)["growth"]
    assert g["review_suggested"] and g["messages"] == ["Weight gain is low.", "Weight-for-age fell."]
    assert report_of(LOW_BASE)["growth"] is None


# ---- standing statements ----
@pytest.mark.parametrize("body", [SAM_BASE, MAM_BASE, LOW_BASE, PRETERM], ids=["sam", "mam", "low", "preterm"])
def test_every_report_says_it_is_not_a_diagnosis_and_that_the_wording_is_draft(body):
    r = report_of(body)
    assert "not a diagnosis" in r["not_a_diagnosis"]
    assert r["wording"]["status"] == "draft_pending_clinical_review" and "DRAFT" in r["wording"]["notice"]
    assert any("worried" in x for x in r["limits"]) and r["sources"]


def test_the_report_package_is_standard_library_only_and_independent_of_the_ml_modules():
    import subprocess
    import sys
    code = ("import sys, thanzi_screen.childreport; "
            "bad = [m for m in sys.modules if m.split('.')[0] in ('numpy', 'sklearn', 'xgboost', 'fastapi', 'pydantic') "
            "or m.startswith(('thanzi_screen.ml', 'thanzi_screen.prediction', 'thanzi_screen.api'))]; "
            "print(bad); sys.exit(1 if bad else 0)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stdout
