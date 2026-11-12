"""Export checks that need numpy and scikit-learn (XGBoost when present): the shipped JSON must give what the library gives,
exactly, and nothing chosen before the test step may depend on test labels. Skipped when the training libraries are missing."""
import importlib.util
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from thanzi_screen.prediction import SimConfig, TargetConfig, build_examples, simulate_children, write_dataset
from thanzi_screen.prediction import candidates as cand
from thanzi_screen.prediction import compare
from thanzi_screen.prediction.card import render_model_card
from thanzi_screen.prediction.model import PredictionModel, load_prediction_model
from thanzi_screen.prediction.predict import assess_features

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not cand.available("lr"), reason="needs numpy and scikit-learn (pip install -e '.[train]')")
TARGET = "future_wasting"


def _script():
    spec = importlib.util.spec_from_file_location("export_prediction", ROOT / "scripts" / "export_prediction.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def examples():
    return build_examples(simulate_children(SimConfig(n_children=1500, seed=11)), TargetConfig(), seed=0)


def _cfg():
    wanted = ("lr", "rf") + (("xgb",) if cand.available("xgb") else ())
    return compare.CompareConfig(n_boot=20, candidates=wanted)


@pytest.fixture(scope="module")
def fitted(examples):
    return compare.run_target_with_state(examples, TARGET, _cfg())


MANIFEST = {"provenance": "simulated", "sha256": "0" * 64, "rows": 1, "children": 1}


def _spec_for(fitted, name, manifest=MANIFEST):
    r, prep, state = fitted
    r2 = {**r, "selection": {**r["selection"], "selected": name}}
    return _script().build_spec(TARGET, r2, prep, state, manifest, TargetConfig(), 0, "", None)


@pytest.mark.parametrize("name", ["lr", "rf", "xgb"])
def test_every_exported_model_matches_the_library_and_explains_exactly(fitted, name):
    if not cand.available(name):
        pytest.skip(f"{name} library not installed")
    _, prep, state = fitted
    spec, diff = _spec_for(fitted, name)
    assert diff <= 1e-5
    m = PredictionModel(json.loads(json.dumps(spec, sort_keys=True)))       # what the file holds
    lib = state["models"][name].predict_proba(prep.X["test"][:150])
    ours = [m._raw_probability(x) for x in prep.X["test"][:150]]
    assert max(abs(a - b) for a, b in zip(lib, ours)) <= 1e-5
    for x in prep.X["test"][:15]:
        base, phi, _ = m.contributions(x)
        assert abs(base + sum(phi) - m.raw_output(x)) < 1e-6
    assert m.kind == {"lr": "logistic", "rf": "rf_prob", "xgb": "gbm_logit"}[name]


def test_the_exported_model_keeps_the_order_of_risks_after_platt(fitted):
    _, prep, state = fitted
    spec, _ = _spec_for(fitted, "lr")
    m = PredictionModel(json.loads(json.dumps(spec, sort_keys=True)))
    xs = prep.X["val"][:300]
    raw = [m._raw_probability(x) for x in xs]
    cal = [m.probability(x)[1] for x in xs]
    order = sorted(range(len(xs)), key=lambda i: raw[i])
    assert [cal[i] for i in order] == sorted(cal[i] for i in order)


def test_strata_cutoffs_come_from_validation_and_the_file_is_simulated_and_not_clinical(fitted):
    r, prep, state = fitted
    spec, _ = _spec_for(fitted, "lr")
    assert spec["clinical_use"] is False and spec["provenance"] == "simulated" and spec["acceptance"]["set"] is False
    assert spec["strata"]["cutoffs"]["high"] == state["thresholds"][0.1]["lr"]
    assert spec["strata"]["cutoffs"]["elevated"] == state["thresholds"][0.2]["lr"]
    assert spec["safeguards"]["max_missing_features"] == max(sum(v is None for v in e.features.values()) for e in prep.rows["train"])
    with pytest.raises(Exception, match="simulated"):
        import tempfile
        p = Path(tempfile.mkdtemp()) / "m.json"
        p.write_text(json.dumps(spec))
        load_prediction_model(p)


def test_test_labels_change_nothing_that_is_exported(examples, fitted):
    flipped = [replace(e, labels={**e.labels, TARGET: 1 - e.labels[TARGET]}) if e.split == "test" and e.labels[TARGET] is not None else e
               for e in examples]
    a, _ = _spec_for(fitted, "lr")
    b, _ = _spec_for(compare.run_target_with_state(flipped, TARGET, _cfg()), "lr")
    drop = lambda s: {k: v for k, v in s.items() if k != "metrics"}          # the reported test AUROC is allowed to differ
    assert json.dumps(drop(a), sort_keys=True) == json.dumps(drop(b), sort_keys=True)


def test_export_is_reproducible_byte_for_byte(examples, fitted):
    again = compare.run_target_with_state(examples, TARGET, _cfg())
    a, _ = _spec_for(fitted, "lr")
    b, _ = _spec_for(again, "lr")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_strata_table_is_in_the_test_report_and_adds_up(fitted):
    r = fitted[0]
    st = r["test"]["strata"]
    assert {row["stratum"] for row in st["table"]} == {"high", "elevated", "not flagged"}
    assert sum(row["n"] for row in st["table"]) == r["test"]["n"]
    assert sum(row["events"] for row in st["table"]) == r["test"]["events"]
    rate = {row["stratum"]: row["event_rate"] for row in st["table"]}
    assert rate["high"] > rate["not flagged"]                    # the simulator has signal, so the strata must separate
    assert st["cutoffs"]["high"] >= st["cutoffs"]["elevated"]


def test_a_shipped_model_scores_real_rows_end_to_end(examples, fitted):
    spec, _ = _spec_for(fitted, "lr")
    m = PredictionModel(json.loads(json.dumps(spec, sort_keys=True)))
    outs = [assess_features(m, e.features) for e in examples[:400]]
    assert sum(o["scored"] for o in outs) > 300 and any(o["stratum"] for o in outs)
    assert all(o["message"] is None for o in outs if not o["elevated"])


def test_model_card_states_simulated_and_has_every_section(fitted):
    r = fitted[0]
    spec, parity = _spec_for(fitted, "lr")
    results = {"dataset": MANIFEST, "libraries": cand.versions(), "targets": {TARGET: r, "future_sam": {"status": "not_trained", "reason": "too few events"}}}
    card = render_model_card(results, {TARGET: spec}, {TARGET: parity})
    for part in ("SIMULATED DATA. NOT CLINICAL.", "Risk strata", "never reported as \"low risk\"", "Subgroups", "Loss to follow-up",
                 "What they do not do", "Export check", "Not exported.** too few events"):
        assert part in card, part


# ---------- the script ----------
def _run(args):
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "export_prediction.py"), *args], capture_output=True, text=True)


