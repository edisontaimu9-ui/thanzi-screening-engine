"""The review pack files are generated from the code, so they cannot drift from what is actually gated."""
import importlib.util
import json
from pathlib import Path

from thanzi_screen.review import SUBJECTS
from thanzi_screen.review import pack as P

ROOT = Path(__file__).resolve().parents[2]


def _script():
    spec = importlib.util.spec_from_file_location("review_pack", ROOT / "scripts" / "review_pack.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_committed_checklist_and_templates_are_current():
    assert _script().stale() == [], "run: python scripts/review_pack.py write"


def test_templates_name_the_current_version_and_fingerprint_and_are_unsigned():
    for s in SUBJECTS.values():
        t = json.loads((ROOT / "docs/review/signoff" / s.filename.replace(".signoff.json", ".signoff.template.json")).read_text(encoding="utf-8"))
        assert (t["version"], t["content_sha256"]) == (s.version(), s.fingerprint())
        assert t["outcome"] == "" and all(v == "" for v in t["checklist"].values()) and all(r["name"] == "" for r in t["reviewers"])


def test_no_real_signoff_file_is_committed_unnoticed():
    # A signed file in the repository is a deliberate act of the owner and should be reviewed as one: this test names them.
    found = sorted(p.name for p in (ROOT / "docs/review/signoff").glob("*.signoff.json"))
    assert found == [], f"signed files committed: {found}. Update this test on purpose if that is intended."


def test_checklist_ids_are_unique_and_every_role_is_known():
    for s in SUBJECTS.values():
        ids = [cid for cid, _ in s.checklist]
        assert len(ids) == len(set(ids)) and ids
        assert set(s.roles) <= set(P.ROLE_CODES)


def test_every_feature_that_is_off_by_default_has_a_subject():
    assert {s.flag for s in SUBJECTS.values()} == {"THANZI_CHILD_REPORT_ENABLED", "THANZI_SURVEILLANCE_REPORTS_ENABLED"}


def test_fingerprints_are_stable_and_distinct():
    a, b = (s.fingerprint() for s in SUBJECTS.values())
    assert a != b and a == SUBJECTS["child_report_wording"].fingerprint()


def test_gate_command_exit_codes(tmp_path, monkeypatch, capsys):
    mod = _script()
    for flag in ("THANZI_CHILD_REPORT_ENABLED", "THANZI_SURVEILLANCE_REPORTS_ENABLED"):
        monkeypatch.delenv(flag, raising=False)
    assert mod.main(["gate", "--dir", str(tmp_path)]) == 0                  # nothing switched on: nothing to block
    monkeypatch.setenv("THANZI_CHILD_REPORT_ENABLED", "1")
    assert mod.main(["gate", "--dir", str(tmp_path)]) == 1                  # switched on without a sign-off
    assert "signoff_missing" in capsys.readouterr().out
    assert mod.main(["gate", "--all", "--dir", str(tmp_path)]) == 1
