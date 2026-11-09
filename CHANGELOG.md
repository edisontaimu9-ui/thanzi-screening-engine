# Changelog

## Unreleased - about and metrics endpoints (add-on)
- New `GET /v1/about` (gateway key): service and rule-set versions, `health`, uptime, route list and a `components` list (`screening_engine`, `ml_logistic`, `ml_deep`, `growth_monitoring`, `llm_service`) with state, version and detail. It never calls the LLM server and never returns its address. The ML models run inside the API, so they are components, not a separate service.
- New `GET /v1/metrics` (gateway key): requests per known route (anything else under `other`), responses per status code, 5xx count, and `/v1/screen` latency (p50, p95, max, mean over the last 1000 calls). Counts and durations only, in memory, reset on restart, one count per worker process (D176). Refused calls (401, 413) are counted.
- New `src/thanzi_screen/api/metrics.py`; `about_info` in `api/service.py`; schemas `AboutResponse`, `ComponentInfo`, `MetricsResponse`, `LatencyStats`. Additive contract change; `docs/api/openapi.json` regenerated. `/health` and `/version` unchanged.
- Tests: `tests/api/test_about_metrics.py` (15); the every-route-needs-the-key test now covers both routes.
- Docs: `docs/deployment/integration-guide.md` section 6 (what the gateway should GET, what to track, rules), `docs/modules/api.md`, `docs/deployment/runbook.md`. Decision D176.

## Unreleased - growth trends and verified weight-gain reference (add-on)
- New `thanzi_screen.growth.trend`: change in WHO z-score between two visits for weight-for-age, length/height-for-age and head circumference-for-age. Weight and length are flagged for a fall of 1.0 SD or more, or a new fall below -2 or -3; head size for a change of 1.0 SD or more either way. Advisory only (D9), stateless, standard library. A flag sets `review_suggested` and a clinician-review note; no CMAM finding, no referral (D170).
- API: `previous_measurement` gains optional `length_height_cm`, `measure_position` and `hc_cm`; this visit's `hc_cm` is reused on the under-5 route. `growth_monitoring` gains `trends`, `review_suggested`, `review_note` and `reference_derived`. All additive; `docs/api/openapi.json` regenerated. Existing keys unchanged.
- New WHO head circumference-for-age tables (R20, four files, checksummed in `MANIFEST.json`; `scripts/build_reference_tables.py` extended; the existing eight tables are byte-identical). Technical guide R21 added to the register.
- R19 weight table verified against the handbook by Edison. Girls 3 to 6 months reads 21-21 there, so a range of 17 to 25 g/day is derived (D164) and marked `reference_derived`. This replaces the earlier "not assessed" for that band. The 28-day minimum is kept (D171).
- Preterm and corrected-age babies still skip growth monitoring with a warning (D172).
- Tests: `tests/growth/test_trend.py` (63), `tests/anthro/test_hc_tables.py` (19), `tests/api/test_growth_trends.py` (62); weight-gain tests updated for the verified reference. Decisions D164 to D173; open issues I64 to I69; I59 closed, I60 and I61 decided, I62 partly closed.

- Edison verified the 1.0 SD trend threshold, the derived girls 3 to 6 month range, the head circumference limits and the message wording (D174): I64, I65, I66 closed, I61 closed. Docs only; no code change.

- I67 and I69 closed by decision (out of scope until a source exists); I68 closed on our side only: Hope has not started the gateway or backend and will follow the engine design (D175). Docs only.

