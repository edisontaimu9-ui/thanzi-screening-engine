"""Deep learning add-on (D145-D152): network, hardware, training, inference, isolation. Synthetic data only."""
import ast
import json
import math
import random
import sys
from pathlib import Path

import pytest

from thanzi_screen.anthro import compute_anthropometry
from thanzi_screen.data import DataError, GenConfig, generate, write_dataset
from thanzi_screen.ml import flag_record, load_models
from thanzi_screen.ml.dl import (MAX_PARAMS, PRESETS, HardwareProfile, Network, compare_record, detect_hardware,
                                 estimate_train_seconds, flag_record_deep, load_deep_models, measure_speed,
                                 parameter_count, recommend_preset)
from thanzi_screen.ml.dl.predict import ERROR_FILE, FIELD_FILE
from thanzi_screen.ml.dl.train import STATEMENT, train_deep
from thanzi_screen.ml.features import FEATURES, FIELDS
from thanzi_screen.ml.flags import FIELD_MESSAGES
from thanzi_screen.ml.train import train_all
from thanzi_screen.rules import Appetite, ClinicalInputs, classify

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "thanzi_screen"
DL = SRC / "ml" / "dl"
FULL = dict(appetite=Appetite.PASSED, danger_signs=frozenset(), complications=frozenset(), clinically_well_and_alert=True)


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    d = tmp_path_factory.mktemp("dl")
    cfg = GenConfig(seed=11, n=6000)
    write_dataset(generate(cfg), cfg, d / "data")
    csv = d / "data" / "synthetic_children.csv"
    train_all(csv, d / "models", seed=0, epochs=8)                                   # Phase 4 baseline, same data
    summary = train_deep(csv, d / "models", seed=0, epochs=12, preset="tiny", baseline_dir=d / "models")
    return d, summary


def _xor(n=900, seed=1):
    rng = random.Random(seed)
    X = [[rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in range(n)]
    return X, [int((a > 0) != (b > 0)) for a, b in X]


# ---- network: learning ----
def test_network_learns_a_nonlinear_rule_a_linear_model_cannot():
    from thanzi_screen.ml.models import LogisticModel
    X, y = _xor()
    lin = LogisticModel(["a", "b"]).fit(X, y, seed=1, epochs=20)
    lin_acc = sum((lin.predict_proba(x) > 0.5) == bool(t) for x, t in zip(X, y)) / len(y)
    net = Network(["a", "b"], (16, 8)).fit(X[:700], y[:700], X[700:], y[700:], seed=1, epochs=60, lr=0.01)
    acc = sum((net.predict_proba(x) > 0.5) == bool(t) for x, t in zip(X[700:], y[700:])) / 200
    assert lin_acc < 0.65 and acc > 0.95


def test_network_multiclass_learns_and_sums_to_one():
    rng = random.Random(3)
    X = [[rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in range(900)]
    Y = ["r" if a > 0.3 else ("g" if b > 0 else "b") for a, b in X]
    net = Network(["a", "b"], (16,), classes=["r", "g", "b"]).fit(X, Y, seed=2, epochs=40, lr=0.01)
    hits = sum(max(net.predict_dist(x).items(), key=lambda kv: kv[1])[0] == t for x, t in zip(X, Y))
    assert hits / len(Y) > 0.95
    assert math.isclose(sum(net.predict_dist([0.1, 0.2]).values()), 1.0)


def test_training_loss_goes_down_and_early_stopping_keeps_best_epoch():
    X, y = _xor(600)
    net = Network(["a", "b"], (8,)).fit(X[:450], y[:450], X[450:], y[450:], seed=0, epochs=50, lr=0.01, patience=3)
    assert net.history[-1]["train_loss"] < net.history[0]["train_loss"]
    assert 1 <= net.best_epoch <= len(net.history) <= 50
    best = min(r["val_loss"] for r in net.history)
    assert net._loss([net._standardise(x) for x in X[450:]], y[450:], {0: 1.0, 1: 1.0}) == pytest.approx(
        best, abs=1e-9)                                                               # the kept weights are the best epoch's


def test_class_weight_moves_the_output_towards_the_rare_class():
    rng = random.Random(5)
    X = [[rng.gauss(0, 1)] for _ in range(1500)]
    y = [int(x[0] + rng.gauss(0, 1) > 2.0) for x in X]
    plain = Network(["a"], (4,)).fit(X, y, seed=1, epochs=15, lr=0.01)
    heavy = Network(["a"], (4,)).fit(X, y, seed=1, epochs=15, lr=0.01, pos_weight=8.0)
    assert heavy.predict_proba([1.5]) > plain.predict_proba([1.5])


def test_dropout_is_deterministic_and_off_at_inference():
    X, y = _xor(400)
    a = Network(["a", "b"], (16,)).fit(X, y, seed=4, epochs=5, dropout=0.3)
    b = Network(["a", "b"], (16,)).fit(X, y, seed=4, epochs=5, dropout=0.3)
    assert a.to_dict() == b.to_dict()
    assert a.predict_proba([0.3, -0.2]) == a.predict_proba([0.3, -0.2])
    with pytest.raises(ValueError):
        Network(["a", "b"], (4,)).fit(X, y, dropout=1.0)


def test_training_is_deterministic_and_seed_matters():
    X, y = _xor(300)
    one = Network(["a", "b"], (8,)).fit(X, y, seed=7, epochs=4).to_dict()
    assert one == Network(["a", "b"], (8,)).fit(X, y, seed=7, epochs=4).to_dict()
    assert one != Network(["a", "b"], (8,)).fit(X, y, seed=8, epochs=4).to_dict()


# ---- network: JSON, limits, guards ----
def test_json_roundtrip_gives_identical_predictions():
    X, y = _xor(300)
    net = Network(["a", "b"], (8, 4)).fit(X, y, seed=1, epochs=4)
    back = Network.from_dict(json.loads(json.dumps(net.to_dict())))
    assert all(back.predict_proba(x) == net.predict_proba(x) for x in X[:50])
    assert back.to_dict() == net.to_dict()


def test_parameter_budget_is_enforced():
    n = parameter_count(len(FEATURES), (64, 32))
    assert Network(FEATURES, (64, 32)).params == n <= MAX_PARAMS
    with pytest.raises(ValueError, match="budget"):
        Network(FEATURES, (512, 256))
    assert Network(FEATURES, (512, 256), max_params=10 ** 6).params > MAX_PARAMS
    assert all(parameter_count(len(FEATURES), h) <= MAX_PARAMS for h in PRESETS.values())


def _good():
    return Network(["a", "b"], (3,)).to_dict()


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(type="pickle"),
    lambda d: d.update(activation="tanh"),
    lambda d: d.update(mean=[0.0]),
    lambda d: d.update(std=[1.0, 0.0]),
    lambda d: d["layers"][0]["w"][0].append(1.0),
    lambda d: d["layers"][0]["b"].pop(),
    lambda d: d["layers"].pop(),
    lambda d: d["layers"][1]["w"][0].__setitem__(0, float("nan")),
    lambda d: d["layers"][0]["b"].__setitem__(0, float("inf")),
    lambda d: d["layers"][0]["b"].__setitem__(0, "x"),
])
def test_malformed_network_files_are_rejected(mutate):
    d = _good()
    mutate(d)
    with pytest.raises(ValueError):
        Network.from_dict(d)


