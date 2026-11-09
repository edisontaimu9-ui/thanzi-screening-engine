"""Growth monitoring: weight-gain velocity against the ASPEN reference (R19, I59). Synthetic inputs only."""
import ast
import json
import random
from pathlib import Path

import pytest

from thanzi_screen.anthro import engine as anthro_engine
from thanzi_screen.growth import MIN_INTERVAL_DAYS, assess_weight_velocity as assess
from thanzi_screen.growth import velocity as V

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "thanzi_screen"
M = V.DAYS_PER_MONTH

# An independent copy of the table as read from the screenshot (weight g/day): (from, to, girls, boys).
SCREENSHOT = [
    (0, 1, (22, 42), (24, 48)), (1, 2, (24, 43), (30, 51)), (2, 3, (16, 23), (19, 36)), (3, 6, (17, 25), (13, 23)),
    (6, 9, (6, 15), (7, 15)), (9, 12, (4, 12), (4, 12)), (12, 18, (4, 10), (4, 10)), (18, 24, (4, 10), (4, 9)),
    (24, 48, (3.5, 5), (3.5, 5)), (48, 84, (4.5, 6.5), (4.5, 6.5)),
]


# ---- the reference file ----
def test_reference_matches_the_transcription_and_is_marked_verified_with_one_derived_range():
    ref = V._reference()
    assert ref["reference_id"] == "R19" and "Checked against the handbook" in ref["provenance"]
    assert "NOT checked" not in ref["provenance"] and "derived" in ref["provenance"]
    got = [(b["from_months"], b["to_months"], tuple(b["girls"]) if b["girls"] else None, tuple(b["boys"])) for b in ref["bands"]]
    assert got == SCREENSHOT


def test_bands_are_contiguous_and_ranges_are_proper():
    bands = V._reference()["bands"]
    assert bands[0]["from_months"] == 0 and bands[-1]["to_months"] >= 60
    assert all(a["to_months"] == b["from_months"] for a, b in zip(bands, bands[1:]))
    for b in bands:
        for key in ("girls", "boys"):
            if b[key] is not None:
                assert 0 < b[key][0] < b[key][1]


def test_girls_three_to_six_months_is_derived_from_21_with_the_neighbouring_half_widths():
    bands = {b["from_months"]: b for b in V._reference()["bands"]}
    g = bands[3]
    assert g["girls_derived"] is True and "21-21" in g["girls_note"] and "boys_derived" not in g
    half = lambda r: (r[1] - r[0]) / 2
    expected_half = (half(bands[2]["girls"]) + half(bands[6]["girls"])) / 2          # 3.5 and 4.5 -> 4.0
    assert expected_half == 4.0 and g["girls"] == [21 - expected_half, 21 + expected_half]
    assert sum(1 for b in bands.values() if b.get("girls_derived") or b.get("boys_derived")) == 1


def test_plausibility_limits_equal_the_engines():
    assert V.WFA_PLAUSIBLE == anthro_engine._PLAUSIBLE["wfa"]
    assert V.DAYS_PER_MONTH == anthro_engine.DAYS_PER_MONTH and V.MAX_AGE_DAYS == anthro_engine.MAX_AGE_DAYS


# ---- the comparison ----
def test_within_below_and_above_a_single_band():
    # boy, 9 to 10 months, range 4 to 12 g/day, 31 days
    ok = assess("male", 274, 8.5, 305, 8.8)
    assert (ok.assessed, ok.status, ok.flagged, ok.messages) == (True, "within_range", False, ())
    assert (ok.reference_low, ok.reference_high, ok.interval_days) == (4.0, 12.0, 31)
    low = assess("male", 274, 8.5, 305, 8.55)
    assert low.status == "below_range" and low.flagged and not low.weight_loss and "faltering" in low.messages[0]
    high = assess("male", 274, 8.5, 305, 9.0)
    assert high.status == "above_range" and not high.flagged and high.messages == ()


def test_the_range_ends_are_inside_the_range():
    days = 30
    lo = assess("male", 274, 8.0, 274 + days, 8.0 + 4.0 * days / 1000)
    hi = assess("male", 274, 8.0, 274 + days, 8.0 + 12.0 * days / 1000)
    assert lo.status == "within_range" and hi.status == "within_range"
    just = assess("male", 274, 8.0, 274 + days, 8.0 + 3.9 * days / 1000)
    assert just.status == "below_range"


