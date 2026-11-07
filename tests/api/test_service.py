"""Phase 6 core: framework-free tests of `thanzi_screen.api.service` (D74-D86)."""
import json
import re
from pathlib import Path

import pytest

from tests.api._support import LOW_BASE, MAM_BASE, SAM_BASE, record_payload
from thanzi_screen.api import security, service, wording
from thanzi_screen.api.service import ApiError, screen
from thanzi_screen.data import GenConfig, generate
from thanzi_screen.data.io import _fmt
from thanzi_screen.data.schema import row_to_inputs
from thanzi_screen.explain import explain, explain_rules_only
from thanzi_screen.ml import flag_record, load_models
from thanzi_screen.ml.features import features_from_inputs
from thanzi_screen.rules import classify
from thanzi_screen.rules import rules_v2016 as R

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def models():
    return load_models()


def _args(row):
    r = {k: _fmt(k, v) for k, v in row.items()}
    return (r["sex"], int(r["age_days"]), float(r["weight_kg"]), float(r["length_height_cm"]),
            r["measure_position"], row_to_inputs(r))


@pytest.fixture(scope="module")
def sweep():
    """Generated records plus hand-built MAM cases covering OTP-ready and not-ready, with hiv true, false, null."""
    rows = generate(GenConfig(seed=11, n=1500))
    payloads = [record_payload(*_args(r)) for r in rows]
    for hiv in (True, False, None):
        for muac in (11.6, 12.0, 12.4):
            for extra in (dict(), dict(appetite="failed"), dict(complications=["malaria"]),
                          dict(clinically_well_and_alert=False), dict(danger_signs=["high_fever"]),
                          dict(appetite="not_done"), dict(danger_signs=None, complications=None)):
                payloads.append({**MAM_BASE, "muac_cm": muac, "hiv_positive": hiv, **extra})
    return payloads


def _text(obj) -> str:
    return json.dumps(obj)


# ---- HIV privacy (D82, D86) ----
def test_the_fail_closed_scan_never_fires_in_normal_operation(sweep, models):
    """The view is built without HIV content. The scan is only a backstop, so it must have nothing to drop."""
    before = security.SCRUB_EVENTS.count
    for p in sweep:
        for hiv in (True, False, None):
            screen({**p, "hiv_positive": hiv}, "worker", models)
    assert security.SCRUB_EVENTS.count == before


def test_worker_view_never_contains_hiv_text(sweep, models):
    for p in sweep:
        for hiv in (True, False, None):
            out = screen({**p, "hiv_positive": hiv}, "worker", models)
            assert "hiv" not in _text(out).lower()


def test_worker_view_does_not_depend_on_hiv_input(sweep, models):
    """The strongest form of D82/I20: the whole worker response is identical for hiv true, false and null."""
    mam_seen = hiv_otp_seen = 0
    for p in sweep:
        outs = [screen({**p, "hiv_positive": h}, "worker", models) for h in (None, True, False)]
        assert outs[0] == outs[1] == outs[2]
        if outs[0]["classification"] == "MAM":
            mam_seen += 1
            if "MAM.HIV_OTP" in screen({**p, "hiv_positive": True}, "audit", models)["rules_fired"]:
                hiv_otp_seen += 1
    assert mam_seen > 30 and hiv_otp_seen > 3     # the sweep really exercises the HIV rule


def test_no_programme_or_hiv_rule_visible_for_any_mam_child(sweep, models):
    for p in sweep:
        out = screen(p, "worker", models)
        if out["classification"] == "MAM":
            assert out["programme"] is None
            assert "MAM.HIV_OTP" not in out["rules_fired"] and "MAM.SFP" not in out["rules_fired"]
            text = _text(out)
            assert "OTP" not in text and "SFP" not in text and "Outpatient" not in text
            assert out["worker_summary"][1] == wording.MAM_ACTION
            assert wording.MAM_WARNING in out["warnings"]


def test_audit_view_keeps_the_real_programme_and_codes(models):
    p = {**MAM_BASE, "hiv_positive": True}
    audit = screen(p, "audit", models)
    assert audit["programme"] == "OTP" and "MAM.HIV_OTP" in audit["rules_fired"]
    assert "HIV" in audit["referral_text"]
    assert any("HIV" in n for n in audit["explanation"]["classification_trace"]["audit_notes"])
    sfp = screen({**p, "hiv_positive": False}, "audit", models)
    assert sfp["programme"] == "SFP" and "MAM.SFP" in sfp["rules_fired"]
    notready = screen({**p, "appetite": "failed"}, "audit", models)
    assert any("HIV-positive with MAM" in w for w in notready["warnings"])


def test_phase2_hiv_warnings_are_all_covered(sweep, models):
    seen = 0
    for p in sweep:
        args = service.parse_payload(p)
        _, anthro, result = features_from_inputs(*args)
        if any("hiv" in w.lower() for w in result.warnings):
            seen += 1
            assert not any("hiv" in w.lower() for w in screen(p, "worker", models)["warnings"])
    assert seen > 0
    src = (ROOT / "src/thanzi_screen/rules/classify.py").read_text()
    assert len(re.findall(r'warnings\.append\([^)]*HIV', src, re.S)) == 1     # a new HIV warning needs a new look


