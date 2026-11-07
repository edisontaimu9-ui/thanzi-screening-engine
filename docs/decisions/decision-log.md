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

## Open issues
- I1. Licences for WHO tables and the CMAM PDF unconfirmed; raw files kept out of git.
- I2. Inputs needed for the OTP vs inpatient split: appetite test, danger signs, medical complications.
- I3. (closed) Phase 1 decisions resolved: D10-D11.
- I5. Cross-check against WHO Anthro software output on sample records (still open). Chapter 7 now verified from the WHO book (R6): adjusted method and worked examples confirmed. Oedema rule and plausibility limits are not in the book chapter and rest on WHO anthro documentation (R6b).
- I6. Phase 2 must define how implausible-flagged values affect classification.
- I4. Confirm with MoH Nutrition Unit that no edition newer than 2016 applies.
