# Deployment runbook

Release candidate `0.7.0`. **Not clinically validated. Decision support only.** The service is stateless: no database,
no stored requests.

## What you get

A Docker image, `thanzi-screen`. It listens on port 8080 inside the container, publishes no port by itself and runs as a
non-root user. Dependency versions are pinned (`constraints.txt`). Each release includes `SHA256SUMS`, two SBOMs, the
OpenAPI contract and test evidence.

## What it does not provide

- TLS, rate limiting, end-user authentication and audit logging of who called what. The gateway provides these.
- Network isolation. Run it on a private network that only the gateway can reach. It sends no CORS headers and does not
  log request bodies, but it is not designed to face the internet.
- Storage. If the gateway logs requests, those logs hold child measurements. Treat them as health data.

## Requirements

| Need | Detail |
|---|---|
| Python (source install) | 3.11 or 3.12 |
| Runtime packages (API) | `fastapi~=0.162.2`, `pydantic~=2.14.3`, `uvicorn~=0.54.0`. The engine, rules and ML flags use the standard library only |
| Dev and test packages | `pytest`, `openpyxl`, `httpx~=0.28.1`, `pyyaml`, `coverage` |
| Exact versions | `pip install -c constraints.txt -e ".[dev,api]"` |
| Container | Docker, to load and run the released image (about 47 MB compressed) |
| Network | GitHub and PyPI access for the first install, or an offline copy of the pinned packages |
| GPU | Not used. The service is CPU only |

## Load the release

1. Verify checksums: `sha256sum -c SHA256SUMS`
2. Load the image: `gunzip -c thanzi-screen-v0.7.0-image.tar.gz | docker load`

## Settings

See [configuration](../configuration.md). Minimum: `THANZI_GATEWAY_KEY`. Add `THANZI_AUDIT_KEY` only if the audit view is
needed. Never set `THANZI_DEV_MODE` in production.

The child report and the surveillance reports also need a signed review file each in `THANZI_REVIEW_SIGNOFF_DIR` (mount the folder read-only). Run
`python scripts/review_pack.py gate --all --dir <folder>` before switching either on. See [review pack](../modules/review-pack.md).

Rotate keys by starting a new container with new keys, switching the gateway, and stopping the old container.

## Run

[`deploy/docker-compose.example.yml`](../../deploy/docker-compose.example.yml) shows the intended shape: private network,
no published port, read-only filesystem, dropped capabilities, no extra privileges and a 256 MB memory limit. It has not
been run on a Docker host: try it in staging first. Plain form:

```bash
docker run -d --name thanzi --network <private-network> \
  -e THANZI_GATEWAY_KEY -e THANZI_AUDIT_KEY thanzi-screen:v0.7.0
```

## Verify every deployment

From a machine that can reach the container:

```bash
python scripts/smoke_api.py --base-url http://<host>:8080 \
  --gateway-key "$THANZI_GATEWAY_KEY" --audit-key "$THANZI_AUDIT_KEY"
```

It sends synthetic children only and prints PASS or FAIL for 19 checks: key handling, documentation routes off, worker
view hides HIV and programme, audit view needs both keys. All must pass.

## Health and monitoring

See [operations](../operations.md).

## Rollback

Keep the previous image tarball. Stop the new container, start the old image with the same keys, run the smoke test.
To disable only the neural-network flag, set `THANZI_DEEP_ENABLED=0` and restart (no rebuild).

## Pinning the base image (optional)

The Dockerfile uses the `python:3.12-slim` tag. For a fully fixed build, resolve its digest
(`docker buildx imagetools inspect python:3.12-slim`) and change the `FROM` line to
`python:3.12-slim@sha256:<digest>`.

## Measured performance (build host, not target hardware)

One worker on one 2.1 GHz vCPU, 2,000 requests: about 550 to 790 requests per second, median latency 1.7 ms (1 client)
to 20 ms (16 clients), 48 MB at start and 54 MB after load. Run `scripts/load_probe.py` on the target hardware and set
targets from the expected load.

## Pre-production checklist

1. Private network only, no published port.
2. TLS terminated at the gateway.
3. Keys from a secret store, never baked into an image or committed.
4. Audit-key holder decided and audit-view use logged.
5. Rate limiting and request logging (without bodies) at the gateway.
6. The gateway does not forward the audit header from browsers.
7. Alerts on `degraded` and on repeated 5xx.
8. Worker wording and the case pack reviewed by a qualified clinician.
9. Load tested on the target servers.
10. For each optional feature switched on (child report, surveillance reports): its sign-off file is in place, `scripts/review_pack.py gate` passes, and `/v1/about` shows it as `ok`, not `blocked`.
