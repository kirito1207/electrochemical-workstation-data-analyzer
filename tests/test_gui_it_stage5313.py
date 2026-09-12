from __future__ import annotations

from dataclasses import replace
from inspect import getsource
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from analysis.it_events import ITAnalysisMode
from chi_gui.it_export import export_it_result
from chi_gui.it_workflow import (
    ITMetadataBatchEdit,
    ITWorkflowState,
    continuous_display_rows,
    execute_it_analysis,
    validate_it_workflow,
    workflow_status_lines,
)
from chi_gui.lsv_workflow import GUIWorkflowValidationError, StaleAnalysisResultError
from chi_gui.metadata_selection import MetadataSelectionModel
from chi_gui.state import FileRecord, FileStatus
from chi_gui.widgets.it_analysis import (
    ITResultsPanel,
    ITSettingsPanel,
    available_it_result_plots,
    it_group_choices,
)
from plotting.it_events import build_it_event_figure


def _records(data, count=2):
    return tuple(
        FileRecord(Path(f"continuous-{index + 1}.bin"), FileStatus.PARSED, "i-t", "i-t",
                   replace(data, file_name=f"continuous-{index + 1}.bin"))
        for index in range(count)
    )


def _metadata_ready(data, count=2):
    records = _records(data, count)
    workflow = ITWorkflowState(); workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"S{index + 1}")
        workflow.update_metadata(row.record_key, "group", "G1")
    workflow.confirm_metadata()
    return workflow, records


def _event_ready(data, count=2):
    workflow, records = _metadata_ready(data, count)
    workflow.add_event(time_s=31, name="光照", value=2, unit="µM")
    workflow.add_event(time_s=61, name="温度", value=7, unit="µM")
    workflow.confirm_timeline(records)
    return workflow, records


def test_it_widget_reuses_lsv_selection_model_and_gestures():
    source = getsource(ITSettingsPanel.__init__)
    assert "MetadataSelectionModel()" in source
    assert 'selectmode="extended"' in source
    for binding in ("<ButtonPress-1>", "<B1-Motion>", "<ButtonRelease-1>",
                    "<Control-a>", "<Control-A>"):
        assert binding in source


def test_single_ctrl_shift_and_ctrl_a_selection_match_lsv_model():
    model = MetadataSelectionModel(); model.reset(("a", "b", "c", "d"))
    assert model.click("b") == ("b",)
    assert model.click("d", ctrl=True) == ("b", "d")
    assert model.click("c", shift=True) == ("c", "d")
    assert model.select_all() == ("a", "b", "c", "d")
    assert model.clear() == ()


def test_drag_range_selection_matches_lsv_model():
    model = MetadataSelectionModel(); model.reset(("a", "b", "c", "d"))
    model.begin_drag("b", 10)
    assert model.drag_to("d", 30) == ("b", "c", "d")
    assert model.finish_drag()


def test_group_choices_are_stable_and_user_defined():
    rows = [
        type("Row", (), {"group": "A"})(), type("Row", (), {"group": "B"})(),
        type("Row", (), {"group": " A "})(), type("Row", (), {"group": ""})(),
    ]
    assert it_group_choices(rows) == ("A", "B")


def test_batch_group_include_and_notes_are_atomic_and_invalidate_confirmation(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 3)
    keys = (records[0].key, records[2].key)
    workflow.batch_update_metadata(keys, ITMetadataBatchEdit(
        include=False, update_group=True, group="PB_A",
        update_notes=True, notes="same condition",
    ))
    assert [(row.include, row.group, row.notes) for row in workflow.metadata_rows] == [
        (False, "PB_A", "same condition"), (True, "G1", ""),
        (False, "PB_A", "same condition"),
    ]
    assert not workflow.metadata_confirmed
    workflow.batch_update_metadata(keys, ITMetadataBatchEdit(include=True))
    assert workflow.metadata_rows[0].include and workflow.metadata_rows[2].include


