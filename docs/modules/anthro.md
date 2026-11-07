# Module: anthro (Phase 1)

Computes WHO z-scores for children 0-59 months. It does not classify (Phase 2).

## API
```python
from thanzi_screen.anthro import compute_anthropometry
r = compute_anthropometry(
    sex="male", weight_kg=7.2, length_height_cm=68.0, measure_position="length",
    age_days=240,            # or date_of_birth=..., measurement_date=...
    oedema=False,
)
r.wfa, r.lhfa, r.wflh       # IndicatorResult: status, z, z_unadjusted, flags, reason, table
r.warnings, r.length_height_used_cm, r.age_days, r.age_months
```
Malformed input raises `InputError`. Valid input outside the WHO standards returns `status="not_computable"` with a reason code. It never extrapolates and never returns 0 for missing data.

## Behaviour and sources
| Behaviour | Value | Tag | Source |
|---|---|---|---|
| Age | whole days, 0-1856; 1 month = 30.4375 days | DOCUMENTED | R2 |
| Length vs height | age <=730 days recumbent length, >=731 standing height | DOCUMENTED | R2, R6 |
| Position conversion | standing height at <=730 days: +0.7 cm; recumbent at >=731 days: -0.7 cm; warning emitted | DOCUMENTED | R6 |
| WFL/H table | <=730 days uses weight-for-length (45-110 cm), else weight-for-height (65-120 cm) | DOCUMENTED | R1, R6 |
| Between 0.5 cm rows | linear interpolation of L, M, S | DECISION (D10), tested against published cut-offs | Edison |
| z-score | LMS: ((y/M)^L - 1)/(L*S) | DOCUMENTED | R6 |
| Beyond +/-3 SD | weight-based indicators (WFA, WFL/H): WHO adjusted method, linear extension using the SD2-SD3 distance; flag `adjusted_beyond_3sd` | DOCUMENTED | R6; confirmed by WHO's own +/-4 SD columns in the supplied WFA tables |
| Length/height-for-age | never adjusted | DOCUMENTED | confirmed by WHO's +/-4 SD columns in the supplied LHFA tables |
| Oedema | weight-based z-scores not calculated (`oedema_weight_unreliable`); LHFA still computed | DOCUMENTED | R6 (WHO anthro) |
| Plausibility | flag `implausible_recheck_measurements` if WFA <-6 or >+5, LHFA outside +/-6, WFL/H outside +/-5 | DOCUMENTED | R6 |

Flags are information for review. They do not change the z-score. Phase 2 decides how flagged values affect classification.

## Reference tables
CSV conversions of the WHO Excel files live in `src/thanzi_screen/anthro/reference_tables/` with `MANIFEST.json` (SHA-256 of each source and CSV). Loading fails on a checksum mismatch. Rebuild with `python scripts/build_reference_tables.py <folder-with-xlsx>` (needs openpyxl).

## Tests (`tests/anthro`, 122 passing)
- LMS maths: median is 0, SD round-trips, L=0 branch, adjusted extension.
- Every row of every table reproduces WHO's published -3..+3 SD columns (3 decimals for age tables, 1 decimal for WFL/H).
- WHO's published +/-4 SD columns for WFA match the adjusted method and LHFA's match the plain method.
- Interpolation (nodes, midpoints, monotonicity), range limits, 730/731 boundaries, position conversion, oedema, flags, input validation, checksum tamper detection.

## Not yet validated
Cross-check against WHO Anthro software output on real sample records (outstanding issue I5).
