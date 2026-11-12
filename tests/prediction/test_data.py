import json
import shutil
from dataclasses import replace

import pytest

from thanzi_screen.factors import Clinical, Demographic, Feeding, Maternal, Socioeconomic, Visit
from thanzi_screen.prediction import (
    FEATURE_NAMES, FEATURES, GROUPS, Child, DatasetError, Observation, Preprocessor, SimConfig, TargetConfig,
    build_examples, build_features, label_summary, label_targets, load_dataset, matrix, simulate_children, split_children,
    write_dataset,
)
from thanzi_screen.prediction.features import FORBIDDEN_PARTS, _slope
from thanzi_screen.prediction.preprocess import PreprocessError
from thanzi_screen.prediction.dataset import CSV_NAME, MANIFEST_NAME
from thanzi_screen.rules import OedemaGrade


@pytest.fixture(scope="module")
def children():
    return simulate_children(SimConfig(n_children=400, seed=7))


def obs(age, w, l, muac=None, oedema=OedemaGrade.NONE, **kw):
    return Observation(Visit(age, w, l, "length" if age <= 730 else "height", muac_cm=muac, oedema=oedema), **kw)


def child(*observations, **kw):
    return Child("c1", "male", tuple(observations), **kw)


# ---------- features ----------
def test_registry_covers_seven_groups_and_has_no_forbidden_names():
    assert {s.group for s in FEATURES.values()} == set(GROUPS) and len(GROUPS) == 7
    assert all(not any(p in n for p in FORBIDDEN_PARTS) for n in FEATURE_NAMES)


def test_features_use_only_current_and_earlier_visits(children):
    for c in children[:60]:
        for i in range(len(c.observations)):
            before = build_features(c, i)
            later = tuple(replace(o, visit=replace(o.visit, weight_kg=o.visit.weight_kg * 0.5)) for o in c.observations[i + 1:])
            changed = Child(c.child_id, c.sex, c.observations[: i + 1] + later, c.demographic, c.maternal, c.socioeconomic, c.district)
            assert build_features(changed, i) == before


def test_features_ignore_identifiers_and_area(children):
    c = children[0]
    other = Child("zzz", c.sex, c.observations, c.demographic, c.maternal, c.socioeconomic, "D99")
    assert build_features(c, 0) == build_features(other, 0)


def test_longitudinal_features_hand_check():
    c = child(obs(400, 9.5, 74.0, 14.0), obs(460, 9.8, 76.0, 14.2), obs(520, 10.0, 78.0, 14.0))
    f = build_features(c, 2)
    assert f["n_prior_visits"] == 2 and f["days_since_prev"] == 60
    assert f["weight_velocity_g_day"] == pytest.approx(200 / 60)
    assert f["d_muac_cm"] == pytest.approx(-0.2)
    assert f["whz_slope_per_month_3"] is not None
    assert build_features(c, 0)["d_whz"] is None and build_features(c, 0)["n_prior_visits"] == 0


def test_missing_stays_missing_never_normal():
    f = build_features(child(obs(400, 9.5, 74.0)), 0)
    assert f["muac_cm"] is None and f["diarrhoea_2wk"] is None and f["wealth_quintile"] is None
    assert f["wash_score"] is None and f["mother_age_years"] is None


def test_oedema_withholds_weight_features():
    f = build_features(child(obs(400, 11.0, 74.0, 13.0, OedemaGrade.PLUS)), 0)
    assert f["oedema_present"] == 1.0 and f["waz"] is None and f["whz"] is None and f["haz"] is not None


def test_slope_needs_three_points():
    assert _slope([(1, 0), (2, 1)]) is None
    assert _slope([(0, 0), (1, 1), (2, 2)]) == pytest.approx(1.0)


