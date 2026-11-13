# API service

A small, stateless HTTP service around the screening engine. Decision support, not diagnosis.
The machine-readable contract is [`docs/api/openapi.json`](../api/openapi.json). Regenerate it after any API change with
`python scripts/export_openapi.py`; CI runs `--check`.

## Layout

- `src/thanzi_screen/api/service.py`: framework-free core, `screen(payload, view, models) -> dict`.
- `src/thanzi_screen/api/security.py`: key checks (constant time), fail-closed start, HIV scan of worker responses.
- `src/thanzi_screen/api/wording.py`: neutral wording for moderate cases. Draft, pending clinical review.
- `src/thanzi_screen/api/metrics.py`: in-memory request counters and latency.
- `src/thanzi_screen/api/app.py`: thin FastAPI app. `create_app(models=None, gateway_key=None, audit_key=None,
  dev_mode=False, models_dir=None)` and `create_app_from_env()` for uvicorn.
- `src/thanzi_screen/schemas/`: pydantic request and response models.

## Run

```bash
pip install -c constraints.txt -e ".[api]"
export THANZI_GATEWAY_KEY=<at least 16 characters>
export THANZI_AUDIT_KEY=<at least 16 characters, different>      # optional: unset turns the audit view off
uvicorn --factory thanzi_screen.api.app:create_app_from_env --host 127.0.0.1 --port 8080
```

Environment variables: see [configuration](../configuration.md).

## Endpoints

| Route | Key | Notes |
|---|---|---|
| `GET /health` | none | `{"status": "ok"}` or `"degraded"`. Nothing else |
| `GET /version` | gateway | Engine, rule set and model versions (`model_version`, `deep_model_version`), status, disclaimer |
| `GET /v1/about` | gateway | Versions, health, uptime, route list and the state of each component. No child data |
| `GET /v1/metrics` | gateway | Request counts by route and status, 5xx count, `/v1/screen` latency (p50, p95, max, mean). Counts and durations only, in memory, reset on restart, per worker process |
| `POST /v1/screen?view=worker` | gateway | Default view. One child per call |
| `POST /v1/screen?view=audit` | gateway + `X-Audit-Key` | Full detail. May contain HIV information |
| `POST /v1/report` | gateway | Same request as `/v1/screen`. Individual child report from the worker view. Off unless `THANZI_CHILD_REPORT_ENABLED=1`. Draft wording. See [child-report](child-report.md) |
| `POST /v1/surveillance/report` | gateway | Grouped facility counts and the org unit list in, facility, district and national report out. Off unless `THANZI_SURVEILLANCE_REPORTS_ENABLED=1`. No child data. Body limit 1 MB. See [surveillance-reports](surveillance-reports.md) |
| `POST /v1/surveillance/dhis2` | gateway | Same input plus a mapping. DHIS2 data value set out (facility level, `dryRun=true` advised). Off unless `THANZI_SURVEILLANCE_REPORTS_ENABLED=1`. Nothing is sent to DHIS2 |
| `POST /v1/surveillance/hotspots` | gateway | Grouped district counts in, hotspot assessment out. No child data. Body limit 256 KB. See [surveillance](surveillance.md) |
| `GET /v1/llm/health`, `POST /v1/llm/generate` | gateway | Only when `THANZI_LLM_ENABLED=1`. See [llm](llm.md) |

The gateway key goes in `X-Gateway-Key` and the audit key in `X-Audit-Key`. A missing or wrong gateway key gives a
generic 401 on every route except `/health`, including unknown routes. `/docs`, `/redoc` and `/openapi.json` are off
outside dev mode. No CORS headers are sent.

## Request

```json
{"sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0, "measure_position": "length",
 "oedema": "none", "muac_cm": 12.0, "appetite": "passed", "danger_signs": [], "complications": [],
 "clinically_well_and_alert": true, "hiv_positive": null}
```

- Required: `sex`, `age_days`, `weight_kg`, `length_height_cm`, `measure_position`, `oedema`. Oedema is never assumed absent.
- Optional clinical fields: `muac_cm`, `appetite`, `danger_signs`, `complications`, `clinically_well_and_alert`,
  `hiv_positive`, `visible_severe_wasting`, `too_weak_to_suckle`, `failure_to_gain_weight`, `hc_cm`.
