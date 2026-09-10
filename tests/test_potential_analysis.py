from __future__ import annotations

import numpy as np
import pytest

from analysis import PotentialOutOfRangeError, extract_current_at_potential
from chi_parser import parse_lsv


def test_zero_volt_uses_float_tolerance_without_interpolation(lsv_path):
    data = parse_lsv(lsv_path)
    selected = extract_current_at_potential(data, 0.0)

    assert selected.target_potential_V == 0.0
    assert not selected.interpolated
    assert selected.lower_potential_V == selected.upper_potential_V


def test_custom_negative_potential_is_not_hardcoded(lsv_path):
    selected = extract_current_at_potential(parse_lsv(lsv_path), -0.050)

    assert selected.target_potential_V == -0.050
    assert not selected.interpolated


def test_non_grid_potential_uses_two_point_linear_interpolation(lsv_path):
    data = parse_lsv(lsv_path)
    selected = extract_current_at_potential(data, 0.0255)
    lower_index = int(np.searchsorted(data.potential_V, 0.0255) - 1)
    upper_index = lower_index + 1
    expected = np.interp(
        0.0255,
        data.potential_V[[lower_index, upper_index]],
        data.current_A[[lower_index, upper_index]],
    )

    assert selected.interpolated
    assert selected.lower_potential_V < 0.0255 < selected.upper_potential_V
    assert selected.current_A == pytest.approx(expected)


def test_target_outside_scan_range_refuses_extrapolation(lsv_path):
    with pytest.raises(PotentialOutOfRangeError, match="extrapolation is not allowed"):
        extract_current_at_potential(parse_lsv(lsv_path), 0.250)


def test_signed_and_magnitude_are_both_preserved(lsv_path):
    selected = extract_current_at_potential(parse_lsv(lsv_path), 0.0)

    assert selected.current_uA == selected.current_A * 1e6
    assert selected.response_magnitude_uA == abs(selected.current_uA)
