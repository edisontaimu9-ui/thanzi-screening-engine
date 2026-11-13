"""The report's own wording: screening is not diagnosis, nothing reassures, nothing names a programme or HIV. Draft, pending review."""
import importlib.util
import re
from pathlib import Path

import pytest

from thanzi_screen.childreport import wording as W

ROOT = Path(__file__).resolve().parents[2]
REASSURING = ("healthy", "normal", "safe", "all clear", "no risk", "nothing wrong", "well-nourished", "fine", "good news", "don't worry")


def test_ids_are_unique_and_every_entry_has_text():
    ids = [e.id for e in W.all_entries()]
    assert len(ids) == len(set(ids)) and all(e.text.strip() and e.used_in.strip() for e in W.all_entries())
    assert set(ids) == set(W.ENTRIES)


def test_status_is_draft_until_signed_off():
    assert W.REVIEW_STATUS == "draft_pending_clinical_review"
    assert "not yet reviewed" in W.text("banner.draft").lower()


@pytest.mark.parametrize("entry", W.all_entries(), ids=lambda e: e.id)
def test_no_entry_reassures(entry):
    low = entry.text.lower()
    assert not any(w in low for w in REASSURING), entry.id
    if re.search(r"\bwell\b", low):                       # "well" is allowed only to say the child is NOT shown to be well
        assert "not reassurance" in low, entry.id


@pytest.mark.parametrize("entry", W.all_entries(), ids=lambda e: e.id)
def test_no_entry_states_a_diagnosis(entry):
    low = entry.text.lower()
    assert "diagnos" not in low or "not a diagnosis" in low, entry.id
    assert not any(w in low for w in ("has malnutrition", "is malnourished", "suffers from", "confirmed")), entry.id


@pytest.mark.parametrize("entry", W.all_entries(), ids=lambda e: e.id)
def test_no_entry_names_a_programme_or_hiv(entry):
    low = entry.text.lower()
    assert not any(w in low for w in ("hiv", "otp", "sfp", "outpatient therapeutic", "supplementary feeding")), entry.id


def test_every_status_the_report_can_show_has_a_not_reassurance_sentence():
    for i in ("prediction.no_concern", "prediction.not_scored", "prediction.not_run", "prediction.partly_scored"):
        assert "not reassurance" in W.text(i)
    assert "does not rule out" in W.text("action.low_risk")
    assert "worried" in W.text("limits.worried")


def test_phase8_wording_listed_for_review_is_still_in_the_code():
    spec = importlib.util.spec_from_file_location("export_report_wording", ROOT / "scripts" / "export_report_wording.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    source = (ROOT / "src" / "thanzi_screen" / "prediction" / "consolidate.py").read_text(encoding="utf-8")
    for part, phrase in mod.PHASE8_PHRASES:
        assert phrase in source, f"{part}: the review sheet lists wording that consolidate.py no longer has"


def test_review_sheet_is_up_to_date():
    spec = importlib.util.spec_from_file_location("export_report_wording", ROOT / "scripts" / "export_report_wording.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    committed = (ROOT / "docs" / "review" / "child-report-wording.md").read_text(encoding="utf-8")
    assert committed == mod.render(), "run: python scripts/export_report_wording.py"