- `null` or omitted means not assessed. `[]` means assessed, none present. An omitted `appetite` means `not_done`.
- Age is `age_days` only. Unknown fields, including `name`, `child_id` and `date_of_birth`, give 422. Types are strict.
- Birth context for preterm routing: `gestational_age_weeks`, `birth_weight_g` (grams) and the preterm fields in
  [preterm](preterm.md).
- `previous_measurement` for growth monitoring: see [growth](growth.md).
- Units: weight in kg, length, height, MUAC and head circumference in cm. `birth_weight_g` is the only value in grams.
- Body limit 16 KB.

## Worker response

`worker_summary` (2 to 3 lines), `classification`, `tier`, `programme`, `rules_fired`, `reasons`, `warnings`,
`ml_flags`, `rule_set_version`, `model_version`, `status`, `disclaimer`. Optional: `route`, `birth_context`,
`clinical_assessment`, `growth_monitoring`. No `referral_text`.

| Field | Values |
|---|---|
| `classification` | `low_risk`, `MAM`, `SAM_OTP`, `SAM_INPATIENT`, `SAM_ASSESS`, `UNABLE_TO_CLASSIFY` |
| `tier` | `low_risk`, `mam`, `urgent`, `recheck`. `null` for the preterm `follow_up` disposition |

Worker-view rules:

- No HIV information and no programme for any moderate (MAM) child. For every MAM child `programme` is null, the HIV and
  non-HIV programme rule codes both show as `MAM.REFER`, summary line 2 is a neutral referral line, and a neutral warning
  is always present. The whole worker response is identical for `hiv_positive` true, false and null.
- The audit view keeps the real programme, rule codes, warnings, `referral_text` and the full explanation.

### `ml_flags`

- `available`: false in degraded mode.
- `recording_error` and optional `deep_recording_error`: `{flagged, suggested_field, messages}`. `suggested_field` is
  `weight`, `length_height`, `muac` or `age`. The audit view adds `probability`. The deep flag is absent when the deep
  model is not loaded, in degraded mode, and on the preterm and corrected-age routes.
- `review`: `{needed, reasons[]}`, a deterministic rules-based "a person should look again" signal. Always present.
- Flags are advisory. The classification, tier, reasons and review never depend on them.

## Preterm routing

`POST /v1/screen` accepts optional `gestational_age_weeks` and `birth_weight_g`. A baby born under 37 weeks or under
2500 g and under 50 weeks post-menstrual age receives the preterm response (`route: preterm`, `preterm_level`, mapped
`tier`). From 50 weeks the under-five response is returned on corrected age with `route: under5_corrected_age` and
`birth_context`. See [preterm](preterm.md).

## Growth monitoring

`growth_monitoring` appears when the request includes `previous_measurement`. It is advisory, runs on the under-five
route only, and sets `review_suggested` when anything is flagged. See [growth](growth.md).

## Errors

| Status | Code |
|---|---|
| 401 | `unauthorised` |
| 403 | `audit_forbidden` |
| 413 | `payload_too_large` (declared body over 16 KB) |
| 422 | `invalid_request`, `invalid_input`, `missing_field`, `unknown_field`, `invalid_json`. Messages never echo submitted values |
| 500 | `internal_error`. Generic, no trace and no input |

## Degraded mode

If the model files are missing or do not match the feature list, the service starts, `/health` reports `degraded`, and
screening still returns the rules result with `ml_flags.available: false`. The rules-based review check and growth
monitoring still work. Missing or mismatched deep-model files leave `deep_recording_error` absent and `/health` at `ok`
(health reflects the logistic models).

## Not provided, by design

No database, no stored requests, no request-body logging, no per-child batch endpoint, no child identifiers. The hotspot, report and DHIS2 routes take grouped counts only.

## Optional language-model routes

`GET /v1/llm/health` and `POST /v1/llm/generate` exist only when `THANZI_LLM_ENABLED=1`. They sit behind the gateway
key, are not part of screening, and change no screening response. See [llm](llm.md).

## Tests

`tests/api/`: `test_service.py` (core), `test_security.py`, `test_http.py` (needs FastAPI and httpx),
`test_robustness.py`, `test_packaging.py`, `test_release_files.py`, `test_about_metrics.py`, `test_deep_flag.py`,
`test_growth_monitoring.py`, `test_growth_trends.py`, `test_preterm_http.py`, `test_llm_routes.py`. With
`THANZI_REQUIRE_API_TESTS=1` (CI) a missing FastAPI fails the run instead of skipping.