def test_weight_loss_is_flagged_with_its_own_message():
    g = assess("female", 400, 9.0, 440, 8.8)
    assert g.status == "below_range" and g.flagged and g.weight_loss and g.weight_change_g == -200.0
    assert g.messages == (V.MESSAGES["weight_loss"],)


def test_unchanged_weight_is_below_range_but_not_called_loss():
    g = assess("female", 400, 9.0, 440, 9.0)
    assert g.flagged and not g.weight_loss and g.rate_g_per_day == 0.0


def _expected(sex, a, b):
    """Independent time-weighted range from the transcription above."""
    low = high = 0.0
    for lo_m, hi_m, girls, boys in SCREENSHOT:
        days = min(hi_m * M, b) - max(lo_m * M, a)
        if days > 0:
            rng = boys if sex == "male" else girls
            low, high = low + rng[0] * days, high + rng[1] * days
    return low / (b - a), high / (b - a)


@pytest.mark.parametrize("sex,a,b", [("male", 60, 100), ("male", 30, 400), ("female", 22 * 30, 26 * 30),
                                     ("male", 330, 380), ("female", 700, 800), ("male", 1700, 1800)])
def test_the_range_is_the_time_weighted_blend_of_the_bands(sex, a, b):
    g = assess(sex, a, 5.0 if a < 400 else 10.0, b, 6.0 if a < 400 else 11.0)
    lo, hi = _expected(sex, a, b)
    assert g.assessed and g.reference_low == pytest.approx(lo, abs=0.01) and g.reference_high == pytest.approx(hi, abs=0.01)


def test_the_blend_across_one_edge_by_hand():
    # boy, day 60 to day 100: 0.875 days in 1-2 months (30-51), 30.4375 days in 2-3 (19-36), 8.6875 days in 3-6 (13-23)
    low = (30 * 0.875 + 19 * 30.4375 + 13 * 8.6875) / 40
    g = assess("male", 60, 4.8, 100, 5.9)
    assert g.reference_low == pytest.approx(low, abs=0.01)


def test_from_two_years_the_reference_is_not_split_by_sex():
    a, b = assess("male", 900, 12.0, 960, 12.3), assess("female", 900, 12.0, 960, 12.3)
    assert (a.status, a.reference_low, a.reference_high) == (b.status, b.reference_low, b.reference_high)


def test_boys_and_girls_differ_where_the_source_differs():
    boy, girl = assess("male", 20, 3.6, 50, 4.6), assess("female", 20, 3.6, 50, 4.6)
    assert boy.reference_low != girl.reference_low


# ---- not assessed ----
def test_girls_three_to_six_months_use_the_derived_range_and_say_so():
    for start, end in ((100, 140), (80, 120), (170, 200)):       # inside, and crossing in from the 2-3 month band
        g = assess("female", start, 5.5, end, 6.2)
        assert g.assessed and g.reference_derived
    inside = assess("female", 100, 5.5, 140, 5.6)                # 100 g in 40 days = 2.5 g/day, below 17
    assert inside.status == "below_range" and inside.flagged and (inside.reference_low, inside.reference_high) == (17.0, 25.0)
    assert V.MESSAGES["derived_reference"] in inside.messages
    fine = assess("female", 100, 5.5, 140, 6.3)                  # 800 g in 40 days = 20 g/day
    assert fine.status == "within_range" and not fine.messages and fine.reference_derived
    assert not assess("male", 100, 5.5, 140, 6.2).reference_derived and not assess("female", 200, 6.5, 240, 6.8).reference_derived


def test_a_range_marked_unusable_is_still_not_assessed(monkeypatch):
    ref = json.loads(json.dumps(V._reference()))
    next(b for b in ref["bands"] if b["from_months"] == 3)["girls"] = None
    monkeypatch.setattr(V, "_reference", lambda: ref)
    g = assess("female", 100, 5.5, 140, 6.2)
    assert not g.assessed and g.reason == "reference_unverified" and g.status is None and not g.flagged


