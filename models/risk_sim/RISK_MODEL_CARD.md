# Model card: advisory clinical risk model

**SIMULATED OUTCOMES. NOT CLINICAL. Trained on an assumed formula, so these numbers only show the code works. They say nothing about real children. The service refuses this model unless simulated models are explicitly allowed.**

Version risk-sim-0.1.0. Kind `logistic`. Target: simulated_adverse_outcome_8w within 8 weeks. Definition: SIMULATED. Bernoulli draw from the assumed formula in thanzi_screen.ml.risk.simulate.
Dataset SHA-256 `36d2d059761c4efa...`, 20000 rows, seed 0. Same dataset and seed give identical files.

## What it does
Estimates the chance of the target outcome for children aged 6 to 59 months. It can only add a concern ("closer follow-up
suggested"). It never changes a classification, tier, referral or warning, never says a child is low risk, and is not run when
a recording error is suspected, MUAC is missing, or the child is outside the age range. Not run for preterm or corrected-age babies.

## Data and split
Scoreable: 16323 of 20000 (81.6%). Not scored: {'age_outside_model_range': 2286, 'measurement_not_assessable': 494, 'muac_missing': 897}.
Temporal split, a child stays in one split. Train ['2025Q1', '2025Q2', '2025Q3'] (8180 rows, 819 events),
validation ['2025Q4'] (2733, 246), test ['2026Q1', '2026Q2'] (5410, 543).
Test prevalence 10.0%.

## Model selection (validation set)
| Candidate | Validation AUROC | Gain over logistic (95% interval) | Decision |
|---|---|---|---|
| lr | 0.850 |  | baseline |
| rf | 0.847 | -0.003 (-0.012 to 0.005) | not accepted (gain too small or interval includes zero) |
| xgb | 0.850 | -0.000 (-0.009 to 0.009) | not accepted (gain too small or interval includes zero) |

Libraries not installed, skipped: none. Exported models match the library (largest difference per candidate): lr 0.0e+00, rf 2.8e-16, xgb 2.7e-07. Limit 1e-05.
Tree models use monotone constraints: a lower z-score or MUAC never lowers the risk.

## Operating point
Threshold 0.2351 on calibrated probability, chosen on validation data for an alert rate of at most 10%.

## Test results (opened once)
- AUROC 0.833 (95% interval 0.810 to 0.851). AUPRC 0.480 (prevalence 0.100). Brier 0.069.
- Calibration slope 0.92 (ideal 1), intercept -0.02 (ideal 0).
- At the threshold: alert rate 11.2%, sensitivity 51.6% (95% interval 0.467 to 0.554), PPV 46.1%, specificity 93.3%.
- Rules alone (SAM or MAM): sensitivity 59.5%, alert rate 15.1%.
- Rules or model: sensitivity 63.5%, alert rate 17.5%.
- Events the rules did not flag: 220. The model flagged 22 of them (10.0%).

Decision curve (net benefit; flag-everyone shown for comparison):

| Threshold probability | Model | Flag everyone |
|---|---|---|
| 0.05 | 0.0672 | 0.0530 |
| 0.10 | 0.0515 | 0.0004 |
| 0.20 | 0.0367 | -0.1245 |

Calibration by decile of predicted risk:

| Decile | n | Mean predicted | Observed |
|---|---|---|---|
| 1 | 541 | 0.002 | 0.011 |
| 2 | 541 | 0.007 | 0.017 |
| 3 | 541 | 0.012 | 0.030 |
| 4 | 541 | 0.020 | 0.030 |
| 5 | 541 | 0.030 | 0.031 |
| 6 | 541 | 0.045 | 0.048 |
| 7 | 541 | 0.068 | 0.070 |
| 8 | 541 | 0.106 | 0.120 |
| 9 | 541 | 0.186 | 0.161 |
| 10 | 541 | 0.446 | 0.486 |

## Subgroups (test set, at the threshold)
**Sex**

| Group | n | Events | AUROC | Sensitivity | PPV | Alert rate | Note |
|---|---|---|---|---|---|---|---|
| female | 2743 | 295 | 0.832 | 49.2% | 49.2% | 10.8% |  |
| male | 2667 | 248 | 0.837 | 54.4% | 43.1% | 11.7% |  |

**Age band**

| Group | n | Events | AUROC | Sensitivity | PPV | Alert rate | Note |
|---|---|---|---|---|---|---|---|
| 12-23 months | 1247 | 134 | 0.791 | 49.3% | 43.4% | 12.2% |  |
| 24-59 months | 3576 | 347 | 0.849 | 52.4% | 47.6% | 10.7% |  |
| 6-11 months | 587 | 62 | 0.833 | 51.6% | 43.2% | 12.6% |  |

**District**

| Group | n | Events | AUROC | Sensitivity | PPV | Alert rate | Note |
|---|---|---|---|---|---|---|---|
| Balaka | 185 | 22 | 0.913 | 63.6% | 48.3% | 15.7% |  |
| Blantyre | 215 | 31 | 0.801 | 35.5% | 40.7% | 12.6% |  |
| Chikwawa | 232 | 24 | 0.790 | 54.2% | 54.2% | 10.3% |  |
| Chiradzulu | 188 | 23 | 0.844 | 60.9% | 48.3% | 15.4% |  |
| Chitipa | 182 | 17 | 0.827 | 52.9% | 42.9% | 11.5% | small group, unreliable |
| Dedza | 193 | 17 | 0.770 | 35.3% | 33.3% | 9.3% | small group, unreliable |
| Dowa | 209 | 27 | 0.832 | 55.6% | 62.5% | 11.5% |  |
| Karonga | 196 | 26 | 0.813 | 53.8% | 58.3% | 12.2% |  |
| Kasungu | 193 | 29 | 0.883 | 55.2% | 66.7% | 12.4% |  |
| Likoma | 175 | 20 | 0.780 | 40.0% | 40.0% | 11.4% |  |
| Lilongwe | 211 | 20 | 0.874 | 50.0% | 50.0% | 9.5% |  |
| Machinga | 179 | 21 | 0.842 | 52.4% | 40.7% | 15.1% |  |
| Mangochi | 193 | 19 | 0.868 | 52.6% | 47.6% | 10.9% | small group, unreliable |
| Mchinji | 193 | 20 | 0.860 | 45.0% | 47.4% | 9.8% |  |
| Mulanje | 188 | 19 | 0.890 | 68.4% | 56.5% | 12.2% | small group, unreliable |
| Mwanza | 170 | 13 | 0.777 | 53.8% | 41.2% | 10.0% | small group, unreliable |
| Mzimba | 188 | 14 | 0.827 | 64.3% | 52.9% | 9.0% | small group, unreliable |
| Neno | 184 | 16 | 0.860 | 50.0% | 53.3% | 8.2% | small group, unreliable |
| Nkhata Bay | 181 | 12 | 0.936 | 75.0% | 37.5% | 13.3% | small group, unreliable |
| Nkhotakota | 186 | 16 | 0.834 | 37.5% | 31.6% | 10.2% | small group, unreliable |
| Nsanje | 214 | 15 | 0.793 | 26.7% | 40.0% | 4.7% | small group, unreliable |
| Ntcheu | 180 | 15 | 0.743 | 40.0% | 35.3% | 9.4% | small group, unreliable |
| Ntchisi | 205 | 17 | 0.746 | 41.2% | 38.9% | 8.8% | small group, unreliable |
| Phalombe | 204 | 16 | 0.865 | 68.8% | 42.3% | 12.7% | small group, unreliable |
| Rumphi | 178 | 12 | 0.851 | 66.7% | 34.8% | 12.9% | small group, unreliable |
| Salima | 184 | 24 | 0.879 | 62.5% | 46.9% | 17.4% |  |
| Thyolo | 195 | 20 | 0.772 | 50.0% | 50.0% | 10.3% |  |
| Zomba | 209 | 18 | 0.822 | 38.9% | 35.0% | 9.6% | small group, unreliable |

**Period**

| Group | n | Events | AUROC | Sensitivity | PPV | Alert rate | Note |
|---|---|---|---|---|---|---|---|
| 2026Q1 | 2738 | 269 | 0.842 | 54.6% | 46.4% | 11.6% |  |
| 2026Q2 | 2672 | 274 | 0.825 | 48.5% | 45.7% | 10.9% |  |


## Leave-one-district-out (external validity)

Retrained without each district, scored on that district. Districts with at least 200 scoreable children and 20 events. Median AUROC 0.839, range 0.786 to 0.889.

| District | n | Events | AUROC |
|---|---|---|---|
| Balaka | 549 | 59 | 0.889 |
| Blantyre | 613 | 72 | 0.803 |
| Chikwawa | 614 | 52 | 0.839 |
| Chiradzulu | 597 | 64 | 0.857 |
| Chitipa | 616 | 58 | 0.792 |
| Dedza | 556 | 51 | 0.841 |
| Dowa | 613 | 67 | 0.864 |
| Karonga | 598 | 65 | 0.813 |
| Kasungu | 607 | 72 | 0.836 |
| Likoma | 557 | 60 | 0.840 |
| Lilongwe | 599 | 60 | 0.879 |
| Machinga | 566 | 66 | 0.822 |
| Mangochi | 582 | 60 | 0.816 |
| Mchinji | 589 | 57 | 0.841 |
| Mulanje | 516 | 57 | 0.842 |
| Mwanza | 565 | 56 | 0.786 |
| Mzimba | 579 | 57 | 0.863 |
| Neno | 586 | 55 | 0.818 |
| Nkhata Bay | 564 | 46 | 0.858 |
| Nkhotakota | 617 | 64 | 0.843 |
| Nsanje | 637 | 51 | 0.839 |
| Ntcheu | 529 | 50 | 0.833 |
| Ntchisi | 585 | 50 | 0.800 |
| Phalombe | 580 | 43 | 0.853 |
| Rumphi | 552 | 50 | 0.839 |
| Salima | 580 | 61 | 0.866 |
| Thyolo | 599 | 56 | 0.815 |
| Zomba | 578 | 49 | 0.839 |

## Acceptance
Acceptance thresholds NOT SET. They must be agreed with clinical reviewers before the test set is opened.


## Limits
- Outcomes are simulated from an assumed formula. Performance here is not evidence of anything clinical.
- Advisory only. A trained health worker decides. Retraining or any change needs revalidation and clinical sign-off.
- Fairness is only as good as the subgroup sizes above. Small groups are marked.
