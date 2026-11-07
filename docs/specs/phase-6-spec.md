# Phase 6 specification: FastAPI packaging

Status: DRAFT. Waiting for Edison's answers to Q1-Q8. Nothing implemented.

## Objective
Package the engine (Phases 1-5) as a small, stateless HTTP service that Hope's app and gateway can call, with a published contract, Docker-ready for UniPod servers. No change to any existing interface.

## Hard rules
- Phases 1-5 are called, not changed. `ClassificationResult`, `MlFlags`, `Explanation` and their codes stay as they are. The API adds a layer; a missed or failed ML flag never alters the rules result (D9).
- Worker-facing responses use the Explanation worker summary, never raw `referral_text` (D71). HIV wording appears in the audit view only (D64).
- Stateless. No database, no stored requests, no request-body logging, no child identifiers accepted. Synthetic data only until data sharing is agreed.
- Decision support, not diagnosis. Every response carries the disclaimer, rule set version, model version and the "demonstration, not validated" status.
- Python 3.11+. Runtime adds FastAPI, pydantic and uvicorn only (Phase 0 spec). Engine stays standard library.

## Ownership
- Mine: request and response contract, validation, error codes, engine wiring, tests, Dockerfile, OpenAPI file.
- Hope (architecture, deployment, security): authentication, TLS, rate limiting, hosting, audit logging, databases, the app and gateway. This service must sit behind her gateway and must not be exposed publicly as it is.
- Maria: clinical review of worker wording and referral logic (D72).

## Resources
No new external sources. FastAPI, pydantic and uvicorn are open source (MIT/BSD). I will record versions and licences in the register before use.

## Honest limits
- No authentication in the service itself (Q5). Unsafe to expose directly.
- Not load tested. Not tested on UniPod servers.
- ML flags are demonstration only (synthetic training, D55).
- I cannot confirm the Docker image builds on your phone. I will try to build in my environment and tell you plainly if I could not.
- FastAPI needs pydantic v2, which uses a compiled core and can be hard to install on Termux. Design below keeps most logic and tests framework-free (Q8).

## Deliverables
1. `src/thanzi_screen/api/service.py`: framework-free core. `screen(payload: dict, view, models) -> dict`. All wiring, view building, degraded mode.
2. `src/thanzi_screen/schemas/`: request and response models (pydantic) for the HTTP edge and the OpenAPI contract.
3. `src/thanzi_screen/api/app.py`: thin FastAPI app. `create_app(models=None, api_key=None)`.
4. `Explanation.worker_summary`: read-only property alias of `summary` (Q4). Nothing renamed.
5. `explain_rules_only(...)`: Phase 5 addition for degraded mode (Q6). Existing functions unchanged.
6. `Dockerfile`, `.dockerignore`, `docs/api/openapi.json` (generated), `scripts/export_openapi.py`, `docs/modules/api.md`.
7. Tests in `tests/api/`, decision log entries, register update.

## Endpoints (Q1)
- `GET /health`: `ok` or `degraded` (models missing or mismatched), versions.
- `GET /version`: engine version, rule set version, model version, status statement, disclaimer.
- `POST /v1/screen?view=worker|audit` (default `worker`): one child per call.
- Batch, history and any storage: out of scope.

## Request
JSON, extra fields forbidden (a `name` or `child_id` is rejected, Q5).
`sex` (male|female), `age_days` (int), `weight_kg`, `length_height_cm`, `measure_position` (length|height), then the `ClinicalInputs` fields: `oedema`, `muac_cm`, `appetite`, `danger_signs`, `complications`, `clinically_well_and_alert`, `hiv_positive`, `visible_severe_wasting`, `too_weak_to_suckle`, `failure_to_gain_weight`.
- `null` means not assessed and `[]` means assessed, none present (D25). The API never fills a missing clinical field with a "normal" value.
- Age is `age_days` only (Q7): no date of birth, which is identifying.
- Structure is checked by pydantic. Ranges and plausibility are the engine's (`InputError`), so there is one source of truth.

## Response, worker view (Q2)
`worker_summary` (2-3 lines), `classification`, `tier`, `programme`, `rules_fired`, `reasons`, `warnings` (Q3), `ml_flags` (recording-error flag, suggested field, review reasons, all as codes plus the plain messages), `rule_set_version`, `model_version`, `status`, `disclaimer`. No `referral_text`.

## Response, audit view
Everything in the worker view plus the full `Explanation` (traces, contributions, margins, audit notes) and the raw `referral_text`. It can contain HIV information, so Hope should gate it.

## Errors
422 for bad structure or engine `InputError`, with a stable `code` and a message. Errors never echo the submitted values. 500 returns a generic body, no stack trace, no input.

## Degraded mode (Q6)
If the model files are missing or do not match the feature list, the service starts and `/health` says `degraded`. `/v1/screen` still returns the rules classification and summary, with `ml_flags: {"available": false}`. The review flag (rules based) still works.

## Docker
`python:3.12-slim`, non-root user, no dev dependencies, models copied in, `HEALTHCHECK` on `/health`, port from env. No secrets in the image.

## Decisions needed
- Q1 Endpoints: `GET /health`, `GET /version`, `POST /v1/screen` with `view=worker` (default) or `audit`. Single child per call, no batch. OK?
- Q2 Worker view contents as listed (codes plus summary, no `referral_text`); audit view adds the full `Explanation` and `referral_text`. OK?
- Q3 Warnings in the worker view: one Phase 2 warning mentions HIV status. The API replaces it with a neutral line ("OTP admission conditions not confirmed: complete the appetite test, complications and well-and-alert checks") and keeps the original in the audit view. A test scans Phase 2 for any warning containing "HIV" so a new one cannot leak. OK, or drop warnings from the worker view?
- Q4 Add the read-only alias `Explanation.worker_summary` (the field is named `summary` today). `summary` stays. The API field is `worker_summary`. OK?
- Q5 Stateless, no logging of bodies, unknown fields rejected. Authentication, TLS, rate limits, audit logging and hosting are Hope's. Include an optional single API key from an environment variable, off by default? OK?
- Q6 Degraded mode as above, with the small `explain_rules_only` addition to Phase 5. OK?
- Q7 `age_days` only, no date of birth. OK?
- Q8 FastAPI and pydantic v2 at the HTTP edge only. Core logic in framework-free `service.py`, so most tests run on Termux with plain pytest. API tests use `importorskip` and run where FastAPI installs. OK?

## Tests (planned)
- Golden contract: for a sweep of generated records, `classification`, `tier`, `programme`, `rules_fired`, `reasons` equal the engine's output exactly.
- No raw `referral_text` and no "HIV" anywhere in any worker view, including with `hiv_positive` true and the HIV warning case; audit view has both.
- Phase 2 warnings containing "HIV" are all covered by the neutral replacement.
- `null` versus `[]` preserved end to end.
- Unknown fields (`name`, `child_id`, `date_of_birth`) rejected; errors do not echo input; no request body in captured logs.
- Degraded mode: rules result unchanged when models are missing; `/health` reports `degraded`.
- Urgent tier always has an action line; summary is 2-3 lines; disclaimer, versions and status present.
- Determinism; `/health` and `/version` shape.
- `docs/api/openapi.json` matches the live app (drift guard).
- Dockerfile checks: non-root user, no dev dependencies, healthcheck present.

## Exit criteria
Tests pass, OpenAPI file and `docs/modules/api.md` written, decision log and register updated, limits stated plainly (including what was not tested), open issues listed. Then WAIT before Phase 7.
