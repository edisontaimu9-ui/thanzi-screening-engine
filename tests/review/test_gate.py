"""Phase 11 gate: a sign-off opens it only when it is complete, current and for the same wording or settings. Everything else keeps it shut."""
import copy
import datetime as dt
import json

import pytest

from thanzi_screen.review import SUBJECTS, check_subject
from thanzi_screen.review import gate as G
from thanzi_screen.review import pack as P

TODAY = dt.date(2026, 11, 13)
CHILD, SURV = "child_report_wording", "surveillance_reports"


def signed(key=CHILD, **over):
    """A complete, valid sign-off made from the template, with `over` applied last."""
    doc = P.build_template(SUBJECTS[key])
    doc.update(outcome="approved", approval_reference="MoH letter 2026/11", notes="")
    for r in doc["reviewers"]:
        r.update(name="A. Reviewer", title="Clinical officer", date="2026-11-10")
    doc["checklist"] = {cid: "pass" for cid in doc["checklist"]}
    doc.update(over)
    return doc


def write(tmp_path, doc, key=CHILD):
    (tmp_path / SUBJECTS[key].filename).write_text(json.dumps(doc), encoding="utf-8")
    return tmp_path


def reasons(tmp_path, doc, key=CHILD):
    return check_subject(key, write(tmp_path, doc, key), TODAY).reasons


def test_complete_signoff_opens_the_gate(tmp_path):
    r = check_subject(CHILD, write(tmp_path, signed()), TODAY)
    assert r.ok and r.reasons == ()


def test_unsigned_template_is_shut(tmp_path):
    r = check_subject(CHILD, write(tmp_path, P.build_template(SUBJECTS[CHILD])), TODAY)
    assert not r.ok
    assert {"outcome_not_approved", "approval_reference_missing", "reviewer_incomplete:clinician"} <= set(r.reasons)
    assert any(x.startswith("checklist_not_passed:") for x in r.reasons)


def test_no_folder_no_file_unreadable_and_not_an_object_are_shut(tmp_path):
    assert check_subject(CHILD, None).reasons == ("signoff_dir_not_set",)
    assert check_subject(CHILD, "").reasons == ("signoff_dir_not_set",)
    assert check_subject(CHILD, tmp_path).reasons == ("signoff_missing",)
    (tmp_path / SUBJECTS[CHILD].filename).write_text("{not json", encoding="utf-8")
    assert check_subject(CHILD, tmp_path).reasons == ("signoff_unreadable",)
    (tmp_path / SUBJECTS[CHILD].filename).write_text("[]", encoding="utf-8")
    assert check_subject(CHILD, tmp_path).reasons == ("signoff_unreadable",)
    (tmp_path / SUBJECTS[CHILD].filename).write_text(" " * (G.MAX_FILE_BYTES + 1), encoding="utf-8")
    assert check_subject(CHILD, tmp_path).reasons == ("signoff_too_large",)


def test_a_directory_in_place_of_the_file_is_shut(tmp_path):
    (tmp_path / SUBJECTS[CHILD].filename).mkdir()
    assert not check_subject(CHILD, tmp_path).ok


@pytest.mark.parametrize("change,code", [
    ({"schema": "other"}, "signoff_schema"),
    ({"subject": SURV}, "subject_mismatch"),
    ({"version": "child_report_wording_0.0"}, "version_mismatch"),
    ({"content_sha256": "0" * 64}, "content_changed_since_review"),
    ({"outcome": "not_approved"}, "outcome_not_approved"),
    ({"outcome": "approved_with_changes", "changes_summary": "  "}, "changes_summary_missing"),
    ({"outcome": "approved_with_changes", "changes_summary": "______"}, "changes_summary_missing"),
    ({"approval_reference": ""}, "approval_reference_missing"),
    ({"approval_reference": "<reference>"}, "approval_reference_missing"),
    ({"reviewers": []}, "reviewer_missing:clinician"),
    ({"reviewers": "x"}, "reviewer_missing:clinician"),
])
def test_each_defect_shuts_the_gate(tmp_path, change, code):
    assert code in reasons(tmp_path, signed(**change))


def test_approved_with_changes_needs_a_summary_and_then_opens(tmp_path):
    assert check_subject(CHILD, write(tmp_path, signed(outcome="approved_with_changes", changes_summary="Line 4 reworded")), TODAY).ok


