"""Every sentence the child report adds of its own, in one place, so reviewers read one file (Phase 9).

STATUS: DRAFT. Nothing here has been reviewed by a clinician or a health worker. The wording and the severity order of Phase 8 are
reviewed in the same session (see `scripts/export_report_wording.py`, which writes the review sheet from this file).

What the report does NOT write itself: the classification phrases, the rule reasons, the growth messages, the recording-error and
review messages and the consolidated prediction message. They are copied word for word from the screening response, so the report
can never say something different from the screening result.

Rules for every entry (tested):
  * screening is not diagnosis: the report never states or implies a diagnosis;
  * no reassurance: no entry says or implies a child is well, normal, healthy or safe, and "no concern" is always said to be
    not reassurance;
  * nothing names a programme or mentions HIV (the worker view carries no HIV information).
"""
from __future__ import annotations

from dataclasses import dataclass

WORDING_VERSION = "child_report_wording_0.1"
REVIEW_STATUS = "draft_pending_clinical_review"


@dataclass(frozen=True)
class Entry:
    id: str
    used_in: str
    text: str


_ENTRIES = (
    # ---- standing statements (every report) ----
    Entry("banner.not_diagnosis", "top of every report",
          "This report is decision support from a screening tool. It is not a diagnosis. A trained health worker or clinician "
          "makes every decision about this child."),
    Entry("banner.draft", "top of every report, until signed off",
          "DRAFT WORDING: not yet reviewed by clinicians and health workers. For demonstration and review only. Do not use for care."),
    Entry("limits.rules_decide", "limits",
          "The screening result follows the national guideline rules and decides referral. Nothing else in this report changes it."),
    Entry("limits.flags_advisory", "limits",
          "Flags, growth findings and predictions are advisory. They can add a concern. They never lower one."),
    Entry("limits.worried", "limits",
          "If you are worried about this child for any reason, refer or ask for clinical advice, whatever this report says."),

    # ---- what to do, by screening tier ----
    Entry("action.urgent", "action, tier urgent",
          "Urgent. Follow the referral in the screening summary now. A clinician makes the final decision."),
    Entry("action.mam", "action, tier mam",
          "Refer for further assessment as set out in the screening summary. Confirm the next step with your supervisor or clinician."),
    Entry("action.low_risk", "action, tier low_risk",
          "Continue routine care and growth monitoring. This does not rule out illness or poor growth."),
    Entry("action.recheck", "action, tier recheck",
          "Recheck the measurements and complete the missing assessments, then screen again. Do not rely on this result until you have."),
    Entry("action.preterm", "action, preterm route",
          "Follow the actions below. The preterm and low birth weight guidance decides the level. A clinician makes the final decision."),
    Entry("action.unplaced", "action, a tier or level this report does not know",
          "Follow the screening summary. This result could not be placed on a standard level, so treat it as needing attention."),

    # ---- attention level labels ----
    Entry("level.urgent", "attention level", "Act now"),
    Entry("level.raised", "attention level", "Closer follow-up"),
    Entry("level.recheck", "attention level", "Recheck the measurements"),
    Entry("level.routine", "attention level", "Routine care"),

    # ---- section lead-ins ----
    Entry("check.lead", "check before acting", "Check these before acting on the result."),
    Entry("growth.lead", "growth between visits", "Growth between the two visits (advisory)."),
    Entry("assessment.lead", "clinical assessment", "A clinician should assess this baby."),

    # ---- prediction, said only about the status of the estimate ----
    Entry("prediction.concern", "prediction, a concern was found",
          "The prediction is advisory. It adds a concern and does not change the screening result."),
    Entry("prediction.no_concern", "prediction, scored, no extra concern",
          "The prediction found no extra concern. This is not reassurance: it does not mean the child is well, and it does not lower the screening result."),
    Entry("prediction.not_scored", "prediction, nothing could be scored",
          "No prediction could be made. This is not reassurance."),
    Entry("prediction.not_run", "prediction, not switched on or not run",
          "No prediction was made. This is not reassurance."),
    Entry("prediction.partly_scored", "prediction, some targets not scored",
          "Some predictions could not be made. Those are not reassurance."),
)

ENTRIES: dict[str, Entry] = {e.id: e for e in _ENTRIES}
assert len(ENTRIES) == len(_ENTRIES), "duplicate wording id"


def text(entry_id: str) -> str:
    return ENTRIES[entry_id].text


def all_entries() -> tuple[Entry, ...]:
    return _ENTRIES