def test_batch_validation_fails_before_any_row_changes(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 2)
    before = [(row.include, row.group, row.notes) for row in workflow.metadata_rows]
    with pytest.raises(ValueError):
        workflow.batch_update_metadata((records[0].key, "missing"),
                                       ITMetadataBatchEdit(update_group=True, group="new"))
    assert [(row.include, row.group, row.notes) for row in workflow.metadata_rows] == before


def test_batch_changes_mark_result_stale_and_preserve_record_key_override(synthetic_it_data):
    workflow, records = _event_ready(synthetic_it_data, 2)
    key = records[0].key
    override = workflow.create_sample_override(key); workflow.confirm_timeline(records)
    request = workflow.build_request(records)
    workflow.accept_result(request, execute_it_analysis(request))
    workflow.batch_update_metadata((key,), ITMetadataBatchEdit(
        include=False, update_group=True, group="PB_B", update_notes=True, notes="excluded"
    ))
    assert workflow.sample_timeline_overrides[key] is override
    assert workflow.result_stale and not workflow.metadata_confirmed
    with pytest.raises(StaleAnalysisResultError):
        workflow.require_exportable_result()
    workflow.batch_update_metadata((key,), ITMetadataBatchEdit(include=True))
    assert workflow.sample_timeline_overrides[key] is override


@pytest.mark.parametrize("count", (1, 4))
def test_no_event_formal_analysis_succeeds_without_timeline_confirmation(synthetic_it_data, count):
    workflow, records = _metadata_ready(synthetic_it_data, count)
    assert not workflow.timeline_confirmed
    assert validate_it_workflow(workflow, records) == ()
    request = workflow.build_request(records)
    result = execute_it_analysis(request)
    assert request.mode == ITAnalysisMode.CONTINUOUS
    assert result.mode == ITAnalysisMode.CONTINUOUS
    assert len(result.files) == count
    assert len(result.continuous_summaries) == count
    assert result.summaries == ()


def test_continuous_summary_uses_complete_record_values(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 1)
    result = execute_it_analysis(workflow.build_request(records))
    row = result.continuous_summaries[0]
    current_uA = synthetic_it_data.current_A * 1e6
    assert row.duration_s == pytest.approx(
        synthetic_it_data.time_s[-1] - synthetic_it_data.time_s[0]
    )
    assert row.mean_current_uA == pytest.approx(np.mean(current_uA))
    assert row.sd_current_uA == pytest.approx(np.std(current_uA, ddof=1))
    assert row.min_current_uA == pytest.approx(np.min(current_uA))
    assert row.max_current_uA == pytest.approx(np.max(current_uA))
    assert row.first_time_s == synthetic_it_data.time_s[0]
    assert row.last_time_s == synthetic_it_data.time_s[-1]
    assert tuple(continuous_display_rows(result)[0]) == (
        "sample_id", "group", "duration_s", "mean_current_uA", "sd_current_uA",
        "min_current_uA", "max_current_uA", "first_time_s", "last_time_s", "status",
    )


def test_continuous_plot_has_full_records_and_no_event_markers(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 3)
    result = execute_it_analysis(workflow.build_request(records))
    assert available_it_result_plots(result) == ("Raw i-t / Continuous",)
    figure = build_it_event_figure(result)
    try:
        assert len(figure.axes[0].lines) == 3
        assert list(figure.axes[0].texts) == []
        assert "Continuous" in figure.axes[0].get_title()
    finally:
        plt.close(figure)


def test_continuous_export_has_summary_and_raw_figure_only(tmp_path, synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 2)
    run = export_it_result(execute_it_analysis(workflow.build_request(records)), tmp_path)
    names = {path.name for path in run.generated_files}
    assert "continuous_summary.csv" in names
    assert not names.intersection({"events.csv", "event_responses.csv", "response_windows.csv",
                                   "event_summary.csv", "calibration.csv"})
    assert any(path.stem == "raw_continuous" for path in run.generated_files)
    assert not any("event_responses" in path.name for path in run.generated_files)


