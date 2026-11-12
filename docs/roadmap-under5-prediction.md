# Roadmap: under-five screening and ML prediction

Two independent modules, one reporting interface. Each phase ends with passing tests and a documented limitation list.

| Phase | Content | Status |
|---|---|---|
| 1 | Factor schema, deterministic indicators, MUAC, oedema, multi-visit velocity and faltering, report interface | done (this change) |
| 2 | Longitudinal dataset schema and simulator, preprocessing, feature engineering (all six factor groups), leak checks | done |
| 3 | Targets (future wasting, future SAM, future growth faltering), Logistic Regression, Random Forest and XGBoost, child-level splits, comparison with paired bootstrap, calibration | planned |
| 4 | Explainability (exact contributions and TreeSHAP, reuse `ml/risk`), risk strata, safety safeguards, model card | planned |
| 5 | API route, report wiring, OpenAPI, release notes | planned |

Rules that hold in every phase: the prediction module never uses the CMAM classification or tier as a feature, only adds
concern, is off unless enabled, refuses simulated models for clinical use, and needs ethics, data-agreement and clinical
sign-off references for real data. Training libraries stay on the development machine only.
