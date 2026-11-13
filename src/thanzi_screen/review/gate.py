"""The deployment gate (Phase 11): a feature switched on in the environment still stays off unless its sign-off file is valid.

Fail closed: any problem means blocked. The result holds reason codes only, never a reviewer's name or anything typed in the file,
so it is safe to log and to show on `/v1/about`. Standard library only.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from .pack import OUTCOMES, ROLE_CODES, SCHEMA, SUBJECTS, Subject

ENV_DIR = "THANZI_REVIEW_SIGNOFF_DIR"
MAX_FILE_BYTES = 65_536
_BLANK = re.compile(r"^(?:[\s_.\-?]*|\s*<[^>]*>\s*)$")     # "", "______", "...", "<name>"


@dataclass(frozen=True)
class GateResult:
    subject: str
    ok: bool
    reasons: tuple[str, ...] = ()


def signoff_dir(env=None) -> str | None:
    value = (os.environ if env is None else env).get(ENV_DIR, "").strip()
    return value or None


def _blank(value) -> bool:
    return not isinstance(value, str) or bool(_BLANK.match(value))


def _date(value) -> _dt.date | None:
    try:
        return _dt.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _load(path: Path):
    if not path.is_file():
        return None, "signoff_missing"
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None, "signoff_too_large"
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, "signoff_unreadable"
    return (doc, None) if isinstance(doc, dict) else (None, "signoff_unreadable")


def check_document(doc: dict, subject: Subject, today: _dt.date | None = None) -> list[str]:
    """Every reason the document does not open the gate for this subject. Empty list means it does."""
    today = today or _dt.date.today()
    why: list[str] = []
    if doc.get("schema") != SCHEMA:
        why.append("signoff_schema")
    if doc.get("subject") != subject.key:
        why.append("subject_mismatch")
    if doc.get("version") != subject.version():
        why.append("version_mismatch")
    if doc.get("content_sha256") != subject.fingerprint():
        why.append("content_changed_since_review")
    outcome = doc.get("outcome")
    if outcome not in OUTCOMES:
        why.append("outcome_not_approved")
    elif outcome == "approved_with_changes" and _blank(doc.get("changes_summary")):
        why.append("changes_summary_missing")
    if _blank(doc.get("approval_reference")):
        why.append("approval_reference_missing")

    reviewers = doc.get("reviewers")
    reviewers = [r for r in reviewers if isinstance(r, dict)] if isinstance(reviewers, list) else []
    for role in subject.roles:
        mine = [r for r in reviewers if r.get("role_code") == role]
        if not mine:
            why.append(f"reviewer_missing:{role}")
        elif not any(not _blank(r.get("name")) and not _blank(r.get("title")) and _date(r.get("date")) for r in mine):
            why.append(f"reviewer_incomplete:{role}")
        elif any(_date(r.get("date")) and _date(r.get("date")) > today for r in mine):
            why.append(f"review_date_in_future:{role}")
    if any(r.get("role_code") not in ROLE_CODES for r in reviewers):
        why.append("reviewer_role_unknown")

    checks = doc.get("checklist")
    checks = checks if isinstance(checks, dict) else {}
    why += [f"checklist_not_passed:{cid}" for cid, _ in subject.checklist if checks.get(cid) != "pass"]
    if subject.placeholder():
        why.append("settings_still_placeholder")
    return why


def check_subject(key: str, directory: str | os.PathLike | None, today: _dt.date | None = None) -> GateResult:
    """Look for the subject's sign-off file in `directory` and check it against the current code."""
    subject = SUBJECTS[key]
    if not directory:
        return GateResult(key, False, ("signoff_dir_not_set",))
    doc, problem = _load(Path(directory) / subject.filename)
    if problem:
        return GateResult(key, False, (problem,))
    try:
        reasons = check_document(doc, subject, today)
    except Exception:            # a gate that cannot decide is shut
        return GateResult(key, False, ("gate_error",))
    return GateResult(key, not reasons, tuple(reasons))