def test_fail_closed_scrub_drops_and_counts(monkeypatch, models):
    normal = screen(LOW_BASE, "worker", models)
    before = security.SCRUB_EVENTS.count
    monkeypatch.setitem(service.M.CLASS_PHRASE, "low_risk", "Low risk (HIV status unknown).")
    out = screen(LOW_BASE, "worker", models)
    assert "hiv" not in _text(out).lower()
    assert len(out["worker_summary"]) == len(normal["worker_summary"]) - 1   # dropped, not passed through
    assert security.SCRUB_EVENTS.count == before + 1


def test_scrub_worker_handles_keys_nesting_and_clean_input():
    clean = {"a": ["x", {"b": "fine"}], "n": 3, "none": None, "t": True}
    assert security.scrub_worker(clean) == clean
    dirty = {"ok": 1, "HiV_status": "x", "list": ["fine", "has hIv inside"], "nested": {"k": "Hiv", "keep": 2}}
    before = security.SCRUB_EVENTS.count
    out = security.scrub_worker(dirty)
    assert out == {"ok": 1, "list": ["fine"], "nested": {"keep": 2}}
    assert security.SCRUB_EVENTS.count == before + 3


# ---- contract with the engine (golden) ----
def test_worker_view_matches_the_engine_exactly(sweep, models):
    for p in sweep[:700]:
        args = service.parse_payload(p)
        _, anthro, result = features_from_inputs(*args)
        out = screen(p, "worker", models)
        assert out["classification"] == result.classification.value
        assert out["tier"] == result.tier.value
        assert out["reasons"] == [{"code": c, "message": t} for c, t in
                                  explain(*args, models).classification_trace.reasons]
        assert [r["code"] for r in out["reasons"]] == list(result.reasons)
        if result.classification.value == "MAM":
            shown = list(dict.fromkeys(wording.RULE_CODE_ALIAS.get(r, r) for r in result.rules_fired))
            assert out["rules_fired"] == shown
        else:
            assert out["rules_fired"] == list(result.rules_fired)
            assert out["programme"] == result.programme
            assert out["worker_summary"] == list(explain(*args, models).summary)
        assert out["rule_set_version"] == R.RULE_SET_VERSION and out["model_version"] == models.version
        flags = flag_record(*args, models)
        assert out["ml_flags"]["recording_error"]["flagged"] == flags.recording_error.flagged
        assert out["ml_flags"]["review"]["needed"] == flags.review.needed


def test_no_raw_referral_text_in_worker_view(sweep, models):
    for p in sweep[:300]:
        out = screen(p, "worker", models)
        assert "referral_text" not in out and "PLACEHOLDER" not in _text(out)
        assert "explanation" not in out


def test_responses_carry_disclaimer_versions_status_and_summary_shape(sweep, models):
    for p in sweep[:300]:
        out = screen(p, "worker", models)
        assert out["disclaimer"] and out["status"] == wording.STATUS and out["rule_set_version"] and out["model_version"]
        assert 2 <= len(out["worker_summary"]) <= 3
        if out["tier"] == "urgent":
            assert out["worker_summary"][1].strip()      # an action line is always there


def test_determinism(models):
    assert screen(SAM_BASE, "worker", models) == screen(SAM_BASE, "worker", models)
    assert screen(SAM_BASE, "audit", models) == screen(SAM_BASE, "audit", models)


# ---- null versus [] ----
def test_null_and_empty_list_are_kept_apart_end_to_end(models):
    assessed = screen({**SAM_BASE, "danger_signs": [], "complications": []}, "worker", models)
    not_assessed = screen({**SAM_BASE, "danger_signs": None, "complications": None}, "worker", models)
    absent = {k: v for k, v in SAM_BASE.items() if k not in ("danger_signs", "complications")}
    assert assessed["classification"] == "SAM_OTP"
    assert not_assessed["classification"] == "SAM_ASSESS"
    assert screen(absent, "worker", models) == not_assessed          # omitted means not assessed, never "none"


def test_oedema_is_required_and_never_assumed():
    p = {k: v for k, v in MAM_BASE.items() if k != "oedema"}
    with pytest.raises(ApiError) as e:
        screen(p)
    assert e.value.code == "missing_field" and "oedema" in e.value.message


def test_omitted_appetite_means_not_done(models):
    p = {k: v for k, v in SAM_BASE.items() if k != "appetite"}
    assert screen(p, "worker", models)["classification"] == "SAM_ASSESS"


