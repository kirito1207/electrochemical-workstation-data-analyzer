from __future__ import annotations

import csv
from dataclasses import replace
from inspect import getsource
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from analysis import (ContinuousInterruption, ContinuousStabilitySettings,
                      EventAnalysisError, ITEventInput, InterruptionType,
                      analyze_continuous_record, analyze_it_continuous_batch,
                      validate_interruption_set)
from chi_gui.it_workflow import ITWorkflowState, execute_it_analysis
from chi_gui.lsv_workflow import LSVWorkflowState, MetadataDraftRow
from chi_gui.state import FileRecord, FileStatus
from chi_gui.widgets.lsv_analysis import LSVSettingsPanel
from export.it_events import export_it_event_csv_bundle
from plotting.it_events import (build_it_drift_figure, build_it_event_figure,
                                build_it_retention_figure)


def _linear_data(base, *, name="linear.bin", slope_uA_s=0.1, intercept_uA=2.0,
                 end=120):
    time = np.arange(1.0, float(end) + 1.0)
    current = (intercept_uA + slope_uA_s * time) * 1e-6
    return replace(base, file_name=name, n_points=len(time), actual_first_time_s=float(time[0]),
                   actual_last_time_s=float(time[-1]), actual_recorded_duration_s=float(time[-1]-time[0]),
                   time_s=time, current_A=np.asarray(current, dtype=float), warnings=())


def _settings():
    return ContinuousStabilitySettings(1, 120, 1, 10, 111, 120)


def _record(data, key="r1"):
    return FileRecord(Path(data.file_name), FileStatus.PARSED, "i-t", "i-t", data)


def test_continuous_means_changes_retention_and_ols_are_exact(synthetic_it_data):
    data = _linear_data(synthetic_it_data)
    result, segments = analyze_continuous_record(data, sample_id="S1", group="A", settings=_settings())
    early = np.mean(data.current_A[:10]); late = np.mean(data.current_A[-10:])
    assert result.early_mean_A == pytest.approx(early)
    assert result.early_sd_A == pytest.approx(np.std(data.current_A[:10], ddof=1))
    assert result.late_mean_A == pytest.approx(late)
    assert result.late_sd_A == pytest.approx(np.std(data.current_A[-10:], ddof=1))
    assert result.delta_current_A == pytest.approx(late - early)
    assert result.delta_magnitude_A == pytest.approx(abs(late) - abs(early))
    assert result.retention_magnitude_pct == pytest.approx(abs(late) / abs(early) * 100)
    assert result.drift_slope_A_per_s == pytest.approx(0.1e-6)
    assert result.drift_intercept_A == pytest.approx(2e-6)
    assert result.drift_r_squared == pytest.approx(1.0)
    assert result.drift_n == 120 and result.qc_status == "Complete"
    assert len(segments) == 1 and segments[0].slope_A_per_s == pytest.approx(0.1e-6)


def test_insufficient_windows_and_near_zero_reference_are_unavailable(synthetic_it_data):
    data = _linear_data(synthetic_it_data, intercept_uA=-0.55, slope_uA_s=0.1)
    settings = ContinuousStabilitySettings(1, 120, 0, 1, 111, 120)
    row, _ = analyze_continuous_record(data, sample_id="S", settings=settings)
    assert row.early_mean_A is None and row.retention_magnitude_pct is None
    assert any("Early window unavailable" in warning for warning in row.warnings)
    zero_settings = ContinuousStabilitySettings(1, 120, 5, 6, 111, 120)
    zero_row, _ = analyze_continuous_record(data, sample_id="S", settings=zero_settings)
    assert zero_row.early_mean_A == pytest.approx(0.0, abs=1e-18)
    assert zero_row.retention_magnitude_pct is None
    assert any("too close to zero" in warning for warning in zero_row.warnings)


def test_interruption_validation_rejects_bad_and_overlapping_intervals():
    with pytest.raises(EventAnalysisError, match="less than"):
        ContinuousInterruption("x", 4, 2).validate()
    rows = (ContinuousInterruption("a", 2, 4), ContinuousInterruption("b", 3, 5))
    with pytest.raises(EventAnalysisError, match="Overlapping"):
        validate_interruption_set(rows)
    with pytest.raises(EventAnalysisError, match="inside"):
        validate_interruption_set((ContinuousInterruption("a", 0, 2),),
                                  record_start_s=1, record_end_s=10)


def test_interruption_preserves_raw_arrays_builds_segments_and_blocks_overall_slope(synthetic_it_data):
    data = _linear_data(synthetic_it_data)
    raw_time = data.time_s.copy(); raw_current = data.current_A.copy()
    gap = ContinuousInterruption("gap", 40, 50, InterruptionType.ACQUISITION_ERROR, "known")
    row, segments = analyze_continuous_record(data, sample_id="S", settings=_settings(), interruptions=(gap,))
    assert np.array_equal(data.time_s, raw_time) and np.array_equal(data.current_A, raw_current)
    assert [item.segment_id for item in segments] == ["segment_1", "segment_2"]
    assert all(item.slope_A_per_s == pytest.approx(0.1e-6) for item in segments)
    assert row.drift_slope_A_per_s is None and row.drift_n == 0
    assert row.retention_magnitude_pct is not None
    assert row.retention_continuity == "interrupted"
    assert any("before/after" in warning for warning in row.warnings)