## Unreleased - growth monitoring (add-on)
- New package `thanzi_screen.growth`: weight-gain velocity (g per day) between an earlier visit and this one, compared with the ASPEN reference range (R19), averaged across age bands. Advisory only (D9): the classification, tier, reasons, review, ML flags and wording are identical with and without it (tested). Standard library only; rule-based, so it works in degraded mode.
- API: optional request field `previous_measurement` (`age_days`, `weight_kg`) and optional response field `growth_monitoring` in both views. Additive; `docs/api/openapi.json` regenerated. Under-5 route only; preterm and corrected-age babies get a warning that it was not run.
- Not assessed, with a stated reason: interval under 28 days, implausible weight, girls 3 to 6 months (the source reads 21-21, treated as unusable), ages past the engine's range.
- The reference table was transcribed from a screenshot and has not been checked against the handbook (I59). The 28-day minimum is an engineering choice (I60).
- Tests: `tests/growth/test_velocity.py` (39), `tests/api/test_growth_monitoring.py` (67). Docs: `docs/modules/growth.md`, R19 in the register, decisions D157 to D163, open issues I59 to I63.

## Unreleased - deep learning (add-on, not validated)
- New package `thanzi_screen.ml.dl`: dense neural network in plain Python (ReLU, Adam, early stopping, optional dropout, class weights, binary or softmax output, JSON save and load), presets `tiny`, `small`, `base` with a 20,000-parameter budget, hardware detection with a preset recommendation, training from the verified synthetic dataset, and inference (`flag_record_deep`, `compare_record`, `predict_batch`). Standard library only; no new packages and `dependencies` stays empty.
- Switched on (D153, Edison 2026-11-08): `POST /v1/screen` adds `ml_flags.deep_recording_error` beside the logistic flag (which stays); `GET /version` adds `deep_model_version`. Model files carry `production: true`. Advisory only: classification, tier, reasons, review and wording are identical with and without it (tests). A failure in it is logged by type and screening continues. `THANZI_DEEP_ENABLED=0` turns it off. Additive contract change; `docs/api/openapi.json` regenerated. Only `api/app.py` and `api/service.py` import the package (AST test).
- Not run in degraded mode or on the corrected-age route. Still synthetic data only, not validated on real children.
- New: `scripts/train_deep.py` (`--preset tiny|small|base|auto`), `models/recording_error_mlp.json`, `models/recording_field_mlp.json`, `models/DL_MODEL_CARD.md`. Existing Phase 4 models and card unchanged.
- Tests: `tests/ml/test_dl.py` (42), `tests/api/test_deep_flag.py` (28). One existing test (`test_worker_view_by_default_matches_the_core`) now passes the app's deep models to the core call. Synthetic results match the logistic model (AUC 0.997 both); no claim about real data.
- Docs: `docs/deployment/integration-guide.md` (technical guide for Hope: architecture, responsibilities, request flow, contract use, failure handling, other components, storage, security, testing), `docs/deployment/deep-flag-integration.md` (gateway integration note with real example, checks and rollback), `docs/modules/dl.md`; decisions D145 to D156; open issues I53 to I58 (I56 decided).

## Unreleased - NLP for free-text notes (add-on, not validated)
- New package `thanzi_screen.ml.nlp`: finds clinical findings in a free-text note (present, absent, uncertain), cross-checks them against the structured entry (advisory reasons, never changes a result), and masks obvious identifiers (best-effort). Standard library only; lexicon in `lexicon.json` (draft, English, shipped as package data).
- Not wired into the API: no route, schema or `openapi.json` change. Independent of the screening code in both directions (AST tests). HIV is excluded from the lexicon.
- Tests: `tests/ml/test_nlp.py` (68), including a 30-note synthetic regression set (not validation).
- Docs: `docs/modules/nlp.md`; decisions D135 to D144; open issues I48 to I52. I43 recorded as decided (keep the LLM route, off by default).

