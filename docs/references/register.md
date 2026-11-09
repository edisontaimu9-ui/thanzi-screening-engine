# Reference register

Every clinical rule and reference value in the engine traces to a source listed here. Tags used in the code and
documentation: **DOCUMENTED** (stated in a source), **ASSUMPTION** and **RECOMMENDATION** (engineering or clinical
judgement that is not stated in a source). Reference IDs are stable and are cited in code and documentation.

## Citation convention

A source is always named by its full official title, with the abbreviation in brackets after the title where one exists and the
publication year where applicable, for example *Care of the Infant and Newborn (COIN), Malawi, 2017* and *Community-Based
Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016*. Never cite a source by its abbreviation alone. Do not add
publication details that are not recorded in this register. In code, take titles from `src/thanzi_screen/references.py`.
Register ids (R1, R3, ...) remain stable keys for cross-reference and are not a substitute for the title.

## Clinical and scientific sources

| ID | Document | Version / date | Source | Licence | Used for | Status |
|---|---|---|---|---|---|---|
| R1 | WHO Child Growth Standards: weight-for-length (0-2 y) and weight-for-height (2-5 y), z-score tables, boys and girls (columns Length/Height, L, M, S, SD3neg..SD3) | 2006 | https://www.who.int/tools/child-growth-standards/standards/weight-for-length-height | To confirm. WHO states its expanded tables carry no warranty | Weight-for-length/height z-scores | Converted CSVs in the package |
| R2 | WHO expanded-tables instructions (PDF) | n.d. | WHO Child Growth Standards site | To confirm | 1 month = 30.4375 days; age tables to 1856 days; length/height discontinuity between 730 and 731 days | Local copy, not in git |
| R3 | Malawi Guidelines for Community-Based Management of Acute Malnutrition (CMAM), 2nd Edition (Ministry of Health) | 2016 | https://www.policyvault.africa/wp-content/uploads/policy/MWI40.pdf | No licence statement in the document; confirm with the MoH Nutrition Unit | CMAM classification and referral rules | Local copy, not in git. Printed page numbers are cited (PDF page = printed + 11). Confirm with the MoH Nutrition Unit that no newer edition applies |
| R4 | WHO length/height-for-age tables | 2006 | https://www.who.int/toolkits/child-growth-standards/standards/length-height-for-age | To confirm | Length/height-for-age z-scores and trends | Converted CSVs in the package |
| R5 | WHO weight-for-age tables | 2006 | https://www.who.int/childgrowth/standards/chts_wfa_boys_p/en/ | To confirm | Weight-for-age z-scores and trends | Converted CSVs in the package |
| R6 | WHO Child Growth Standards: Length/height-for-age, weight-for-age, weight-for-length, weight-for-height and BMI-for-age: Methods and development (ISBN 92 4 154693 X), ch. 7 "Computation of centiles and z-scores", printed pp. 302-304 | 2006 | WHO publication | WHO copyright; reuse terms to confirm | Adjusted z-score for weight-based indicators, SD23 definitions, worked examples (used in tests), 0.7 cm length/height convention | Primary source, local copy, not in git |
| R6b | WHO igrowup/anthro implementation documentation (https://worldhealthorganization.r-universe.dev/anthro/doc/manual.html) | anthro 1.1.0 | Public documentation | Package terms to confirm | Oedema rule, ±0.7 cm conversion in software, plausibility limits (WAZ -6/+5, HAZ ±6, WHZ ±5) | Secondary source; not in the book chapter |
| R7 | WHO Growth Velocity standards, Methods and development (ISBN 978 92 4 154763 5) | 2009 | WHO publication | WHO copyright | Not used; possible future growth-velocity features | Local copy, unused |
| R8 | WHO arm-circumference-for-age tables, 3-59 months | n/a | WHO | WHO | Future MUAC model for the synthetic data generator | Not held. MUAC in synthetic data is a placeholder |
| R9 | Published Malawi prevalence figures (reports only) | n/a | To be sourced | To check | Replace placeholder parameters in the synthetic data generator | Not held |
| R14 | Fenton 2025 Preterm Growth Chart Data (Dr Tanis Fenton), LMS tables for girls and boys, 22 to 50 weeks PMA | 2025 | Preterm service package | **CC BY-NC-ND 4.0**: attribution, non-commercial, no derivatives | Weight, length and head circumference z-scores for the preterm engine | `fenton2025_lms.json`, unmodified, SHA-256 checked in a test |
| R15 | Care of the Infant and Newborn (COIN), Malawi, 2017, Participants' Manual, Sessions 2, 12 and 19 and wall charts | 2017 | Preterm service package (rules transcribed in `preterm_rules.json`) | Malawi Ministry of Health | Feeding, KMC, referral and discharge rules for preterm and low-birth-weight babies | Values tagged "proposed" need clinician sign-off |
| R19 | ASPEN Paediatric and Neonatal Nutrition Support Handbook, Third Edition (2024): Growth Monitoring, "Reference normal growth velocity" for term infants and paediatric patients (weight, g/day) | 3rd ed. | Transcribed into `src/thanzi_screen/growth/aspen_weight_velocity.json` | To confirm (values quoted for decision support) | Weight-gain velocity ranges for ages 0 to 5 years (advisory growth flag) | Verified against the handbook by a dietitian. Girls 3 to 6 months reads 21-21 in the source, so a range of 17 to 25 g/day is derived and marked `reference_derived`. Weight rows only |
| R20 | WHO Child Growth Standards: head circumference-for-age, z-score tables, boys and girls, 0-13 weeks and 0-5 years (columns Week or Month, L, M, S, SD, SD3neg..SD3; L = 1) | 2006 | WHO tables | To confirm. WHO states its tables carry no warranty | Head circumference z-score trends | Converted CSVs and checksums in `src/thanzi_screen/anthro/reference_tables/`. Ends at 60 months |
| R21 | WHO Regional Office for the Eastern Mediterranean: Child Growth Monitoring: A Technical Guide for Healthcare Professionals (Cheikh Ismail, Al-Jawaldeh, Al Dhaheri) | n.d. | WHO publication (PDF) | WHO copyright; reuse terms to confirm | Basis for the trend rules: a line crossing a z-score line, a sharp up or down trend, cut-offs below -2 and -3. Gives no number of SD for crossing. Case study 2 is a test case | Local copy, not in git |

## Optional components (not part of screening)

| ID | Item | Version | Source | Licence | Used for | Status |
|---|---|---|---|---|---|---|
| R16 | Local LLM serving software: Ollama, llama.cpp `llama-server` (run outside this repository) | Not pinned | https://github.com/ollama/ollama and https://github.com/ggml-org/llama.cpp | To confirm (believed MIT for both; not checked) | Local model serving for `thanzi_screen.llm` | ASSUMPTION. Not installed or run by the tests |
| R17 | Candidate small models: Qwen2.5 0.5B/1.5B instruct, Qwen3 0.6B/1.7B | Not pinned | Ollama library or Hugging Face model cards | To confirm per model and size. Licences differ between sizes | Optional text generation, never screening | ASSUMPTION. No weights in git. Record source, version, date and licence before use |
| R18 | httpx 0.28.1 | 2026-11-08 | https://pypi.org/project/httpx/ | BSD-3-Clause | HTTP transport for the language-model client | Optional `llm` extra; not in the release image |

## Software dependencies

| ID | Item | Licence | Used for |
|---|---|---|---|
| R12 | Runtime API packages: FastAPI 0.162.2, pydantic 2.14.3, uvicorn 0.54.0, Starlette 1.10.0 (transitive) | MIT, MIT, BSD-3-Clause, BSD-3-Clause | HTTP layer only. The engine, rules and ML flags use the standard library |
| R13 | Pinned runtime closure (14 packages, `constraints.txt`): annotated-doc 0.0.5, annotated-types 0.8.0, anyio 4.16.0, click 8.5.1, fastapi 0.162.2, h11 0.16.0, idna 3.20, opentelemetry-api 1.45.2, pydantic 2.14.3, pydantic_core 2.50.4, starlette 1.10.0, typing-inspection 0.4.5, typing_extensions 4.16.0, uvicorn 0.54.0 | MIT, BSD-3-Clause, Apache-2.0, PSF-2.0 (see package metadata) | Runtime |
| R13 (dev and CI only) | pytest 9.2.0, httpx 0.28.1, httpcore 1.0.9, certifi 2026.10.23 (MPL-2.0), openpyxl 3.1.5, PyYAML 6.0.3, coverage 7.17.2, pip-audit 2.10.1, cyclonedx-bom 8.0.1, gitleaks 8.30.1, Trivy and trivy-action, GitHub Actions (checkout, setup-python, upload-artifact), actionlint 1.7.12 (local only) | MIT, BSD-3-Clause, Apache-2.0 | Tests, security scans, SBOMs, release. Never in the runtime image |

Licences were read from installed package metadata or the tools' LICENSE files on 2026-11-07. `pip-audit` found no known
vulnerabilities in the pinned set on that date. Re-check licences and re-run the audit at each release.

## Rules extracted from R3 (all DOCUMENTED)

| Rule | Value | Location |
|---|---|---|
| MUAC 6-59 months | <11.5 cm severe; 11.5 to <12.5 moderate; ≥12.5 none | Table 4, p.14 |
| WFL/H z-score | <-3 severe; -3 to -2 moderate | Table 5, pp.16-17 |
| Oedema grading | +1 feet; +2 feet and lower legs, or hands; +3 also periorbital | Annex 1-5, p.28 |
| Independent criteria | Meeting any one criterion qualifies | Section 1, p.14 |
| Inpatient (NRU), children over 6 months | Oedema +++; or oedema (any grade) with severe wasting; or severe wasting or oedema +/++ with danger signs or medical complications (MUAC <11.5 or WFH/L <-3) | Table 5, p.16 |
| OTP, 6-59 months | MUAC <11.5, WFL/H <-3, or oedema +/++, AND appetite test passed, no complications, clinically well and alert | Table 5, p.17 |
| SFP, 6-59 months | MUAC 11.5 to 12.5 or WFL/H -3 to -2 | Table 5, p.17 |
| HIV-positive child with MAM | Admit to OTP when MUAC <12.5 or WFH/L -3 to -2, AND appetite passed, no complications, well and alert | Table 5, p.17 |
| Infants <6 months | WFL <-3 (if >45 cm); any oedema; visible severe wasting (if <45 cm); too weak to suckle; failure to gain weight | Table 5, p.16 |
| Danger signs (7) | Anorexia (no appetite); intractable vomiting; convulsions; lethargy, not alert; unconsciousness; inability to drink or breastfeed; high fever (>39 °C rectal or >38.5 °C axillary) | Table 5, p.16 |
| Medical complications (11) | Hypoglycaemia; hypothermia (<35 °C axillary or <35.5 °C rectal); infections; severe dehydration; shock; very severe anaemia; cardiac failure; severe dermatosis; signs of vitamin A deficiency; diarrhoea; malaria | Table 5, p.16 |
| Appetite test | Done on admission and every visit; determines OTP vs NRU. The pass/fail procedure is not encoded: the user enters the result | Section 1.8, p.11 |
| Infant failure to gain weight, or WFA | Infants <6 months faltering or WFA z <-3: refer to a clinician for further assessment; those not gaining weight after counselling or treatment: refer to NRU | Table 5 footnote, p.16 |
| Infant weight criterion | "If infant is > 6 months and weighs < 3.0 kg" is an NRU admission criterion. Implemented from 6.0 months | Table 5, p.16 |
| Out of scope | OTP-to-NRU referral criteria (deterioration, oedema increase, weight loss, no response at 3 months); ages 5-15 years; pregnant and lactating women | Table 5, pp.16-17 |

## Assumptions and recommendations

- **ASSUMPTION:** WFL/H z exactly -2.00 is not moderate (WHO convention z < -2). Table 5 says "-3 to -2".
- **ASSUMPTION:** An infant under 6 months with WFA z < -3 is referred to a clinician and mapped to the MAM tier (further
  assessment). Table 5 does not state a tier.
- **ASSUMPTION:** MUAC exactly 12.5 cm is "no wasting" (Table 4 lists 12.5 in both bands). <12.5 is moderate.
- **RECOMMENDATION:** Low-risk tier (counselling and routine monitoring). Not traced to a page of the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016.
- **RECOMMENDATION:** Four engine outputs (low risk, MAM, SAM-OTP eligible, SAM-inpatient) are mapped to three user-facing
  tiers.
- **DESIGN CHOICE:** Linear interpolation of L, M, S between 0.5 cm rows, tested against published cut-offs.