def test_defined_but_unconfirmed_event_is_not_silently_ignored(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 1)
    workflow.add_event(time_s=31, name="Event")
    assert workflow.analysis_mode == ITAnalysisMode.EVENT
    with pytest.raises(GUIWorkflowValidationError, match="Timeline"):
        workflow.build_request(records)


def test_confirmed_event_mode_still_uses_existing_response_path(synthetic_it_data):
    workflow, records = _event_ready(synthetic_it_data, 1)
    result = execute_it_analysis(workflow.build_request(records))
    assert result.mode == ITAnalysisMode.EVENT
    assert len(result.files[0].responses) == 2
    assert available_it_result_plots(result) == ("Raw + Events", "Event Response")


def test_unconfirmed_override_event_blocks_and_confirmed_override_works(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 2)
    workflow.create_sample_override(records[0].key)
    workflow.add_event(time_s=31, name="Override only")
    with pytest.raises(GUIWorkflowValidationError, match="尚未确认"):
        workflow.build_request(records)
    workflow.confirm_timeline(records)
    workflow.select_timeline_context(None)
    workflow.confirm_timeline(records)  # Explicitly confirm the empty inherited Timeline in Event mode.
    result = execute_it_analysis(workflow.build_request(records))
    assert result.mode == ITAnalysisMode.EVENT
    assert len(result.files[0].responses) == 1
    assert result.files[1].responses == ()


def test_default_events_keep_event_mode_when_included_override_is_empty(synthetic_it_data):
    workflow, records = _event_ready(synthetic_it_data, 1)
    workflow.create_sample_override(records[0].key)
    workflow.delete_events(("event_1", "event_2"))
    assert workflow.events
    assert workflow.current_events == []
    assert workflow.analysis_mode == ITAnalysisMode.EVENT
    with pytest.raises(GUIWorkflowValidationError, match="尚未确认"):
        workflow.build_request(records)


def test_deleting_last_event_switches_to_continuous_and_clears_calibration(synthetic_it_data):
    workflow, records = _event_ready(synthetic_it_data, 1)
    workflow.set_calibration(True, ("event_1", "event_2"), "浓度", "µM")
    request = workflow.build_request(records)
    workflow.accept_result(request, execute_it_analysis(request))
    workflow.delete_events(("event_1", "event_2"))
    assert workflow.analysis_mode == ITAnalysisMode.CONTINUOUS
    assert not workflow.calibration_enabled
    assert workflow.calibration_event_ids == ()
    assert workflow.calibration_x_label == workflow.calibration_x_unit == ""
    assert workflow.result_stale
    assert workflow.build_request(records).mode == ITAnalysisMode.CONTINUOUS


def test_adding_first_event_switches_to_event_and_stales_result(synthetic_it_data):
    workflow, records = _metadata_ready(synthetic_it_data, 1)
    request = workflow.build_request(records)
    workflow.accept_result(request, execute_it_analysis(request))
    workflow.add_event(time_s=31, name="First")
    assert workflow.analysis_mode == ITAnalysisMode.EVENT
    assert workflow.result_stale
    with pytest.raises(GUIWorkflowValidationError, match="Timeline"):
        workflow.build_request(records)


def test_continuous_status_results_and_footer_regressions_are_explicit():
    workflow = ITWorkflowState()
    assert "Continuous mode" in workflow_status_lines(workflow)[1]
    result_source = getsource(ITResultsPanel.render)
    assert 'state="hidden" if continuous else "normal"' in result_source
    settings_source = getsource(ITSettingsPanel.__init__)
    assert "self.footer_actions.grid" in settings_source
    assert 'text="开始正式 i-t 分析"' in settings_source


def test_stage5313_does_not_add_advanced_kinetics_or_lsv_science():
    text = Path("src/analysis/it_events.py").read_text(encoding="utf-8").lower()
    for token in ("retention", "drift slope", "t90", "auc", "recovery", "detrend"):
        assert token not in text