def test_input_and_mode_guards():
    net = Network(["a", "b"], (3,))
    with pytest.raises(ValueError):
        net.predict_proba([1.0])
    with pytest.raises(ValueError):
        net.predict_dist([1.0, 2.0])
    multi = Network(["a", "b"], (3,), classes=["x", "y"])
    with pytest.raises(ValueError):
        multi.predict_proba([1.0, 2.0])
    with pytest.raises(ValueError):
        Network(["a"], (3,), classes=["only"])
    with pytest.raises(ValueError):
        net.fit([], [])
    with pytest.raises(ValueError):
        net.fit([[1.0, 2.0]], [0, 1])


def test_extreme_inputs_stay_finite():
    X, y = _xor(300)
    net = Network(["a", "b"], (8,)).fit(X, y, seed=1, epochs=3)
    for x in ([1e12, -1e12], [0.0, 0.0], [-1e-12, 1e-12]):
        assert 0.0 <= net.predict_proba(x) <= 1.0


def test_top_signals_names_the_input_that_matters():
    rng = random.Random(9)
    X = [[rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)] for _ in range(800)]
    y = [int(x[1] > 0.2) for x in X]
    net = Network(["a", "b", "c"], (8,)).fit(X, y, seed=1, epochs=30, lr=0.01)
    assert net.top_signals([0.1, 0.9, 0.0], k=1) == ("b",)
    assert net.top_signals([0.1, 0.9, 0.0]) == net.top_signals([0.1, 0.9, 0.0])
    assert set(net.top_signals([0.1, 0.9, 0.5])) <= {"a", "b", "c"}


def test_predict_batch_matches_single_calls():
    X, y = _xor(200)
    net = Network(["a", "b"], (4,)).fit(X, y, seed=1, epochs=2)
    assert net.predict_batch(X[:5]) == [net.predict_proba(x) for x in X[:5]]


# ---- hardware ----
def test_detect_hardware_is_sane():
    hw = detect_hardware(0.02)
    assert hw.cpu_count >= 1 and hw.macs_per_second > 1e4
    assert hw.memory_mb is None or hw.memory_mb > 0
    assert measure_speed(0.01) > 0


