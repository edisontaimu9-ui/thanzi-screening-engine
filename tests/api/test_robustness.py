"""Hostile and malformed requests over HTTP: never a 500, never an echo, never a stack trace (Phase 7, D101)."""
import json

import pytest

from tests.api._support import LOW_BASE, need_api

need_api()

from fastapi.testclient import TestClient  # noqa: E402

from thanzi_screen.api.app import create_app  # noqa: E402
from thanzi_screen.ml import load_models  # noqa: E402

GW, AU = "gateway-key-0123456789", "audit-key-0123456789ab"
HG = {"X-Gateway-Key": GW}
SAFE = {200, 400, 401, 403, 404, 405, 413, 415, 422}


@pytest.fixture(scope="module")
def client():
    return TestClient(create_app(models=load_models(), gateway_key=GW, audit_key=AU), raise_server_exceptions=False)


def _clean(resp):
    assert resp.status_code in SAFE, (resp.status_code, resp.text[:200])
    assert "Traceback" not in resp.text and "File \"" not in resp.text


@pytest.mark.parametrize("body", [
    b"", b"null", b"[]", b"[1,2,3]", b"\"text\"", b"42", b"true", b"{", b"{\"a\":", b"\xff\xfe\x00",
    b"{\"sex\": \"male\"}", b"{" * 5000, b"[" * 5000, b"{\"a\":" * 2000 + b"1" + b"}" * 2000,
])
def test_malformed_bodies_are_refused_cleanly(client, body):
    r = client.post("/v1/screen", content=body, headers={**HG, "Content-Type": "application/json"})
    assert r.status_code in (400, 413, 422), r.status_code
    _clean(r)


@pytest.mark.parametrize("ctype", ["text/plain", "application/xml", "multipart/form-data; boundary=x", "", "application/json; charset=utf-16"])
def test_wrong_content_types_never_crash(client, ctype):
    r = client.post("/v1/screen", content=json.dumps(LOW_BASE), headers={**HG, "Content-Type": ctype})
    _clean(r)


@pytest.mark.parametrize("value", [
    float("nan"), float("inf"), -float("inf"), 1e308, -1e308, 1e-308, 0, -0.0, "9.5", "NaN", True, False, None, [], {}, [9.5], {"a": 1},
    "\u0000", "9" * 10000, "ï»¿", "<script>alert(1)</script>", "'; DROP TABLE x; --", "\u202e",
])
@pytest.mark.parametrize("field", ["weight_kg", "length_height_cm", "muac_cm", "age_days", "sex", "oedema", "appetite"])
def test_every_field_survives_odd_values(client, field, value):
    body = {**LOW_BASE, field: value}
    try:
        raw = json.dumps(body, allow_nan=True)
    except (TypeError, ValueError):
        return
    r = client.post("/v1/screen", content=raw, headers={**HG, "Content-Type": "application/json"})
    _clean(r)


def test_odd_values_are_not_echoed_in_errors(client):
    for value in ("<script>alert(1)</script>", "'; DROP TABLE x; --", "9" * 400):
        r = client.post("/v1/screen", json={**LOW_BASE, "sex": value}, headers=HG)
        assert r.status_code == 422 and value not in r.text


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_wrong_methods_on_screen_never_crash(client, method):
    for headers in (HG, {}):
        r = client.request(method, "/v1/screen", headers=headers)
        assert r.status_code in (401, 404, 405), (method, r.status_code)


def test_duplicate_and_odd_headers_do_not_bypass_the_key(client):
    r = client.post("/v1/screen", json=LOW_BASE, headers=[("X-Gateway-Key", "wrong"), ("X-Gateway-Key", GW)])
    assert r.status_code in (200, 401)                       # either is safe; the point is no 500
    r = client.post("/v1/screen", json=LOW_BASE, headers={"X-Gateway-Key": GW + " "})
    assert r.status_code == 401
    r = client.post("/v1/screen", json=LOW_BASE, headers={"x-gateway-key": GW.upper()})
    assert r.status_code == 401


def test_query_string_abuse(client):
    for q in ("?view=", "?view=audit&view=worker", "?view=%00", "?view=" + "a" * 5000, "?x=" + "1" * 5000):
        r = client.post("/v1/screen" + q, json=LOW_BASE, headers=HG)
        _clean(r)


def test_many_sequential_requests_stay_consistent(client):
    first = client.post("/v1/screen", json=LOW_BASE, headers=HG).json()
    for _ in range(200):
        assert client.post("/v1/screen", json=LOW_BASE, headers=HG).json() == first


@pytest.mark.parametrize("value", [1e-308, 1e-10, 1e-6, 4e-7, 0.5, 0.7])
@pytest.mark.parametrize("age_days", [0, 100, 730, 731, 1000, 1856])
@pytest.mark.parametrize("position", ["length", "height"])
def test_i28_tiny_length_is_never_a_500(client, value, age_days, position):
    body = {**LOW_BASE, "length_height_cm": value, "age_days": age_days, "measure_position": position}
    r = client.post("/v1/screen", json=body, headers=HG)
    assert r.status_code in (200, 422), (r.status_code, r.text[:200])
    assert "Traceback" not in r.text
    if r.status_code == 422:
        assert str(value) not in r.text


def test_i28_tiny_length_is_a_422_with_a_stable_code(client):
    r = client.post("/v1/screen", json={**LOW_BASE, "length_height_cm": 1e-10}, headers=HG)
    assert r.status_code == 422
    assert "1e-10" not in r.text
