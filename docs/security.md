# Security, validation and error handling

## Threat model

The service is designed to run on a private network behind a gateway. It is not designed to face the internet.
It handles health data in transit and keeps none at rest.

## Access control

- Every route except `GET /health` requires `X-Gateway-Key`, including unknown routes. A missing or wrong key gives a
  generic 401. Comparison is constant time on SHA-256 digests.
- The service fails closed: it refuses to start without `THANZI_GATEWAY_KEY`, with a key shorter than 16 characters,
  or with an audit key equal to the gateway key.
- `?view=audit` additionally requires `X-Audit-Key`. Without a valid audit key, or when the audit key is unset, the
  response is 403. The gateway must never forward the audit header from a browser.
- `/docs`, `/redoc` and `/openapi.json` are disabled outside development mode. No CORS headers are sent.

## Privacy

- Stateless. No database, no stored requests, no request-body or query-value logging. Logs contain access lines
  (client address, path, status) and error types only.
- Child identifiers are rejected: `name`, `child_id`, `date_of_birth` and any other unknown field give 422
  `unknown_field`. Age is `age_days` only.
- The worker view contains no HIV information. A final scan drops any key or string containing "hiv" and logs the event;
  it should never fire and a test checks this.
- The worker response for a moderate case is identical for `hiv_positive` true, false and null, and shows no programme.
- Gateway logs of requests and responses hold child measurements. Treat them as health data.

## Input validation

- Strict types. Required: `sex`, `age_days`, `weight_kg`, `length_height_cm`, `measure_position`, `oedema`.
- `null` or omitted means "not assessed" and `[]` means "assessed, none present". The service never fills in a
  default that would hide a finding.
- Ranges and plausibility are enforced by the engine. Implausible z-scores are ignored by the rules and flagged for a
  recheck, and the classification never falls to low risk on an implausible measurement alone.
- Body limit 16 KB, one child per call, no batch.
- Hostile input (bad JSON, wrong types, NaN, infinity, huge numbers, long strings, nested bodies, wrong methods and
  content types, duplicate headers, query abuse) is covered by robustness tests: every case returns a 4xx with no echo
  of submitted values and no stack trace.

## Error handling

| Status | Code | Meaning |
|---|---|---|
| 401 | `unauthorised` | Missing or wrong gateway key |
| 403 | `audit_forbidden` | Audit key wrong, or audit view off |
| 413 | `payload_too_large` | Declared body over 16 KB |
| 422 | `invalid_request`, `invalid_input`, `missing_field`, `unknown_field`, `invalid_json` | Data is wrong. Messages never echo values |
| 500 | `internal_error` | Generic, no trace and no input |

A failure inside an advisory component (neural-network flag, growth monitoring) is logged by exception type only and the
screening response is returned without it.

## Safety invariants (tested)

- A child is never classified less urgently than the most severe single criterion met.
- Lower MUAC, lower weight or a higher oedema grade is never less urgent.
- A danger sign or complication never lowers urgency or leads to outpatient care.
- Missing information never lowers urgency, and OTP is never recommended with incomplete information.
- Advisory flags never change a classification.

## Container hardening

The image runs as a non-root user, publishes no port, contains no secrets and has a built-in health check. The example
compose file adds a read-only filesystem, dropped capabilities, `no-new-privileges`, a memory limit and an internal
network.

## Supply chain

- Every dependency is pinned in `constraints.txt` and installed with it in the image and in CI.
- CI runs `pip-audit`, a Trivy image scan, a gitleaks history scan, builds CycloneDX SBOMs, and pins GitHub Actions to
  commit SHAs. Dependabot watches Actions, Docker and pip.
- Releases include checksums, SBOMs and test evidence.

## Deployment responsibilities (not enforceable from code)

1. Private network only, no published container port.
2. TLS at the gateway.
3. Keys from a secret store, different values, rotated by starting a new container.
4. A decision on who may hold the audit key and how audit-view use is logged.
5. Rate limiting and per-user logging at the gateway, without bodies.
6. Never set `THANZI_DEV_MODE`.

## Known security limitations

- Keys are environment variables and are readable through `docker inspect`.
- The compose examples have not been run on a Docker host.
- Network isolation cannot be verified from code and must be confirmed in each environment.
- The optional language-model route accepts free text and cannot tell whether it is identifiable. Patient records must
  not be sent to it, and it is off by default.
