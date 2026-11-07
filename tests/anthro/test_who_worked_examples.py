"""Worked examples printed in WHO Child Growth Standards: Methods and Development
(2006), Chapter 7, pp. 302-304 (register R6). Independent of the supplied tables.
Printed values are rounded, hence the tolerances.
"""
import pytest

from thanzi_screen.anthro.lms import sd_value, zscore_adjusted, zscore_plain

# (label, y, L, M, S, plain z, adjusted z)
CASES = [
    ("Child 1: 44-month boy, BMI 20.5", 20.5, -0.3067, 15.4013, 0.08115, 3.37, 3.40),
    ("Child 2: 28-month boy, BMI 12.0", 12.0, -0.4850, 15.8667, 0.07818, -3.83, -3.76),
]


@pytest.mark.parametrize("label,y,l,m,s,plain,adjusted", CASES)
def test_who_chapter7_examples(label, y, l, m, s, plain, adjusted):
    assert zscore_plain(y, m, l, s) == pytest.approx(plain, abs=0.01)
    assert zscore_adjusted(y, m, l, s) == pytest.approx(adjusted, abs=0.02)


def test_who_chapter7_intermediate_cutoffs():
    assert sd_value(15.4013, -0.3067, 0.08115, 3) == pytest.approx(19.84, abs=0.01)
    assert sd_value(15.4013, -0.3067, 0.08115, 2) == pytest.approx(18.19, abs=0.01)
    assert sd_value(15.8667, -0.4850, 0.07818, -2) == pytest.approx(13.65, abs=0.01)
    assert sd_value(15.8667, -0.4850, 0.07818, -3) == pytest.approx(12.71, abs=0.01)


def test_who_chapter7_child3_in_range_is_unadjusted():
    # LMS z = 2.37, between -3 and 3: final z equals the LMS z-score
    z = zscore_adjusted(18.8, 15.2759, -0.4488, 0.08380)
    assert z == pytest.approx(2.37, abs=0.01)
    assert z == pytest.approx(zscore_plain(18.8, 15.2759, -0.4488, 0.08380))
