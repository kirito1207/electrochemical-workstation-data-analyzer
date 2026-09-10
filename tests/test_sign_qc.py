from __future__ import annotations

import numpy as np

from analysis import MIXED_SIGN_WARNING, evaluate_current_signs


def _qc(values, *, metric="magnitude"):
    return evaluate_current_signs(
        values,
        group="A",
        target_potential_V=0.0,
        analysis_metric=metric,
        zero_tolerance_A=1e-12,
    )


def test_all_negative_currents_are_sign_consistent():
    qc = _qc([-1e-6, -2e-6, -3e-6])

    assert (qc.negative_count, qc.positive_count, qc.near_zero_count) == (3, 0, 0)
    assert qc.sign_consistent
    assert qc.warning == ""


def test_all_positive_currents_are_sign_consistent():
    qc = _qc([1e-6, 2e-6, 3e-6])

    assert (qc.negative_count, qc.positive_count, qc.near_zero_count) == (0, 3, 0)
    assert qc.sign_consistent
    assert qc.warning == ""


def test_mixed_signs_produce_warning():
    qc = _qc([-1e-6, 2e-6, 0.5e-12])

    assert (qc.negative_count, qc.positive_count, qc.near_zero_count) == (1, 1, 1)
    assert not qc.sign_consistent
    assert qc.warning == MIXED_SIGN_WARNING


def test_magnitude_mode_does_not_hide_mixed_sign_warning():
    qc = _qc([-1e-6, 2e-6], metric="magnitude")

    assert not qc.sign_consistent
    assert "Absolute magnitude may conceal" in qc.warning


def test_signed_mode_preserves_direction_without_magnitude_warning():
    qc = _qc([-1e-6, 2e-6], metric="signed")

    assert (qc.negative_count, qc.positive_count) == (1, 1)
    assert not qc.sign_consistent
    assert qc.warning == ""


def test_sign_qc_does_not_delete_samples():
    currents = [-1e-6, 2e-6, 0.0]
    _qc(currents)

    assert len(currents) == 3


def test_sign_qc_does_not_modify_original_currents():
    currents = np.asarray([-1e-6, 2e-6, 0.0], dtype=np.float64)
    before = currents.copy()
    _qc(currents)

    np.testing.assert_array_equal(currents, before)


def test_analysis_records_group_and_all_material_sign_qc(synthetic_analysis_result):
    rows = synthetic_analysis_result.current_sign_qc

    assert [row.group for row in rows] == ["A", "B", "C", "ALL"]
    assert [row.total_count for row in rows] == [13, 13, 13, 39]
