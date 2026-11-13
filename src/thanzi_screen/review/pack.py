"""What has to be reviewed before a feature may be switched on (Phase 11).

Two subjects, both off by default since the phase that built them:

- `child_report_wording`: the individual child report (Phase 9) and the Phase 8 prediction wording. Reviewed by a clinician.
- `surveillance_reports`: aggregated reports and DHIS2 export (Phase 10). Confirmed by the Ministry nutrition unit and the DHIS2 administrators.

Each subject has a fingerprint of exactly what the reviewers read, a version, a reviewer checklist and the roles that must sign.
A sign-off is valid only for the fingerprint it names, so any later change to the wording or the settings needs a new review.
Nothing here changes what the screening engine decides.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable

SCHEMA = "thanzi-signoff-1"
OUTCOMES = ("approved", "approved_with_changes")      # "not_approved" is a valid thing to write down, and never opens the gate
ROLE_CODES = {
    "clinician": "Clinician (doctor, clinical officer or nurse) who reviewed the wording",
    "moh_nutrition_unit": "Ministry of Health and Sanitation nutrition unit",
    "dhis2_administrator": "DHIS2 administrator for the target instance",
}

# Phase 8 wording that lives inline in prediction/consolidate.py. tests/childreport/test_wording.py checks each of these is still there.
PHASE8_PHRASES = (
    ("high stratum clause", "one of the highest chances of"),
    ("elevated stratum clause", "a higher than usual chance of"),
    ("opening", "The prediction models estimate"),
    ("closing", "Consider closer follow-up and a clinician review."),
)


@dataclass(frozen=True)
class Subject:
    key: str
    title: str
    flag: str                      # the environment variable that asks for the feature
    filename: str                  # the sign-off file the gate looks for
    roles: tuple[str, ...]         # every role here must appear among the reviewers
    checklist: tuple[tuple[str, str], ...]
    version: Callable[[], str]
    fingerprint: Callable[[], str]
    placeholder: Callable[[], bool]    # True while the settings still say PLACEHOLDER
    sheet: str                     # where the reviewers read what they are signing


def _sha(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


# ---- child report wording ----

def _child_version() -> str:
    from ..childreport import wording as W
    return W.WORDING_VERSION


def _child_fingerprint() -> str:
    from ..childreport import wording as W
    from ..explain.messages import CLASS_PHRASE
    from ..prediction.consolidate import AUTHORITY, TARGET_ORDER
    return _sha({"version": W.WORDING_VERSION, "entries": [[e.id, e.used_in, e.text] for e in W.all_entries()],
                 "class_phrase": CLASS_PHRASE, "authority": AUTHORITY, "target_order": list(TARGET_ORDER),
                 "phase8": [list(p) for p in PHASE8_PHRASES]})


# ---- surveillance reports ----

def _surv_version() -> str:
    from ..surveillance import hotspots, reports
    return f"{reports.CONFIG_VERSION}+{hotspots.CONFIG_VERSION}"


def _surv_fingerprint() -> str:
    from ..surveillance import dhis2, hotspots, reports
    return _sha({"reports": reports.CONFIG, "hotspots": hotspots.CONFIG, "elements": dhis2.ELEMENTS})


def _surv_placeholder() -> bool:
    from ..surveillance import hotspots, reports
    return any("placeholder" in str(c.get("status", "")).lower() for c in (reports.CONFIG, hotspots.CONFIG))


_CHILD_CHECKS = (
    ("wording.no_diagnosis", "Every line is decision support only. None states a diagnosis or hints at one."),
    ("wording.no_reassurance", "No line says or implies that a child is well, normal or safe."),
    ("wording.empty_not_reassurance", "No concern, a target that was not scored and no prediction at all are each said to be not reassurance."),
    ("wording.plain_language", "A health worker at the intended level can understand every line without help."),
    ("wording.prediction_order", "The Phase 8 wording and the severity order (future_sam, future_wasting, future_faltering) are acceptable."),
    ("scope.worker_view_only", "The report is for the health worker and carries no HIV information. This is the intended audience."),
    ("scope.language", "English-only wording is acceptable for the first sites, or a translation is planned and recorded in the notes."),
    ("scope.limits_accepted", "The limits in docs/modules/child-report.md are accepted."),
)
_SURV_CHECKS = (
    ("thresholds.confirmed", "The hotspot and watch thresholds, the minimum number screened and the reference-rate rule are confirmed."),
    ("small_cells.suppression", "The small-cell suppression threshold and the secondary suppression rule are confirmed."),
    ("small_cells.dhis2_export", "A decision is recorded on whether facility SAM or MAM counts of 1 to 4 may be exported (dhis2_export_suppresses_small_cells)."),
    ("dhis2.ids", "The data element ids, id schemes and org unit ids in the mapping are confirmed by the DHIS2 administrators."),
    ("dhis2.dry_run", "An import with dryRun=true was run on the target DHIS2 instance and its summary was checked."),
    ("data.agreement", "The approval or data-sharing agreement for facility-level reporting is on file (reference above)."),
    ("scope.limits_accepted", "The limits in docs/modules/surveillance-reports.md are accepted."),
)

SUBJECTS: dict[str, Subject] = {
    "child_report_wording": Subject(
        "child_report_wording", "Individual child report wording", "THANZI_CHILD_REPORT_ENABLED", "child-report-wording.signoff.json",
        ("clinician",), _CHILD_CHECKS, _child_version, _child_fingerprint, lambda: False, "docs/review/child-report-wording.md"),
    "surveillance_reports": Subject(
        "surveillance_reports", "Aggregated surveillance reports and DHIS2 export", "THANZI_SURVEILLANCE_REPORTS_ENABLED",
        "surveillance-reports.signoff.json", ("moh_nutrition_unit", "dhis2_administrator"), _SURV_CHECKS, _surv_version, _surv_fingerprint,
        lambda: _surv_placeholder(), "docs/modules/surveillance-reports.md and the settings in src/thanzi_screen/surveillance/*.json"),
}


def build_template(subject: Subject) -> dict:
    """The unsigned sign-off for the current version. Copy it, fill it in, save it as `subject.filename` (no `.template`)."""
    return {
        "schema": SCHEMA,
        "subject": subject.key,
        "version": subject.version(),
        "content_sha256": subject.fingerprint(),
        "outcome": "",
        "changes_summary": "",
        "approval_reference": "",
        "reviewers": [{"name": "", "role_code": role, "title": "", "date": ""} for role in subject.roles],
        "checklist": {cid: "" for cid, _ in subject.checklist},
        "notes": "",
    }


def template_text(subject: Subject) -> str:
    return json.dumps(build_template(subject), indent=2, ensure_ascii=False) + "\n"


def checklist_markdown() -> str:
    lines = [
        "# Reviewer checklist (Phase 11)", "",
        "Generated by `scripts/review_pack.py write` from `src/thanzi_screen/review/pack.py`: edit the code, not this file.", "",
        "A feature that is off by default stays off, even with its switch set to `1`, until a sign-off file for its **current** version is in the",
        "sign-off folder (`THANZI_REVIEW_SIGNOFF_DIR`). Any later change to the wording or the settings needs a new review. How to do it: `docs/modules/review-pack.md`.", "",
        f"Outcomes: `approved`, `approved_with_changes` (say what changed in `changes_summary`), or `not_approved` (the gate stays shut). "
        "Write `pass` or `fail` against every checklist line. Anything but `pass` keeps the gate shut.", "",
    ]
    for s in SUBJECTS.values():
        lines += [f"## {s.title}", "", f"Switch: `{s.flag}`. Sign-off file: `{s.filename}`. Read: {s.sheet}.", "",
                  "Reviewers needed: " + "; ".join(f"`{r}` ({ROLE_CODES[r]})" for r in s.roles) + ".", "",
                  "| Checklist id | What you confirm |", "|---|---|"]
        lines += [f"| `{cid}` | {text} |" for cid, text in s.checklist]
        lines.append("")
    lines += ["Not covered by any sign-off: clinical validation of the screening rules, the prediction models, translation, and the data and ethics approvals "
              "for real data. Those stay outside this gate.", ""]
    return "\n".join(lines)
