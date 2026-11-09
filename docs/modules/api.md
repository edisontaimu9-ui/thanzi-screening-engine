# Module: api (Phase 6)

A small, stateless HTTP service around Phases 1-5. Decision support, not diagnosis. Demonstration only: synthetic data, not validated on real children.

## Layout
- `src/thanzi_screen/api/service.py`: framework-free core, `screen(payload, view, models) -> dict`. All wiring, view building, degraded mode.
- `src/thanzi_screen/api/security.py`: gateway and audit key checks (constant-time), fail-closed start, HIV scan of worker responses.
- `src/thanzi_screen/api/wording.py`: neutral MAM wording (I20, D86). Draft, pending clinician review (I23).
- `src/thanzi_screen/api/app.py`: thin FastAPI app. `create_app(models=None, gateway_key=None, audit_key=None, dev_mode=False, models_dir=None)`; `create_app_from_env()` for uvicorn.
- `src/thanzi_screen/schemas/`: pydantic request and response models (the OpenAPI contract). Contract file: `docs/api/openapi.json`.

## Run
```
pip install -e ".[api]"
export THANZI_GATEWAY_KEY=<at least 16 characters>
export THANZI_AUDIT_KEY=<at least 16 characters, different>     # optional: unset turns the audit view off
uvicorn --factory thanzi_screen.api.app:create_app_from_env --host 127.0.0.1 --port 8080
```
Environment: `THANZI_GATEWAY_KEY` (required), `THANZI_AUDIT_KEY`, `THANZI_MODELS_DIR` (default: `models/` in the repo), `THANZI_DEV_MODE=1` (local development only), `PORT` (Docker).

Regenerate the contract after any API change: `python scripts/export_openapi.py` (CI runs `--check`).

## Endpoints
| Route | Key | Notes |
|---|---|---|
| `GET /health` | none | `{"status": "ok"}` or `"degraded"`. Nothing else. |
| `GET /version` | gateway | engine, rule set and model versions, status, disclaimer |
| `GET /v1/about` | gateway | what is running: versions, health, uptime, routes and the state of each component (engine, ML models, growth monitoring, LLM service). No child data (D176) |
| `GET /v1/metrics` | gateway | request counts by route and status, 5xx count, `/v1/screen` latency (p50, p95, max, mean). Counts and durations only, in memory, reset on restart, per process (D176) |
| `POST /v1/screen?view=worker` | gateway | default view. One child per call |
| `POST /v1/screen?view=audit` | gateway + `X-Audit-Key` | full detail. May contain HIV information |

Gateway key goes in header `X-Gateway-Key`, audit key in `X-Audit-Key`. Missing or wrong gateway key: generic 401 on every route except `/health` (including unknown routes). Audit view without a valid audit key, or with audit off: 403. `/docs`, `/redoc` and `/openapi.json` are off outside dev mode. No CORS.

## Request
```json
{"sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0, "measure_position": "length",
 "oedema": "none", "muac_cm": 12.0, "appetite": "passed", "danger_signs": [], "complications": [],
 "clinically_well_and_alert": true, "hiv_positive": null}
```
- Required: `sex`, `age_days`, `weight_kg`, `length_height_cm`, `measure_position`, `oedema` (never assumed absent, D87).
- `null` or omitted means not assessed. `[]` means assessed, none present (D25). Omitted `appetite` means `not_done`.
- Age is `age_days` only. Unknown fields, including `name`, `child_id` and `date_of_birth`, are a 422. Types are strict. Ranges and plausibility are the engine's.

## Worker response
`worker_summary` (2-3 lines), `classification`, `tier`, `programme`, `rules_fired`, `reasons`, `warnings`, `ml_flags`, `rule_set_version`, `model_version`, `status`, `disclaimer`. No `referral_text`.

