# Phase 4 specification: risk-flagging ML (targets A and B)

Status: Q1-Q6 approved by Edison 2026-11-07 (D45-D50); implemented. Interpretations: D51-D56.

## Objective
Add advisory ML flags that help health workers catch bad measurements and cases needing a second look. Targets approved in D35: **A** detect measurement and data-entry errors; **B** flag borderline or inconsistent cases for clinician review. No deterioration prediction (C).

## Hard rules
- ML never changes a classification, tier, referral or warning from Phases 1-2 (D9). It adds separate flags only. A missed flag leaves the rules-only result unchanged.
- Flags use stable reason codes (for team translation) and plain-language explanations (Phase 5 builds on these).
- Trained on Phase 3 synthetic data only. The model card states: demonstration, not validated on real children, not for clinical deployment.
- Pure Python, standard library only at runtime, offline-friendly. Models saved as JSON, never pickle.

## Honest limits
- Target A labels are real by construction (we injected the errors), but injected-error types and rates are my assumptions (D41). Performance on real recording errors is unknown.
- Age heaping is a population-level pattern. One record cannot show it, so per-record detection will be weak. I will report this, not hide it.
- Target B labels are a deterministic function of engine outputs (D40). A model can at best copy that function, and the function itself is already code. So ML adds nothing for B today (see Q1).
- Many errors are already caught by Phase 1 plausibility flags. The ML must beat that baseline to justify itself.

## Resources
Phase 3 dataset (R-internal), Phase 1 and 2 engine. No new external sources. R8 and R9 are not blockers; retraining is expected when they arrive.

## Deliverables
1. `src/thanzi_screen/ml/`: `features.py` (leak-free features), `models.py` (stdlib logistic regression and shallow decision tree, JSON save/load), `train.py`, `evaluate.py` (metrics, baselines, subgroup report), `flags.py` (inference: `flag_record(...) -> MlFlags`).
2. `scripts/train_models.py`: reads the verified Phase 3 dataset (loader refuses unverified data), trains, writes `models/*.json` with metrics and the training manifest SHA-256.
3. `docs/modules/ml.md` and a model card per model.

## Features (inference-time information only)
Recorded values, age, sex, position; Phase 1 z-scores and flags; cross-indicator consistency (e.g. WFA vs LHFA and WFL/H z); digit patterns (MUAC above 30, length ending digits swapped-looking, age near a 6-month multiple); missingness indicators; Phase 2 class and rules fired. Excluded: every `true_*` column, `injected_error`, `review_*`, `split`, `record_type`, `child_id`. A test fails if any excluded name enters the feature set.

## Models
- A: logistic regression (binary: any error) and a shallow decision tree (error type attribution: which field to recheck). Transparent and small, which suits Phase 5 explanations.
- B: see Q1. If kept as ML, the same two model families.
- Training on `train`, threshold and hyperparameters on `val`, final report on `test`. The 16 boundary records are a separate stress test, never training data.

## Evaluation
Precision, recall, F1 and alert rate per error type; baseline comparison against Phase 1 plausibility flags alone; confusion matrices; calibration table; subgroup report by sex, age band and district (synthetic districts carry no signal, so this checks the code, not real fairness; real fairness testing needs real data, Week 6 of the work plan); boundary-set behaviour.

## Tests (planned)
Determinism (same seed, same JSON); feature leakage guard; JSON round trip; flags never alter `ClassificationResult`; inference with missing inputs; reason codes valid; refuses unverified datasets; metrics at or above stated floors on `test`; subgroup report generated; model card present with the not-validated statement.

## Decisions needed
- Q1 Target B. Recommendation: implement B as a **rules-based review flag** (promote the D40 logic into the engine with reason codes), and train an ML model only as a diagnostic that reports how well it copies the rule. Reason: ML on a deterministic label is circular. If you prefer ML for B anyway, I will build it and label it clearly as a replica. Which?
- Q2 Models: stdlib logistic regression plus shallow decision tree, no scikit-learn (hard to install on Termux, and offline use matters). OK? Optional dev-only scikit-learn comparison is possible if you want it.
- Q3 Target A form: binary "possible recording error" plus a suggested field to recheck (decision tree), rather than a 5-class classifier. OK?
- Q4 Operating point for A: pick the threshold on `val` for at least 80% recall on errors the Phase 1 flags miss, accepting a stated alert rate (I will report it; I suggest at most 10% of records flagged). Different targets?
- Q5 Output shape: separate `MlFlags` object from `flag_record`, leaving `ClassificationResult` unchanged so the team's interface is stable. OK?
- Q6 Commit trained `models/*.json` (small) to git with their metrics. OK?

## Exit criteria
Tests pass, model cards and `docs/modules/ml.md` written, decision log and register updated, limits stated plainly, open issues listed. Then WAIT before Phase 5.
