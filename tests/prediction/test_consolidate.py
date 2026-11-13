"""Several one-target results become one summary: escalate only, never sees the rules, one result per target."""
import inspect

from thanzi_screen.prediction import consolidate as C
from thanzi_screen.prediction.consolidate import consolidate, one_per_target


def blk(target, stratum=None, scored=True, pathway="full", reason=None, inputs=None, plain=None, drivers=()):
    return {"available": True, "scored": scored, "not_scored_reason": None if scored else (reason or "essential_input_unavailable"),
            "not_scored_message": None if scored else "x", "stratum": stratum, "elevated": None if not scored else stratum is not None,
            "message": None, "drivers": list(drivers), "target": target, "target_plain": plain or target.replace("future_", ""),
            "horizon_days": [28, 180], "model_version": f"{target}-{pathway}", "pathway": pathway, "inputs": inputs, "non_clinical": True}


def test_no_concern_is_not_reassurance_and_has_no_message():
    out = consolidate([blk("future_wasting"), blk("future_sam")])
    assert out["scored"] is True and out["elevated"] is False and out["message"] is None and out["stratum"] is None and out["concerns"] == []


def test_nothing_scored_is_not_a_no_concern():
    out = consolidate([blk("future_wasting", scored=False)])
    assert out["scored"] is False and out["elevated"] is None and out["not_scored"][0]["reason"] == "essential_input_unavailable"


def test_concerns_are_ordered_by_stratum_then_severity_and_make_one_message():
    out = consolidate([blk("future_faltering", "elevated", plain="faltering weight gain"), blk("future_wasting", "elevated", plain="wasting"),
                       blk("future_sam", "high", plain="severe acute malnutrition")])
    assert [c["target"] for c in out["concerns"]] == ["future_sam", "future_wasting", "future_faltering"] and out["stratum"] == "high"
    assert out["message"].count("The prediction models estimate") == 1
    assert "one of the highest chances of severe acute malnutrition; and a higher than usual chance of wasting and faltering weight gain" in out["message"]
    assert "between 1 and 6 months from now" in out["message"] and "clinician review" in out["message"]


def test_one_result_per_target_prefers_the_first_that_scored():
    full_fail, anthro_ok = blk("future_wasting", scored=False, pathway="full"), blk("future_wasting", "high", pathway="anthropometric")
    assert one_per_target([full_fail, anthro_ok]) == [anthro_ok]
    assert one_per_target([blk("future_wasting", "high"), blk("future_wasting", "elevated", pathway="anthropometric")])[0]["stratum"] == "high"
    out = consolidate([full_fail, anthro_ok])
    assert out["not_scored"] == [] and out["targets_scored"] == ["future_wasting"]


def test_an_unscored_target_is_listed_beside_a_scored_one():
    out = consolidate([blk("future_wasting", "high"), blk("future_sam", scored=False, reason="age_outside_model_range")])
    assert out["elevated"] is True and [n["target"] for n in out["not_scored"]] == ["future_sam"]


def test_drivers_are_deduplicated_and_capped():
    d = lambda f: {"feature": f, "text": f, "direction": "raises"}  # noqa: E731
    out = consolidate([blk("future_sam", "high", drivers=[d("a"), d("b")]), blk("future_wasting", "high", drivers=[d("b"), d("c"), d("d")])])
    assert [x["feature"] for x in out["drivers"]] == ["a", "b", "c"]


def test_inputs_are_merged_under_the_most_serious_state():
    a = blk("future_sam", inputs={"not_assessed": ["clinical"], "not_applicable": ["longitudinal"], "unavailable": []})
    b = blk("future_wasting", inputs={"not_assessed": [], "not_applicable": [], "unavailable": ["longitudinal"]})
    out = consolidate([a, b])["inputs"]
    assert out == {"not_assessed": ["clinical"], "not_applicable": [], "unavailable": ["longitudinal"]}


def test_the_summary_cannot_see_or_change_the_rules():
    assert list(inspect.signature(consolidate).parameters) == ["blocks", "audit"]
    out = consolidate([blk("future_sam", "high")])
    assert out["authority"] == C.AUTHORITY and "decide" in out["authority"]
    assert not any(k in out for k in ("classification", "tier", "referral", "referral_text"))


def test_audit_adds_each_model_and_the_worker_view_does_not():
    b = [blk("future_sam", "high")]
    assert "models" not in consolidate(b) and consolidate(b, audit=True)["models"] == b