## Unreleased - local LLM client (add-on, not validated)
- New package `thanzi_screen.llm`: async client for local model servers (Ollama, llama.cpp, OpenAI-compatible) with a provider registry and a mock provider. Configurable model, endpoint, timeouts and generation settings; concurrency limit, bounded queue, limited retries, health checks that never raise; `<think>` removal for Qwen3-style models. Independent of the screening code in both directions (tests enforce it).
- Optional routes `GET /v1/llm/health` and `POST /v1/llm/generate`, mounted only when `THANZI_LLM_ENABLED=1`. `create_app(llm=...)` and a lifespan that closes the client. `docs/api/openapi.json` unchanged. Screening behaviour and `/health` unchanged (tested with a dead model server).
- `pyproject.toml`: new optional extra `llm` (httpx, already pinned). Release `Dockerfile` unchanged. New `deploy/llm.env.example`, `deploy/docker-compose.llm.example.yml` (untested), `deploy/Dockerfile.llm`.
- Docs: `docs/modules/llm.md`; decisions D128 to D134; open issues I43 to I47; register R16 to R18.
- Open: real-server run (I45), model licences (I44), whether to keep the generate route (I43).

## Unreleased - preterm integration (not validated)
- New `thanzi_screen.preterm`: the supplied preterm engine (Fenton 2025 + COIN 2017) added without logic changes, with `routing.py`, `routing_config.json` and `integration.py`. Fenton data kept unmodified (CC BY-NC-ND 4.0).
- `POST /v1/screen` routes babies born under 37 weeks or under 2500 g: preterm engine under 50 weeks PMA, under-5 engine on corrected age after. New optional request fields (`gestational_age_weeks`, `birth_weight_g`, `neonatal_danger_signs` and others). Requests without them behave exactly as before. New response models `PretermResponse`, `PretermAuditResponse`, `BirthContext`; `docs/api/openapi.json` regenerated.
- `ml/preterm_features.py`: `features()` row and vector, separate from `FEATURES` so saved models still load. `rule_level` is never a label.
- `pyproject.toml` package data and a Dockerfile build check ship the JSON files in the image. Still one image.
- Decisions applied (2026-11-08): follow_up has no under-5 tier; corrected-age end for GA 32 to under 37 weeks is provisional; hypoglycaemia and oedema escalation are configurable per the protocol; length and position are optional only on the preterm route; unknown GA gives a clinical-assessment flag; worker wording says "faltering growth" while the audit keeps CMAM terms; urgent triggers come from `preterm_rules.json`.
- Approved (2026-11-08): 24-month corrected-age end; hypoglycaemia (complication) and any oedema grade give urgent_refer per CMAM 2016 Table 5; null tier allowed for follow_up; corrected age feeds all age-dependent CMAM criteria.
- Open questions: `docs/decisions/decision-log.md` I32 to I40. Version stays 0.7.0 until Edison decides the release.

## 0.7.0 - Phase 7 (release candidate, not validated)
- Test evidence: rule traceability matrix generated from a full run (`docs/testing/traceability.md`); property and invariant tests; hostile-input robustness tests; coverage reported in CI (not gated).
- Case pack for clinical review (`docs/testing/case-pack.xlsx`), generated from the engine; CI fails if it drifts.
- Tools: `scripts/smoke_api.py` (black-box smoke test), `scripts/load_probe.py` (latency and throughput), `scripts/build_traceability.py`, `scripts/build_case_pack.py`, `scripts/refresh_constraints.py`.
- CI hardening: Actions pinned to commit SHAs, job timeouts, concurrency, pip cache, stronger container smoke test (key handling, HIV scrub, audit split, healthcheck, log check), `pip-audit`, Trivy image scan, gitleaks history scan, CycloneDX SBOM, Dependabot.
- Reproducible builds: `constraints.txt` pins every dependency; the Dockerfile and CI install with it.
- Release workflow (tag `v*`): builds and tests the image, publishes a pre-release with image tarball, SBOMs, checksums and test evidence.
- Deployment: runbook and an example compose file.
- No change to classification rules, thresholds, wording or API behaviour. Version 0.7.0.
- Fixed before the tag (I28, D106): a `length_height_cm` that is not positive after the 0.7 cm age-convention conversion is rejected as `InputError` (422 over HTTP) instead of causing a generic 500. Regression tests replace the expected-failure markers. No other behaviour changes.

