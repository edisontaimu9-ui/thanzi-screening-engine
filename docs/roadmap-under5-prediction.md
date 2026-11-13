# Roadmap: under-five screening and ML prediction

Two independent modules, one reporting interface. Each phase ends with passing tests and a documented limitation list.

| Phase | Content | Status |
|---|---|---|
| 1 | Factor schema, deterministic indicators, MUAC, oedema, multi-visit velocity and faltering, report interface | done (this change) |
| 2 | Longitudinal dataset schema and simulator, preprocessing, feature engineering (all six factor groups), leak checks | done |
| 3 | Logistic Regression, Random Forest and XGBoost for the three targets, child-level splits, comparison with paired child-level bootstrap, Platt calibration, subgroup and follow-up checks (targets and splits came in Phase 2) | done |
| 4 | Model export (the service runs without scikit-learn or XGBoost), explainability (exact contributions and TreeSHAP, a tested copy of the `ml/risk` tree code), risk strata, safety safeguards, model card | done |
| 5 | API block on `/v1/screen`, OpenAPI, release notes (report wiring is not done: see the limits in `docs/modules/prediction-export.md`) | done |
| 6 | Pathway-specific minimum inputs, three empty-input states (not assessed, not applicable, unavailable), comparable-earlier-visit rules, `inputs` in the API block | done (this change) |
| 7 | Pathway training and export: an anthropometric pathway model trained and tested with clinical, feeding, maternal and household inputs empty, so they never stop a score and are never filled in | done (this change) |
| 8 | Several one-target models run together and consolidated into one `ml_prediction` summary for the worker. Escalate only. Rules stay authoritative (tested) | done |
| 9 | Individual child report (`POST /v1/report`, off by default): screening is not diagnosis, escalate only, worker view only. Wording is a draft with a review sheet; clinical review is outstanding | built, wording awaiting review |
| 10 | Aggregated surveillance reports (facility, district, national) with DHIS2 export (data value sets, mapping file, org unit codes). Off by default; thresholds, small-count export and DHIS2 ids need Ministry sign-off | built, awaiting Ministry decisions (this change) |
| 11 | Clinical review pack and deployment gates: reviewer checklist, sign-off files tied to the exact wording and settings, a gate in the service and a preflight script so the Phase 9 and 10 features cannot be switched on without them (`docs/modules/review-pack.md`) | built, awaiting reviewers (this change) |

Decisions behind phases 6 to 11 (owner, 2026): one prediction target per model file; consolidate for the worker; deterministic rules and referral
always win; strict missing-data handling with pathway minimums; never impute silently; earlier visits only when valid and comparable;
every phase needs tests and clinical review before deployment.

Rules that hold in every phase: the prediction module never uses the CMAM classification or tier as a feature, only adds
concern, is off unless enabled, refuses simulated models for clinical use, and needs ethics, data-agreement and clinical
sign-off references for real data. Training libraries stay on the development machine only.
