# Changelog

All notable changes. Versions follow the package version in `pyproject.toml`. Unreleased changes are on `main` and not
yet tagged. API changes are additive unless stated, and `docs/api/openapi.json` is regenerated with each one.


## Unreleased

- **Aggregated surveillance reports and DHIS2 export (Phase 10).** `POST /v1/surveillance/report` takes counts already grouped per facility and month plus the org unit
  list (national, districts, facilities) and returns a facility, district and national report: sums that always agree, reporting completeness (a facility that did not
  report is `not_reported`, never zero), district hotspot status from the existing hotspot rule, `data_status` (`insufficient_data` shows counts but no rate), and small-cell
  suppression with secondary suppression so a hidden count cannot be worked out by subtraction. `POST /v1/surveillance/dhis2` returns the facility counts as a DHIS2
  `dataValueSets` body from a caller-supplied mapping (data elements, id schemes, org unit ids): facility level only (DHIS2 rolls up), counts not rates, zero exported and a missing
  report not, an incomplete or invalid mapping stops the export, `dryRun=true` advised. Both routes are **off by default**: `THANZI_SURVEILLANCE_REPORTS_ENABLED=1` switches them on,
  otherwise `404 surveillance_reports_off`. Body limit 1 MB on these two routes only. New `thanzi_screen.surveillance.reports` and `.dhis2` (standard library) and `report_config.json`;
  `scripts/export_dhis2.py` writes the mapping template and org unit template (`docs/dhis2/`) and builds a data value set offline. Additive; `/v1/surveillance/hotspots` is unchanged and
  stays district only. `openapi.json` regenerated. **Awaiting Ministry decisions:** thresholds, whether facility SAM or MAM counts of 1 to 4 may be exported
  (`dhis2_export_suppresses_small_cells`, default `true`), DHIS2 ids. See `docs/modules/surveillance-reports.md`.
- **Individual child report (Phase 9).** `POST /v1/report` takes the `/v1/screen` request and returns one report: screening result, action, items to
  check, growth, prediction status, limits and sources. Built from the worker view only (no HIV information, no audit version). The result is copied,
  never recomputed, and growth or prediction findings can only lift `routine` to `raised`. Off by default: `THANZI_CHILD_REPORT_ENABLED=1` switches it on, otherwise
  `404 report_off`. **The wording is a draft pending clinical review** and every report says so. New `thanzi_screen.childreport` (standard library), the review sheet
  `docs/review/child-report-wording.md` (written by `scripts/export_report_wording.py`, covers the Phase 8 wording and severity order too), and `/v1/report` in
  the route list and metrics. Additive. `openapi.json` regenerated. See `docs/modules/child-report.md`.
- **One summary from several prediction models (Phase 8).** `THANZI_PREDICTION_MODEL` may be a file, a folder or a comma-separated list. `ml_prediction`
  is now one consolidated summary (concerns, not_scored, inputs, one message, authority statement), with each model's result under `models` in
  the audit view only. **Contract change** to the unreleased Phase 5 block (per-model fields moved under `models`). `prediction_model_version`
  lists every version. `openapi.json` regenerated.
- **Anthropometric pathway (Phase 7).** `export_prediction.py --pathway anthropometric` builds a measurements-only model that scores without
  history, feeding, birth, maternal or household answers, and without an earlier visit. Model files may use a subset of inputs. No API change.
- **Pathway minimums and input states (Phase 6).** `ml_prediction` is `not scored` for missing inputs only when they are essential to the model's
  pathway (`essential_input_unavailable`, replacing `too_many_missing_inputs`). The block gains `pathway` and `inputs` (not_assessed,
  not_applicable, unavailable, by group). An earlier visit is used only when valid and comparable. Additive except that reason code.
- **Prediction block in the API (Phase 5).** With `THANZI_PREDICTION_ENABLED=1` and `THANZI_PREDICTION_MODEL`, `/v1/screen` adds an
  advisory `ml_prediction` block (plain under-5 route). Additive: off by default, fail-safe, never changes the rules. `/version`
  gains `prediction_model_version` and `/v1/about` gains the `ml_prediction` component (after `ml_risk`). `openapi.json` regenerated.
  See `docs/modules/prediction-export.md`.
- **References use full official titles.** Citations in rule traces, messages, API descriptions, the case pack, the traceability
  report, tests and documentation now give the full title with the abbreviation and year (for example *Community-Based
  Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016* and *Care of the Infant and Newborn (COIN), Malawi, 2017*),
  never an abbreviation alone. New `thanzi_screen.references` holds the titles. **Contract change:** the `source` field of each
  rule in the classification trace is now the full title (it was the register id `R3`), and the preterm `tag` for rules taken
  from the manual is now the full title (it was `COIN`). Worker-facing classification messages name the guideline in full.

### Added
- **Prediction module, Phase 4 (exported model, risk strata, explanations, model card).** The selected model of each trained target is
  exported as one plain JSON file (`thanzi-prediction-model/1`) holding the preprocessor, the model (logistic coefficients or trees), Platt
  calibration, strata cut-offs, eligibility range, missing-input limit, target definition and provenance, and runs in the service without
  numpy, scikit-learn or XGBoost. `thanzi_screen.prediction.model` loads it and fails closed: a simulated model is refused unless
  allowed and can never be clinical; a real-data model needs ethics, data-agreement and clinical sign-off references and acceptance
  thresholds that were set in advance and passed. `predict.assess_child` adds concern only (two strata, `elevated` and `high`, never a
  "low risk" label), says nothing when there is no extra concern, never raises, and returns a stable "not scored" code for age outside the
  range, too many missing inputs or a gap never seen in training. `explain` gives exact contributions (logistic and exact TreeSHAP) and up
  to three plain-language drivers that raise the estimate. `scripts/export_prediction.py` checks every file against the training library
  (parity limit 1e-5) before writing it, and writes `MODEL_CARD.md`. The test report gains a strata table. `trees.py` is a tested copy of
  the `ml/risk` tree code because the prediction module never imports `thanzi_screen.ml`. **Fix:** a preprocessor loaded from a JSON file
  written with sorted keys had its columns in the wrong order; columns now follow the canonical feature order (tested). No API route yet
  (Phase 5). See `docs/modules/prediction-export.md`.
