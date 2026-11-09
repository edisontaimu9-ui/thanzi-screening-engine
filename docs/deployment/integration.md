# Gateway integration guide

For teams connecting a gateway, backend or front end to the screening API. It describes what the API requires, what it
returns and how to handle each case. The contract is [`docs/api/openapi.json`](../api/openapi.json). Items marked
**recommendation** are advice, not requirements of the API.

Decision support only. Not clinically validated.

## 1. Responsibilities

The API is a calculator behind the gateway. See [architecture](../architecture.md) for the split of responsibilities.
In short: the gateway authenticates users, terminates TLS, rate limits, removes identity fields, converts dates of birth
to `age_days`, keeps visit history, stores results and renders output. The API classifies and returns advisory flags.

## 2. Calling the API

1. Authenticate the user and drop identifying fields.
2. `POST /v1/screen` with `X-Gateway-Key` (worker view by default). Each call is independent and idempotent, so a retry
   is safe.
3. Render the response and store what is needed (section 7).

Request rules:

- `null` or omitted means "not assessed". `[]` means "assessed, none present". Keep these apart in the front end. Never
  fill a missing finding with a "normal" value.
- Types are strict. Catch obvious typing slips early (for example 110 kg for a baby). That is what the recording-error
  flags are for.
- Body limit 16 KB. One child per call. No batch.
- `age_days` is whole days from the date of birth to the **date of measurement**, computed the same way for every visit.

## 3. Using the response

| Field | What the app should do |
|---|---|
| `classification` | Show it. Never override, hide or downgrade it |
| `tier` | Drive colour and ordering. `recheck` means measure again, not "fine". Handle `null` (preterm `follow_up`) and use `preterm_level` |
| `worker_summary` | Main text (2 to 3 English lines) |
| `reasons[]` | Show `message`, or translate by `code` |
| `warnings[]` | Show. For moderate cases a neutral referral warning is always present |
| `programme` | Do not infer a programme when null |
| `ml_flags` | Advisory recheck prompts (below) |
| `growth_monitoring` | Optional. Advisory (section 6) |
| `status`, `disclaimer` | Keep visible with the result |
| `*_version` | Store with every result |

`ml_flags`:

- `available: false` means degraded mode (rules result only). The app must still work.
- `recording_error` and `deep_recording_error` (optional) both use the same message text. When both flag the same field,
  show it once. If only one flags, show the recheck message (recommendation). Never show reassurance such as "no errors
  found" because the flags are quiet.
- `review` is a separate rules-based signal and is always present.
- Never show `probability`. It exists only in the audit view.

Strict-schema clients must treat these as optional: `deep_recording_error`, `deep_model_version`, `route`,
`birth_context`, `clinical_assessment`, `growth_monitoring`. Generate types from `openapi.json` and tolerate new optional
fields.

The audit view (both keys) carries HIV information and the real programme. Use it server-side only, with its own access
control, and never in a browser response or shared log.

## 4. Failure handling

| Status | Meaning | Gateway action |
|---|---|---|
| 200 | Screened | Render |
| 401 `unauthorised` | Missing or wrong gateway key | Configuration fault. Alert, do not retry in a loop |
| 403 `audit_forbidden` | Audit key wrong or audit off | Do not fall back silently to the worker view for an audit task |
| 413 `payload_too_large` | Body over 16 KB | Bug in the caller |
| 422 | Data is wrong. Messages never echo values | Show "check the entries". Do not retry unchanged |
| 500 `internal_error` | Generic | Retry once. If it persists, alert and show "could not screen, use the paper chart from the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016" |
| Timeout or no connection | Service down | Same fallback as 500 |

The app needs a manual or offline path: the API is not a safety net on its own. Measured median latency on one 2.1 GHz
vCPU is about 2 ms for one client and about 20 ms at 16 concurrent clients, so a client timeout of 2 to 5 seconds is
generous (recommendation). Repeat the measurement on target hardware with `scripts/load_probe.py`.