def test_minimum_interval_boundary():
    assert MIN_INTERVAL_DAYS == 28
    short = assess("male", 274, 8.5, 274 + 27, 8.7)
    assert not short.assessed and short.reason == "interval_too_short" and "4 weeks" in short.messages[0]
    assert assess("male", 274, 8.5, 274 + 28, 8.7).assessed


def test_implausible_weights_are_not_assessed_not_flagged():
    for prev, cur in ((85.0, 8.8), (8.5, 88.0), (0.5, 8.8)):
        g = assess("male", 274, prev, 305, cur)
        assert not g.assessed and g.reason == "implausible_weight" and not g.flagged


def test_beyond_the_engines_ages_is_not_assessed():
    g = assess("male", 1800, 16.0, 1900, 16.3)
    assert not g.assessed and g.reason == "outside_reference_ages"


def test_an_interval_ending_at_the_last_engine_day_is_assessed():
    assert assess("male", 1800, 16.0, 1856, 16.3).assessed


@pytest.mark.parametrize("args", [
    ("other", 10, 3.0, 50, 4.0), ("male", 50, 3.0, 50, 4.0), ("male", 60, 3.0, 50, 4.0), ("male", -1, 3.0, 50, 4.0),
    ("male", 10, 0.0, 50, 4.0), ("male", 10, -3.0, 50, 4.0), ("male", 10, 3.0, 50, float("nan")),
    ("male", 10, 3.0, 50, float("inf")), ("male", True, 3.0, 50, 4.0), ("male", 10, 3.0, 50.0, 4.0),
    ("male", 10, "3.0", 50, 4.0), ("male", 10, True, 50, 4.0),
])
def test_input_that_is_not_an_interval_raises(args):
    with pytest.raises(ValueError):
        assess(*args)


def test_invariants_over_random_inputs():
    rng = random.Random(7)
    for _ in range(3000):
        sex = rng.choice(("male", "female"))
        a = rng.randint(0, 1700)
        b = a + rng.randint(1, 200)
        w1 = rng.uniform(2.0, 18.0)
        w2 = w1 + rng.uniform(-1.0, 3.0)
        if w2 <= 0:
            continue
        g = assess(sex, a, w1, b, w2)
        assert g.assessed == (g.reason is None) and g.interval_days == b - a
        assert g.flagged == (g.status == "below_range")
        if g.assessed:
            assert g.reference_low < g.reference_high and g.weight_loss == (w2 < w1)
            base = ((V.MESSAGES["weight_loss"],) if g.weight_loss else (V.MESSAGES["below_range"],) if g.flagged else ())
            assert g.messages == (base + (V.MESSAGES["derived_reference"],) if base and g.reference_derived else base)
        else:
            assert g.status is None and not g.flagged and g.messages


def test_result_is_advisory_and_cites_the_reference():
    g = assess("male", 274, 8.5, 305, 8.55)
    assert g.reference == "R19" and "does not change the classification" in g.advisory


# ---- isolation ----
def _imports(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            for n in node.names:
                yield 0, n.name
        elif isinstance(node, ast.ImportFrom):
            yield node.level, node.module or ""


def test_growth_uses_only_the_standard_library_and_the_anthro_tables():
    import sys
    std = set(sys.stdlib_module_names)
    for path in (SRC / "growth").glob("*.py"):
        for level, module in _imports(path):
            if level == 0:
                assert module.split(".")[0] in std, (path.name, module)
            elif level == 2:
                assert module.split(".")[0] == "anthro", (path.name, module)
            else:
                assert level == 1, (path.name, module)


def test_only_the_api_service_imports_growth():
    offenders = []
    for path in SRC.rglob("*.py"):
        if (SRC / "growth") in path.parents:
            continue
        for level, module in _imports(path):
            if module.split(".")[0] == "growth" and level >= 1 or module.startswith("thanzi_screen.growth"):
                offenders.append(str(path.relative_to(SRC)))
    assert set(offenders) == {"api/service.py"}, offenders


def test_reference_file_ships_with_the_package():
    cfg = (ROOT / "pyproject.toml").read_text()
    assert '"thanzi_screen.growth" = ["aspen_weight_velocity.json"]' in cfg
    assert json.loads((SRC / "growth" / "aspen_weight_velocity.json").read_text())["reference_id"] == "R19"