def test_script_exports_simulated_models_only_with_the_flag(tmp_path):
    data = tmp_path / "d"
    write_dataset(simulate_children(SimConfig(n_children=1200, seed=5)), {"provenance": "simulated"}, data)
    args = ["--data", str(data / "visits.csv"), "--out", str(tmp_path / "o"), "--n-boot", "10", "--candidates", "lr", "--targets", TARGET]
    refused = _run(args)
    assert refused.returncode == 2 and "simulated" in refused.stderr and not (tmp_path / "o").exists()
    ok = _run(args + ["--allow-simulated"])
    assert ok.returncode == 0, ok.stderr
    m = load_prediction_model(tmp_path / "o" / f"{TARGET}.json", allow_simulated=True)
    assert m.clinical_use is False and m.simulated
    assert "SIMULATED DATA. NOT CLINICAL." in (tmp_path / "o" / "MODEL_CARD.md").read_text()
    assert json.loads((tmp_path / "o" / "results.json").read_text())["exported"] == [TARGET]


def test_script_writes_nothing_for_real_data_without_signoff_and_acceptance(tmp_path):
    data = tmp_path / "d"
    real = {"provenance": "real", "ethics_ref": "E-1", "data_agreement_ref": "DA-1", "extraction_description": "test",
            "period_covered": "2025", "deidentified": True}
    write_dataset(simulate_children(SimConfig(n_children=1200, seed=5)), real, data)       # shape only: the data are simulated
    args = ["--data", str(data / "visits.csv"), "--out", str(tmp_path / "o"), "--n-boot", "10", "--candidates", "lr", "--targets", TARGET]
    none = _run(args)
    assert none.returncode == 2 and "Nothing written" in none.stderr and not (tmp_path / "o").exists()
    acc = tmp_path / "acc.json"
    acc.write_text(json.dumps({"set": True, "passed": False, "checks": []}))
    failed = _run(args + ["--clinical-signoff", "S-1", "--acceptance", str(acc)])
    assert failed.returncode == 2 and not (tmp_path / "o").exists()
    acc.write_text(json.dumps({"set": True, "passed": True, "checks": ["pre-registered"]}))
    ok = _run(args + ["--clinical-signoff", "S-1", "--acceptance", str(acc)])
    assert ok.returncode == 0, ok.stderr
    m = load_prediction_model(tmp_path / "o" / f"{TARGET}.json")                 # loads WITHOUT allow_simulated: real, with governance
    assert m.provenance == "real" and m.spec["governance"]["clinical_signoff"] == "S-1"
