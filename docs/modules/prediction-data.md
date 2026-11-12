# Prediction module: data, labels, features, preprocessing

**Status: Phase 2 (data, labels, features, preprocessing, simulator). Models are compared in Phase 3: see `prediction-models.md`. Not clinically validated.**

`thanzi_screen.prediction` is independent of the screening module. It never imports `thanzi_screen.under5`,
`thanzi_screen.report`, `thanzi_screen.ml` or `thanzi_screen.growth`, never calls the rules classifier, and never uses a
CMAM classification, tier or referral as a feature (all checked in `tests/under5/test_independence.py`).

## Dataset

One CSV row per visit, plus a `MANIFEST.json` with a SHA-256 checksum. The loader refuses a missing manifest, a changed
file, an identifier column, a child whose static fields differ between rows, a simulated dataset unless
`allow_simulated`, and real data without `ethics_ref`, `data_agreement_ref`, `extraction_description`, `period_covered`
and `deidentified: true`.

Columns hold the factor groups: visit (age in days, weight, length or height, MUAC, oedema, appetite, danger signs,
complications), demographic and birth, clinical history, feeding, maternal, socioeconomic. `child_id` is pseudonymous
and used only to keep a child in one split. `district` and the visit month are for fairness checks only. There is **no
outcome column**: labels are built from later visits.

## Labels (`targets.py`)

Window default: a later visit 28 to 180 days after the index visit.

| Target | Positive when |
|---|---|
| `future_wasting` | at any usable visit in the window: WHZ below -2, MUAC below 12.5 cm, or oedema |
| `future_sam` | at any usable visit in the window: WHZ below -3, MUAC below 11.5 cm, or oedema |
| `future_faltering` | at the first usable visit in the window: WAZ fell by 1.0 SD or more, or weight is 0.1 kg or more lower |

- **Incident prediction.** An index visit already at the wasting or SAM outcome is excluded for that target.
- **Missing follow-up is never a negative.** No visit in the window, or none usable, gives no label and a reason code.
  `label_summary` reports positives, negatives and every exclusion reason so loss to follow-up can be examined.
- The horizon, the 1.0 SD fall and the 0.1 kg loss are engineering choices. Agree them with clinical reviewers before
  training on real data. The MUAC cut-offs and WHO lines come from the CMAM Guidelines, Malawi, 2016 and WHO standards.

## Features (`features.py`)

63 features in seven groups: anthropometric, longitudinal growth, demographic, clinical, feeding, maternal,
socioeconomic. `build_features(child, index)` reads only visits up to the index (tested by altering every later visit).
Longitudinal features: number of prior visits, days since previous, change in WAZ, HAZ, WHZ and MUAC, weight velocity in
g per day, WHZ slope over the last three visits, lowest earlier WHZ, WAZ and MUAC, and WAZ fall from the best value in
180 days. Missing inputs stay `None`. Clinically directional features carry monotone constraints for later tree models
(lower z-score or MUAC never lowers risk).

## Preprocessing (`preprocess.py`, standard library only)

- `split_children`: deterministic hash of seed and child id. 70, 15 and 15 percent by default. A child never spans splits.
- `Preprocessor.fit` uses **training rows only**: median, 1st and 99th percentile winsorising limits, mean and spread.
  A missing value is replaced by the training median and a `<feature>_missing` column is added, so "not assessed" stays
  visible and is never turned into normal. The fitted object serialises to JSON.

## Simulator and caveats

`scripts/simulate_longitudinal.py` writes simulated children (git-ignored under `data/synthetic/longitudinal/`). Latent
WHO z-scores follow AR(1) trajectories, driven by assumed poverty, illness, feeding and frailty effects, then become
weights, lengths and MUAC through the WHO tables. Visit gaps are irregular, loss to follow-up and missing factor values are
more likely in poorer households, and oedema is rare. **Every association is an assumption, so a model trained on this
data only learns the assumptions.** With 3,000 children the simulated prevalence is about 16 percent for wasting, 1 percent
for SAM and 21 percent for faltering. SAM has few positives, which will limit any model of it, as it will with real data.

## Gaps never seen in training

If a feature was never missing in the training rows, the preprocessor has no indicator column for it and the model has no
learned meaning for a gap there. At prediction time such a row raises `UnseenMissingError` instead of being filled with the
training median. `matrix()` leaves these rows out and lists them in its optional `skipped` argument, so they are counted
and not hidden. The later API layer reports them as not scored.