def test_derived_flags():
    c = child(obs(400, 9.5, 74.0), demographic=Demographic(birth_weight_g=2400, gestational_age_weeks=35, birth_interval_months=20),
              maternal=Maternal(age_years=17, education="primary"),
              socioeconomic=Socioeconomic(improved_water=True, improved_sanitation=False))
    f = build_features(c, 0)
    assert (f["low_birth_weight"], f["preterm"], f["birth_interval_lt24"], f["teen_mother"]) == (1.0, 1.0, 1.0, 1.0)
    assert f["mother_education_level"] == 1.0 and f["wash_score"] == 1.0


# ---------- labels ----------
HEALTHY = (obs(400, 9.8, 76.0, 14.0))


def test_followup_in_window_gives_labels():
    c = child(HEALTHY, obs(480, 6.3, 74.0, 11.0))          # wasted and severe at 80 days
    r = label_targets(c, 0)
    assert r["future_wasting"]["label"] == 1 and r["future_sam"]["label"] == 1 and r["future_faltering"]["label"] == 1


def test_negative_label_when_followup_is_fine():
    r = label_targets(child(HEALTHY, obs(480, 10.4, 79.0, 14.2)), 0)
    assert [r[t]["label"] for t in r] == [0, 0, 0]


def test_no_followup_is_censored_not_negative():
    for c in (child(HEALTHY), child(HEALTHY, obs(410, 9.9, 76.5, 14.0)), child(HEALTHY, obs(700, 11.0, 85.0, 14.0))):
        r = label_targets(c, 0)
        assert all(v["label"] is None and v["reason"] == "no_followup_in_window" for v in r.values())


def test_window_edges_are_inclusive():
    assert label_targets(child(HEALTHY, obs(428, 10.0, 77.0, 14.0)), 0)["future_wasting"]["label"] == 0
    assert label_targets(child(HEALTHY, obs(580, 10.9, 82.0, 14.0)), 0)["future_wasting"]["label"] == 0
    assert label_targets(child(HEALTHY, obs(427, 10.0, 77.0, 14.0)), 0)["future_wasting"]["reason"] == "no_followup_in_window"


def test_already_at_outcome_excluded_but_faltering_still_labelled():
    c = child(obs(400, 7.0, 74.0, 11.0), obs(480, 7.4, 76.0, 11.8))
    r = label_targets(c, 0)
    assert r["future_wasting"]["reason"] == "already_at_outcome" and r["future_sam"]["reason"] == "already_at_outcome"
    assert r["future_faltering"]["label"] == 0


def test_muac_and_oedema_count_as_outcomes():
    assert label_targets(child(HEALTHY, obs(480, 10.0, 78.0, 12.0)), 0)["future_wasting"]["label"] == 1
    assert label_targets(child(HEALTHY, obs(480, 10.0, 78.0, 12.0)), 0)["future_sam"]["label"] == 0
    r = label_targets(child(HEALTHY, obs(480, 10.0, 78.0, 13.5, OedemaGrade.PLUS)), 0)
    assert r["future_sam"]["label"] == 1 and r["future_faltering"]["reason"] == "waz_unavailable"


def test_small_weight_drop_is_not_faltering_but_loss_is():
    assert label_targets(child(HEALTHY, obs(480, 9.75, 79.0, 14.0)), 0)["future_faltering"]["label"] == 0
    assert label_targets(child(HEALTHY, obs(480, 9.6, 79.0, 14.0)), 0)["future_faltering"]["label"] == 1


def test_unusable_followup_is_censored():
    r = label_targets(child(HEALTHY, obs(480, 40.0, 79.0, 14.0)), 0)
    assert r["future_wasting"]["reason"] == "followup_not_usable"


def test_labels_never_in_features_or_dataset_columns():
    from thanzi_screen.prediction.dataset import COLUMNS
    assert not any("future" in c or "label" in c or "outcome" in c for c in COLUMNS + FEATURE_NAMES)


