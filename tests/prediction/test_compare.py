import json
import random
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from thanzi_screen.prediction import (
    SimConfig, TargetConfig, build_examples, simulate_children, write_dataset,
)
from thanzi_screen.prediction import candidates as cand
from thanzi_screen.prediction import compare, select

SRC = Path(__file__).resolve().parents[2] / "src"
ROOT = SRC.parent


# ---------- pieces that need no training library ----------
def _scores(n=600, seed=0):
    rng = random.Random(seed)
    y = [int(rng.random() < 0.3) for _ in range(n)]
    base = [0.25 * v + rng.gauss(0, 0.5) for v in y]
    return y, base, [f"c{i}" for i in range(n)]


def test_challenger_identical_to_the_reference_is_never_chosen():
    y, s, groups = _scores()
    p = [1 / (1 + 2.718281828 ** -v) for v in s]
    out = compare.choose_model({"lr": p, "rf": list(p), "xgb": list(p)}, y, groups, compare.CompareConfig(n_boot=60))
    assert out["selected"] == "lr" and not any(c["passes"] for c in out["challengers"].values())


def test_a_clearly_better_challenger_is_chosen_but_a_marginal_one_is_not():
    rng = random.Random(1)
    y = [int(rng.random() < 0.3) for _ in range(1500)]
    groups = [f"c{i}" for i in range(1500)]
    weak = [min(max(0.3 + 0.05 * (v - 0.3) + rng.gauss(0, 0.1), 0.01), 0.99) for v in y]
    strong = [min(max(0.2 + 0.5 * v + rng.gauss(0, 0.1), 0.01), 0.99) for v in y]
    cfg = compare.CompareConfig(n_boot=80)
    assert compare.choose_model({"lr": weak, "rf": strong}, y, groups, cfg)["selected"] == "rf"
    near = [min(max(p + rng.gauss(0, 0.02), 0.01), 0.99) for p in weak]
    assert compare.choose_model({"lr": weak, "rf": near}, y, groups, cfg)["selected"] == "lr"


def test_baseline_is_the_best_training_column_with_its_training_direction():
    rng = random.Random(2)
    y = [int(rng.random() < 0.4) for _ in range(800)]
    X = [[rng.gauss(0, 1), rng.gauss(0, 1) - 1.5 * v, rng.gauss(0, 1)] for v in y]       # column 1 is the signal, lower is riskier
    b = cand.fit_baseline(X, y, ["a", "b", "c"])
    assert b.params["feature"] == "b" and b.params["direction"] == "lower is riskier"
    hi, lo = b.predict_proba([[0, -3, 0]])[0], b.predict_proba([[0, 3, 0]])[0]
    assert hi > lo


def test_a_target_with_too_few_events_is_reported_not_trained():
    ex = build_examples(simulate_children(SimConfig(n_children=300, seed=3)), TargetConfig())
    out = compare.run_target(ex, "future_sam", compare.CompareConfig(min_events=10 ** 6))
    assert out["status"] == "not_trained" and "too few" in out["reason"] and "test" not in out


def test_followup_balance_reports_lost_children_and_is_json_safe():
    ex = build_examples(simulate_children(SimConfig(n_children=400, seed=3)), TargetConfig())
    fb = compare.followup_balance(ex, "future_wasting")
    assert fb["lost_to_followup"] > 0 and fb["labelled"] > 0 and fb["features"]["whz"] is not None
    json.dumps(compare._clean(fb), allow_nan=False)


