from __future__ import annotations

from dataclasses import replace
from inspect import getsource
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from chi_gui.it_export import export_it_result
from chi_gui.it_workflow import (ITWorkflowState, calibration_display_rows,
                                 execute_it_analysis, response_display_rows,
                                 summary_display_rows, validate_it_workflow)
from chi_gui.lsv_workflow import GUIWorkflowValidationError, StaleAnalysisResultError
from chi_gui.main_window import MainWindow
from chi_gui.state import FileRecord, FileStatus
from chi_gui.widgets.it_analysis import nearest_it_response_point
from chi_gui.workspaces import WorkspaceManager
from plotting.it_events import (build_it_calibration_figure, build_it_event_figure,
                                build_it_response_figure)


def _records(data, count=2):
    return tuple(
        FileRecord(Path(f"record {index + 1}.bin"), FileStatus.PARSED, "i-t", "i-t",
                   replace(data, file_name=f"record {index + 1}.bin"))
        for index in range(count)
    )


def _ready(records, *, calibration=False):
    workflow = ITWorkflowState(); workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"IT-{index + 1}")
        workflow.update_metadata(row.record_key, "group", "Control" if index % 2 == 0 else "Treatment")
    workflow.confirm_metadata()
    workflow.add_event(time_s=31.0, name="Light on", value=2.0, unit="level")
    workflow.add_event(time_s=61.0, name="Temperature", value=7.0, unit="level")
    workflow.add_event(time_s=91.0, name="Gas switch")
    workflow.confirm_timeline(records)
    if calibration:
        workflow.set_calibration(True, ("event_1", "event_2"), "Condition level", "level")
    return workflow


def test_it_tabs_are_enabled_without_replacing_lsv_workflow():
    source = getsource(MainWindow._set_route)
    assert 'route in {"LSV", "i-t"}' in source
    assert hasattr(MainWindow, "_run_lsv_analysis")
    assert hasattr(MainWindow, "_run_it_analysis")


def test_metadata_has_no_bare_material_and_requires_confirmation(synthetic_it_data):
    records = _records(synthetic_it_data, 1)
    workflow = ITWorkflowState(); workflow.sync_records(records)
    assert not hasattr(workflow.metadata_rows[0], "electrode_type")
    assert "样本信息" in validate_it_workflow(workflow, records)[0]
    with pytest.raises(GUIWorkflowValidationError): workflow.build_request(records)


def test_one_and_many_files_are_supported(synthetic_it_data):
    for count in (1, 2, 5):
        records = _records(synthetic_it_data, count)
        workflow = _ready(records)
        assert len(execute_it_analysis(workflow.build_request(records)).files) == count