def test_example_labels_match_direct_labelling(children):
    ex = build_examples(children)
    by = {c.child_id: c for c in children}
    for e in ex[:200]:
        c = by[e.child_id]
        i = next(k for k, o in enumerate(c.observations) if o.visit.age_days == e.index_age_days)
        direct = label_targets(c, i)
        assert e.labels == {t: direct[t]["label"] for t in direct}


def test_summary_reports_censoring(children):
    s = label_summary(build_examples(children))
    assert set(s) == {"future_wasting", "future_sam", "future_faltering"}
    assert s["future_wasting"]["excluded"].get("no_followup_in_window", 0) > 0
    assert all(v["positives"] > 0 and v["negatives"] > 0 for v in s.values())


# ---------- simulation ----------
def test_simulation_is_deterministic_and_seed_sensitive():
    a, b = simulate_children(SimConfig(n_children=30, seed=1)), simulate_children(SimConfig(n_children=30, seed=1))
    assert a == b and a != simulate_children(SimConfig(n_children=30, seed=2))


def test_simulation_exercises_missingness_and_every_group(children):
    ex = build_examples(children)
    for g in GROUPS:
        names = [n for n, s in FEATURES.items() if s.group == g]
        assert any(e.features[n] is not None for e in ex for n in names), g
    assert any(e.features["wealth_quintile"] is not None for e in ex)
    assert any(e.features["diarrhoea_2wk"] is None for e in ex)
    poor = [e for e in ex if e.features["wealth_quintile"] in (1.0, 2.0)]
    rich = [e for e in ex if e.features["wealth_quintile"] in (4.0, 5.0)]
    miss = lambda es: sum(e.features["mother_muac_cm"] is None for e in es) / len(es)
    assert miss(poor) > miss(rich)


# ---------- dataset ----------
def test_dataset_round_trip(children, tmp_path):
    write_dataset(children, {"provenance": "simulated"}, tmp_path)
    back, manifest = load_dataset(tmp_path / CSV_NAME, allow_simulated=True)
    assert manifest["children"] == len(children)
    by = {c.child_id: c for c in back}
    for c in children[:100]:
        assert by[c.child_id] == c


def test_loader_refuses_bad_datasets(children, tmp_path):
    write_dataset(children[:20], {"provenance": "simulated"}, tmp_path)
    p = tmp_path / CSV_NAME
    with pytest.raises(DatasetError, match="simulated"):
        load_dataset(p)
    original = p.read_text()
    p.write_text(original.replace("male", "femalee", 1))
    with pytest.raises(DatasetError, match="checksum"):
        load_dataset(p, allow_simulated=True)
    p.write_text(original)
    (tmp_path / MANIFEST_NAME).unlink()
    with pytest.raises(DatasetError, match="manifest missing"):
        load_dataset(p, allow_simulated=True)


def test_real_data_needs_governance(children, tmp_path):
    write_dataset(children[:10], {"provenance": "real"}, tmp_path)
    with pytest.raises(DatasetError, match="ethics_ref"):
        load_dataset(tmp_path / CSV_NAME)
    write_dataset(children[:10], {"provenance": "real", "ethics_ref": "E1", "data_agreement_ref": "D1",
                                  "extraction_description": "x", "period_covered": "2025", "deidentified": True}, tmp_path)
    assert len(load_dataset(tmp_path / CSV_NAME)[0]) == 10


