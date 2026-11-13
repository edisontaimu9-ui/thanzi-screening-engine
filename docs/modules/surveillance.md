# Module: hotspot surveillance, `thanzi_screen.surveillance`

Finds districts where more screened children are classified SAM or MAM than elsewhere, so programme staff can target
support. **Advisory only.** It never changes a child's classification, referral or wording. Standard library only.
Aligns with the AI for Public Good Challenge brief 3 (AI-Assisted Malnutrition Screening): aggregate screening data to
identify geographical hotspots.

## Who does what
The engine stays stateless: no database, no stored records, no child identifiers.

| Part | Owner |
|---|---|
| Storing de-identified screening outcomes, the monthly `GROUP BY`, dashboards and maps | Hope (database and backend) |
| Statistics and hotspot rule: `POST /v1/surveillance/hotspots` | This engine |
| Thresholds in `hotspot_config.json` | Ministry of Health and Sanitation nutrition unit (placeholders today) |

## Request
Counts already grouped by district and month. Latest month is assessed, earlier months give the trend.
```json
{"rows": [{"district": "Mangochi", "period": "2026-10", "screened": 300, "sam": 15, "mam": 35, "unable": 4},
          {"district": "Mangochi", "period": "2026-09", "screened": 280, "sam": 8, "mam": 20}],
 "reference_rate": 0.06}
```
`reference_rate` is optional (0 to 1). Without it, each district is compared with all the other districts in the batch.
`sam` = SAM_OTP + SAM_INPATIENT + SAM_ASSESS. `unable` = UNABLE_TO_CLASSIFY. Up to 1,000 rows (body limit 256 KB on this
route only; `/v1/screen` keeps 16 KB). Any other field (`child_id`, `name`, `latitude`, `facility`, ...) is a 422.

Example grouping for the backend (adapt names to the real table):
```sql
SELECT district, to_char(screened_at,'YYYY-MM') AS period, count(*) AS screened,
       count(*) FILTER (WHERE class LIKE 'SAM%') AS sam, count(*) FILTER (WHERE class = 'MAM') AS mam,
       count(*) FILTER (WHERE class = 'UNABLE_TO_CLASSIFY') AS unable
FROM screening_outcomes GROUP BY 1, 2;
```

## Rule
For the latest period, per district:
1. `screened` below `min_screened` (30): `insufficient_data`. Never read as low risk.
2. Prevalence is (SAM + MAM) / screened with a Wilson 95% interval.
3. `hotspot`: interval lower bound is above the reference rate and prevalence is at least `min_prevalence_for_hotspot`.
4. `watch`: above the reference without significance, or a significant rise on the previous month (two-proportion z-test).
5. Otherwise `not_flagged`. A district with no row for the latest month is `no_data`.
6. `data_quality_review` is set when 20% or more of screened children were UNABLE_TO_CLASSIFY.

## Privacy
District level only on this route. Facility-level reports and the DHIS2 export are a separate, off-by-default module: see [surveillance-reports](surveillance-reports.md).
District level only. If either the SAM or the MAM count is between 1 and 4, `sam`, `mam`, `gam_cases`, `prevalence`, the
interval and `previous_prevalence` are withheld (`counts_suppressed: true`). The status is kept so a real hotspot is not
hidden. The service logs and stores nothing from the request.

## Limits
- Screening attendees are not a random sample. Prevalence among them is not population prevalence.
- Thresholds are **placeholders**, not Malawi figures. Confirm before use.
- No spatial clustering, forecasting or boundaries yet. Tested on synthetic inputs only.
- Preterm babies are counted only if the caller includes them in the counts.
