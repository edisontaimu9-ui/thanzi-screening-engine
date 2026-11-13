"""Phase 11 in the service: a switch set to 1 is not enough. Without a valid sign-off the routes answer exactly as if off."""
import json

from tests.api._support import LOW_BASE, need_api
from tests.api.test_surveillance_reports_http import BODY, MAPPING
from tests.review.test_gate import CHILD, SURV, signed
from thanzi_screen.review import SUBJECTS
from thanzi_screen.review import pack as P

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402

GW = "gateway-key-0123456789"
HG = {"X-Gateway-Key": GW}


def _env(monkeypatch, tmp_path=None, child=True, surv=False):
    monkeypatch.delenv("THANZI_REVIEW_SIGNOFF_DIR", raising=False)
    monkeypatch.setenv("THANZI_CHILD_REPORT_ENABLED", "1" if child else "0")
    monkeypatch.setenv("THANZI_SURVEILLANCE_REPORTS_ENABLED", "1" if surv else "0")
    if tmp_path is not None:
        monkeypatch.setenv("THANZI_REVIEW_SIGNOFF_DIR", str(tmp_path))


def _components(c):
    return {x["name"]: x for x in c.get("/v1/about", headers=HG).json()["components"]}


def _put(tmp_path, key, doc):
    (tmp_path / SUBJECTS[key].filename).write_text(json.dumps(doc), encoding="utf-8")


def test_switch_without_signoff_is_blocked_and_says_so(monkeypatch, caplog):
    _env(monkeypatch)
    c = TestClient(create_app(gateway_key=GW))
    r = c.post("/v1/report", json=LOW_BASE, headers=HG)
    assert r.status_code == 404 and r.json()["code"] == "report_off"
    comp = _components(c)["child_report"]
    assert comp["state"] == "blocked" and "signoff_dir_not_set" in comp["detail"]
    assert "blocked by the review gate" in caplog.text


def test_switch_with_valid_signoff_turns_the_route_on(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    _put(tmp_path, CHILD, signed())
    c = TestClient(create_app(gateway_key=GW))
    r = c.post("/v1/report", json=LOW_BASE, headers=HG)
    assert r.status_code == 200, r.text
    assert _components(c)["child_report"]["state"] == "ok"


def test_stale_signoff_blocks(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    _put(tmp_path, CHILD, signed(content_sha256="0" * 64))
    c = TestClient(create_app(gateway_key=GW))
    assert c.post("/v1/report", json=LOW_BASE, headers=HG).status_code == 404
    assert "content_changed_since_review" in _components(c)["child_report"]["detail"]


def test_signoff_without_the_switch_stays_off(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, child=False)
    _put(tmp_path, CHILD, signed())
    c = TestClient(create_app(gateway_key=GW))
    assert c.post("/v1/report", json=LOW_BASE, headers=HG).status_code == 404
    assert _components(c)["child_report"]["state"] == "off"


def test_blocked_reasons_do_not_show_what_the_reviewer_typed(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    doc = signed(approval_reference="SECRET-REF", outcome="not_approved")
    doc["reviewers"][0]["name"] = "Dr SECRETNAME"
    _put(tmp_path, CHILD, doc)
    c = TestClient(create_app(gateway_key=GW))
    assert "SECRET" not in json.dumps(c.get("/v1/about", headers=HG).json())


def test_explicit_argument_still_decides_alone():
    c = TestClient(create_app(gateway_key=GW, child_report=True, surveillance_reports=False))
    assert c.post("/v1/report", json=LOW_BASE, headers=HG).status_code == 200
    comps = _components(c)
    assert comps["child_report"]["state"] == "ok" and comps["surveillance_reports"]["state"] == "off"


def test_surveillance_blocked_while_placeholder_then_open_when_confirmed(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path, child=False, surv=True)
    _put(tmp_path, SURV, signed(SURV))
    c = TestClient(create_app(gateway_key=GW))
    for path, body in (("/v1/surveillance/report", BODY), ("/v1/surveillance/dhis2", {**BODY, "mapping": MAPPING})):
        r = c.post(path, json=body, headers=HG)
        assert r.status_code == 404 and r.json()["code"] == "surveillance_reports_off"
    assert "settings_still_placeholder" in _components(c)["surveillance_reports"]["detail"]
    monkeypatch.setattr(P, "_surv_placeholder", lambda: False)       # the Ministry values are in
    c = TestClient(create_app(gateway_key=GW))
    assert c.post("/v1/surveillance/report", json=BODY, headers=HG).status_code == 200
    assert _components(c)["surveillance_reports"]["state"] == "ok"
