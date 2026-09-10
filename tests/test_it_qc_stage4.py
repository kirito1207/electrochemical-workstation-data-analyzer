from __future__ import annotations

import hashlib
from dataclasses import replace

import numpy as np
import pytest

from analysis import (
    ITAnalysisInput,
    ITAnalysisSettings,
    StepDefinition,
    StepProtocol,
    analyze_it_batch,
    evaluate_delta_direction,
    flag_delta_outliers,
    suggest_addition_times,
)


def test_multi_electrode_summary_mean_sd_sem_cv(synthetic_it_batch_result):
    row = next(
        item for item in synthetic_it_batch_result.concentration_summary
        if item.concentration_uM == 7.0
    )

    assert row.n == 3
    assert row.mean_signed_delta_I_uA == pytest.approx(-3.5)
    assert row.sd_signed_delta_I_uA == pytest.approx(0.35)
    assert row.sem_signed_delta_I_uA == pytest.approx(0.35 / np.sqrt(3))
    assert row.cv_signed_percent == pytest.approx(10.0)


def test_mixed_delta_direction_warns_in_magnitude_mode(synthetic_it_result):
    base = synthetic_it_result.delta_i[1]
    rows = (
        replace(base, source_file="a.bin", sample_id="A", signed_delta_I_A=-1e-6, signed_delta_I_uA=-1.0, magnitude_delta_I_uA=1.0),
        replace(base, source_file="b.bin", sample_id="B", signed_delta_I_A=2e-6, signed_delta_I_uA=2.0, magnitude_delta_I_uA=2.0),
    )

    qc = evaluate_delta_direction(rows, analysis_metric="magnitude")

    assert qc[0].negative_count == 1
    assert qc[0].positive_count == 1
    assert not qc[0].direction_consistent
    assert qc[0].warning == "Absolute ΔI may conceal mixed response directions."


def test_mad_outlier_is_flagged_without_deleting_electrodes(synthetic_it_result):
    base = synthetic_it_result.delta_i[1]
    values = [-1.0] * 12 + [-9.0]
    rows = tuple(
        replace(
            base,
            source_file=f"e{index}.bin",
            sample_id=f"E{index}",
            signed_delta_I_A=value * 1e-6,
            signed_delta_I_uA=value,
            magnitude_delta_I_uA=abs(value),
        )
        for index, value in enumerate(values)
    )

    flags = flag_delta_outliers(rows, analysis_metric="magnitude")

    assert len(rows) == 13
    assert len(flags) == 1
    assert flags[0].sample_id == "E12"
    assert flags[0].status == "Possible outlier"


def test_addition_time_suggestions_are_unconfirmed_and_do_not_modify_data(synthetic_it_data):
    before = synthetic_it_data.current_A.copy()
    suggestions = suggest_addition_times(
        synthetic_it_data,
        comparison_window_s=3.0,
        minimum_separation_s=20.0,
        threshold_robust_z=1.5,
    )

    times = [item.candidate_time_s for item in suggestions]
    assert all(any(abs(time - expected) <= 2.0 for time in times) for expected in (31.0, 61.0, 91.0))
    assert all(item.status == "Suggested only / 未确认" for item in suggestions)
    assert all(item.concentration_uM is None for item in suggestions)
    np.testing.assert_array_equal(synthetic_it_data.current_A, before)


def test_bad_file_does_not_stop_later_files_and_source_is_unchanged(tmp_path, it_path):
    protocol = StepProtocol(
        user_confirmed=True,
        source="test",
        steps=(
            StepDefinition("baseline", 0.0, 0.1, True),
            StepDefinition("step", 3.0, 100.0, True),
        ),
    )
    missing = tmp_path / "missing.bin"
    inputs = (
        ITAnalysisInput(it_path, "E1", protocol),
        ITAnalysisInput(missing, "BROKEN", protocol),
        ITAnalysisInput(it_path, "E2", protocol),
    )
    before = hashlib.sha256(it_path.read_bytes()).hexdigest()

    result = analyze_it_batch(inputs, settings=ITAnalysisSettings(analysis_metric="signed"))

    after = hashlib.sha256(it_path.read_bytes()).hexdigest()
    assert len(result.files) == 2
    assert [item.sample_id for item in result.files] == ["E1", "E2"]
    assert len(result.errors) == 1
    assert result.errors[0].exception_type == "FileNotFoundError"
    assert before == after
