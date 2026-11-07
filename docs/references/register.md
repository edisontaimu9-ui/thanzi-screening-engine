# Reference register

Tags: DOCUMENTED (stated in a source), ASSUMPTION, RECOMMENDATION.

| ID | Document | Version / date | Source | Licence | Intended use | Status |
|---|---|---|---|---|---|---|
| R1 | WHO Child Growth Standards: weight-for-length (0-2 y) and weight-for-height (2-5 y), z-score tables, boys and girls (4 xlsx; columns Length/Height, L, M, S, SD3neg..SD3) | WHO 2006 standards | https://www.who.int/tools/child-growth-standards/standards/weight-for-length-height | To confirm. WHO states its expanded tables carry no warranty | LMS z-score computation | Held; converted CSVs committed (licence still to confirm, issue I1) |
| R2 | WHO expanded-tables instructions (PDF) | n.d. | WHO Child Growth Standards site | To confirm | Technical notes: 1 month = 30.4375 days; age tables to 1856 days; length/height discontinuity between 730 and 731 days | Held, not in git |
| R3 | Malawi Guidelines for Community-Based Management of Acute Malnutrition, 2nd Edition (MoH) | 2016 | https://www.policyvault.africa/wp-content/uploads/policy/MWI40.pdf | No licence statement in document; confirm with MoH Nutrition Unit | Classification and referral rules | Held (uploaded by Edison 2026-11-07), not in git. Approved edition per Edison; no newer edition per Edison. Printed page numbers used below (PDF page = printed + 11) |
| R4 | WHO length/height-for-age tables | 2006 | https://www.who.int/toolkits/child-growth-standards/standards/length-height-for-age | To confirm | Phase 1 (if approved) | Held; converted CSVs in `src/thanzi_screen/anthro/reference_tables/` |
| R5 | WHO weight-for-age tables | 2006 | https://www.who.int/childgrowth/standards/chts_wfa_boys_p/en/ | To confirm | Phase 1; infant growth-faltering check | Held; converted CSVs in package |
| R6 | WHO Child Growth Standards: Length/height-for-age, weight-for-age, weight-for-length, weight-for-height and BMI-for-age: Methods and development (ISBN 92 4 154693 X), ch. 7 'Computation of centiles and z-scores', printed pp. 302-304 (PDF p. 324) | 2006 | Uploaded by Edison (WHO publication) | WHO copyright; reuse terms to confirm | Adjusted z-score for weight-based indicators, SD23 definitions, worked examples (used in tests). Also supports the 0.7 cm length/height convention (sections 3 and 7). | Held, primary source, not in git |
| R6b | WHO igrowup/anthro implementation (https://worldhealthorganization.r-universe.dev/anthro/doc/manual.html) | anthro 1.1.0 | Public documentation | Package terms to confirm | Oedema rule, +/-0.7 cm conversion in software, plausibility limits (WAZ -6/+5, HAZ +/-6, WHZ +/-5) | Secondary source; not in the book chapter |
| R7 | WHO Growth Velocity standards, Methods and development (ISBN 978 92 4 154763 5) | 2009 | Uploaded by Edison | WHO copyright | Not used in Phase 1; possible later growth-faltering features | Held, unused |
| R10 | AI for Public Good Challenge Briefs, Brief 3: AI-Assisted Malnutrition Screening (Ministry of Health and Sanitation) | Current programme year | Uploaded by Edison (UniPod Malawi, MUBAS, timbuktoo, UNDP) | To confirm | Challenge requirements and role split (`docs/challenge-alignment.md`). Not a clinical source | Held, not in git |
| R11 | Thanzi AI 8-Week Work Plan (AI for Public Good Challenge) | Current programme year | Uploaded by Edison | Internal | Team roles, responsibility matrix, weekly deliverables, risks. Its Chakudya/Thanzi Coach reuse was dropped (D31) | Held, not in git |
| R8 | WHO arm-circumference-for-age tables, 3-59 months | n/a | Pending upload by Edison | WHO | Future MUAC model. Not used yet (D38) | Not held |
| R9 | Published Malawi prevalence figures (reports only) | n/a | Pending from Edison | To check | Replace placeholder parameters (D37) | Not held |

## Extracted rules (R3), all DOCUMENTED
| Rule | Value | Location |
|---|---|---|
| MUAC 6-59 months | <11.5 cm severe; 11.5 to <12.5 moderate; >=12.5 none | Table 4, p.14 |
| WFL/H z-score | <-3 severe; -3 to -2 moderate | Table 5, pp.16-17 |
| Oedema grading | +1 feet; +2 feet and lower legs, or hands; +3 also periorbital | Annex 1-5, p.28 |
| Independent criteria | Meeting any one criterion qualifies | Section 1, p.14 |
| Inpatient (NRU), children >6 months | Oedema +++; or oedema (any grade) with severe wasting; or severe wasting/oedema +/++ with danger signs or medical complications | Table 5, p.16 |
| OTP, 6-59 months | MUAC <11.5, WFL/H <-3, or oedema +/++, AND appetite test passed, no complications, clinically well and alert | Table 5, p.17 |
| SFP, 6-59 months | MUAC 11.5-12.5 or WFL/H -3 to -2 | Table 5, p.17 |
| HIV-positive child with MAM | Admit to OTP | Table 5, p.17 |
| Infants <6 months | WFL <-3 (if >45 cm); any oedema; visible severe wasting (if <45 cm); too weak to suckle; failure to gain weight | Table 5, p.16 |

## Additional rules extracted from R3 in Phase 2, all DOCUMENTED (printed pages)
| Rule | Value | Location |
|---|---|---|
| Danger signs (7) | Anorexia (no appetite); intractable vomiting; convulsions; lethargy, not alert; unconsciousness; inability to drink or breastfeed; high fever (>39 C rectal or >38.5 C axillary) | Table 5, p.16 |
| Medical complications (11) | Hypoglycaemia; hypothermia (<35 C axillary or <35.5 C rectal); infections; severe dehydration; shock; very severe anaemia; cardiac failure; severe dermatosis; signs of vitamin A deficiency; diarrhoea; malaria | Table 5, p.16 |
| Appetite test | Done on admission and every visit; never skipped; determines OTP vs NRU. Pass/fail procedure not encoded (user enters result) | s.1.8, p.11 |
| Inpatient (>6 months) | Oedema +++; or any oedema with severe wasting (MUAC <11.5 or WFH/L <-3); or oedema +/++ or severe wasting WITH danger signs or complications | Table 5, p.16 |
| Infant failure to gain weight / WFA | Infants <6 months faltering or WFA z <-3: refer to clinician for further assessment; those not gaining weight after counselling/treatment: refer to NRU | Table 5 footnote, p.16 |
| OTP, HIV-positive MAM | MUAC <12.5 or WFH/L -3 to -2, AND appetite passed, no complications, well and alert | Table 5, p.17 |
| Out of scope | OTP-to-NRU referral criteria (deterioration, oedema increase, weight loss, no response at 3 months); ages 5-15 years; pregnant and lactating women | Table 5, pp.16-17 |
| Infant weight criterion | Infant column: "If infant is > 6 months and weighs < 3.0 kg" is an NRU admission criterion. Implemented from 6.0 months (D29) | Table 5, p.16 |

## Assumptions and recommendations
- ASSUMPTION A1 (Phase 2): WFL/H z exactly -2.00 is not moderate (WHO convention z < -2). Table 5 says "-3 to -2".
- ASSUMPTION A2 (Phase 2): infant WFA < -3 referral to clinician is mapped to the MAM tier (further assessment). Not stated as a tier in R3 (issue I9).
- ASSUMPTION: MUAC exactly 12.5 cm is "no wasting" (Table 4 lists 12.5 in both bands). Confirmed by Edison: <12.5 is moderate.
- RECOMMENDATION: Low-risk tier (counselling and routine monitoring). Not traced to a CMAM page.
- RECOMMENDATION: four engine outputs (low risk, MAM, SAM-OTP eligible, SAM-inpatient) mapped to three user-facing tiers.
- DECISION (Phase 1): linear interpolation of L, M, S between 0.5 cm rows.