## 5. Monitoring calls

Poll these on a schedule, keep the latest answer and use it for alerting and an admin "About" page. None carries child
data. See [operations](../operations.md) for alert thresholds.

| Need | Call | Key |
|---|---|---|
| Is it up | `GET /health` | none |
| Versions and component state | `GET /v1/about` | gateway |
| Counts and timings | `GET /v1/metrics` | gateway |
| Live language-model state (if enabled) | `GET /v1/llm/health` | gateway |
| Versions only | `GET /version` | gateway |

`/v1/about` lists five components, each with `name`, `state`, `version` and `detail`:

| Component | States | Notes |
|---|---|---|
| `screening_engine` | `ok` | Rules from the Community-Based Management of Acute Malnutrition (CMAM) Guidelines, Malawi, 2016, preterm engine, corrected-age route. Never depends on the ML models |
| `ml_logistic` | `ok`, `degraded` | `degraded`: model files missing or mismatched |
| `ml_deep` | `ok`, `off` | `off`: switched off or files missing |
| `growth_monitoring` | `ok` | Needs `previous_measurement` |
| `llm_service` | `ok`, `off` | Configuration state only. `/v1/about` never calls the model server |

The ML models run inside the screening API. There is no separate ML service to poll.

Rules: poll every 30 to 60 seconds (recommendation), cache the answer, send the key only from the server, show `/v1/about`
and `/v1/metrics` to administrators only, and never poll `/v1/screen` as a health check (it carries a child record).

## 6. Growth monitoring

The API stores nothing and cannot see earlier visits. The gateway keeps each child's visits and sends one as
`previous_measurement`.

Choosing the earlier visit:

- Send **one** visit: the most recent one at least **28 days** before this visit that has a weight. Under 28 days the API
  answers `interval_too_short` for everything. If there is none, send nothing.
- Every field comes from that one visit: `age_days` and `weight_kg` are required. Add `length_height_cm` with
  `measure_position` (`length` or `height`, how that visit was measured), and `hc_cm`, only if that visit measured them.
  Never combine values from different visits.
- Send this visit's `hc_cm` only when the earlier visit also has `hc_cm`. A head circumference without an earlier one is
  not used and produces the warning "Preterm-only fields were given but this baby is not screened by the preterm
  engine: they were ignored." Filter that warning or omit `hc_cm`.
- Store `measure_position` for every visit. A child measured lying down at one visit and standing at the next is
  converted by the engine only if you say which was which.

Reading the answer:

- `growth_monitoring` is optional and advisory. It is **absent** on the preterm and corrected-age routes (a warning says
  so). Absent does not mean growth is fine.
- Weight gain: `assessed`, `status` (`below_range`, `within_range`, `above_range`), `flagged`, `messages`,
  `reference_derived`. Trends: `trends` holds `weight_for_age` always, and `length_height_for_age` and
  `head_circumference_for_age` only when both visits provided them. Each has `assessed`, `reason`, `z_previous`,
  `z_current`, `z_change`, `direction` (`fell`, `rose`, `steady`), `lines_crossed`, `status_change` (`below_minus2`,
  `below_minus3` or null), `flagged` and `messages`.
- Not-assessed reasons: `interval_too_short`, `implausible_weight`, `implausible_measurement`,
  `outside_reference_ages`, `oedema_weight_unreliable`. Show the message and do not treat it as "growth is fine".
- When `review_suggested` is true, show `review_note` and the messages of every flagged part.
- A child can be `low_risk` and still flagged for growth. Show both. The flag never changes the classification and sets no
  referral.
- For girls aged 3 to 6 months `reference_derived` is true. Say so next to the weight-gain result.
- A bad earlier visit (same or later age, non-positive value, a length without `measure_position`, an unknown key) is a
  422. Treat it as a data-entry or gateway bug.

## 7. What to store

The API stores nothing. Anything the gateway stores is health data.

