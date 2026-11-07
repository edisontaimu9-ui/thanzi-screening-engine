import math

import pytest

from thanzi_screen.anthro.lms import sd_value, zscore_adjusted, zscore_plain

LMS_CASES = [(0.3487, 3.3464, 0.14602), (-0.3833, 7.2402, 0.09113), (1.0, 49.8842, 0.03795), (-0.1534, 18.4968, 0.1358)]


@pytest.mark.parametrize("l,m,s", LMS_CASES)
def test_z_at_median_is_zero(l, m, s):
    assert zscore_plain(m, m, l, s) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("l,m,s", LMS_CASES)
@pytest.mark.parametrize("k", [-3, -2, -1, 1, 2, 3])
def test_roundtrip_sd_values(l, m, s, k):
    y = sd_value(m, l, s, k)
    assert zscore_plain(y, m, l, s) == pytest.approx(k, abs=1e-9)
    assert zscore_adjusted(y, m, l, s) == pytest.approx(k, abs=1e-9)


def test_l_zero_branch():
    m, s = 10.0, 0.1
    assert sd_value(m, 0, s, 2) == pytest.approx(m * math.exp(0.2))
    assert zscore_plain(m * math.exp(0.2), m, 0, s) == pytest.approx(2.0)


@pytest.mark.parametrize("l,m,s", LMS_CASES)
def test_adjusted_beyond_3_is_linear_extension(l, m, s):
    sd2, sd3 = sd_value(m, l, s, 2), sd_value(m, l, s, 3)
    y = sd3 + 0.5 * (sd3 - sd2)
    assert zscore_adjusted(y, m, l, s) == pytest.approx(3.5, abs=1e-9)
    sd2n, sd3n = sd_value(m, l, s, -2), sd_value(m, l, s, -3)
    y = sd3n - 1.25 * (sd2n - sd3n)
    assert zscore_adjusted(y, m, l, s) == pytest.approx(-4.25, abs=1e-9)


@pytest.mark.parametrize("l,m,s", LMS_CASES)
def test_adjusted_equals_plain_within_3(l, m, s):
    for k in (-2.9, -1.2, 0.4, 2.99):
        y = sd_value(m, l, s, k)
        assert zscore_adjusted(y, m, l, s) == pytest.approx(zscore_plain(y, m, l, s))


def test_rejects_bad_values():
    with pytest.raises(ValueError):
        zscore_plain(0, 1, 1, 0.1)
    with pytest.raises(ValueError):
        zscore_plain(1, 1, 1, 0)