def test_recommend_preset_follows_speed_and_memory():
    fast = HardwareProfile(8, 8192, 5e8)
    slow = HardwareProfile(2, 3000, 2e6)
    tiny_ram = HardwareProfile(8, 256, 5e8)
    unknown_ram = HardwareProfile(4, None, 5e8)
    assert recommend_preset(fast, 35000, len(FEATURES)) == "base"
    assert recommend_preset(slow, 35000, len(FEATURES)) == "tiny"
    assert recommend_preset(tiny_ram, 35000, len(FEATURES)) == "tiny"
    assert recommend_preset(unknown_ram, 35000, len(FEATURES)) == "base"
    assert recommend_preset(fast, 35000, len(FEATURES), budget_seconds=0.001) == "tiny"


def test_estimate_scales_with_rows_and_size():
    hw = HardwareProfile(4, 4096, 5e7)
    a = estimate_train_seconds(hw, 1000, len(FEATURES), PRESETS["tiny"], 10)
    assert estimate_train_seconds(hw, 2000, len(FEATURES), PRESETS["tiny"], 10) == pytest.approx(2 * a)
    assert estimate_train_seconds(hw, 1000, len(FEATURES), PRESETS["base"], 10) > a


def test_hardware_facts_never_reach_model_files(trained):
    d, _ = trained
    text = (d / "models" / ERROR_FILE).read_text() + (d / "models" / "DL_MODEL_CARD.md").read_text()
    assert "macs_per_second" not in text and "cpu_count" not in text


# ---- training artifacts ----
def test_deep_training_is_deterministic(trained, tmp_path):
    d, _ = trained
    train_deep(d / "data" / "synthetic_children.csv", tmp_path, seed=0, epochs=12, preset="tiny", baseline_dir=d / "models")
    for name in (ERROR_FILE, FIELD_FILE, "DL_MODEL_CARD.md"):
        assert (tmp_path / name).read_bytes() == (d / "models" / name).read_bytes()


def test_deep_training_refuses_unverified_data(trained, tmp_path):
    d, _ = trained
    (tmp_path / "x.csv").write_bytes((d / "data" / "synthetic_children.csv").read_bytes())
    with pytest.raises(DataError):
        train_deep(tmp_path / "x.csv", tmp_path / "m")


def test_unknown_preset_is_rejected(trained, tmp_path):
    with pytest.raises(ValueError):
        train_deep(trained[0] / "data" / "synthetic_children.csv", tmp_path, preset="huge")


def test_deep_files_labels_and_card(trained):
    d, summary = trained
    a = json.loads((d / "models" / ERROR_FILE).read_text())
    f = json.loads((d / "models" / FIELD_FILE).read_text())
    for obj in (a, f):
        assert obj["production"] is True                     # switched on (D153): runs in the API as an advisory flag
        assert obj["metadata"]["validated_on_real_data"] is False
        assert obj["metadata"]["statement"] == STATEMENT
        assert tuple(obj["metadata"]["feature_names"]) == FEATURES
    assert a["model"]["parameters"] <= MAX_PARAMS and tuple(f["model"]["classes"]) == FIELDS
    card = (d / "models" / "DL_MODEL_CARD.md").read_text()
    assert "Not validated on real children" in card and "Against the logistic model (same dataset" in card
    assert summary["baseline_test"] is not None


def test_baseline_is_skipped_when_it_was_trained_on_other_data(trained, tmp_path):
    d, _ = trained
    cfg = GenConfig(seed=12, n=3000)
    write_dataset(generate(cfg), cfg, tmp_path / "data")
    s = train_deep(tmp_path / "data" / "synthetic_children.csv", tmp_path / "m", epochs=3, preset="tiny", baseline_dir=d / "models")
    assert s["baseline_test"] is None
    assert "Not compared in this run" in (tmp_path / "m" / "DL_MODEL_CARD.md").read_text()


def test_operating_point_and_quality_on_synthetic(trained):
    _, s = trained
    t = s["test"]
    assert s["operating_point"]["operating_point_met"]
    assert t["auc"] > 0.95 and t["ml"]["alert_rate"] <= 0.12
    assert t["ml_recall_on_missed_by_phase1"] >= 0.8
    assert s["field"]["test_accuracy_on_error_records"] > 0.9
    assert s["training"]["error"]["epochs_run"] >= 1


# ---- inference ----
def _flags(models, weight=8.6, length=70.0, age=300, muac=13.5, **kw):
    clin = ClinicalInputs(muac_cm=muac, **{**FULL, **kw})
    return flag_record_deep("male", age, weight, length, "length", clin, models)