## 0.6.0 - Phase 6
- `thanzi_screen.api`: framework-free `service.screen(payload, view, models)`, `security` (gateway and audit keys, fail-closed start, HIV scrub of worker responses), thin FastAPI `app` (`create_app`, `create_app_from_env`). Endpoints `GET /health`, `GET /version`, `POST /v1/screen?view=worker|audit`. Stateless, no request logging, unknown and identifying fields rejected.
- Worker view: no HIV information, no programme for any MAM child (D86), no raw `referral_text`. Audit view (separate key) keeps real programme, rule codes, warnings, referral text and the full `Explanation`.
- Degraded mode when ML models are missing or mismatched: rules result unchanged, `ml_flags.available` false.
- `thanzi_screen.schemas`: pydantic request and response models. `docs/api/openapi.json` generated by `scripts/export_openapi.py` (`--check` in CI).
- Phase 5 additions only: `Explanation.worker_summary` (read-only alias), `explain_rules_only`, `flag_trace` may be None.
- `Dockerfile` (non-root, healthcheck, no port published, no secrets), `.dockerignore`, `.github/workflows/ci.yml` (Python 3.11 and 3.12, full tests with `THANZI_REQUIRE_API_TESTS=1`, OpenAPI check, Docker smoke job). `pyproject.toml` extra `api`.

## 0.5.0 - Phase 5
- `thanzi_screen.explain`: `explain(...) -> Explanation` with a worker summary (2-3 lines) and audit traces: classification (rules with source and page, criteria against cut-offs, margins), ML flag (exact signed contributions, tree path) and review reasons with evidence.
- Message catalogue with stable codes (`explain/messages.py`). English draft; HIV wording in the audit trace only.
- `scripts/explain_demo.py`. Explanations never change a classification or a flag.

## 0.4.0 - Phase 4
- Rules-based review flag (`thanzi_screen.rules.review`) for ML target B, with reason codes and plain-language messages (D45).
- `thanzi_screen.ml`: leak-free features, plain-Python logistic regression and shallow decision tree (JSON models), recording-error flag with suggested field to recheck (target A), `flag_record` returning a separate `MlFlags`. `ClassificationResult` unchanged.
- Trained models, metrics and model card in `models/`; ML replica of the review rules kept as a non-production diagnostic.
- `scripts/train_models.py`; optional dev-only `scripts/compare_sklearn.py`.

## 0.3.0 - Phase 3
- `thanzi_screen.data`: seeded synthetic generator (50,000 random records plus 16 boundary records), recorded-error injection with ground-truth labels, missingness, leak-free stratified splits, validation, SHA-256 manifest, loader that refuses unverified or non-synthetic data.
- `scripts/generate_synthetic.py` CLI. Coarse `district` field (D33). MUAC is a placeholder assumption, not WHO MUAC-for-age.
- Labels for ML targets A (injected error) and B (review reasons) added. No deterioration target (C deferred).

## 0.2.0 - Phase 2
- CMAM 2016 classification and referral (`thanzi_screen.rules`): low risk, MAM, SAM-OTP, SAM-inpatient, SAM-assess, unable to classify.
- Rule registry with source, page and tag per rule; infant (<6 months) pathway; HIV-positive MAM rule.
- Weight <3.0 kg at 6 months or older triggers inpatient (R3 Table 5, D29). `AnthropometryResult.weight_kg` added.
- Safety tests: never less urgent than the most severe criterion; never OTP without complete information.

## 0.1.0 - Phase 1
- Anthropometric engine: WHO z-scores for weight-for-age, length/height-for-age, weight-for-length/height (0-59 months).
- WHO adjusted method for weight-based indicators beyond +/-3 SD, with flags.
- Checksummed reference tables, conversion script, 126 unit tests, including WHO worked examples.

## 0.0.0 - Phase 0
- Project scaffold, specification, reference register, decision log.