- Store with each result: the gateway's own record ID, `classification`, `tier`, the flags, `rule_set_version`,
  `model_version`, `deep_model_version`, `api_version` and the time. Versions let you explain an old result after a rules
  or model update.
- Growth monitoring needs, per child and visit: measurement date, weight, length or height with `measure_position`, and
  head circumference if measured.
- Keep identity and measurements in separate stores linked by the gateway's own ID.
- Do not store the audit view in ordinary tables. Do not log request or response bodies.

## 8. Other components

- **Translation:** do not machine-translate free text. Translate by stable code (`classification`, `tier`,
  `reasons[].code`, review codes, `suggested_field`, growth values). Keep English as the fallback. Clinical wording in any
  language needs clinical review. The authoritative message set is `src/thanzi_screen/explain/messages.py`.
- **Analytics:** aggregate from worker-view fields (`classification`, `tier`, `ml_flags`, versions), never the audit view.
  The API returns no place or facility; the gateway adds them. Apply de-identification and small-cell suppression in the
  analytics layer. Per-facility flag rates can reveal systematic measuring or typing problems.
- **Language-model routes:** leave off unless a reviewed use exists. Model text must not reach health workers without
  clinical review ([llm](../modules/llm.md)).

## 9. Integration tests

1. Run `python scripts/smoke_api.py --base-url http://HOST:8080 --gateway-key ... --audit-key ...` after every deploy
   (19 checks, synthetic children only).
2. Validate real responses against `docs/api/openapi.json` in the gateway's CI.
3. Exercise edge cases: `UNABLE_TO_CLASSIFY`; a moderate case (null programme, neutral wording); a baby under 2500 g
   (`route: preterm`); a corrected-age baby (no ML flags); a weight typed ten times too high (both flags fire); degraded
   mode (point `THANZI_MODELS_DIR` at an empty folder); the deep flag off (`THANZI_DEEP_ENABLED=0`); a wrong key (401).
4. Growth cases, all with `previous_measurement`:
   - Boy, 548 days, 12.0 kg, 75.1 cm lying, `oedema: none`, `muac_cm` 14, appetite passed, no danger signs or
     complications, clinically well; earlier visit 122 days, 6.5 kg, 62.3 cm lying. Expect `classification: low_risk`
     and `review_suggested: true` with `trends.length_height_for_age` flagged (`direction: fell`,
     `status_change: below_minus2`, `lines_crossed: [-1, -2]`) and `trends.weight_for_age` not flagged. This is the WHO
     technical guide's own case study.
   - Earlier visit 20 days before: every part `interval_too_short`, `review_suggested: false`.
   - Girl aged 3 to 6 months with low gain: `reference_derived: true`.
   - `oedema: "+"`: the weight trend reports `oedema_weight_unreliable`; the length trend still runs.
   - Preterm baby (`gestational_age_weeks` 33, `birth_weight_g` 1900) or a corrected-age baby: no `growth_monitoring`,
     plus a warning.
   - A length with no `measure_position` in `previous_measurement`: 422 `missing_field`.
5. Expected classifications for a wider set are in the case pack (`docs/testing/case-pack.xlsx`), with rule and page.
6. Repeat `scripts/load_probe.py` on the target hardware.

## 10. Outstanding integration items

| Item | Owner |
|---|---|
| Network isolation, TLS, rate limits, hosting | Platform / infrastructure owner |
| Who holds the audit key and how access is logged | Platform owner with the clinical lead |
| Accept the optional response fields or switch the deep flag off | Gateway developer |
| What a worker sees when the two ML flags disagree, and wording review | Clinical reviewer |
| Store visit history and send `previous_measurement`; handle `growth_monitoring` | Gateway developer |
| Poll `/health`, `/v1/about`, `/v1/metrics`; keep readings; alert; admin About page | Gateway developer |
| Translation by code | Language team with clinical input |
| Expected request volume and target server specification | Platform owner |
| Real-data validation and fairness testing | Requires Ministry data and clinical reviewers |