def test_identifier_column_and_static_drift_refused(children, tmp_path):
    write_dataset(children[:10], {"provenance": "simulated"}, tmp_path)
    p = tmp_path / CSV_NAME
    lines = p.read_text().splitlines()
    lines[0] = lines[0].replace("district", "village")
    p.write_text("\n".join(lines) + "\n")
    m = json.loads((tmp_path / MANIFEST_NAME).read_text())
    import hashlib
    m["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
    (tmp_path / MANIFEST_NAME).write_text(json.dumps(m))
    with pytest.raises(DatasetError, match="identifier"):
        load_dataset(p, allow_simulated=True)


# ---------- splits and preprocessing ----------
def test_split_is_deterministic_order_free_and_by_child(children):
    ids = [c.child_id for c in children]
    a = split_children(ids, 3)
    assert a == split_children(list(reversed(ids)), 3) and a != split_children(ids, 4)
    ex = build_examples(children, seed=3)
    seen = {}
    for e in ex:
        assert seen.setdefault(e.child_id, e.split) == e.split
    share = sum(v == "train" for v in a.values()) / len(a)
    assert 0.6 < share < 0.8


def test_preprocessor_fits_on_training_only_and_flags_missing(children):
    ex = build_examples(children)
    train = [e.features for e in ex if e.split == "train"]
    pre = Preprocessor.fit(train)
    assert pre.spec["n_train_rows"] == len(train)
    other = [e.features for e in ex if e.split != "train"]
    assert Preprocessor.fit(train).to_dict() == pre.to_dict()
    assert "mother_muac_cm_missing" in pre.columns
    for e in ex[:300]:
        v = pre.transform(e.features)
        assert len(v) == len(pre.columns) and all(x == x and abs(x) < 1e6 for x in v)
    row = dict(ex[0].features, mother_muac_cm=None)
    v = pre.transform(row)
    assert v[pre.columns.index("mother_muac_cm_missing")] == 1.0
    med = pre.spec["features"]["mother_muac_cm"]
    assert v[pre.columns.index("mother_muac_cm")] == pytest.approx((med["median"] - med["mean"]) / med["scale"])
    assert other  # validation and test rows exist and were not used to fit


def test_preprocessor_json_round_trip_and_strictness(children):
    ex = build_examples(children)
    pre = Preprocessor.fit([e.features for e in ex if e.split == "train"])
    again = Preprocessor.from_dict(json.loads(json.dumps(pre.to_dict())))
    assert again.transform(ex[5].features) == pre.transform(ex[5].features)
    with pytest.raises(PreprocessError):
        pre.transform({**ex[0].features, "surprise": 1.0})
    bad = {k: v for k, v in ex[0].features.items() if k != "whz"}
    with pytest.raises(PreprocessError):
        pre.transform(bad)
    with pytest.raises(PreprocessError):
        pre.transform({**ex[0].features, "whz": float("nan")})


def test_matrix_selects_labelled_rows_of_one_split(children):
    ex = build_examples(children)
    pre = Preprocessor.fit([e.features for e in ex if e.split == "train"])
    X, y, rows = matrix(ex, "future_wasting", "val", pre)
    assert len(X) == len(y) == len(rows) and set(y) <= {0, 1}
    assert all(r.split == "val" and r.labels["future_wasting"] is not None for r in rows)


def test_gap_never_seen_in_training_is_refused_not_imputed(children):
    from thanzi_screen.prediction import UnseenMissingError
    ex = build_examples(children)
    train = [dict(e.features, age_months=e.features["age_months"]) for e in ex if e.split == "train"]
    pre = Preprocessor.fit(train)
    never = next(n for n, p in pre.spec["features"].items() if not p["indicator"])
    row = dict(ex[0].features, **{never: None})
    with pytest.raises(UnseenMissingError):
        pre.transform(row)
    assert len(pre.transform(row, strict_missing=False)) == len(pre.columns)


def test_matrix_reports_rows_it_skips(children):
    ex = build_examples(children)
    pre = Preprocessor.fit([e.features for e in ex if e.split == "train"])
    never = next(n for n, p in pre.spec["features"].items() if not p["indicator"])
    tampered = [type(e)(e.child_id, e.index_age_days, e.split, e.district, e.period, dict(e.features, **{never: None}),
                        e.labels, e.reasons) for e in ex if e.split == "val"]
    skipped = []
    X, y, rows = matrix(tampered, "future_wasting", "val", pre, skipped)
    assert X == [] and skipped and len(skipped) == len([e for e in tampered if e.labels["future_wasting"] is not None])