def test_importing_the_comparison_code_loads_no_training_library_and_no_screening_module():
    code = ("import sys; import thanzi_screen.prediction, thanzi_screen.prediction.compare, thanzi_screen.prediction.candidates;"
            "print('\\n'.join(sorted(m.split('.')[0] if not m.startswith('thanzi_screen') else m for m in sys.modules)))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={"PYTHONPATH": str(SRC)}, check=True)
    mods = set(out.stdout.split())
    assert not mods & {"numpy", "sklearn", "xgboost", "scipy"}, mods
    assert not any(m.startswith(("thanzi_screen.under5", "thanzi_screen.report", "thanzi_screen.ml", "thanzi_screen.growth")) for m in mods)


# ---------- end to end (needs numpy and scikit-learn; XGBoost is used when present) ----------
@pytest.fixture(scope="module")
def examples():
    return build_examples(simulate_children(SimConfig(n_children=1500, seed=11)), TargetConfig(), seed=0)


def _cfg(**kw):
    wanted = ("lr", "rf") + (("xgb",) if cand.available("xgb") else ())
    return compare.CompareConfig(n_boot=30, candidates=wanted, **kw)


@pytest.fixture(scope="module")
def trained(examples):
    pytest.importorskip("sklearn")
    return compare.run_target(examples, "future_wasting", _cfg())


def test_end_to_end_result_is_complete_and_json_safe(trained):
    assert trained["status"] == "trained"
    json.dumps(trained, allow_nan=False)
    t = trained["test"]
    assert set(t["models"]) >= {"lr", "rf", "baseline"} and trained["selection"]["selected"] in t["models"]
    lr = t["models"]["lr"]
    assert lr["auroc"] > 0.6 and 0.5 < lr["calibration_after"]["slope"] < 2.0     # the simulator has signal; probabilities are sane
    assert lr["auroc_ci"][0] <= lr["auroc"] <= lr["auroc_ci"][1]
    assert "auroc_diff_vs_lr" not in lr and "auroc_diff_vs_baseline" in lr
    assert t["n"] == trained["splits"]["test"]["rows"] - trained["skipped_unseen_missing"]["test"]
    assert set(t["subgroups"]["tables"]) == {"age_band", "sex", "district"}


def test_calibration_is_fitted_on_validation_only_and_keeps_the_order_of_risks(trained):
    for m in trained["test"]["models"].values():
        assert m["platt"]["slope"] > 0


def test_children_never_span_splits_and_the_preprocessor_sees_training_rows_only(examples):
    pytest.importorskip("sklearn")
    prep = compare.prepare(examples, "future_wasting")
    ids = {s: {e.child_id for e in prep.rows[s]} for s in ("train", "val", "test")}
    assert not (ids["train"] & ids["val"] or ids["train"] & ids["test"] or ids["val"] & ids["test"])
    assert prep.pre.spec["n_train_rows"] == len(select(examples, "future_wasting", "train"))
    changed = [replace(e, features={k: (v + 100.0 if v is not None else v) for k, v in e.features.items()}) if e.split != "train" else e
               for e in examples]
    assert compare.prepare(changed, "future_wasting").pre.spec == prep.pre.spec


def test_nothing_chosen_before_the_test_step_depends_on_test_labels(examples):
    pytest.importorskip("sklearn")
    cfg = _cfg()
    a = compare.fit_stage(compare.prepare(examples, "future_wasting"), cfg)
    flipped = [replace(e, labels={**e.labels, "future_wasting": 1 - e.labels["future_wasting"]})
               if e.split == "test" and e.labels["future_wasting"] is not None else e for e in examples]
    b = compare.fit_stage(compare.prepare(flipped, "future_wasting"), cfg)
    assert a["platt"] == b["platt"] and a["selection"] == b["selection"] and a["thresholds"] == b["thresholds"]


def test_same_data_and_seed_give_identical_results(examples):
    pytest.importorskip("sklearn")
    cfg = compare.CompareConfig(n_boot=20, candidates=("lr", "rf"))
    assert compare.run_target(examples, "future_wasting", cfg) == compare.run_target(examples, "future_wasting", cfg)


def test_xgboost_respects_the_monotone_constraints(examples):
    pytest.importorskip("xgboost")
    prep = compare.prepare(examples, "future_wasting")
    m = cand.fit_candidate("xgb", prep.X["train"], prep.y["train"], prep.pre.columns, seed=0)
    cols = list(prep.pre.columns)
    for feature in ("whz", "muac_cm", "waz"):                      # lower is never safer
        j = cols.index(feature)
        for row in prep.X["val"][:40]:
            p = []
            for v in (-3.0, -1.5, 0.0, 1.5, 3.0):
                r = list(row)
                r[j] = v
                p.append(m.predict_proba([r])[0])
            assert all(a >= b - 1e-9 for a, b in zip(p, p[1:])), (feature, p)


def test_report_states_simulated_and_names_the_baseline_feature(trained):
    text = compare.render_report({"targets": {"future_wasting": trained}}, "simulated")
    assert "SIMULATED DATA. NON-CLINICAL." in text and "Best single feature" in text and "Not trained" not in text


def test_script_refuses_simulated_data_without_the_flag_and_writes_a_report_with_it(tmp_path):
    pytest.importorskip("sklearn")
    data = tmp_path / "d"
    write_dataset(simulate_children(SimConfig(n_children=900, seed=5)), {"provenance": "simulated"}, data)
    script = ROOT / "scripts" / "train_prediction.py"
    env_args = [sys.executable, str(script), "--data", str(data / "visits.csv"), "--out", str(tmp_path / "o"), "--n-boot", "10",
                "--candidates", "lr", "--targets", "future_wasting"]
    refused = subprocess.run(env_args, capture_output=True, text=True)
    assert refused.returncode == 2 and "simulated" in refused.stderr
    ok = subprocess.run(env_args + ["--allow-simulated"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    res = json.loads((tmp_path / "o" / "results.json").read_text())
    assert res["clinical_use"] is False and res["dataset"]["provenance"] == "simulated"
    assert "SIMULATED DATA. NON-CLINICAL." in (tmp_path / "o" / "REPORT.md").read_text()
