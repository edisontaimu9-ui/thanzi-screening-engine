# Deployment runbook (for Hope)

Release candidate `0.7.0`. **Not clinically validated. Decision support only.** The service is stateless: no database, no stored requests.

## What you get
A Docker image, `thanzi-screen`. It listens on port 8080 inside the container and publishes no port by itself. It runs as a non-root user. Dependency versions are pinned (`constraints.txt`); `SHA256SUMS` and two SBOMs come with the release.

## What it does not do (yours to provide)
- TLS, rate limiting, authentication of end users, audit logging of who called what. The gateway holds these.
- Network isolation (I21): run it on a private network only your gateway can reach. The service has no CORS headers and does not log request bodies, but it is not designed to face the internet.
- Storage of any kind. If the gateway logs requests, those logs hold child measurements: treat them as health data.

## Before you load it
1. Check the checksums: `sha256sum -c SHA256SUMS` (the image tarball is in the list).
2. Load: `gunzip -c thanzi-screen-v0.7.0-image.tar.gz | docker load`

## Settings (environment variables)
| Variable | Needed | Meaning |
|---|---|---|
| `THANZI_GATEWAY_KEY` | yes | Shared secret the gateway sends as `X-Gateway-Key`. At least 16 characters (use 48 hex). The service **refuses to start** without it or with a short one. |
| `THANZI_AUDIT_KEY` | no | Second secret for `?view=audit`, sent as `X-Audit-Key` together with the gateway key. Must differ from the gateway key. If unset the audit view is off. The audit view carries HIV information and the real programme: give the key only to people entitled to it (I24). |
| `PORT` | no | Listening port, default 8080. |
| `THANZI_MODELS_DIR` | no | Already set in the image. If the models are missing or mismatched the service starts in degraded mode: rules result unchanged, ML flag unavailable (`/health` says `degraded`). |

Never set `THANZI_DEV_MODE`. It exposes docs routes and can run without a key. Keys are read from environment variables only (I29): anyone who can run `docker inspect` on the host can read them.

Make keys with `openssl rand -hex 24`. Rotate by starting a new container with new keys, switching the gateway, and stopping the old one.

## Run
See `deploy/docker-compose.example.yml` (private network, no published port, read-only filesystem, no extra privileges, 256 MB limit). It is an example and was not run on a Docker host in Phase 7: try it in staging first. Plain form:

    docker run -d --name thanzi --network <private-network> \
      -e THANZI_GATEWAY_KEY -e THANZI_AUDIT_KEY thanzi-screen:v0.7.0

## Check it after every deployment
From a machine that can reach the container:

    python scripts/smoke_api.py --base-url http://<host>:8080 \
      --gateway-key "$THANZI_GATEWAY_KEY" --audit-key "$THANZI_AUDIT_KEY"

It sends synthetic children only and prints PASS or FAIL for 19 checks: key handling, docs routes off, worker view hides HIV and programme, audit view needs both keys. All must pass.

## Health and monitoring
- `GET /health` needs no key and returns only `{"status": "ok"}` or `"degraded"`. The image has a built-in healthcheck (`docker inspect --format '{{.State.Health.Status}}'`).
- Alert on `degraded` (models missing) and on repeated 5xx from the service.
- Logs hold no keys and no request values (checked in CI). They do hold access lines (client address, path, status).

## Rollback
Keep the previous image tarball. Stop the new container, start the old image with the same keys, run the smoke test.

## Pinning the base image (optional)
The Dockerfile uses the `python:3.12-slim` tag. For a fully fixed build, resolve its digest on a machine with registry access (`docker buildx imagetools inspect python:3.12-slim`) and change the `FROM` line to `python:3.12-slim@sha256:<digest>`.

## Measured performance (from the test report, not UniPod)
One worker on one 2.1 GHz vCPU, 2000 requests: about 550 to 790 requests per second, median latency 1.7 ms (1 client) to 20 ms (16 clients), 48 MB at start, 54 MB after load. Run `scripts/load_probe.py` on UniPod hardware and send the numbers; targets need your expected load.

## Tools and dependencies (for the programme technical lead)
The programme asks teams to send their tools and dependencies in advance so the environment can be prepared. For this engine:

| Need | Detail |
|---|---|
| Python | 3.11 or 3.12 |
| Runtime packages (API only) | `fastapi~=0.162.2`, `pydantic~=2.14.3`, `uvicorn~=0.54.0`. The engine, rules and ML flags use the standard library only |
| Dev and test packages | `pytest`, `openpyxl`, `httpx~=0.28.1`, `pyyaml`, `coverage` |
| Exact versions | Pinned in `constraints.txt`: `pip install -c constraints.txt -e ".[dev,api]"` |
| Container | Docker, to load and run the released image (about 47 MB compressed) |
| Source | Git, to clone `https://github.com/edisontaimu9-ui/thanzi-screening-engine` |
| Network | GitHub and PyPI access for the first install, or an offline copy of the pinned packages |
| GPU | Not used. The service is CPU only. The workstation GPU (RTX A4000, 16 GB) is not needed to run or test it |

## Target hardware (as stated by the programme)
Development workstations with Intel Core 9 processors and an NVIDIA RTX A4000 GPU (16 GB), or the GPU configuration the UniPod confirms. This describes the programme's development environment, not a production server specification. The measured performance above was taken on one vCPU, so it is a floor, not a forecast for that hardware. Run `scripts/load_probe.py` there and send the numbers.

## Contacts and owners
Network isolation, TLS, audit key holder: Hope. Clinical wording and review: Maria Talimire. Engine and releases: Edison.
