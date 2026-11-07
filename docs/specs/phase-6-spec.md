# Phase 6 specification: FastAPI packaging

Status: Q1-Q8 approved by Edison 2026-11-07 (D74-D81) with three conditions: HIV privacy in worker responses (Q3), access restricted to Hope's gateway (Q5), full API tests in CI (Q8). Interpretations of the conditions: D82-D84. **Specification only. No implementation until Edison says go.**

## Objective
Package the engine (Phases 1-5) as a small, stateless HTTP service that Hope's app and gateway can call, with a published contract, Docker-ready for UniPod servers. No change to any existing interface.

## Hard rules
- Phases 1-5 are called, not changed. `ClassificationResult`, `MlFlags`, `Explanation` and their codes stay as they are. The API adds a layer; a missed or failed ML flag never alters the rules result (D9).
- Worker-facing responses use the Explanation worker summary, never raw `referral_text` (D71). No HIV information appears anywhere in a worker response: not in text, codes, keys or values. It appears in the audit view only (D64, D76, D82).
- Access is restricted to Hope's gateway. The service fails closed: no credential configured, no start (D78, D83).
- The full test suite, including every API test, runs in CI and must pass before Phase 6 closes (D81, D84).
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
- The service enforces a gateway credential, but network isolation (private network, no public port) is a deployment matter for Hope. I cannot verify it from code. Needs her confirmation (I21).
- A child with class MAM sent to OTP instead of SFP is only possible under the HIV rule (CMAM Table 5). Anyone who knows the rule can infer HIV status from that programme. I keep `programme` because the worker needs the action; I cannot hide the inference without hiding the action (I20).
- Not load tested. Not tested on UniPod servers.
- ML flags are demonstration only (synthetic training, D55).
- I cannot run GitHub Actions. I will run the same steps in my environment, but the first real CI result appears after you push. If CI fails, paste the log and I fix it (I22).
- FastAPI needs pydantic v2, which uses a compiled core and can be hard to install on Termux. Most logic and tests stay framework-free, and CI is the gate for the API tests (Q8).

## Deliverables
1. `src/thanzi_screen/api/service.py`: framework-free core. `screen(payload: dict, view, models) -> dict`. All wiring, view building, degraded mode.
2. `src/thanzi_screen/schemas/`: request and response models (pydantic) for the HTTP edge and the OpenAPI contract.
3. `src/thanzi_screen/api/app.py`: thin FastAPI app. `create_app(models=None, gateway_key=None, audit_key=None, dev_mode=False)`.
3a. `src/thanzi_screen/api/security.py`: gateway and audit key checks (constant-time compare), fail-closed startup, worker-view HIV scrubbing (D82, D83).
4. `Explanation.worker_summary`: read-only property alias of `summary` (Q4). Nothing renamed.
5. `explain_rules_only(...)`: Phase 5 addition for degraded mode (Q6). Existing functions unchanged.
6. `Dockerfile`, `.dockerignore`, `docs/api/openapi.json` (generated), `scripts/export_openapi.py` (with `--check`), `docs/modules/api.md` (includes a deployment checklist for Hope).
7. `.github/workflows/ci.yml` (D84), `pyproject.toml` extras `api` (fastapi, pydantic, uvicorn) and dev `httpx`.
8. Tests in `tests/api/`, decision log entries, register update (versions and licences).

## Endpoints (Q1)
- `GET /health`: `ok` or `degraded` (models missing or mismatched). No credential needed, and it returns nothing else, so a container health check works.
- `GET /version`: engine version, rule set version, model version, status statement, disclaimer. Needs the gateway key.
- `POST /v1/screen?view=worker|audit` (default `worker`): one child per call. Needs the gateway key. `view=audit` also needs the audit key.
- Batch, history and any storage: out of scope.

## Request
JSON, extra fields forbidden (a `name` or `child_id` is rejected, Q5).
`sex` (male|female), `age_days` (int), `weight_kg`, `length_height_cm`, `measure_position` (length|height), then the `ClinicalInputs` fields: `oedema`, `muac_cm`, `appetite`, `danger_signs`, `complications`, `clinically_well_and_alert`, `hiv_positive`, `visible_severe_wasting`, `too_weak_to_suckle`, `failure_to_gain_weight`.
- `null` means not assessed and `[]` means assessed, none present (D25). The API never fills a missing clinical field with a "normal" value.
- Age is `age_days` only (Q7): no date of birth, which is identifying.
- Structure is checked by pydantic. Ranges and plausibility are the engine's (`InputError`), so there is one source of truth.

## Response, worker view (Q2)
`worker_summary` (2-3 lines), `classification`, `tier`, `programme`, `rules_fired` (display codes, see below), `reasons`, `warnings` (Q3), `ml_flags` (recording-error flag, suggested field, review reasons, all as codes plus the plain messages), `rule_set_version`, `model_version`, `status`, `disclaimer`. No `referral_text`.

