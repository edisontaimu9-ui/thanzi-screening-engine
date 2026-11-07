# Reference register

Tags: DOCUMENTED (stated in a source), ASSUMPTION, RECOMMENDATION.

| ID | Document | Version / date | Source | Licence | Intended use | Status |
|---|---|---|---|---|---|---|
| R1 | WHO Child Growth Standards: weight-for-length (0-2 y) and weight-for-height (2-5 y), z-score tables, boys and girls (4 xlsx; columns Length/Height, L, M, S, SD3neg..SD3) | WHO 2006 standards | https://www.who.int/tools/child-growth-standards/standards/weight-for-length-height | To confirm. WHO states its expanded tables carry no warranty | LMS z-score computation | Held, not in git |
| R2 | WHO expanded-tables instructions (PDF) | n.d. | WHO Child Growth Standards site | To confirm | Technical notes: 1 month = 30.4375 days; age tables to 1856 days; length/height discontinuity between 730 and 731 days | Held, not in git |
| R3 | Malawi Guidelines for Community-Based Management of Acute Malnutrition, 2nd Edition (MoH) | 2016 | https://www.policyvault.africa/wp-content/uploads/policy/MWI40.pdf | No licence statement in document; confirm with MoH Nutrition Unit | Classification and referral rules | Held, not in git. Approved edition per Edison; no newer edition per Edison |
| R4 | WHO length/height-for-age tables | 2006 | https://www.who.int/toolkits/child-growth-standards/standards/length-height-for-age | To confirm | Phase 1 (if approved) | Not yet obtained |
| R5 | WHO weight-for-age tables | 2006 | https://www.who.int/childgrowth/standards/chts_wfa_boys_p/en/ | To confirm | Phase 1 (if approved); infant growth-faltering check | Not yet obtained |

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

## Assumptions and recommendations
- ASSUMPTION: MUAC exactly 12.5 cm is "no wasting" (Table 4 lists 12.5 in both bands). Confirmed by Edison: <12.5 is moderate.
- RECOMMENDATION: Low-risk tier (counselling and routine monitoring). Not traced to a CMAM page.
- RECOMMENDATION: four engine outputs (low risk, MAM, SAM-OTP eligible, SAM-inpatient) mapped to three user-facing tiers.
- ASSUMPTION (Phase 1, pending): linear interpolation of L, M, S between 0.5 cm rows.
