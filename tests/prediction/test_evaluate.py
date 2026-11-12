import math
import random

import pytest

from thanzi_screen.prediction import evaluate as ev


def test_auroc_known_values_and_ties():
    assert ev.auroc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(0.75)
    assert ev.auroc([1, 2, 3, 4], [0, 0, 1, 1]) == 1.0
    assert ev.auroc([4, 3, 2, 1], [0, 0, 1, 1]) == 0.0
    assert ev.auroc([1, 1, 1, 1], [0, 1, 0, 1]) == 0.5          # all tied: no information
    assert math.isnan(ev.auroc([0.2, 0.3], [0, 0])) and math.isnan(ev.auroc([0.2, 0.3], [1, 1]))


def test_auroc_matches_pairwise_definition():
    rng = random.Random(1)
    s = [round(rng.random(), 1) for _ in range(300)]          # rounding forces ties
    y = [int(rng.random() < 0.3) for _ in s]
    pos, neg = [a for a, b in zip(s, y) if b], [a for a, b in zip(s, y) if not b]
    pairs = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
    assert ev.auroc(s, y) == pytest.approx(pairs)


def test_auprc_hand_example_and_no_positives():
    assert ev.auprc([0.1, 0.4, 0.35, 0.8], [0, 0, 1, 1]) == pytest.approx(5 / 6)
    assert ev.auprc([0.9, 0.8, 0.1], [1, 1, 0]) == 1.0
    assert math.isnan(ev.auprc([0.5, 0.4], [0, 0]))


def test_brier():
    assert ev.brier([0.0, 1.0], [0, 1]) == 0.0
    assert ev.brier([0.5, 0.5], [0, 1]) == 0.25


def test_platt_recovers_a_known_miscalibration():
    rng = random.Random(3)
    z = [rng.gauss(0, 2) for _ in range(40000)]
    y = [int(rng.random() < ev.sigmoid(0.5 * v + 0.3)) for v in z]
    a, b = ev.fit_platt([ev.sigmoid(v) for v in z], y)
    assert a == pytest.approx(0.5, abs=0.04) and b == pytest.approx(0.3, abs=0.06)


def test_calibrated_probabilities_have_slope_one_and_intercept_zero():
    rng = random.Random(4)
    p = [rng.random() for _ in range(40000)]
    y = [int(rng.random() < q) for q in p]
    a, b = ev.fit_platt(p, y)
    assert a == pytest.approx(1.0, abs=0.06) and b == pytest.approx(0.0, abs=0.06)


def test_apply_platt_keeps_order_for_a_positive_slope_and_survives_extremes():
    p = [0.0, 1e-9, 0.2, 0.5, 0.9, 1.0]
    out = ev.apply_platt(p, 0.7, -0.4)
    assert out == sorted(out) and all(0 < v < 1 for v in out)


def test_calibration_table_covers_every_row_and_ece():
    p = [i / 100 for i in range(100)]
    y = [1 if i >= 50 else 0 for i in range(100)]
    t = ev.calibration_table(p, y, bins=10)
    assert sum(r["n"] for r in t) == 100 and len(t) == 10
    assert t[0]["observed_rate"] == 0.0 and t[-1]["observed_rate"] == 1.0
    perfect = [{"n": 10, "mean_predicted": 0.3, "observed_rate": 0.3}] * 3
    assert ev.expected_calibration_error(perfect) == 0.0


def test_alert_rate_threshold_never_exceeds_the_rate_even_with_ties():
    rng = random.Random(5)
    p = [round(rng.random(), 2) for _ in range(1000)]          # many ties
    for rate in (0.05, 0.1, 0.25):
        t = ev.threshold_for_alert_rate(p, rate)
        assert sum(v >= t for v in p) <= rate * len(p)
    assert sum(v >= ev.threshold_for_alert_rate([0.5] * 10, 0.1) for v in [0.5] * 10) == 0   # all tied: alert nobody


def test_at_threshold_counts():
    r = ev.at_threshold([0.9, 0.8, 0.3, 0.2, 0.1], [1, 0, 1, 0, 0], 0.5)
    assert (r["tp"], r["fp"], r["fn"], r["tn"]) == (1, 1, 1, 2)
    assert r["sensitivity"] == 0.5 and r["ppv"] == 0.5 and r["alert_rate"] == 0.4 and r["specificity"] == pytest.approx(2 / 3)


def test_net_benefit_hand_calculation():
    # 10 children, 4 events; at pt 0.2 alert on 5 with 3 true: 3/10 - 2/10 * 0.25
    p = [0.9, 0.8, 0.7, 0.3, 0.25] + [0.1] * 5
    y = [1, 1, 1, 0, 0, 1, 0, 0, 0, 0]
    assert ev.net_benefit(p, y, 0.2) == pytest.approx(3 / 10 - 2 / 10 * 0.25)


def test_resamples_keep_children_whole_and_are_reproducible():
    groups = ["a"] * 3 + ["b"] * 1 + ["c"] * 5
    rs = ev.resamples(groups, 50, seed=9)
    assert rs == ev.resamples(groups, 50, seed=9) and rs != ev.resamples(groups, 50, seed=10)
    for idx in rs:
        counts = {g: sum(groups[i] == g for i in idx) for g in "abc"}
        assert counts["a"] % 3 == 0 and counts["c"] % 5 == 0          # a child is drawn with all of its rows


def test_cluster_interval_is_wider_than_a_row_interval_when_rows_cluster():
    rng = random.Random(6)
    groups, p, y = [], [], []
    for c in range(150):
        base = rng.gauss(0, 1)
        for _ in range(8):                                          # 8 near-identical rows per child
            groups.append(c)
            p.append(ev.sigmoid(base + rng.gauss(0, 0.1)))
            y.append(int(rng.random() < ev.sigmoid(base)))
    lo_c, hi_c = ev.ci_from(ev.auroc, p, y, ev.resamples(groups, 150, 0))
    lo_r, hi_r = ev.ci_from(ev.auroc, p, y, ev.resamples(list(range(len(y))), 150, 0))
    assert (hi_c - lo_c) > (hi_r - lo_r)


def test_paired_difference_of_a_model_with_itself_is_zero():
    rng = random.Random(7)
    p = [rng.random() for _ in range(400)]
    y = [int(rng.random() < q) for q in p]
    d, lo, hi = ev.paired_diff_ci(ev.auroc, p, p, y, ev.resamples(list(range(400)), 40, 0))
    assert d == 0.0 and lo == 0.0 and hi == 0.0


def test_subgroup_table_marks_small_groups():
    groups = ["big"] * 100 + ["tiny"] * 10
    rng = random.Random(8)
    p = [rng.random() for _ in groups]
    y = [int(rng.random() < 0.4) for _ in groups]
    rows = {r["group"]: r for r in ev.subgroup_table(groups, p, y, 0.5)}
    assert rows["tiny"]["small"] and not rows["big"]["small"] and rows["big"]["n"] == 100
