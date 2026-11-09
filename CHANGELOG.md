# Changelog

All notable changes. Versions follow the package version in `pyproject.toml`. Unreleased changes are on `main` and not
yet tagged. API changes are additive unless stated, and `docs/api/openapi.json` is regenerated with each one.


## Unreleased

- **References use full official titles.** Citations in rule traces, messages, API descriptions, the case pack, the traceability
  report, tests and documentation now give the full title with the abbreviation and year (for example *Community-Based
  Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016* and *Care of the Infant and Newborn (COIN), Malawi, 2017*),
  never an abbreviation alone. New `thanzi_screen.references` holds the titles. **Contract change:** the `source` field of each
  rule in the classification trace is now the full title (it was the register id `R3`), and the preterm `tag` for rules taken
  from the manual is now the full title (it was `COIN`). Worker-facing classification messages name the guideline in full.

### Added
- **Service information endpoints.** `GET /v1/about` returns service and rule-set versions, health, uptime, the route
  list and the state of each component (`screening_engine`, `ml_logistic`, `ml_deep`, `growth_monitoring`,
  `llm_service`). It never calls the language-model server and never returns its address. `GET /v1/metrics` returns
  request counts per known route, responses per status code, the 5xx count and `/v1/screen` latency (p50, p95, max, mean
  over the last 1,000 calls). Counts and durations only, in memory, reset on restart, one set per worker process. Both
  require the gateway key. `/health` and `/version` are unchanged.
- **Growth trends.** `thanzi_screen.growth.trend` compares WHO z-scores between two visits for weight-for-age,
  length/height-for-age and head circumference-for-age. Weight and length are flagged for a fall of 1.0 SD or more or a
  new fall below -2 or -3; head size for a change of 1.0 SD or more in either direction. Advisory only: a flag sets
  `review_suggested` and a review note, never a finding under the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 or referral. `previous_measurement` gains optional
  `length_height_cm`, `measure_position` and `hc_cm`; `growth_monitoring` gains `trends`, `review_suggested`,
  `review_note` and `reference_derived`. New WHO head circumference-for-age tables with checksums.
- **Growth monitoring.** `thanzi_screen.growth` compares weight gain (g per day) between an earlier visit and the current
  one with the ASPEN reference range. Optional request field `previous_measurement` and optional response field
  `growth_monitoring`. Under-five route only. Not assessed, with a stated reason, for intervals under 28 days, implausible
  weights and ages beyond the engine's range.
- **Deep recording-error flag.** `thanzi_screen.ml.dl` is a dense neural network in plain Python with presets, a parameter
  budget, hardware detection and JSON persistence. `POST /v1/screen` adds `ml_flags.deep_recording_error` beside the
  logistic flag and `GET /version` adds `deep_model_version`. Advisory only. `THANZI_DEEP_ENABLED=0` turns it off. A failure
  inside it is logged by type and screening continues. Trained on synthetic data only.
- **Free-text note checker.** `thanzi_screen.ml.nlp` finds clinical findings in a note (present, absent, uncertain),
  cross-checks them against the structured entry and masks obvious identifiers. Library only: not exposed by the API.
- **Local language-model client.** `thanzi_screen.llm`: async client for Ollama, llama.cpp and OpenAI-compatible servers,
  with a mock provider, concurrency limits, bounded queue, limited retries and health checks that never raise. Optional
  routes `GET /v1/llm/health` and `POST /v1/llm/generate` exist only when `THANZI_LLM_ENABLED=1`. New optional extra
  `llm`. Independent of the screening code in both directions.
- **Preterm and low-birth-weight screening.** `thanzi_screen.preterm` (Fenton 2025 z-scores, Care of the Infant and Newborn (COIN), Malawi, 2017 rules) with
  automatic routing in `POST /v1/screen` by `gestational_age_weeks` and `birth_weight_g`: the preterm engine under 50
  weeks post-menstrual age, then the under-five engine on corrected age. New optional request fields and response models
  `PretermResponse`, `PretermAuditResponse` and `BirthContext`. Requests without the new fields behave as before.
- Documentation: architecture, configuration, security and operations guides; gateway integration guide.

### Changed
- Preterm and corrected-age babies are not run through growth monitoring and the deep flag; a warning says so.

## 0.7.0 - release candidate, not validated

### Added
- Test evidence: rule traceability matrix generated from a full test run, property and invariant tests, hostile-input
  robustness tests, coverage reported in CI.
