# Phase 3 specification: data engineering

Status: Q1-Q6 answered and approved by Edison 2026-11-07 (D35-D39); implemented. Interpretations: D40-D44.

## Objective
Build a reproducible, versioned synthetic data pipeline for under-fives (0-59 months) that exercises the whole engine (Phase 1 z-scores, Phase 2 rules) and prepares the data layer for Phase 4. Synthetic only (data policy). Standard library only at runtime; no code or data from any other project.

## Honest limits (read first)
Synthetic data seeded from WHO distributions reproduces anthropometric structure, not real-world risk patterns. Any clinical relationship I add (e.g. appetite failure given severity, progression over time) is an ASSUMPTION I invented, not evidence. A model trained on it learns my assumptions. So synthetic data can validate the engine, the pipeline and data-quality handling. It cannot validate clinical risk prediction. That needs approved real data.

## Resources
| ID | Resource | Use | Status |
|---|---|---|---|
| R1, R4, R5 | WHO weight-for-length/height, length/height-for-age, weight-for-age tables | Invert LMS to generate measurements | Held, in package |
| R8 (needed) | WHO arm-circumference-for-age tables, 3-59 months (WHO site) | Generate realistic MUAC | Please upload, or I give the official link for you to download. Not yet held |
| R9 (optional) | Published Malawi prevalence (e.g. NSO DHS/MICS reports, nutrition survey reports) | Set stunting, wasting and oedema prevalence parameters from cited published figures, not my guesses | Needs Edison to supply or approve; check licence/terms before use. Report figures only, no microdata |
| R7 | WHO growth velocity standards | Longitudinal features, only if Q2 chooses visits | Held |
Record source, version, date, licence and intended use for each in the register.

## Deliverables
1. `src/thanzi_screen/data/`: `schema.py` (record schema, enums, `is_synthetic` marker), `generator.py` (seeded generation), `noise.py` (measurement error and missingness), `validate.py` (schema, range and plausibility checks), `splits.py` (leak-free splits), `manifest.py` (SHA-256 manifest and data card).
2. `scripts/generate_synthetic.py`: CLI, args seed, n, config file; writes CSV to `data/synthetic/` plus `MANIFEST.json`.
3. Config file of every distribution parameter, each tagged DOCUMENTED (cited) or ASSUMPTION.
4. `docs/modules/data.md` and a data card.

## Generation design
1. Sample sex, a coarse `district` (coded value from a config list of Malawi districts, D33; no facility, community or coordinates) and age (days) from a configurable age distribution (default uniform 0-1856 days, ASSUMPTION).
2. Sample target z-scores: LHFA z, then WFLH z with a configurable correlation. Defaults N(mean, sd) with prevalence-driven shift, parameters from R9 once supplied.
3. Invert the WHO LMS tables (Phase 1 `lms`/`tables`) to get length/height and weight, then round to realistic precision (length 0.1 cm, weight 0.01 kg).
4. MUAC from R8 via a configurable correlation with WFLH z (ASSUMPTION), rounded to 0.1 cm, only for 6-59 months (D2).
5. Clinical inputs (oedema, appetite, danger signs, complications, HIV, infant items) sampled conditional on severity with configurable rates (ASSUMPTION, no clinical claim).
6. Boundary oversampling: deliberate records at each Phase 2 threshold (MUAC 11.5/12.5, z -3/-2, 6 months, 3.0 kg) so rare edge cases are present.
7. Ground-truth fields: the sampled true z-scores, and the Phase 2 classification computed by the real engine (never re-implemented).

## Data-quality engineering (noise, all configurable and labelled)
Age heaping, MUAC digit preference, transposition and unit errors (injected, with an `injected_error` label so ground truth is known), missingness (MCAR and severity-dependent) at configurable rates. Phase 1 plausibility flags and Phase 2 UNABLE_TO_CLASSIFY handle them; tests check this.

## Validation and safety
- Reject any dataset where `is_synthetic` is not true. A real-data loader is out of scope until ethics and data-sharing approval exists.
- District only for geography. Small-cell suppression is the dashboard owner's concern.
- No identifiers: child IDs are random surrogate keys; no names, dates of birth or locations. Age stored in days only.
- Same seed and config produce a byte-identical file and the same SHA-256 (as D15).
- Splits by child ID, fixed seed, stratified by Phase 2 class; no ID in two splits.

## Tests (planned)
Reproducibility and hash; schema and range validation; recomputing z-scores with Phase 1 matches the sampled targets within rounding tolerance; marginal moments of sampled z-scores near targets; classification labels equal a fresh `classify` call; boundary records present; noise and missingness rates near config; no split leakage; real-data refusal; no identifier fields.

## Decisions needed
- Q1 ML target for Phase 4 (determines what Phase 3 must emit). Rule-derived class as a target is not useful: ML would just relearn the rules and D9 forbids overriding them. Options: (A) detect measurement and data-entry errors (injected labels are known, so ground truth is real by construction); (B) flag cases to escalate for clinician review (borderline, missing or conflicting inputs); (C) predict deterioration or progression over visits (needs longitudinal data, and progression dynamics would be invented). My recommendation: A and B for the synthetic phase; C only as a clearly labelled simulation, or deferred to approved real data.
- Q2 Cross-sectional only, or multi-visit records (needed for C and growth velocity)? Recommendation: cross-sectional now.
- Q3 Prevalence parameters: will you supply R9 figures, or use neutral placeholder defaults clearly marked ASSUMPTION?
- Q4 Please supply or approve R8 (WHO MUAC-for-age). Without it MUAC would rely on a pure assumption.
- Q5 Dataset size: default 50,000 records (plus boundary set), CSV with manifest. Pandas/NumPy are not needed; OK to stay standard library?
- Q6 Output format: CSV only, or also Parquet (adds a dependency)? Recommendation: CSV only.

## Exit criteria
Tests pass, data card and module docs written, register and decision log updated, outstanding issues listed. Then WAIT before Phase 4.