# ---- degraded mode (D79) ----
def test_degraded_mode_leaves_the_rules_result_unchanged(sweep, models):
    for p in sweep[:400]:
        full, degraded = screen(p, "worker", models), screen(p, "worker", None)
        for k in ("classification", "tier", "programme", "rules_fired", "reasons", "warnings"):
            assert full[k] == degraded[k]
        assert degraded["ml_flags"]["available"] is False and degraded["ml_flags"]["recording_error"] is None
        assert degraded["ml_flags"]["review"] == full["ml_flags"]["review"]
        assert degraded["model_version"] == "none"
        assert degraded["worker_summary"][:2] == full["worker_summary"][:2]
    audit = screen(SAM_BASE, "audit", None)
    assert audit["explanation"]["flag_trace"] is None


def test_explain_rules_only_matches_explain_without_the_ml_line(sweep, models):
    for p in sweep[:300]:
        args = service.parse_payload(p)
        full, rules_only = explain(*args, models), explain_rules_only(*args)
        assert rules_only.summary[:2] == full.summary[:2]
        assert rules_only.classification_trace == full.classification_trace
        assert rules_only.review_trace == full.review_trace
        assert rules_only.flag_trace is None
        assert not any(l.startswith("Recording check") for l in rules_only.summary)


def test_worker_summary_is_a_read_only_alias(models):
    e = explain(*service.parse_payload(SAM_BASE), models)
    assert e.worker_summary == e.summary
    with pytest.raises(AttributeError):
        e.worker_summary = ()


# ---- input handling ----
@pytest.mark.parametrize("extra", [{"name": "Secret Person"}, {"child_id": "C-123"}, {"date_of_birth": "2024-01-01"},
                                   {"Secret Key Name": 1}])
def test_unknown_and_identifying_fields_are_rejected_without_echo(extra):
    with pytest.raises(ApiError) as e:
        screen({**LOW_BASE, **extra})
    assert e.value.code == "unknown_field" and e.value.status == 422
    for needle in ("Secret", "C-123", "2024-01-01", "child_id", "date_of_birth", "name"):
        assert needle not in e.value.message


@pytest.mark.parametrize("change", [
    {"weight_kg": "SECRET-VALUE"}, {"weight_kg": True}, {"age_days": 500.5}, {"age_days": "SECRET-VALUE"},
    {"sex": "SECRET-VALUE"}, {"oedema": "SECRET-VALUE"}, {"appetite": "SECRET-VALUE"},
    {"danger_signs": ["SECRET-VALUE"]}, {"danger_signs": "SECRET-VALUE"}, {"complications": [1]},
    {"hiv_positive": "SECRET-VALUE"}, {"muac_cm": "SECRET-VALUE"}, {"measure_position": "SECRET-VALUE"},
    {"weight_kg": float("nan")}, {"weight_kg": -3}, {"weight_kg": 0}, {"age_days": -1}, {"muac_cm": -1},
])
def test_bad_values_give_422_and_never_echo_the_value(change):
    with pytest.raises(ApiError) as e:
        screen({**LOW_BASE, **change})
    assert e.value.status == 422 and e.value.code in ("invalid_request", "invalid_input")
    assert "SECRET-VALUE" not in e.value.message and "SECRET" not in repr(e.value.args)


def test_non_object_body_and_bad_view_are_rejected():
    for body in ([], "x", None, 5):
        with pytest.raises(ApiError):
            screen(body)
    with pytest.raises(ApiError):
        screen(LOW_BASE, "everything")


def test_engine_messages_that_could_carry_a_value_are_replaced():
    from thanzi_screen.anthro import InputError
    assert service._engine_message(InputError("weight_kg must be a positive finite number")).startswith("weight_kg")
    assert "SECRET" not in service._engine_message(InputError("'SECRET' is not a valid Sex"))
    assert "9" not in service._engine_message(InputError("value 9 is bad"))


def test_request_model_enums_match_the_engine():
    from thanzi_screen.rules import Complication, DangerSign
    ann = __import__("typing").get_args
    pytest.importorskip("pydantic")
    from thanzi_screen.schemas import requests as rq
    assert set(ann(rq.DangerSignName)) == {d.value for d in DangerSign}
    assert set(ann(rq.ComplicationName)) == {c.value for c in Complication}


def test_infant_pathway_and_age_limits_do_not_crash(models):
    infant = {**LOW_BASE, "age_days": 60, "weight_kg": 4.5, "length_height_cm": 55.0, "muac_cm": None,
              "visible_severe_wasting": False, "too_weak_to_suckle": False, "failure_to_gain_weight": False}
    out = screen(infant, "worker", models)
    assert out["classification"] in ("low_risk", "MAM", "UNABLE_TO_CLASSIFY", "SAM_INPATIENT")
    assert "hiv" not in _text(out).lower()
    screen({**LOW_BASE, "age_days": 5000}, "worker", models)       # out of range is the engine's call, not a crash


def test_version_info(models):
    v = service.version_info(models)
    assert v["rule_set_version"] == R.RULE_SET_VERSION and v["model_version"] == models.version
    assert service.version_info(None)["model_version"] == "none"
