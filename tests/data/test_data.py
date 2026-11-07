import csv
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from thanzi_screen.anthro import compute_anthropometry
from thanzi_screen.data import COLUMNS, DataError, GenConfig, generate, load_dataset, validate_rows, write_dataset
from thanzi_screen.data.schema import FORBIDDEN_COLUMNS, row_to_inputs
from thanzi_screen.rules import classify

CFG = GenConfig(seed=7, n=3000)


@pytest.fixture(scope="module")
def rows():
    return generate(CFG)


@pytest.fixture(scope="module")
def written(tmp_path_factory, rows):
    d = tmp_path_factory.mktemp("syn")
    manifest = write_dataset(rows, CFG, d)
    return d, manifest


def rand(rows):
    return [r for r in rows if r["record_type"] == "random"]


# ---- reproducibility ----
def test_same_seed_same_rows_and_hash(rows, tmp_path):
    other = generate(CFG)
    assert other == rows
    m1 = write_dataset(rows, CFG, tmp_path / "a")
    m2 = write_dataset(other, CFG, tmp_path / "b")
    assert m1["sha256"] == m2["sha256"]
    assert (tmp_path / "a" / "synthetic_children.csv").read_bytes() == (tmp_path / "b" / "synthetic_children.csv").read_bytes()


def test_different_seed_differs():
    assert generate(GenConfig(seed=8, n=50))[0]["child_id"] != generate(GenConfig(seed=7, n=50))[0]["child_id"]


def test_manifest_contents(written):
    _, m = written
    assert m["is_synthetic"] is True and m["rows"] == len(generate(CFG)) and m["boundary_rows"] == 16
    assert m["config_sha256"] == CFG.sha256() and m["seed"] == 7 and list(m["columns"]) == list(COLUMNS)


# ---- schema and validation ----
def test_rows_validate(rows):
    assert validate_rows(rows) == []


def test_no_identifier_columns_in_schema():
    assert not set(COLUMNS) & FORBIDDEN_COLUMNS


def test_validation_catches_problems(rows):
    bad = [dict(rows[0])]
    bad[0]["is_synthetic"] = False
    assert any("is_synthetic" in p for p in validate_rows(bad))
    bad = [dict(rows[0]), dict(rows[0])]
    assert any("duplicate" in p for p in validate_rows(bad))
    bad = [dict(rows[0], age_days=5000)]
    assert any("age_days" in p for p in validate_rows(bad))
    bad = [dict(rows[0], district="Atlantis")]
    assert any("district" in p for p in validate_rows(bad))
    bad = [{**rows[0], "village": "x"}]
    assert any("forbidden" in p for p in validate_rows(bad))


def test_geography_is_district_only(rows):
    assert {r["district"] for r in rows} <= set(CFG.districts)
    assert len({r["district"] for r in rand(rows)}) == 28
    assert not [c for c in COLUMNS if c in ("facility", "community", "village", "latitude", "longitude")]


# ---- engine consistency ----
def test_z_scores_match_sampled_targets(rows):
    ok = [r for r in rand(rows) if r["injected_error"] == "none" and r["oedema"] == "none" and r["wflh_z"] is not None]
    assert len(ok) > 2000
    for r in ok:
        assert abs(r["wflh_z"] - r["true_wflh_z"]) < 0.1
        assert abs(r["lhfa_z"] - r["true_lhfa_z"]) < 0.1


def test_labels_equal_fresh_classify(rows):
    for r in rows[::15]:
        a = compute_anthropometry(sex=r["sex"], weight_kg=r["weight_kg"], length_height_cm=r["length_height_cm"],
                                  measure_position=r["measure_position"], age_days=r["age_days"],
                                  oedema=r["oedema"] != "none")
        res = classify(a, row_to_inputs(r))
        assert r["cmam_class"] == res.classification.value and r["tier"] == res.tier.value
        assert r["rules_fired"] == ";".join(res.rules_fired)


def test_sampled_moments_near_config(rows):
    zs = [r["true_wflh_z"] for r in rand(rows)]
    assert abs(statistics.mean(zs) - CFG.wflh_mean) < 0.1
    assert abs(statistics.pstdev(zs) - CFG.wflh_sd) < 0.12


def test_all_classes_exercised(rows):
    classes = Counter(r["cmam_class"] for r in rand(rows))
    for c in ("low_risk", "MAM", "SAM_OTP", "SAM_INPATIENT", "SAM_ASSESS", "UNABLE_TO_CLASSIFY"):
        assert classes[c] > 0


# ---- boundary set ----
def test_boundary_records(rows):
    b = [r for r in rows if r["record_type"] == "boundary"]
    assert len(b) == 16 and all(r["split"] == "boundary" and r["injected_error"] == "none" for r in b)
    by_muac = {r["muac_cm"]: r["cmam_class"] for r in b[:4]}
    assert by_muac[11.4].startswith("SAM") and by_muac[11.5] == "MAM" and by_muac[12.4] == "MAM" and by_muac[12.5] == "low_risk"
    weights = {r["weight_kg"]: r["cmam_class"] for r in b if r["age_days"] == 243}
    assert weights[2.99] == "SAM_INPATIENT"
    assert any("INF.WEIGHT_LT3KG" in r["rules_fired"] for r in b)
    six = {r["age_days"]: r["cmam_class"] for r in b if r["age_days"] in (182, 183)}
    assert six[182] == "low_risk" and six[183].startswith("SAM")  # MUAC ignored below 6 months
    assert {r["oedema"] for r in b} >= {"+", "++", "+++"}