def test_event_add_sort_edit_delete_and_stable_id(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = ITWorkflowState(); workflow.sync_records(records)
    later = workflow.add_event(time_s=61, name="Later")
    earlier = workflow.add_event(time_s=31, name="Earlier")
    assert [row.event_id for row in workflow.events] == [earlier.event_id, later.event_id]
    workflow.edit_event(later.event_id, time_s=71, name="Edited")
    assert next(row for row in workflow.events if row.event_id == later.event_id).name == "Edited"
    workflow.delete_events((earlier.event_id,))
    assert [row.event_id for row in workflow.events] == [later.event_id]


def test_duplicate_event_time_rejected_inline():
    workflow = ITWorkflowState(); workflow.add_event(time_s=10, name="A")
    with pytest.raises(ValueError, match="不能重复"):
        workflow.add_event(time_s=10, name="B")


def test_empty_timeline_is_continuous_but_defined_unconfirmed_event_blocks(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = ITWorkflowState(); workflow.sync_records(records)
    workflow.update_metadata(records[0].key, "group", "G"); workflow.confirm_metadata()
    assert workflow.build_request(records).mode.value == "continuous"
    workflow.add_event(time_s=31, name="A")
    assert any("Timeline" in error for error in validate_it_workflow(workflow, records))


def test_cursor_state_is_not_part_of_formal_it_signature(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records)
    signature = workflow.current_signature()
    manager = WorkspaceManager(); manager.active.it_workflow = workflow
    manager.active.cursor_by_route["i-t"].set(35.0)
    assert workflow.current_signature() == signature
    assert workflow.timeline_confirmed


@pytest.mark.parametrize("fraction", (0, -0.1, 1.01, float("nan")))
def test_tail_fraction_inline_validation(fraction):
    workflow = ITWorkflowState()
    with pytest.raises(Exception): workflow.set_tail_fraction(fraction)


def test_tail_fraction_and_metric_reach_existing_backend(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records)
    workflow.set_tail_fraction(.5); workflow.set_metric("magnitude")
    request = workflow.build_request(records); result = execute_it_analysis(request)
    assert request.policy.fraction == .5 and result.analysis_metric == "magnitude"
    assert result.files[0].windows[0].n == 15


def test_calibration_is_off_by_default_and_numeric_events_not_auto_selected(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records)
    result = execute_it_analysis(workflow.build_request(records))
    assert workflow.calibration_event_ids == ()
    assert all(item.calibration is None for item in result.files)


def test_explicit_calibration_and_unit_validation(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records, calibration=True)
    result = execute_it_analysis(workflow.build_request(records))
    assert result.files[0].calibration.event_ids == ("event_1", "event_2")
    workflow.set_calibration(True, ("event_1", "event_3"), "X", "level")
    assert any("numeric value" in error for error in validate_it_workflow(workflow, records))


def test_result_tables_are_derived_from_backend_and_keep_unavailable(synthetic_it_data):
    short = replace(synthetic_it_data, n_points=70, actual_last_time_s=70,
                    actual_recorded_duration_s=70, time_s=synthetic_it_data.time_s[:70],
                    current_A=synthetic_it_data.current_A[:70])
    records = _records(short, 1); workflow = _ready(records)
    result = execute_it_analysis(workflow.build_request(records))
    rows = response_display_rows(result)
    assert len(rows) == 3 and any("unavailable" in row["status"] for row in rows)
    assert {"mean", "sd", "sem", "cv_percent"} <= set(summary_display_rows(result)[0])


def test_signed_and_magnitude_summaries_are_backend_fields(synthetic_it_data):
    records = _records(synthetic_it_data, 2); workflow = _ready(records)
    signed = execute_it_analysis(workflow.build_request(records))
    assert summary_display_rows(signed)[0]["mean"] == signed.summaries[0].mean_delta_current_uA
    workflow.set_metric("magnitude")
    magnitude = execute_it_analysis(workflow.build_request(records))
    assert summary_display_rows(magnitude)[0]["mean"] == magnitude.summaries[0].mean_response_magnitude_uA


def test_result_stale_and_export_blocked_after_settings_change(synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records)
    request = workflow.build_request(records); workflow.accept_result(request, execute_it_analysis(request))
    workflow.set_tail_fraction(.3)
    assert workflow.result_stale
    with pytest.raises(StaleAnalysisResultError): workflow.require_exportable_result()


def test_workspace_it_states_and_lsv_states_are_isolated():
    manager = WorkspaceManager(); first = manager.active
    first.it_workflow.add_event(time_s=10, name="A")
    second = manager.create(); second.it_workflow.add_event(time_s=20, name="B")
    assert first.it_workflow.events[0].name == "A"
    assert second.it_workflow.events[0].name == "B"
    assert first.lsv_workflow is not first.it_workflow


def test_all_it_result_figures_and_hover_use_sample_ids(synthetic_it_data):
    records = _records(synthetic_it_data, 2); workflow = _ready(records, calibration=True)
    result = execute_it_analysis(workflow.build_request(records))
    raw = build_it_event_figure(result)
    response, series = build_it_response_figure(result, include_hover_metadata=True)
    calibration = build_it_calibration_figure(result)
    try:
        assert len(raw.axes[0].lines) == len(result.files) + len(result.timeline.events)
        point = series[0].points[0]
        x, y = response.axes[0].transData.transform((point.x, point.value_uA))
        found = nearest_it_response_point(series, response.axes[0], float(x), float(y))
        assert found.sample_id == "IT-1"
        assert calibration.axes[0].lines
    finally:
        for figure in (raw, response, calibration): plt.close(figure)


def test_calibration_rows_hide_lod_and_export_does_not_reanalyse(tmp_path, synthetic_it_data):
    records = _records(synthetic_it_data, 1); workflow = _ready(records, calibration=True)
    result = execute_it_analysis(workflow.build_request(records))
    assert "lod" not in calibration_display_rows(result)[0]
    run = export_it_result(result, tmp_path)
    assert run.result is result
    assert (run.output_directory / "i-t/csv/events.csv").exists()
    assert any(path.suffix == ".svg" for path in run.generated_files)


def test_stage531_gui_contains_no_automatic_event_detection_or_fixed_concentration_schema():
    text = Path("src/chi_gui/it_workflow.py").read_text(encoding="utf-8").lower()
    for token in ("detect_event", "concentration_um", "t90", "auc", "smoothing"):
        assert token not in text
