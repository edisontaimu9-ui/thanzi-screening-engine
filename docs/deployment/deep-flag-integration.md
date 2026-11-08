# Deep flag: integration note for the gateway (Hope)

For whoever connects a gateway or front end to the screening API. It covers only what changed with the deep flag
(D153 to D156). Everything else in `docs/modules/api.md` and `docs/api/openapi.json` stands.

For the full system view see `docs/deployment/integration-guide.md`.

## What changed
Two additive response fields. No new route, no new status code, no new header, no change to auth.

| Where | Field | Meaning |
|---|---|---|
| `POST /v1/screen`, under `ml_flags` | `deep_recording_error` | A second advisory "recheck a measurement" flag, from a small neural network. Same shape as `recording_error`: `flagged`, `suggested_field`, `messages`. The audit view adds `probability`. |
| `GET /version` | `deep_model_version` | Version string of the deep model, or `null` when it is not loaded. |

`deep_recording_error` is **absent** from `ml_flags` when the deep model is not loaded, in degraded mode, and for babies
screened on the preterm or corrected-age routes. Code must treat it as optional.

## Example (worker view, `ml_flags` only; weight typed as 110 kg instead of 11.0 kg)
```json
{
  "available": true,
  "recording_error": {"flagged": true, "suggested_field": "weight",
                      "messages": ["Recheck the weight (possible decimal or unit slip)."]},
  "review": {"needed": true, "reasons": [
    {"code": "unable_to_classify", "message": "Could not classify. Recheck the measurements or complete the missing assessments."},
    {"code": "implausible_value", "message": "A measurement looks implausible. Recheck weight, length or height and age."}]},
  "advisory": "Advisory flag only. It does not change the classification. A trained health worker decides.",
  "deep_recording_error": {"flagged": true, "suggested_field": "weight",
                           "messages": ["Recheck the weight (possible decimal or unit slip)."]}
}
```
A record with nothing to flag returns `"deep_recording_error": {"flagged": false, "suggested_field": null, "messages": []}`.

## What a consumer must do
1. **Accept the new fields.** If the gateway or app validates responses against a strict schema, add the two fields as
   optional, or regenerate from `docs/api/openapi.json`. A strict client that rejects unknown fields will fail.
2. **Treat both fields as optional.** Missing and `null` are both normal.
3. **Never let it change the result.** The classification, tier, reasons and review are the same with and without this flag
   (tested). Do not hide, delay or downgrade a classification because of it.
4. **Never show `probability` to a health worker.** It appears only in the audit view, which needs the audit key.
5. **Messages are the same wording for both flags.** When both flag the same field the text is identical, so show it once.
6. **If the two flags disagree** (one `flagged`, one not), the API decides nothing. A suggested default for the front end,
   to be confirmed by Maria and Edison (I58): show the recheck message if either flag is true, and never show "all clear"
   language on the strength of the flags alone.

## Check it after deploy
```
curl -s -H "X-Gateway-Key: $KEY" http://HOST:8080/version
```
Expect `"deep_model_version": "0.1.0"`. Then post a record with a slip and look for `deep_recording_error`:
```
curl -s -H "X-Gateway-Key: $KEY" -H "Content-Type: application/json" http://HOST:8080/v1/screen \
  -d '{"sex":"male","age_days":500,"weight_kg":110.0,"length_height_cm":80.0,"measure_position":"length","oedema":"none","muac_cm":14.0,"appetite":"passed","danger_signs":[],"complications":[],"clinically_well_and_alert":true}'
```
Run `python scripts/smoke_api.py --base-url http://HOST:8080` as before. `/health` keeps its meaning: it reports the
logistic models, not the deep one.

## Rollback (no rebuild)
Set `THANZI_DEEP_ENABLED=0` in the container environment and restart. `/version` then shows `"deep_model_version": null`
and `ml_flags` has no `deep_recording_error`. Screening and the logistic flag are unchanged. Remove the variable (or set `1`)
and restart to switch it back on. If the deep model files are missing or do not match, the flag is simply absent and the
service stays `ok`.

## Limits to keep in mind
Trained on synthetic data only and not validated on real children, the same status as the logistic flag. Advisory only.
It is not run for corrected-age or preterm babies. If a failure occurs inside it, the service logs the error type (never
the input) and returns the normal response without the field.
