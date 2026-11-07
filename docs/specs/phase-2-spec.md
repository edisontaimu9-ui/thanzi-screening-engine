# Phase 2 specification: CMAM classification and referral

Status: Q1-Q7 approved by Edison 2026-11-07; implemented. Interpretations and open items: decision-log D23-D28, I7-I11.

## Objective
Turn Phase 1 outputs (z-scores, flags) plus clinical inputs into a classification, user-facing tier, referral text and fired rule IDs. Rule set pinned to Malawi CMAM 2016 (2nd Ed.) as `rules_v2016` (D6). Rules only; no ML (D9).

## Resources
- R3 (CMAM 2016, MoH). Rules already extracted in `docs/references/register.md` (all DOCUMENTED).
- NOT yet extracted from R3, needed before implementation (issue I2): appetite test pass/fail definition, list of danger signs, list of medical complications, wording of referral actions. I will not invent these. Please upload the CMAM PDF (or the relevant pages: Table 5, pp.16-17, and the danger sign and complication lists) so they can be extracted with page references.

## Inputs
From Phase 1: WFL/H z-score (absent when oedema, D14), plausibility flags (D12), age in days.
New: MUAC cm (6-59 months only, D2); oedema grade none/+/++/+++ (D3); appetite test passed/failed/not done; danger signs (list or boolean, pending R3); medical complications (list or boolean, pending R3); optional HIV status (D7); for infants <6 months: visible severe wasting, too weak to suckle, failure to gain weight.

## Outputs
Classification: `low_risk | MAM | SAM_OTP | SAM_INPATIENT | SAM_ASSESS | UNABLE_TO_CLASSIFY`. User-facing tier (D4): low risk / MAM / urgent. List of rule IDs fired, each with source ID, page and tag. Warnings. Referral text. Fixed "decision support, not diagnosis" statement. Rule set version.

## Rule logic (all DOCUMENTED in R3 unless marked)
Any one criterion qualifies (p.14).
1. Severe: MUAC <11.5, or WFL/H <-3, or oedema (any grade).
2. Moderate: MUAC 11.5 to <12.5 (D5), or WFL/H -3 to -2.
3. Inpatient (>6 months): oedema +++; or oedema (any) with severe wasting; or severe wasting/oedema +/++ with danger signs or medical complications.
4. OTP (6-59 months): severe criterion with oedema at most ++, AND appetite passed, no complications, clinically well and alert.
5. MAM: moderate criterion only, referral for further assessment.
6. HIV-positive child with MAM: admit to OTP (implemented as MAM tier, programme OTP; D26).
7. Infants <6 months: WFL <-3 (if >45 cm); any oedema; visible severe wasting (if <45 cm); too weak to suckle; failure to gain weight. All map to inpatient/urgent.
8. Low risk: none of the above (RECOMMENDATION, D8).

## Proposed decisions (need your yes/no)
- Q1 (I6) Implausible-flagged values: a z-score carrying `implausible_recheck_measurements` is not used to classify. Classify on remaining criteria (MUAC, oedema); if none remain, output REFER_RECHECK ("recheck measurements") rather than low risk. Never silently classify low risk from a suspect value. RECOMMENDATION.
- Q2 Oedema present: WFL/H is not computed (D14), so "oedema with severe wasting" uses MUAC <11.5 only. Confirm this reading.
- Q3 Missing OTP/inpatient inputs (appetite not done, danger signs or complications unknown) on a SAM child: output SAM_INPATIENT-pending, i.e. urgent tier with "assess for OTP vs inpatient" text; never OTP by default. Both map to urgent, so the tier is unaffected. RECOMMENDATION.
- Q4 Appetite test failed in an otherwise-OTP child: route to inpatient. Implied by Table 5 (OTP requires pass); confirm from PDF.
- Q5 Age boundary: Table 5 says ">6 months" for inpatient and "<6 months" for infants. Exactly 6 months is unspecified. Proposal: treat >=6 months (MUAC applies from 6, D2) as the child pathway. Confirm from PDF.
- Q6 MUAC supplied for a child <6 months: ignored with a warning (D2).
- Q7 Referral wording: placeholder text until extracted from R3; every string to carry a source tag.

## Module layout
`src/thanzi_screen/rules/`: `models.py` (input/output dataclasses), `rules_v2016.py` (rule table, one function per rule, ID/source/page/tag), `classify.py` (orchestrator, version-aware), `referral.py` (text). Standard library only. Depends on `anthro`, never the reverse.

## Tests
One test per rule and per boundary: MUAC 11.4/11.5/12.4/12.5; WFL/H -3.01/-3.00/-2.01/-2.00; each oedema grade; age 5/6 months; appetite pass/fail/not done; HIV on/off; implausible-flag handling; missing inputs; every output carries rule IDs, version and disclaimer. `tests/safety/` seed: classification never less urgent than the most severe single criterion met.

## Exit criteria
All tests pass, docs/modules/rules.md written, register and decision log updated, outstanding issues listed. Then WAIT before Phase 3.
