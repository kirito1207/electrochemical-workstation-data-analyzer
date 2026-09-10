from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from analysis import (
    ITAnalysisSettings,
    calculate_delta_i,
    define_intervals,
    extract_plateaus,
    fit_calibration,
)


def test_interval_segmentation_uses_half_open_boundaries(synthetic_it_data, synthetic_it_protocol):
    intervals = define_intervals(synthetic_it_data, synthetic_it_protocol)

    assert [(row.interval_start_s, row.interval_end_s) for row in intervals] == [
        (1.0, 31.0),
        (31.0, 61.0),
        (61.0, 91.0),
        (91.0, 120.0),
    ]
    assert [row.end_inclusive for row in intervals] == [False, False, False, True]


def test_default_plateau_is_last_twenty_percent(synthetic_it_result):
    first = synthetic_it_result.plateaus[0]

    assert first.plateau_n_points == 6
    assert first.plateau_start_s == 25.0
    assert first.plateau_end_s == 30.0


def test_plateau_fraction_is_configurable(synthetic_it_data, synthetic_it_protocol):
    rows = extract_plateaus(
        synthetic_it_data,
        synthetic_it_protocol,
        sample_id="E1",
        plateau_fraction=0.50,
    )

    assert rows[0].plateau_n_points == 15
    assert rows[0].plateau_start_s == 16.0


def test_short_plateau_warns_without_expanding_window(synthetic_it_result):
    row = synthetic_it_result.plateaus[0]

    assert row.plateau_duration_s == 6.0
    assert row.plateau_n_points == 6
    assert "Plateau window shorter than preferred 10 s." in row.warnings


def test_plateau_mean_sd_sem_and_drift_are_calculated(synthetic_it_result):
    baseline = synthetic_it_result.plateaus[0]

    assert baseline.plateau_mean_uA == pytest.approx(2.0)
    assert baseline.plateau_sd_uA == pytest.approx(0.0, abs=1e-12)
    assert baseline.plateau_sem_uA == pytest.approx(0.0, abs=1e-12)
    assert baseline.plateau_drift_uA_per_s == pytest.approx(0.0, abs=1e-12)


def test_delta_i_uses_step_minus_baseline_not_difference_of_absolutes(synthetic_it_result):
    step = synthetic_it_result.delta_i[2]

    assert step.plateau_mean_uA == pytest.approx(-1.5)
    assert step.baseline_mean_uA == pytest.approx(2.0)
    assert step.signed_delta_I_uA == pytest.approx(-3.5)
    assert step.magnitude_delta_I_uA == pytest.approx(3.5)
    assert step.magnitude_delta_I_uA != pytest.approx(
        abs(step.plateau_mean_uA) - abs(step.baseline_mean_uA)
    )


def test_include_in_calibration_controls_selected_linear_range(synthetic_it_result):
    calibration = synthetic_it_result.calibration

    assert calibration.included_concentrations_uM == (0.0, 2.0, 7.0)
    assert calibration.n_points == 3
    assert 13.0 not in calibration.included_concentrations_uM


def test_ols_recovers_known_synthetic_slope_intercept_and_r_squared(synthetic_it_result):
    calibration = synthetic_it_result.calibration

    assert calibration.slope_uA_per_uM == pytest.approx(-0.5)
    assert calibration.intercept_uA == pytest.approx(0.0, abs=1e-12)
    assert calibration.r_squared == pytest.approx(1.0)
    assert calibration.lod_status == "LOD not calculated"


def test_plateau_drift_recovers_known_linear_slope(synthetic_it_data, synthetic_it_protocol):
    time = synthetic_it_data.time_s
    drifted = np.asarray(synthetic_it_data.current_A + time * 0.01e-6, dtype=np.float64)
    data = replace(synthetic_it_data, current_A=drifted)
    rows = extract_plateaus(
        data,
        synthetic_it_protocol,
        sample_id="E1",
        preferred_min_plateau_duration_s=0.0,
    )

    assert rows[0].plateau_drift_uA_per_s == pytest.approx(0.01)
