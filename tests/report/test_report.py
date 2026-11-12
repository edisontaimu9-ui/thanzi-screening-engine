import copy

import pytest

from thanzi_screen.factors import ChildRecord, Visit
from thanzi_screen.report import build_report
from thanzi_screen.under5 import screen_record


def screening(w=10.9, l=82.0, muac=14.0):
    r = ChildRecord("male", (Visit(500, w, l, "length", muac_cm=muac),))
    return screen_record(r).to_dict()


def pred(elevated):
    return {"module": "ml_prediction", "status": "ok", "elevated": elevated}


def test_prediction_never_changes_screening_block():
    s = screening()
    before = copy.deepcopy(s)
    for p in (None, pred(False), pred(True)):
        rep = build_report(s, p)
        assert rep["deterministic_screening"] == before
    assert s == before


def test_elevated_prediction_on_low_risk_raises_attention_only():
    rep = build_report(screening(), pred(True))
    assert rep["deterministic_screening"]["classification"]["tier"] == "low_risk"
    assert rep["attention"]["level"] == "raised" and rep["attention"]["changes_classification"] is False


def test_low_prediction_is_not_reassurance_and_cannot_lower_urgent():
    urgent = screening(w=6.5, l=76.0, muac=10.5)
    assert urgent["classification"]["tier"] == "urgent"
    assert build_report(urgent, pred(False))["attention"]["level"] == "urgent"
    assert build_report(screening(), pred(False))["attention"]["level"] == "routine"


def test_not_run_block_is_explicit():
    rep = build_report(screening())
    assert rep["ml_prediction"]["status"] == "not_run" and rep["ml_prediction"]["elevated"] is False
    assert "not reassurance" in rep["ml_prediction"]["note"]


def test_wrong_inputs_rejected():
    with pytest.raises(ValueError):
        build_report({"module": "other"})
    with pytest.raises(ValueError):
        build_report(screening(), {"module": "other"})
    with pytest.raises(ValueError):
        build_report(screening(), None, not_run_reason="because")
