# Under-five screening module (deterministic)

**Status: Phase 1. Library only (not exposed by the API yet). Not clinically validated.**

`thanzi_screen.under5` screens one child record from any number of visits. It is rules only. It never imports machine
learning code and never reads a prediction (checked by `tests/under5/test_independence.py`).

## What it produces

- **CMAM classification** of the latest visit, from `thanzi_screen.rules`, unchanged.
- **Indicator panel** per visit: WAZ (underweight), HAZ (stunting) and WHZ (wasting) from the WHO Child Growth Standards
  engine, with moderate (below -2 SD) and severe (below -3 SD) status, plus above +2 and +3 SD for WAZ and WHZ. Concurrent
  wasting and stunting is flagged.
- **MUAC** category with the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016 cut-offs
  (11.5 and 12.5 cm), 6 to 59 months. Missing is `not_measured`, never normal. **MUAC-for-age z-scores are not computed**:
  the WHO tables are not among the repository's checksummed reference tables and no values are invented.
- **Oedema** grade. When present, weight-based indicators are withheld (WHO rule) and reported as not assessable.
- **Longitudinal growth** over all usable visits: weight velocity in g per day against the ASPEN reference range
  (`thanzi_screen.growth`, reused), z-score change per interval in SD and SD per month, and growth faltering.
- **Factor completeness** for the demographic, clinical, feeding, maternal and socioeconomic groups. Reporting only.

## Growth faltering

| Kind | Flagged interval when |
|---|---|
| weight | weight below the ASPEN range, weight loss, or WAZ falls by `fall_sd` or more |
| linear | HAZ falls by `fall_sd` or more, or newly crosses -2 or -3 |
| wasting | WHZ falls by `fall_sd` or more, or newly crosses -2 or -3 |

Level per kind: `none`, `possible` (one flagged interval, or a cumulative fall inside 180 days), `sustained` (flagged in
two consecutive intervals), `not_assessable`. Fewer than two usable visits, intervals under 28 or over 270 days, and
implausible or oedema-affected values give `not_assessable` with a reason. They never give `none`.

**The thresholds are engineering choices** (`FalteringConfig`), consistent with `thanzi_screen.growth.trend`. There is no
single published faltering definition for this programme. A clinician must review them before real use.

## Factor schema

`thanzi_screen.factors` holds the shared input contract: `Visit` (anthropometry, MUAC, oedema, appetite, danger signs,
complications), `Demographic`, `Clinical`, `Feeding`, `Maternal`, `Socioeconomic` and `ChildRecord`. `None` means not
assessed, an empty collection means assessed and none present. No identifiers. HIV status is deliberately excluded.

## Preterm and low birth weight

This module uses chronological age and adds a warning when birth weight is under 2500 g or gestation under 37 weeks. Use
the preterm routing of `POST /v1/screen` for babies under 50 weeks post-menstrual age.

## Unified report

`thanzi_screen.report.build_report(screening, prediction=None)` lays the two modules out side by side. The screening block
is copied verbatim. The prediction block is copied verbatim or is an explicit `not_run`. The `attention` level can only
be raised by a prediction, never lowered, and nothing changes a classification, tier or referral.