**No HIV information, and no programme for any MAM child (D82, D86).** For every MAM child: `programme` is null, `MAM.HIV_OTP` and `MAM.SFP` both show as `MAM.REFER`, summary line 2 is the same neutral referral line, and the same neutral warning is always present. The whole worker response is identical for `hiv_positive` true, false and null. A last scan drops any key or string containing "hiv" (any case) and counts it; it should never fire (a test checks this). The audit view keeps the real programme, rule codes, warnings, `referral_text` and the full `Explanation`.

## Preterm routing
`POST /v1/screen` also takes optional `gestational_age_weeks`, `birth_weight_g` (grams) and preterm fields. A baby born under 37 weeks or under 2500 g under 50 weeks PMA gets the preterm response (`route: preterm`, `preterm_level`, mapped `tier`). From 50 weeks PMA the under-5 response is returned on corrected age with `route: under5_corrected_age` and `birth_context`. See `docs/modules/preterm.md`.

## Errors
422 with a stable `code` (`invalid_request`, `invalid_input`, `missing_field`, `unknown_field`, `invalid_json`) and a message that never echoes submitted values. 401 `unauthorised`. 403 `audit_forbidden`. 413 `payload_too_large` (declared body over 16 KB). 500 `internal_error`, generic, no trace and no input.

## Degraded mode (D79)
`growth_monitoring` (D157, D165) appears when the request has `previous_measurement` (an earlier `age_days` and `weight_kg`, optionally `length_height_cm` with `measure_position`, and `hc_cm`): the weight gain per day since that visit against the ASPEN reference range, z-score trends for weight, length or height, and head circumference, and `review_suggested`. Advisory only, under-5 route only. See `docs/modules/growth.md`.

`ml_flags.deep_recording_error` (D153) is a second advisory flag from a small neural network, beside `recording_error`. It has the same shape (`probability` in the audit view only), appears only when the deep models are loaded, and is never run in degraded mode or on the corrected-age route. `GET /version` adds `deep_model_version` (null when not loaded). Switch it off with `THANZI_DEEP_ENABLED=0`. A failure inside it is logged by type only and screening continues without it (D154). The classification, tier, reasons and review never depend on it.

If the model files are missing or do not match the feature list, the service starts, `/health` says `degraded`, and screening still returns the rules result with `ml_flags.available: false`. The rules-based review flag still works.

## Not done, by design
No database, no stored requests, no request-body logging, no batch, no child identifiers.

## Deployment checklist (for Hope, D83)
The service enforces a gateway key. Everything below is deployment work it cannot check from code (I21, I24).
1. Run it on a private network only. Do not publish the container port to the internet. Only the gateway may reach it.
2. Terminate TLS at the gateway. The service speaks plain HTTP.
3. Set `THANZI_GATEWAY_KEY` (and `THANZI_AUDIT_KEY` if the audit view is wanted) from a secret store. Never bake them into the image or commit them. Rotate by restarting with new values.
4. Decide who may hold the audit key and how audit-view use is logged. The audit view can contain HIV information.
5. Add rate limiting and request logging at the gateway. The service logs no request bodies and no query values; keep that true at the gateway.
6. Keep the gateway from forwarding the audit header from browsers. Audit access should be server to server.
7. Watch `/health` for `degraded` and the logs for "HIV scan" errors (a bug if seen).
8. Confirm the neutral MAM wording with Maria before field use (I23), and check how health workers learn the programme through the clinic's own process.
9. Test on the UniPod servers and under load before any pilot. Neither has been done.

## Tests
`tests/api/`: `test_service.py` (core, framework-free), `test_security.py`, `test_http.py` (needs FastAPI and httpx), `test_packaging.py` (CI and Docker files, checked as text). With `THANZI_REQUIRE_API_TESTS=1` (CI) missing FastAPI fails the run instead of skipping.

## Optional local LLM routes (D133)
`GET /v1/llm/health` and `POST /v1/llm/generate` exist only when `THANZI_LLM_ENABLED=1` (or when `create_app(llm=...)` is given a client). They sit behind the gateway key, are not part of screening, and do not change `/health` or any screening response. Details, settings and error codes: `docs/modules/llm.md`.

