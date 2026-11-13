# Module: aggregated surveillance reports and DHIS2 export (Phase 10)

`thanzi_screen.surveillance.reports` and `thanzi_screen.surveillance.dhis2`. Facility, district and national reports for one month,
and the facility counts as a DHIS2 data value set. **Advisory only.** Nothing here changes a child's classification, referral or wording.
Standard library only, stateless: no database, no stored records, no child identifiers, and nothing is sent to DHIS2.

**Off by default.** `THANZI_SURVEILLANCE_REPORTS_ENABLED=1` switches on both routes. Until then they answer `404 surveillance_reports_off`.
Facility-level output, the placeholder thresholds and the question of exporting small counts need Ministry sign-off first (see
[Decisions for the Ministry](#decisions-for-the-ministry)). The existing hotspot route is unchanged and stays district only.

## Who does what
| Part | Owner |
|---|---|
| Storing de-identified screening outcomes, the monthly `GROUP BY` per facility, the org unit list, calling the routes, importing into DHIS2 | Hope (database and backend) |
| Sums, reporting completeness, district hotspot status, suppression, the data value set | This engine |
| DHIS2 data elements, data set, org unit ids and the mapping file | DHIS2 administrators at the Ministry of Health and Sanitation |
| Thresholds (`hotspot_config.json`, `report_config.json`) | Ministry of Health and Sanitation nutrition unit (placeholders today) |

## `POST /v1/surveillance/report`
```json
{"org_units": [{"code": "MW", "name": "Malawi", "level": "national"},
               {"code": "MW-ZA", "name": "Zomba", "level": "district", "parent": "MW"},
               {"code": "MW-ZA-F1", "name": "Zomba Central Hospital", "level": "facility", "parent": "MW-ZA"}],
 "rows": [{"org_unit": "MW-ZA-F1", "period": "2026-10", "screened": 300, "sam": 15, "mam": 35, "unable": 4},
          {"org_unit": "MW-ZA-F1", "period": "2026-09", "screened": 280, "sam": 8, "mam": 20}],
 "period": "2026-10", "reference_rate": 0.06}
```
`period` is optional (default: the latest month in `rows`; later months are ignored). `reference_rate` is optional, as for hotspots.
Send the whole hierarchy, so a facility with no row shows as `not_reported` and the reporting rate is right. Up to 3,000 org units and
3,000 rows; body limit 1 MB on these two routes only (`/v1/screen` keeps 16 KB, hotspots 256 KB). Rows are for facilities only: districts
and the national total are summed from them, so the levels always agree. Any other field (`child_id`, `date_of_birth`, `latitude`,
`village`, ...) is a 422.

The response has `national`, `districts` (hotspots first), `facilities`, a `summary` (district statuses and the reporting rate), the
`advisory` and the `limits`. Each unit carries `data_status`, the counts, `prevalence` with a Wilson 95% interval, reporting completeness
(district and national) and, for districts, `hotspot_status`, `trend` and the reference rate.

## Rules
1. **Sums.** A district is the sum of its reporting facilities in the month; the national total is the sum of all reporting facilities.
2. **`data_status`.** `ok`; `insufficient_data` when `screened` is below `min_screened` (30): counts stay, the rate and interval are not
   shown, never read as low risk; `not_reported` when nothing was reported. **Not reported is not zero and not low risk.**
3. **District hotspot status** is the existing rule in `hotspots.assess`, run on district sums for every month up to the report month
   (one rule, one place; see [surveillance](surveillance.md)). A district with no report is `no_data`.
4. **`data_quality_review`** when 20% or more of screened children were UNABLE_TO_CLASSIFY.
5. **Small cells.** If SAM or MAM is 1 to 4, `sam`, `mam`, `gam_cases`, `prevalence` and the interval are withheld
   (`counts_suppressed`), as for hotspots. The status is kept so a real hotspot is not hidden. `screened` is kept.
6. **Secondary suppression.** One hidden child under a shown total could be worked out as the total minus the visible siblings. So when
   exactly one child in a group is hidden, the smallest visible sibling with cases is hidden too (`secondary_suppression`); if no sibling
   has cases, the parent is hidden instead. It runs bottom-up: facilities under districts, then districts under the national unit.
   Tested: no group is left with one hidden child under a shown total.

## `POST /v1/surveillance/dhis2` and `scripts/export_dhis2.py`
Same `org_units`, `rows` and `period`, plus a `mapping`. Returns `data_value_set` (the body for `POST /api/dataValueSets`),
`import_parameters` and a `summary`. Nothing is sent: the backend imports it.

```json
{"mapping": {"elements": {"screened": "THZ_SCREENED", "sam": "THZ_SAM", "mam": "THZ_MAM", "unable": "THZ_UNABLE"},
             "data_set": "THZ_U5_SCREENING", "data_element_id_scheme": "CODE", "org_unit_id_scheme": "CODE", "org_units": {}}}
```
- **Facility level only.** DHIS2 rolls up to districts and the national level. Exporting district totals too would count each child twice.
- **Counts, not rates.** Define the rates in DHIS2 as indicators: GAM prevalence = (`sam` + `mam`) / `screened`; unable share = `unable` / `screened`.
- **Mapping is never guessed.** `screened`, `sam` and `mam` must be mapped (`unable` is optional). Ids must fit the scheme (`CODE`: letters, digits,
  `_ . -`, up to 50; `UID`: 11 characters, a letter first). With the `UID` scheme every exported facility needs an entry in `org_units`; with `CODE`
  the engine code is used unless `org_units` overrides it. An incomplete or invalid mapping, or two facilities mapping to one DHIS2 org unit,
  stops the export (422 `mapping_incomplete` or `invalid_mapping`). Nothing is partly exported.
- **Zero is exported, a missing report is not.** A reporting facility with no SAM sends `"0"`; a facility that did not report sends nothing.
- **Small counts.** `dhis2_export_suppresses_small_cells` in `report_config.json` (default `true`) leaves SAM and MAM out for a facility where
  either is 1 to 4. `screened` and `unable` are still sent. See the decisions below.
- **Import safely.** `import_parameters` has `dryRun=true` and `importStrategy=CREATE_AND_UPDATE`. Run it with `dryRun=true` first and check
  DHIS2's import summary. Check the payload against the Ministry's DHIS2 version before the first real import.

Files for the DHIS2 administrators, in `docs/dhis2/` (written by `python scripts/export_dhis2.py templates`, checked by the tests):
`mapping.template.json` (the four counts with a suggested name, value type `INTEGER_ZERO_OR_POSITIVE` and aggregation `SUM`, and the two
indicators to define) and `org-units.template.csv` (engine code, name, level, parent, DHIS2 org unit id). Offline use:
`python scripts/export_dhis2.py build request.json mapping.json -o data-value-set.json`.

## Privacy
Aggregated counts only. No child record, identifier or date of birth is accepted, and unknown fields are refused. Org unit names are place names
(a district name is limited to letters, spaces, apostrophes and hyphens; a facility name to a short safe character set). The service logs and
stores nothing from the request. The report and the export both use the same small-cell threshold (`suppress_cells_below` in `hotspot_config.json`).

## Decisions for the Ministry
- Confirm every threshold in `hotspot_config.json` (placeholders) and `report_config.json`.
- Facility-level SAM and MAM counts of 1 to 4 are normal in routine facility reporting. Whether they may be loaded into the Ministry's DHIS2 under its
  data agreement is the Ministry's decision. The default withholds them. Changing `dhis2_export_suppresses_small_cells` is a deliberate, reviewed change.
- Whether the routes are switched on in each environment (`THANZI_SURVEILLANCE_REPORTS_ENABLED`).
- Confirm the DHIS2 data element names, the data set and the org unit codes or UIDs.

## Limits
- Screening attendees are not a random sample. Prevalence among them is not population prevalence.
- Thresholds are placeholders, not Malawi figures. Tested on synthetic inputs only, and on a DHIS2 payload shape checked against the documentation,
  not against a live DHIS2 server.
- Three levels only (national, district, facility). No zones, no sex or age-band disaggregation, no spatial clustering, no forecasting.
- Secondary suppression protects one hidden child per group. Two or more hidden children cannot be separated by subtraction, but their sum is shown in
  the total. Publishing outside the Ministry needs a stricter review.
- Preterm babies are counted only if the caller includes them in the counts.