def test_deep_flags_normal_record_not_flagged_and_catch_errors(trained):
    m = load_deep_models(trained[0] / "models")
    f = _flags(m)
    assert not f.recording_error.flagged and not f.review.needed and f.model_version
    f = _flags(m, weight=86.0)
    assert f.recording_error.flagged and f.recording_error.suggested_field == "weight"
    assert f.recording_error.messages == (FIELD_MESSAGES["weight"],)
    f = _flags(m, muac=135.0)
    assert f.recording_error.flagged and f.recording_error.suggested_field == "muac"
    assert f.recording_error.top_signals


def test_deep_flags_with_missing_inputs_work(trained):
    m = load_deep_models(trained[0] / "models")
    f = flag_record_deep("female", 400, 9.0, 72.0, "length", ClinicalInputs(), m)
    assert 0.0 <= f.recording_error.probability <= 1.0 and f.review is not None


def test_deep_flags_never_change_classification(trained):
    m = load_deep_models(trained[0] / "models")
    for muac, w in ((11.0, 8.0), (12.0, 8.6), (13.5, 86.0), (13.5, 8.6)):
        clin = ClinicalInputs(muac_cm=muac, **FULL)
        a = compute_anthropometry(sex="male", weight_kg=w, length_height_cm=70.0, measure_position="length", age_days=300)
        before = classify(a, clin)
        flag_record_deep("male", 300, w, 70.0, "length", clin, m)
        assert before == classify(a, clin)


def test_compare_record_reports_both_families(trained):
    d, _ = trained
    lr, dl = load_models(d / "models"), load_deep_models(d / "models")
    clin = ClinicalInputs(muac_cm=13.5, **FULL)
    ok = compare_record("male", 300, 8.6, 70.0, "length", clin, lr, dl)
    assert ok.agree and not ok.logistic.flagged and not ok.deep.flagged
    bad = compare_record("male", 300, 86.0, 70.0, "length", clin, lr, dl)
    assert bad.logistic.flagged and bad.deep.flagged and bad.agree
    assert bad.mean_probability == pytest.approx((bad.logistic.probability + bad.deep.probability) / 2)
    assert bad.deep.suggested_field == "weight" and bad.advisory


def test_load_rejects_a_feature_mismatch_and_wrong_outputs(trained, tmp_path):
    d, _ = trained
    for name in (ERROR_FILE, FIELD_FILE):
        obj = json.loads((d / "models" / name).read_text())
        obj["metadata"]["feature_names"] = obj["metadata"]["feature_names"][:-1]
        (tmp_path / name).write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="retrain"):
        load_deep_models(tmp_path)
    (tmp_path / ERROR_FILE).write_text((d / "models" / FIELD_FILE).read_text())      # swapped files
    (tmp_path / FIELD_FILE).write_text((d / "models" / ERROR_FILE).read_text())
    with pytest.raises(ValueError):
        load_deep_models(tmp_path)


# ---- shipped models ----
def test_committed_deep_models_exist_and_load():
    m = load_deep_models(ROOT / "models")
    assert m.version == "0.1.0" and m.error.params <= MAX_PARAMS
    f = flag_record_deep("male", 300, 86.0, 70.0, "length", ClinicalInputs(muac_cm=13.5, **FULL), m)
    assert f.recording_error.flagged and f.recording_error.suggested_field == "weight"
    card = (ROOT / "models" / "DL_MODEL_CARD.md").read_text()
    assert "Not validated on real children" in card


# ---- isolation and packaging ----
def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield 0, a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or ""


def test_network_and_hardware_import_nothing_from_the_project():
    for name in ("network.py", "hardware.py"):
        for level, module in _imports(DL / name):
            if level == 0:
                assert not module.startswith("thanzi_screen"), (name, module)
            else:
                assert level == 1 and module in ("network",), (name, level, module)


def test_dl_package_uses_only_the_standard_library():
    std = set(sys.stdlib_module_names)
    for path in DL.glob("*.py"):
        for level, module in _imports(path):
            if level == 0:
                assert module.split(".")[0] in std | {"thanzi_screen"}, (path.name, module)


def test_only_the_api_edge_imports_the_dl_package():
    """D153: the API may use the deep flag. Nothing else in the screening code may, and the rules never do."""
    allowed = {"api/app.py", "api/service.py"}
    offenders = []
    for path in SRC.rglob("*.py"):
        if DL in path.parents:
            continue
        for level, module in _imports(path):
            if "dl" in module.split("."):
                offenders.append(str(path.relative_to(SRC)))
    assert set(offenders) <= allowed, offenders
    for name in ("rules", "anthro", "explain", "preterm"):
        for path in (SRC / name).rglob("*.py"):
            assert not any("dl" in m.split(".") for _, m in _imports(path)), path


def test_dependencies_stay_empty_and_no_new_packages():
    import tomllib
    cfg = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert cfg["project"]["dependencies"] == []
    assert set(cfg["project"]["optional-dependencies"]) == {"dev", "api", "llm"}
