# Individual child report

**Status: Phase 9. Draft wording, pending clinical review. Off by default. Not clinically validated.**

`POST /v1/report` takes the same request as `/v1/screen` and returns one report for one child: the screening result, what to do, what to
check before acting, growth between visits, the status of the advisory prediction, and the standing limits. Screening is not diagnosis,
and the report says so on every call.

Code (standard library): `thanzi_screen.childreport.build` (`build_child_report`) and `thanzi_screen.childreport.wording` (every sentence the
report adds of its own). The route is in `api/app.py`, the glue in `api/service.child_report`, the contract in `schemas/child_report.py`.

## Switching it on

| Setting | Effect |
|---|---|
| `THANZI_CHILD_REPORT_ENABLED` unset or not `1` | `POST /v1/report` returns `404` with code `report_off`. Nothing else changes. |
| `THANZI_CHILD_REPORT_ENABLED=1` and a valid sign-off (Phase 11) | The route works. Every report carries `wording.status = draft_pending_clinical_review` and a draft notice. |

It stays off until the wording is reviewed (see below). From Phase 11 the switch alone is not enough: the service also needs a valid sign-off file for this wording version in `THANZI_REVIEW_SIGNOFF_DIR` (`docs/modules/review-pack.md`), otherwise `/v1/about` shows `child_report` as `blocked` and the route answers 404 `report_off`.

## What the report holds

| Field | Content |
|---|---|
| `wording` | Wording version, review status and the draft notice. |
| `not_a_diagnosis` | The not-a-diagnosis statement. |
| `attention` | `level` (`routine`, `raised`, `recheck`, `urgent`), its label, and `raised_by_findings`. |
| `result` | The screening result, copied from the worker view: classification, tier, programme (null for every moderate case), rules fired, summary lines, reasons. |
| `action` | One sentence by tier, and on the preterm route the engine's own actions. |
| `check_before_acting` | Recording-error, review, clinical-assessment messages and warnings, each once. Null when there is nothing to check. |
| `growth` | Growth-monitoring messages, only when an earlier visit was given. |
| `prediction` | `status` (`concern`, `no_concern`, `not_scored`, `not_run`), the Phase 8 consolidated sentence when there is a concern, what could not be scored. |
| `limits`, `sources` | Standing limits and the full titles of the sources. |

## Guarantees (all tested)

- **Built from the worker view only.** The audit view is refused, so no HIV information and no hidden programme can reach the report. There is no audit
  version of the report and no second key. A moderate case's report is identical whatever the hidden programme.
- **The rules decide.** `result` is copied, never recomputed. With any combination of growth and prediction findings, `result` and `action` are
  identical to the report without them, and the screening response of `/v1/screen` is identical with the route on or off.
- **Escalate only.** The level comes from the screening tier. A growth review or a prediction concern can lift `routine` to `raised`. Nothing
  lowers a level. An unknown tier is never read as routine.
- **No reassurance.** No wording says or implies a child is well, normal or safe. No concern, a target not scored and no prediction at all are each said
  to be not reassurance, and the low-risk action says it does not rule out illness or poor growth.
- **Fails closed.** Anything that is not a worker screening result, and any output that mentions HIV, is refused (`report_unavailable`, 500, from the API).

## Wording review

Every sentence the report writes itself is in `src/thanzi_screen/childreport/wording.py`. Everything else is quoted from the screening result, so the report
cannot say something the screening result does not.

`python scripts/export_report_wording.py` writes the review sheet `docs/review/child-report-wording.md`: each sentence with a decision column, and
the Phase 8 consolidated prediction wording and severity order, so both are reviewed in one sitting. `--check` fails if the sheet is stale (a test does the
same). A change to the wording means regenerating the sheet and changing `WORDING_VERSION`.

## Limits

- Wording is a draft. No clinician or health worker has reviewed it.
- The report is built for the plain under-five route, the corrected-age route and the preterm route. A route the screening response does not describe is refused.
- There is no translation yet. Message codes are stable for it (`explain/messages.py`), the report sentences are English only.
- It is a data structure, not a printable page. Layout is for the gateway or the app.