- Case pack for clinical review (`docs/testing/case-pack.xlsx`), generated from the engine. CI fails if it drifts.
- Tools: `scripts/smoke_api.py` (black-box smoke test), `scripts/load_probe.py`, `scripts/build_traceability.py`,
  `scripts/build_case_pack.py`, `scripts/refresh_constraints.py`.
- CI hardening: Actions pinned to commit SHAs, job timeouts, concurrency control, pip cache, container smoke test, `pip-audit`,
  Trivy image scan, gitleaks history scan, CycloneDX SBOM and Dependabot.
- Reproducible builds: `constraints.txt` pins every dependency and the Dockerfile and CI install with it.
- Release workflow (tag `v*`): builds and tests the image and publishes a pre-release with the image tarball, SBOMs,
  checksums and test evidence.
- Deployment runbook and an example compose file.

### Fixed
- A `length_height_cm` that is not positive after the 0.7 cm age-convention conversion is rejected as an input error (422)
  instead of causing a generic 500.

## 0.6.0

- `thanzi_screen.api`: framework-free `service.screen(payload, view, models)`, `security` (gateway and audit keys,
  fail-closed start, HIV scrub of worker responses) and a thin FastAPI app (`create_app`, `create_app_from_env`).
  Endpoints `GET /health`, `GET /version` and `POST /v1/screen?view=worker|audit`. Stateless, no request logging, unknown
  and identifying fields rejected.
- Worker view: no HIV information, no programme for moderate cases, no raw `referral_text`. Audit view (separate key) keeps
  the real programme, rule codes, warnings, referral text and the full explanation.
- Degraded mode when ML models are missing or mismatched: rules result unchanged and `ml_flags.available` false.
- `thanzi_screen.schemas`: pydantic request and response models. `docs/api/openapi.json` generated by
  `scripts/export_openapi.py` (`--check` in CI).
- `Explanation.worker_summary`, `explain_rules_only`, and `flag_trace` may be None.
- `Dockerfile` (non-root, health check, no published port, no secrets), `.dockerignore` and a CI workflow (Python 3.11 and
  3.12, full tests, OpenAPI check, Docker smoke job).

## 0.5.0

- `thanzi_screen.explain`: `explain(...) -> Explanation` with a worker summary (2 to 3 lines) and audit traces:
  classification (rules with source and page, criteria against cut-offs, margins), ML flag (exact signed contributions,
  tree path) and review reasons with evidence.
- Message catalogue with stable codes (`explain/messages.py`). English draft. HIV wording in the audit trace only.
- `scripts/explain_demo.py`. Explanations never change a classification or a flag.

## 0.4.0

- Rules-based review flag (`thanzi_screen.rules.review`) with reason codes and plain-language messages.
- `thanzi_screen.ml`: leak-free features, plain-Python logistic regression and shallow decision tree (JSON models), a
  recording-error flag with a suggested field to recheck, and `flag_record` returning a separate `MlFlags`.
  `ClassificationResult` is unchanged.
- Trained models, metrics and a model card in `models/`. An ML replica of the review rules is kept as a non-production
  diagnostic.
- `scripts/train_models.py` and an optional dev-only `scripts/compare_sklearn.py`.

## 0.3.0

- `thanzi_screen.data`: seeded synthetic generator (50,000 random records plus 16 boundary records), recorded-error
  injection with ground-truth labels, missingness, leak-free stratified splits, validation, SHA-256 manifest, and a loader
  that refuses unverified or non-synthetic data.
- `scripts/generate_synthetic.py`. Coarse `district` field. MUAC is a placeholder model, not WHO MUAC-for-age.

## 0.2.0

- Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 classification and referral (`thanzi_screen.rules`): low risk, MAM, SAM-OTP, SAM-inpatient, SAM-assess and
  unable to classify.
- Rule registry with source, page and tag per rule. Infant (under 6 months) pathway. HIV-positive MAM rule.
- Weight under 3.0 kg at 6 months or older triggers inpatient care. `AnthropometryResult.weight_kg` added.
- Safety tests: never less urgent than the most severe criterion; never OTP without complete information.

## 0.1.0

- Anthropometric engine: WHO z-scores for weight-for-age, length/height-for-age and weight-for-length/height (0 to 59
  months).
- WHO adjusted method for weight-based indicators beyond ±3 SD, with flags.
- Checksummed reference tables, a conversion script, and unit tests including WHO worked examples.

## 0.0.0

- Project scaffold, specification and reference register.
