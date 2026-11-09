"""Black-box smoke test for a running Thanzi screening API. Standard library only.

    python scripts/smoke_api.py --base-url http://127.0.0.1:8080 \
        --gateway-key "$THANZI_GATEWAY_KEY" --audit-key "$THANZI_AUDIT_KEY"

Used by CI against the Docker container and by operators after any deployment. Sends synthetic requests only.
Exit code 0 when every check passes, 1 otherwise. Keys can also come from the environment
(THANZI_GATEWAY_KEY, THANZI_AUDIT_KEY). Without --audit-key the audit checks are skipped and said so.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

LOW = {"sex": "male", "age_days": 500, "weight_kg": 9.5, "length_height_cm": 75.0, "measure_position": "length",
       "oedema": "none", "muac_cm": 14.0, "appetite": "passed", "danger_signs": [], "complications": [],
       "clinically_well_and_alert": True}
MAM = {**LOW, "muac_cm": 12.0}
SAM = {**LOW, "muac_cm": 11.0}


def call(base: str, method: str, path: str, body: dict | None = None, headers: dict | None = None, timeout: float = 10.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(base + path, data=data, method=method,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base-url", default="http://127.0.0.1:8080")
    ap.add_argument("--gateway-key", default=os.environ.get("THANZI_GATEWAY_KEY"))
    ap.add_argument("--audit-key", default=os.environ.get("THANZI_AUDIT_KEY"))
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    if not args.gateway_key:
        print("a gateway key is required (--gateway-key or THANZI_GATEWAY_KEY)", file=sys.stderr)
        return 2
    gw = {"X-Gateway-Key": args.gateway_key}
    au = {**gw, "X-Audit-Key": args.audit_key or ""}
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  ({detail})"))
        if not ok:
            failures.append(name)

    code, text = call(base, "GET", "/health")
    check("health is open and says ok or degraded", code == 200 and json.loads(text).get("status") in ("ok", "degraded"), f"{code} {text[:80]}")
    check("health does not leak versions", "version" not in text.lower(), text[:80])
    code, _ = call(base, "GET", "/version")
    check("version needs the gateway key", code == 401, str(code))
    code, text = call(base, "GET", "/version", headers=gw)
    check("version works with the gateway key", code == 200 and "rule_set_version" in text, f"{code}")

    code, text = call(base, "POST", "/v1/screen", LOW)
    check("screen without a key is refused (401)", code == 401, str(code))
    code, _ = call(base, "POST", "/v1/screen", LOW, {"X-Gateway-Key": args.gateway_key + "x"})
    check("screen with a wrong key is refused (401)", code == 401, str(code))
    for path in ("/docs", "/redoc", "/openapi.json"):
        code, _ = call(base, "GET", path, headers=gw)
        check(f"{path} is not served", code == 404, str(code))

    code, text = call(base, "POST", "/v1/screen", LOW, gw)
    low = json.loads(text) if code == 200 else {}
    check("low-risk child: worker view, low_risk, no programme", code == 200 and low.get("view") == "worker"
          and low.get("classification") == "low_risk" and low.get("programme") is None, f"{code} {text[:120]}")
    check("response carries disclaimer, versions and status", all(low.get(k) for k in ("disclaimer", "rule_set_version", "status")), str(sorted(low)))
    code, text = call(base, "POST", "/v1/screen", SAM, gw)
    sam = json.loads(text) if code == 200 else {}
    check("SAM child: urgent tier", code == 200 and sam.get("classification") == "SAM_OTP" and sam.get("tier") == "urgent", f"{code} {text[:120]}")

    code1, t1 = call(base, "POST", "/v1/screen", {**MAM, "hiv_positive": True}, gw)
    code2, t2 = call(base, "POST", "/v1/screen", {**MAM, "hiv_positive": False}, gw)
    code3, t3 = call(base, "POST", "/v1/screen", MAM, gw)
    check("moderate child: worker view identical for HIV true, false and not given",
          code1 == code2 == code3 == 200 and t1 == t2 == t3, f"{code1} {code2} {code3}")
    mam = json.loads(t1) if code1 == 200 else {}
    check("moderate child: no programme and no hiv text in the worker view", mam.get("programme") is None and "hiv" not in t1.lower(), t1[:120])

    code, text = call(base, "POST", "/v1/screen", {**LOW, "child_name": "x"}, gw)
    check("identifying field is rejected (422) and not echoed", code == 422 and "child_name" not in text, f"{code}")
    code, text = call(base, "POST", "/v1/screen", {**LOW, "weight_kg": -1}, gw)
    check("invalid value is rejected (422)", code == 422, f"{code}")

    if args.audit_key:
        code, _ = call(base, "POST", "/v1/screen?view=audit", MAM, gw)
        check("audit view without the audit key is refused (403)", code == 403, str(code))
        code, _ = call(base, "POST", "/v1/screen?view=audit", MAM, {**gw, "X-Audit-Key": args.audit_key + "x"})
        check("audit view with a wrong audit key is refused", code in (401, 403), str(code))
        code, text = call(base, "POST", "/v1/screen?view=audit", {**MAM, "hiv_positive": True}, au)
        aud = json.loads(text) if code == 200 else {}
        check("audit view with both keys shows the real programme and rule", code == 200 and aud.get("view") == "audit"
              and aud.get("programme") == "OTP" and "MAM.HIV_OTP" in aud.get("rules_fired", []) and "explanation" in aud, f"{code} {text[:120]}")
    else:
        print("SKIP  audit checks (no audit key given)")

    print(f"\n{len(failures)} failed" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
