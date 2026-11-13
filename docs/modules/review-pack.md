# Clinical review pack and deployment gates

**Status: Phase 11. Built. No sign-off file is shipped: the gate is shut until reviewers sign.**

Two features are off by default because they need people to approve them first: the individual child report (Phase 9, draft wording) and the
aggregated surveillance reports with DHIS2 export (Phase 10, placeholder settings). Phase 11 turns that promise into a check the service makes
itself. A feature opens only when **both** are true:

1. its switch is `1` (`THANZI_CHILD_REPORT_ENABLED`, `THANZI_SURVEILLANCE_REPORTS_ENABLED`), and
2. a valid sign-off file for its **current** version is in the folder named by `THANZI_REVIEW_SIGNOFF_DIR`.

Otherwise the routes answer exactly as when off (`404 report_off`, `404 surveillance_reports_off`), the service still starts, a warning with reason codes
goes to the log, and `GET /v1/about` shows the component as `blocked` with the same codes. The gate never changes what the screening engine decides.

Code (standard library): `thanzi_screen.review.pack` (subjects, checklists, fingerprints, templates) and `thanzi_screen.review.gate` (the check).
Tool: `scripts/review_pack.py`.

## What a sign-off is tied to

| Subject | Fingerprint covers | Roles that must sign |
|---|---|---|
| `child_report_wording` | Every sentence of the child report, the class phrases, the Phase 8 prediction wording, authority sentence and severity order, and the wording version | `clinician` |
| `surveillance_reports` | `report_config.json`, `hotspot_config.json` and the DHIS2 element definitions | `moh_nutrition_unit` and `dhis2_administrator` |

Change any covered text or setting and the fingerprint changes, so the earlier sign-off stops working (`content_changed_since_review`). That is the point:
reviewers sign what they read. `surveillance_reports` also stays shut while either settings file still says `PLACEHOLDER` in its `status` (`settings_still_placeholder`).
Change the settings and their `status` text first, then regenerate the pack, then sign.

## How to run a review

1. `python scripts/review_pack.py write` (and `python scripts/export_report_wording.py`) so the checklist, templates and wording sheet match the code.
2. Reviewers read the sheet and `docs/review/reviewer-checklist.md`. For the child report the sheet is `docs/review/child-report-wording.md`.
3. Copy `docs/review/signoff/<subject>.signoff.template.json` to the signed name (drop `.template`), for example `child-report-wording.signoff.json`, and fill in:
   `outcome` (`approved`, `approved_with_changes` with `changes_summary`, or `not_approved`), `approval_reference`, every reviewer's `name`, `title` and
   ISO `date` (YYYY-MM-DD, not in the future), and `pass` against every checklist line. Anything other than `pass` keeps the gate shut.
4. Put the signed file in the folder that `THANZI_REVIEW_SIGNOFF_DIR` points to. In the release image the `docs` folder is not copied, so mount a folder (read-only is fine).
5. Run the preflight: `python scripts/review_pack.py gate --all --dir <folder>`. Start the service with the switch set to `1`.

If reviewers ask for wording changes, change the code, bump `WORDING_VERSION` for the child report, regenerate the sheet and the pack, and sign again.

## Preflight

```
python scripts/review_pack.py gate               # reads the same switches as the service; exit 1 if a switched-on feature is blocked
python scripts/review_pack.py gate --all         # shows the state of every feature, with reason codes
python scripts/review_pack.py check              # exit 1 if the committed checklist or templates are stale (also a test)
```

## Reason codes

`signoff_dir_not_set`, `signoff_missing`, `signoff_unreadable`, `signoff_too_large`, `signoff_schema`, `subject_mismatch`, `version_mismatch`,
`content_changed_since_review`, `outcome_not_approved`, `changes_summary_missing`, `approval_reference_missing`, `reviewer_missing:<role>`,
`reviewer_incomplete:<role>`, `review_date_in_future:<role>`, `reviewer_role_unknown`, `checklist_not_passed:<id>`, `settings_still_placeholder`, `gate_error`.
Codes only: a reviewer's name or anything typed in the file is never logged or returned.

## Limits

- The gate checks that a complete sign-off exists for this exact version. It cannot check that the people are who they say, or that a clinician really read the sheet. The file
  is a record the owner keeps and the approving body can audit, not a cryptographic signature.
- A signed child report still carries the draft notice (`wording.status = draft_pending_clinical_review`) until the owner changes `REVIEW_STATUS` and `WORDING_VERSION`
  in `childreport/wording.py` after the review. That is a separate, deliberate edit and it needs a new review of the changed text.
- Not covered by any sign-off: clinical validation of the screening rules, the prediction models, translation, and the ethics and data approvals for real data.
- The explicit `child_report=` and `surveillance_reports=` arguments of `create_app` bypass the gate. They are for tests and embedding code, never for the environment.
- Phase 11 gates only the two features above. The prediction block (Phase 5 to 8) keeps its own refusals (simulated models, sign-off references in the model file).