**HIV privacy in the worker view (Q3 condition, D76, D82).** Nothing in the response contains HIV information, in any key or value:
- the HIV warning is replaced by a neutral line;
- rule code `MAM.HIV_OTP` is shown as `MAM.OTP_ELIGIBLE` (the audit view keeps the real code);
- request values are never echoed;
- a final check scans the serialised worker response for the text hiv (any case) and fails closed: if found, the field is dropped and the event is counted, never silently passed through.
Residual limit: I20.

## Response, audit view
Everything in the worker view with the real rule codes, plus the full `Explanation` (traces, contributions, margins, audit notes) and the raw `referral_text`. It can contain HIV information. It needs a separate audit key (D83). If no audit key is configured, the audit view is disabled (403).

## Errors
422 for bad structure or engine `InputError`, with a stable `code` and a message. Errors never echo the submitted values. 500 returns a generic body, no stack trace, no input.

## Degraded mode (Q6)
If the model files are missing or do not match the feature list, the service starts and `/health` says `degraded`. `/v1/screen` still returns the rules classification and summary, with `ml_flags: {"available": false}`. The review flag (rules based) still works.

## Access control (Q5 condition, D78, D83)
- `THANZI_GATEWAY_KEY` is required. Without it the service refuses to start, unless `THANZI_DEV_MODE=1` is set explicitly (local development only, logs a loud warning).
- Every route except `/health` needs header `X-Gateway-Key`, compared in constant time. Missing or wrong gives a generic 401 with no hint.
- `view=audit` also needs `X-Audit-Key` matching `THANZI_AUDIT_KEY`. Unset means audit is off.
- `/docs`, `/redoc` and `/openapi.json` are off outside dev mode. The contract is the committed `docs/api/openapi.json`.
- No CORS middleware. The service is not browser-facing; browsers go through Hope's gateway.
- Keys come from the environment or a secret store, are never logged and are not in the image. Rotation is a restart with new values.
- Network isolation (private network, port not published, only the gateway can reach it), TLS, rate limits and audit logging are Hope's. The deployment checklist is in `docs/modules/api.md`.

## Docker
`python:3.12-slim`, non-root user, no dev dependencies, models copied in, `HEALTHCHECK` on `/health`, port from env. No secrets in the image. The image does not publish a port by default.

## CI (Q8 condition, D81, D84)
`.github/workflows/ci.yml` on push and pull request to `main`:
- Python 3.11 and 3.12 matrix. `pip install -e ".[dev,api]"`, then the full `python -m pytest -q` (Phases 1-6).
- `THANZI_REQUIRE_API_TESTS=1`: if FastAPI is missing, API tests fail instead of skipping.
- `python scripts/export_openapi.py --check` fails if `docs/api/openapi.json` is stale.
- A `docker` job builds the image, starts it with test keys, checks `/health`, runs one `POST /v1/screen`, and confirms a non-root user.
- Actions pinned to major versions (SHA pinning is stricter; Hope may prefer it).
Phase 6 does not close until CI is green on `main` (you report the result).

## Decisions (approved by Edison 2026-11-07)
- Q1 Endpoints: `GET /health`, `GET /version`, `POST /v1/screen?view=worker|audit`. Single child per call, no batch. (D74)
- Q2 Worker view: summary plus codes, no `referral_text`. Audit view adds the full `Explanation` and `referral_text`. (D75)
- Q3 Warnings: the HIV warning is replaced by a neutral line in the worker view, original kept in the audit view; a test scans Phase 2 for any warning containing "HIV". **Condition: protect HIV privacy in worker responses.** (D76, D82)
- Q4 Read-only alias `Explanation.worker_summary`; `summary` stays. (D77)
- Q5 Stateless, no body logging, unknown fields rejected; authentication, TLS, rate limits, audit logging and hosting are Hope's. **Condition: access restricted to Hope's gateway.** (D78, D83)
- Q6 Degraded mode with `explain_rules_only`. (D79)
- Q7 `age_days` only, no date of birth. (D80)
- Q8 FastAPI and pydantic at the HTTP edge only, framework-free `service.py`. **Condition: run the full API tests in CI.** (D81, D84)

## Tests (planned)
- Worker response, serialised, never contains the text hiv in any case, across a sweep with `hiv_positive` true, false and null, including OTP-ready and not-ready MAM cases. `rules_fired` shows `MAM.OTP_ELIGIBLE`. The audit view shows `MAM.HIV_OTP`.
- Fail-closed scrub: a forced HIV string in a worker field is dropped and counted.
- Access: no key gives 401 on every route except `/health`; wrong key gives 401; audit without audit key gives 403; startup without a gateway key raises unless dev mode; `/docs` and `/openapi.json` return 404 outside dev mode; constant-time compare is used; `/health` returns no version.
- CI file checks: matrix, `THANZI_REQUIRE_API_TESTS`, OpenAPI check and Docker job present.
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