@pytest.mark.parametrize("field,value", [("name", ""), ("name", "______"), ("title", ""), ("date", ""), ("date", "13/11/2026"), ("date", "not a date")])
def test_incomplete_reviewer_shuts_the_gate(tmp_path, field, value):
    doc = signed()
    doc["reviewers"][0][field] = value
    assert "reviewer_incomplete:clinician" in reasons(tmp_path, doc)


def test_future_review_date_is_refused(tmp_path):
    doc = signed()
    doc["reviewers"][0]["date"] = "2026-11-14"
    assert "review_date_in_future:clinician" in reasons(tmp_path, doc)


def test_unknown_role_is_refused(tmp_path):
    doc = signed()
    doc["reviewers"].append({"name": "X", "role_code": "somebody", "title": "t", "date": "2026-11-10"})
    assert "reviewer_role_unknown" in reasons(tmp_path, doc)


@pytest.mark.parametrize("value", ["", "fail", "Pass", True, None, "n/a"])
def test_every_checklist_line_must_be_exactly_pass(tmp_path, value):
    doc = signed()
    first = SUBJECTS[CHILD].checklist[0][0]
    doc["checklist"][first] = value
    assert f"checklist_not_passed:{first}" in reasons(tmp_path, doc)


def test_missing_checklist_line_and_bad_checklist_are_refused(tmp_path):
    doc = signed()
    gone = SUBJECTS[CHILD].checklist[-1][0]
    del doc["checklist"][gone]
    assert f"checklist_not_passed:{gone}" in reasons(tmp_path, doc)
    assert any(x.startswith("checklist_not_passed:") for x in reasons(tmp_path, signed(checklist=["pass"])))


def test_surveillance_needs_both_roles(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "_surv_placeholder", lambda: False)
    doc = signed(SURV)
    assert check_subject(SURV, write(tmp_path, doc, SURV), TODAY).ok
    one = copy.deepcopy(doc)
    one["reviewers"] = [r for r in one["reviewers"] if r["role_code"] != "dhis2_administrator"]
    assert "reviewer_missing:dhis2_administrator" in reasons(tmp_path, one, SURV)


def test_surveillance_stays_shut_while_settings_say_placeholder(tmp_path):
    # The shipped settings are PLACEHOLDER values: a signature cannot open the gate until the Ministry values replace them.
    assert P._surv_placeholder() is True
    assert "settings_still_placeholder" in reasons(tmp_path, signed(SURV), SURV)


def test_change_to_the_wording_invalidates_an_earlier_signoff(tmp_path, monkeypatch):
    doc = signed()
    assert check_subject(CHILD, write(tmp_path, doc), TODAY).ok
    from thanzi_screen.childreport import wording as W
    first = W.all_entries()[0]
    changed = (W.Entry(first.id, first.used_in, first.text + " Changed."),) + W.all_entries()[1:]
    monkeypatch.setattr(W, "all_entries", lambda: changed)
    assert "content_changed_since_review" in check_subject(CHILD, tmp_path, TODAY).reasons


def test_change_to_the_settings_invalidates_an_earlier_signoff(monkeypatch):
    before = P._surv_fingerprint()
    from thanzi_screen.surveillance import hotspots
    monkeypatch.setitem(hotspots.CONFIG, "min_prevalence_for_hotspot", 0.5)
    assert P._surv_fingerprint() != before


def test_phase8_wording_is_part_of_the_child_fingerprint(monkeypatch):
    before = P._child_fingerprint()
    monkeypatch.setattr(P, "PHASE8_PHRASES", P.PHASE8_PHRASES + (("x", "y"),))
    assert P._child_fingerprint() != before


def test_reasons_never_carry_what_the_reviewer_typed(tmp_path):
    doc = signed(approval_reference="SECRET-REF", notes="PRIVATE NOTE")
    doc["reviewers"][0].update(name="Dr SECRETNAME", title="SECRETTITLE", date="bad")
    text = json.dumps(reasons(tmp_path, doc))
    assert not any(w in text for w in ("SECRET", "PRIVATE"))


def test_a_gate_that_cannot_decide_is_shut(tmp_path, monkeypatch):
    write(tmp_path, signed())
    monkeypatch.setattr(G, "check_document", lambda *a, **k: 1 / 0)
    assert check_subject(CHILD, tmp_path, TODAY).reasons == ("gate_error",)
