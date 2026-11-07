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