# ---- noise and missingness ----
def test_injected_error_rate_and_types(rows):
    r_ = rand(rows)
    rate = sum(r["injected_error"] != "none" for r in r_) / len(r_)
    assert 0.02 < rate < 0.055
    assert {r["injected_error"] for r in r_} >= {"weight_decimal_shift", "length_digit_transposition", "muac_unit_error", "age_heaping"}


def test_injected_errors_change_recorded_values(rows):
    for r in rand(rows):
        k = r["injected_error"]
        if k == "weight_decimal_shift":
            assert r["weight_kg"] != r["true_weight_kg"]
        elif k == "length_digit_transposition":
            assert r["length_height_cm"] != r["true_length_height_cm"]
        elif k == "muac_unit_error":
            assert r["muac_cm"] == round(r["true_muac_cm"] * 10, 1)
        elif k == "age_heaping":
            assert r["age_days"] != r["true_age_days"]
        else:
            assert r["age_days"] == r["true_age_days"] and r["weight_kg"] == r["true_weight_kg"]


def test_muac_missingness_and_age_rule(rows):
    child = [r for r in rand(rows) if r["true_age_days"] / 30.4375 >= 6]
    infant = [r for r in rand(rows) if r["true_age_days"] / 30.4375 < 6]
    assert all(r["true_muac_cm"] is None and r["muac_cm"] is None for r in infant)
    miss = sum(r["muac_cm"] is None for r in child) / len(child)
    assert 0.03 < miss < 0.08


def test_injected_errors_are_detected_by_engine_often(rows):
    # Weight decimal shifts must show up as implausible values or review flags in most cases
    shifted = [r for r in rand(rows) if r["injected_error"] == "weight_decimal_shift"]
    flagged = sum(r["review_needed"] for r in shifted)
    assert flagged / len(shifted) > 0.8


# ---- review target (B) ----
def test_review_reasons_consistent(rows):
    for r in rows:
        assert r["review_needed"] == bool(r["review_reasons"])
        if r["cmam_class"] == "UNABLE_TO_CLASSIFY":
            assert "unable_to_classify" in r["review_reasons"]


# ---- splits ----
def test_no_split_leakage_and_stratified(rows):
    ids = [r["child_id"] for r in rows]
    assert len(ids) == len(set(ids))
    fr = {s: [r for r in rand(rows) if r["split"] == s] for s in ("train", "val", "test")}
    assert sum(len(v) for v in fr.values()) == len(rand(rows))
    assert abs(len(fr["train"]) / len(rand(rows)) - 0.70) < 0.01
    for cls in ("low_risk", "MAM", "SAM_OTP", "SAM_INPATIENT"):
        for s in fr:
            share = sum(r["cmam_class"] == cls for r in fr[s]) / len(fr[s])
            total = sum(r["cmam_class"] == cls for r in rand(rows)) / len(rand(rows))
            assert abs(share - total) < 0.02


# ---- loader refuses unverified or real data ----
def test_load_roundtrip(written):
    d, _ = written
    loaded = load_dataset(d / "synthetic_children.csv")
    assert len(loaded) == len(generate(CFG))


def test_loader_refuses_missing_manifest(written, tmp_path):
    d, _ = written
    (tmp_path / "x.csv").write_bytes((d / "synthetic_children.csv").read_bytes())
    with pytest.raises(DataError, match="manifest missing"):
        load_dataset(tmp_path / "x.csv")


def test_loader_refuses_tampered_csv(written, tmp_path):
    d, _ = written
    (tmp_path / "synthetic_children.csv").write_bytes((d / "synthetic_children.csv").read_bytes() + b"x\n")
    (tmp_path / "MANIFEST.json").write_text((d / "MANIFEST.json").read_text())
    with pytest.raises(DataError, match="checksum"):
        load_dataset(tmp_path / "synthetic_children.csv")


def test_loader_refuses_non_synthetic_manifest(written, tmp_path):
    d, _ = written
    m = json.loads((d / "MANIFEST.json").read_text())
    m["is_synthetic"] = False
    (tmp_path / "MANIFEST.json").write_text(json.dumps(m))
    (tmp_path / "synthetic_children.csv").write_bytes((d / "synthetic_children.csv").read_bytes())
    with pytest.raises(DataError, match="synthetic"):
        load_dataset(tmp_path / "synthetic_children.csv")


def test_loader_refuses_rows_marked_real(written, tmp_path):
    d, m = written
    text = (d / "synthetic_children.csv").read_text().replace(",true,random,", ",false,random,", 1)
    p = tmp_path / "synthetic_children.csv"
    p.write_text(text)
    import hashlib
    mm = json.loads((d / "MANIFEST.json").read_text())
    mm["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (tmp_path / "MANIFEST.json").write_text(json.dumps(mm))
    with pytest.raises(DataError, match="is_synthetic"):
        load_dataset(p)


def test_writer_refuses_invalid_rows(rows, tmp_path):
    bad = [dict(rows[0], is_synthetic=False)]
    with pytest.raises(DataError):
        write_dataset(bad, CFG, tmp_path)


# ---- config ----
def test_config_rejects_unknown_keys_and_hash_stable():
    with pytest.raises(ValueError):
        GenConfig.from_dict({"nope": 1})
    assert GenConfig.from_dict({"seed": 7, "n": 3000}).sha256() == CFG.sha256()
    assert GenConfig.from_dict(json.loads(json.dumps(CFG.to_dict()))).sha256() == CFG.sha256()


def test_cli_runs(tmp_path):
    root = Path(__file__).resolve().parents[2]
    out = subprocess.run([sys.executable, str(root / "scripts" / "generate_synthetic.py"), "--n", "50", "--seed", "3",
                          "--out", str(tmp_path)], capture_output=True, text=True, check=True).stdout
    assert "rows=66" in out and (tmp_path / "MANIFEST.json").exists()
