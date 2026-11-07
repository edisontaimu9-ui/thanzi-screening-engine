# Decision log

## Approved (Phase 0)
- D1. Age range 0-59 months.
- D2. MUAC is a primary criterion, for 6-59 months only. Not collected or classified for 0-5 months.
- D3. Oedema is entered by the user (grades +, ++, +++).
- D4. Tiers follow Malawi CMAM: low risk (counselling, routine monitoring); MAM (referral for further assessment); SAM or bilateral pitting oedema (urgent referral). Engine internally distinguishes SAM-OTP and SAM-inpatient, both mapped to the urgent tier. Final thresholds to be validated against current MoH guidance.
- D5. MUAC <12.5 cm is moderate.
- D6. Rule set pinned to Malawi CMAM 2016 (2nd Ed.) as `rules_v2016`, with a version field so a later edition can be added.
- D7. Optional HIV status input flag (sensitive data) for the HIV-positive MAM to OTP rule.
- D8. Low-risk tier retained (recommendation, not traced to a page).
- D9. Safety invariant: ML may add flags or escalate for review, never downgrade or override a rule. Enforced by tests in `tests/safety/`.

## Approved (Phase 1)
Phase 1 closed: approved by Edison 2026-11-07 (D10-D15 stand).
- D10. Linear interpolation of L, M, S between 0.5 cm WFL/H rows; tested against WHO published cut-offs.
- D11. Beyond +/-3 SD, WHO adjusted method for weight-based indicators (WFA, WFL/H) with flag `adjusted_beyond_3sd`. Length/height-for-age is never adjusted (confirmed by WHO's own +/-4 SD columns).
- D12. Flag `implausible_recheck_measurements` uses WHO limits (WFA <-6/>+5, LHFA +/-6, WFL/H +/-5). Flags never change the z-score. Phase 2 decides their effect.
- D13. Position handling follows WHO: standing height <=730 days gets +0.7 cm, recumbent >=731 days gets -0.7 cm, with a warning. This replaces my earlier "warn only" proposal because WHO documents the conversion. Easy to revert.
- D14. With oedema present, WFA and WFL/H are not computed (WHO rule); LHFA still is. Phase 2 uses the oedema grade directly.
- D15. Converted WHO CSV tables live inside the package (`src/thanzi_screen/anthro/reference_tables/`) with a SHA-256 manifest, so installs and Docker images work. `data/reference_tables/` is no longer used.

## Approved (Phase 2 spec answers, Edison 2026-11-07)
- D16 (Q1). Implausible-flagged z-scores are ignored. Valid MUAC and oedema are used. If no valid wasting assessment remains, output UNABLE_TO_CLASSIFY (recheck measurements). Never low risk.
- D17 (Q2). With oedema, WFL/H is excluded (D14); MUAC <11.5 is the wasting criterion for "oedema with severe wasting". Bilateral pitting oedema independently qualifies as SAM.
- D18 (Q3). SAM with essential information missing (appetite, danger signs, complications, clinical status): SAM_ASSESS, "Urgent assessment: determine OTP vs inpatient". Never defaults to OTP.
- D19 (Q4). Failed appetite test in SAM: inpatient. Confirmed by R3: anorexia (no appetite) is a danger sign, Table 5 p.16.
- D20 (Q5). Exactly 6 months uses the 6-59 month child pathway.
- D21 (Q6). MUAC under 6 months is ignored with a warning.
- D22 (Q7). Referral text is clearly marked placeholder until official wording is extracted. Destinations (NRU, OTP, SFP) come from R3.

## Approved (Phase 2 close, Edison 2026-11-07)
- D29 (I7). Implement the R3 Table 5 p.16 criterion "infant > 6 months and weighs < 3.0 kg" as an inpatient (NRU) trigger. Applied from 6.0 months (conservative at the boundary, consistent with D20) up to 59 months, independent of other inputs, ignoring implausible flags, with a "verify the measurement" warning. Rule ID `INF.WEIGHT_LT3KG`. `AnthropometryResult` gained an optional `weight_kg` field (backward compatible) to carry the weight.
- D30 (I10). Referral wording remains placeholder. Clinical referral rules are defined; only slip text is refined later.
- Phase 2 closed.

## Scope (Edison 2026-11-07)
- D31. Reuse of the Chakudya Nutrition Registry, its MCP server and Thanzi Coach, proposed in the team work plan (R11), was dropped because of added complexity. This repository stays independent. Team roles: Edison (engine, AI design), Hope Kalitera (architecture, backend and frontend, deployment, security), Maria Talimire (clinical validation). See `docs/challenge-alignment.md`.

- D32. WhatsApp channel dropped from the prototype because of the privacy policy (Edison 2026-11-07).
- D33. Synthetic data (Phase 3) carries a coarse district field, needed for the team's hotspot dashboard. Edison is not responsible for the dashboard.
- D34. Ownership (Edison 2026-11-07): local languages belong to the NLP/AI technical team with Edison's clinical input; point-of-care nutrition guidance belongs to Edison as Clinical Nutrition Lead (develop, validate, align with Malawi guidelines). Guidance content must come from approved Malawi sources, never invented. Not yet scheduled in a phase.

## Approved (Phase 3 spec answers, Edison 2026-11-07)
- D35. ML target for Phase 4 is A (detect measurement and data-entry errors) and B (flag borderline or inconsistent cases for clinician review) only. C (predict deterioration) is not implemented at this stage.
- D36. Single visit per child.
- D37. Prevalence and clinical-rate parameters are neutral placeholders marked ASSUMPTION; Edison will supply published Malawi figures later (reports only, no microdata).
- D38. MUAC-for-age z-score logic is not hard-coded until Edison uploads the official WHO tables (R8). MUAC is a configurable placeholder linked to WFL/H z.
- D39. 50,000 random records plus a small boundary set. CSV with SHA-256 manifest, standard library only.

- Phase 3 closed by Edison 2026-11-07; D40-D44 confirmed.

## Approved (Phase 4 spec answers, Edison 2026-11-07)
- D45. Target B is implemented as a **rules-based review flag**. An ML model for B exists only as a clearly labelled diagnostic replica, not production.
- D46. Models are plain-Python logistic regression and a shallow decision tree, standard library only at runtime. scikit-learn is optional and dev-only: try it on Termux first; if it will not install, skip it. (Edison's message was cut off after "If it fails then"; I read it this way.)
- D47. Target A is one flag for "possible recording error" plus a suggested field to recheck. No five-class classifier.
- D48. Operating point for A: at least 80% recall on errors Phase 1 flags miss, at most 10% of records flagged.
- D49. Output is a separate `MlFlags` object. `ClassificationResult` is unchanged.
- D50. Trained `models/*.json` are committed to git with their metrics.

## Implementation interpretations in Phase 4 (confirmed by Edison 2026-11-07)
- D51. Features use only recorded values, Phase 1 z-scores and flags, and Phase 2 outputs (36 features, listed in `ml/features.py`). They include "would a digit swap or a 10x weight shift make this plausible" checks and the distance of the age to an exact 6-month multiple.
- D52. "Errors Phase 1 misses" means injected-error records with no Phase 1 implausible flag.
- D53. `MlFlags` carries the ML error flag and the rules-based review result side by side, each labelled by source.
- D54. Age heaping is detected almost perfectly only because the synthetic injection rounds ages exactly. Real heaping is fuzzy, so this will not transfer. The same feature flags a child legitimately aged exactly 12 months (the boundary stress test shows this).
- D55. Results on synthetic data are high (AUC about 0.997). That reflects clean synthetic errors, not real-world performance.
- D56. Threshold chosen on validation by maximising recall on Phase-1-missed errors under the 10% alert cap.

- D57. Phase 4 closed by Edison 2026-11-07 (D45-D56 confirmed). Phase 5 spec drafted, awaiting his answers to Q1-Q7.

## Implementation interpretations in Phase 3 (confirmed by Edison 2026-11-07)
- D40. Target B labels (`review_reasons`) are built deterministically from engine outputs: unable to classify, missing assessment, implausible value, weight under 3 kg verify, MUAC vs WFL/H discordance, near MUAC threshold (within 0.2 cm), near WFL/H threshold (within 0.1 z). Margins are assumptions. A model can only learn this function, not clinical truth.
- D41. Four injected error types: weight decimal shift, length digit transposition, MUAC unit error (cm recorded as mm), age heaping to 6-month multiples. Overall rate 4% (assumption). `injected_error` records the true label.
- D42. Boundary set has 16 records: MUAC 11.4/11.5/12.4/12.5, WFL/H near -3.01/-3.00/-2.01/-2.00 (weights are rounded to 0.01 kg, so z lands within about 0.01 of target), ages 182 and 183 days, weights 2.99/3.00/3.01 kg at 8 months, oedema +/++/+++. They carry split `boundary` and are excluded from training.
- D43. The 28-district list in `config.py` is from my own knowledge and must be checked against the official list. Districts are assigned uniformly with no spatial pattern.
- D44. Generated CSV (about 11 MB) is git-ignored. It is regenerated from seed and config. The SHA-256 can differ between Python versions or platforms because of floating-point math; the manifest records the Python version.

## Implementation interpretations in Phase 2 (D23-D28 and A1, A2 confirmed by Edison 2026-11-07)
- D23. Stricter reading of D16: if WFL/H is flagged implausible and MUAC is normal, return UNABLE_TO_CLASSIFY rather than low risk (a suspect weight or height could hide wasting). A valid abnormal MUAC or oedema still classifies.
- D24. Added input `clinically_well_and_alert` (R3 OTP criterion). Lethargy or unconsciousness as danger signs force "not well and alert".
- D25. Danger signs or complications are `None` when not assessed, empty set when assessed and absent.
- D26. HIV-positive MAM meeting OTP conditions: classification MAM, tier MAM, programme OTP. The spec draft said urgent tier; R3 does not make this child SAM, so I did not.
- D27. Infants: exactly 45 cm applies the WFL criterion (conservative); visible severe wasting is accepted at any length when entered true.
- D28. User-facing tier "recheck" added as a fourth tier for UNABLE_TO_CLASSIFY.

## Open issues
- I1. Licences for WHO tables and the CMAM PDF unconfirmed; raw files kept out of git.
- I2. Inputs needed for the OTP vs inpatient split: appetite test, danger signs, medical complications.
- I3. (closed) Phase 1 decisions resolved: D10-D11.
- I5. Cross-check against WHO Anthro software output on sample records (still open). Chapter 7 now verified from the WHO book (R6): adjusted method and worked examples confirmed. Oedema rule and plausibility limits are not in the book chapter and rest on WHO anthro documentation (R6b).
- I6. Phase 2 must define how implausible-flagged values affect classification.
- I4. Confirm with MoH Nutrition Unit that no edition newer than 2016 applies.
- I2. (closed in Phase 2) Danger signs, complications and appetite role extracted from R3 pp.11, 16.
- I6. (closed) Resolved by D16, D23.
- I7. (closed) Implemented as D29.
- I8. (closed) D26 confirmed 2026-11-07.
- I9. (closed) A2 confirmed 2026-11-07.
- I10. Official referral slip wording: placeholders remain by decision (D30); refine later.
- I11. (closed) A1 and D23 confirmed 2026-11-07.
- I12. R8 (WHO arm-circumference-for-age tables) pending upload from Edison. Until then MUAC stays a placeholder (D38).
- I13. R9 (published Malawi prevalence figures) pending from Edison (D37).
- I14. Real recording errors are messier than the four injected types. Revalidate on real data before any use.
- I15. Fairness across districts, age bands and sex cannot be tested on synthetic data (districts carry no signal). Needs real data (work plan Week 6).
- I16. Age flag treats exact 6-month-multiple ages as suspicious. Decide how to handle ages that come from a recorded date of birth.