@pytest.mark.parametrize("which", ("early", "late"))
def test_window_overlapping_interruption_is_not_partially_recomputed(synthetic_it_data, which):
    data = _linear_data(synthetic_it_data)
    gap = ContinuousInterruption("gap", 5 if which == "early" else 115,
                                 8 if which == "early" else 118)
    row, _ = analyze_continuous_record(data, sample_id="S", settings=_settings(), interruptions=(gap,))
    assert getattr(row, f"{which}_mean_A") is None
    assert row.retention_magnitude_pct is None
    assert "Window overlap" in row.qc_status


def test_short_record_is_partial_without_failing_batch(synthetic_it_data):
    long = _linear_data(synthetic_it_data, name="long.bin")
    short = _linear_data(synthetic_it_data, name="short.bin", end=60)
    result = analyze_it_continuous_batch(
        (ITEventInput(long, "L", "A"), ITEventInput(short, "S", "A")), settings=_settings()
    )
    by_id = {row.sample_id: row for row in result.stability_records}
    assert by_id["L"].retention_magnitude_pct is not None
    assert by_id["S"].retention_magnitude_pct is None
    assert "Partial" in by_id["S"].qc_status


def test_group_summaries_cover_all_stability_metrics(synthetic_it_data):
    inputs = tuple(ITEventInput(_linear_data(synthetic_it_data, name=f"{i}.bin",
                                             slope_uA_s=0.05 + i * 0.01),
                                f"S{i}", "A" if i < 2 else "B") for i in range(4))
    result = analyze_it_continuous_batch(inputs, settings=_settings())
    assert {(row.group, row.metric) for row in result.stability_group_summaries} == {
        (group, metric) for group in ("A", "B") for metric in
        ("Retention magnitude", "Drift slope", "Early current", "Late current")
    }
    assert all(row.n == 2 for row in result.stability_group_summaries)


def test_workflow_interruption_add_edit_delete_stale_and_workspace_isolation(synthetic_it_data):
    data = _linear_data(synthetic_it_data)
    records = (_record(data),)
    first = ITWorkflowState(); first.sync_records(records)
    key = records[0].key
    first.update_metadata(key, "group", "A"); first.confirm_metadata()
    first.set_continuous_settings(_settings())
    interval = first.add_interruption(key, start_s=40, end_s=50,
                                      interruption_type=InterruptionType.MANUAL_PAUSE, reason="pause")
    first.edit_interruption(key, interval.interval_id, start_s=41, end_s=51,
                            interruption_type=InterruptionType.CONNECTION_ISSUE, reason="cable")
    assert first.current_interruptions[0].reason == "cable"
    with pytest.raises(EventAnalysisError, match="Overlapping"):
        first.add_interruption(key, start_s=45, end_s=55)
    request = first.build_request(records); first.accept_result(request, execute_it_analysis(request))
    first.delete_interruptions(key, (interval.interval_id,))
    assert first.result_stale and first.current_interruptions == ()
    second = ITWorkflowState(); second.sync_records(records)
    assert second.continuous_interruptions == {} and second.continuous_settings != _settings()


def test_raw_timeline_spans_and_reference_lines_are_present(synthetic_it_data):
    data = _linear_data(synthetic_it_data)
    gap = ContinuousInterruption("gap", 40, 50)
    result = analyze_it_continuous_batch((ITEventInput(data, "S", "A"),), settings=_settings(),
                                         interruptions_by_sample={"S": (gap,)})
    raw = build_it_event_figure(result); retention = build_it_retention_figure(result); drift = build_it_drift_figure(result)
    try:
        assert len(raw.axes[0].patches) >= 4  # analysis, early, late, interruption
        assert np.allclose(retention.axes[0].lines[-1].get_ydata(), 100)
        assert np.allclose(drift.axes[0].lines[-1].get_ydata(), 0)
    finally:
        plt.close(raw); plt.close(retention); plt.close(drift)


def test_continuous_exports_scientific_values_qc_and_provenance(tmp_path, synthetic_it_data):
    data = _linear_data(synthetic_it_data)
    gap = ContinuousInterruption("gap", 40, 50, InterruptionType.OTHER, "operator note")
    result = analyze_it_continuous_batch((ITEventInput(data, "S", "A"),), settings=_settings(),
                                         interruptions_by_sample={"S": (gap,)})
    paths = export_it_event_csv_bundle(result, tmp_path)
    assert {path.name for path in paths} >= {"continuous_stability.csv", "continuous_segments.csv",
                                             "continuous_group_summary.csv", "interruptions.csv"}
    with (tmp_path / "continuous_stability.csv").open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert float(row["early_window_start_s"]) == 1
    assert row["retention_continuity"] == "interrupted" and "operator note" in row["interruptions"]


def test_lsv_batch_include_exclude_is_additive_and_keeps_existing_controls():
    source = getsource(LSVSettingsPanel.__init__)
    assert 'text="纳入"' in source and 'text="不纳入"' in source
    assert 'text="设置 Group"' in source and 'text="设置电极类型"' in source
    workflow = LSVWorkflowState()
    workflow.metadata_rows = [MetadataDraftRow(key, f"{key}.bin", f"{key}.bin", f"{key}.bin",
                                                sample_id=key, group="A")
                              for key in ("a", "b", "c")]
    workflow.batch_update(("a", "c"), "include", False)
    assert [row.include for row in workflow.metadata_rows] == [False, True, False]


def test_event_core_and_parser_are_not_changed_by_stability_module():
    event_text = Path("src/analysis/it_events.py").read_text(encoding="utf-8").lower()
    parser_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                            for path in Path("src/chi_parser").glob("*.py")).lower()
    for forbidden in ("detrend", "exponential", "t90", "time-to-peak", "shared-k"):
        assert forbidden not in event_text
        assert forbidden not in parser_text