- **Prediction module, Phase 3 (model comparison and calibration, no exported model).** `thanzi_screen.prediction.evaluate`
  (standard library: AUROC, AUPRC, Brier, Platt calibration, calibration slope and intercept, calibration deciles, operating
  points, net benefit, subgroup tables, child-level bootstrap), `candidates` (logistic regression, random forest, XGBoost with
  the monotone constraints from the feature registry, and a best-single-feature baseline) and `compare` (one target at a time).
  Fixed order: preprocessor and models fitted on training children only, Platt calibration and the alert thresholds fitted on
  validation children, a challenger replaces logistic regression only if its validation AUROC gain is at least 0.01 and the paired
  child-level bootstrap interval excludes zero, and the test children are read once, to report. Intervals resample children, not
  rows. A target with fewer than 30 events in any split is reported as not trained. `scripts/train_prediction.py` writes
  `results.json` and `REPORT.md` (`models/prediction_sim/` by default, git-ignored). Training libraries are imported only inside
  the functions that need them (`train` extra, development machine only); importing the package loads none (tested). Nothing is
  marked for clinical use and no model file is exported yet. See `docs/modules/prediction-models.md`.
- **Prediction module, Phase 2 (library and simulator, no model yet).** `thanzi_screen.prediction`: longitudinal records,
  a one-row-per-visit CSV dataset with manifest and governance checks, labels for future wasting, future SAM and future
  growth faltering built from later visits (missing follow-up is censored, never negative; incident prediction excludes
  children already at the outcome), 63 leak-free features in seven groups (anthropometric, longitudinal growth,
  demographic, clinical, feeding, maternal, socioeconomic), child-level splits and a training-only preprocessor with
  missing-value indicators, and a clearly marked simulator (`scripts/simulate_longitudinal.py`). Independent of the
  screening module and the rules classifier (tested). All simulated associations are assumptions. See
  `docs/modules/prediction-data.md`. A feature that is missing at prediction time but was never missing in training is
  refused (`UnseenMissingError`) rather than imputed with the median.
- **Under-five screening module, Phase 1 (library only).** `thanzi_screen.factors` (shared factor-group schema: visits,
  demographic, clinical, feeding, maternal, socioeconomic), `thanzi_screen.under5` (WAZ, HAZ, WHZ status, MUAC category,
  oedema finding, multi-visit weight velocity and growth faltering with configurable thresholds, factor completeness) and
  `thanzi_screen.report` (unified report with separate screening and prediction blocks). Rules only, no ML imports (tested).
  MUAC-for-age z-scores are not computed because the WHO tables are not in the repository. Faltering thresholds are
  engineering choices, not clinical guidance. See `docs/modules/under5-screening.md` and `docs/roadmap-under5-prediction.md`.
- **Advisory clinical risk model (pipeline, simulated outcomes only).** `thanzi_screen.ml.risk` adds a second, data-driven opinion
  beside the rules: logistic regression, random forest and XGBoost candidates, Platt calibration, exact explanations (logistic
  contributions and exact TreeSHAP in plain Python), and a JSON model file the service evaluates without scikit-learn or XGBoost.
  `POST /v1/screen` adds an optional `ml_risk` block on the plain under-5 route when `THANZI_RISK_ENABLED=1` (off by default). It can only
  add a concern: classification, tier, referral and warnings are identical with it on or off (property-tested), it never reports a
  child as low risk, and it is not run for children under 6 months, with MUAC missing, with a suspected recording error, or on the
  preterm and corrected-age routes. A model trained on simulated outcomes is marked `non_clinical` and refused unless
  `THANZI_RISK_ALLOW_SIMULATED=1`; a model trained on real data is refused without ethics, data agreement and clinical sign-off
  references and a passed, pre-set acceptance check. New scripts `simulate_risk_outcomes.py` and `train_risk.py`, a simulated demo model in
  `models/risk_sim/` with its model card, `GET /v1/about` component `ml_risk` and `GET /version` field `risk_model_version`. No real data has
  been used: the numbers in the card only show the code works. See `docs/modules/ml-risk.md`.
- **Optional `train` extra.** `pip install -e ".[train]"` installs NumPy, scikit-learn and XGBoost for training the random forest and
  XGBoost risk-model candidates. Development machine only: not in the release image, not in `constraints.txt`, never imported by the service.
- **Hotspot surveillance.** `POST /v1/surveillance/hotspots` and `thanzi_screen.surveillance`. Takes counts per district and
  month (grouped by the caller, no child-level data), returns per-district prevalence with a Wilson interval, a trend and a
  status (`hotspot`, `watch`, `not_flagged`, `insufficient_data`, `no_data`). Small counts are suppressed, districts under 30
  screened are never read as low risk, and nothing changes any individual classification. Thresholds are placeholders in
  `hotspot_config.json`. The `/v1/screen` body limit is unchanged; this route allows 256 KB. Storage and grouping stay
  with the backend. See `docs/modules/surveillance.md`.
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
