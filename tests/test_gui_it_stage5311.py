from __future__ import annotations

from dataclasses import replace
from inspect import getsource
from pathlib import Path
import warnings

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

from analysis.it_events import Event
from chi_gui.it_workflow import ITWorkflowState, execute_it_analysis, validate_it_workflow
from chi_gui.it_export import export_it_result
from chi_gui.lsv_workflow import GUIWorkflowValidationError
from chi_gui.state import FileRecord, FileStatus
from chi_gui.widgets.it_analysis import (ITSettingsPanel, available_it_result_plots,
                                         event_double_click_edits,
                                         normalize_it_result_plot)
from chi_gui.workspaces import WorkspaceManager
from plotting.font_config import configure_plotting_fonts
from plotting.it_events import (build_it_calibration_figure, build_it_event_figure,
                                build_it_response_figure)


def _records(data, count=2):
    return tuple(FileRecord(Path(f"sample-{index}.bin"), FileStatus.PARSED, "i-t", "i-t",
                            replace(data, file_name=f"sample-{index}.bin"))
                 for index in range(count))


def _ready(records):
    workflow = ITWorkflowState(); workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"S{index + 1}")
        workflow.update_metadata(row.record_key, "group", "中文组")
    workflow.confirm_metadata()
    workflow.add_event(time_s=31, name="光照开启", value=2, unit="µM")
    workflow.add_event(time_s=61, name="温度变化", value=7, unit="µM")
    workflow.add_event(time_s=91, name="加样")
    workflow.confirm_timeline(records)
    return workflow


def test_sample_information_title_is_compact_and_event_double_click_is_bound():
    source = getsource(ITSettingsPanel.__init__)
    assert 'text="① 样本信息"' in source
    assert "i-t 不使用 Bare / Material" not in source
    assert 'self.events.bind("<Double-1>", self._double_edit_event)' in source
    assert "编辑" in source


@pytest.mark.parametrize("column", ("#2", "#3", "#4", "#5", "#6"))
def test_double_click_event_time_value_unit_and_notes_open_whole_row_editor(column):
    assert event_double_click_edits(column)


def test_event_id_column_is_not_editable_and_edit_keeps_id():
    assert not event_double_click_edits("#1")
    workflow = ITWorkflowState(); event = workflow.add_event(time_s=10, name="A")
    edited = workflow.edit_event(event.event_id, time_s=11, name="B")
    assert edited.event_id == event.event_id


def test_no_override_uses_confirmed_default(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    request = workflow.build_request(records)
    assert all(timeline.events == workflow.timeline.events for timeline in request.record_timelines)


def test_create_override_deep_copies_default_and_preserves_event_ids(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    key = records[0].key; default_before = tuple(workflow.events)
    override = workflow.create_sample_override(key)
    assert override.events is not workflow.events
    assert tuple(event.event_id for event in override.events) == tuple(event.event_id for event in default_before)
    workflow.edit_event(default_before[0].event_id, time_s=35)
    assert workflow.events[0].time_s == 31
    assert override.events[0].time_s == 35


def test_default_edit_affects_inheritor_but_not_existing_override(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    workflow.select_timeline_context(None)
    workflow.edit_event("event_1", time_s=33)
    assert workflow.timeline_for_record_key(records[1].key).events[0].time_s == 33
    assert workflow.timeline_for_record_key(records[0].key).events[0].time_s == 31


def test_restore_default_removes_override_and_marks_result_stale(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    request = workflow.build_request(records); workflow.accept_result(request, execute_it_analysis(request))
    workflow.create_sample_override(records[0].key)
    workflow.restore_default_timeline(records[0].key)
    assert records[0].key not in workflow.sample_timeline_overrides
    assert workflow.timeline_for_record_key(records[0].key).events == workflow.timeline.events
    assert workflow.result_stale


def test_unconfirmed_override_blocks_instead_of_falling_back(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    errors = validate_it_workflow(workflow, records)
    assert any("S1" in error and "尚未确认" in error for error in errors)
    with pytest.raises(GUIWorkflowValidationError): workflow.build_request(records)


def test_override_confirmation_rejects_event_outside_its_record(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    workflow.edit_event("event_3", time_s=121)
    with pytest.raises(GUIWorkflowValidationError, match="outside"):
        workflow.confirm_timeline(records)


def test_overrides_use_record_key_and_survive_sample_id_rename_and_exclusion(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records); key = records[0].key
    override = workflow.create_sample_override(key)
    workflow.update_metadata(key, "sample_id", "玻碳2")
    assert workflow.sample_timeline_overrides[key] is override
    workflow.update_metadata(key, "include", False)
    assert workflow.sample_timeline_overrides[key] is override
    workflow.update_metadata(key, "include", True)
    assert workflow.sample_timeline_overrides[key] is override


def test_removed_record_cleans_orphan_override(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records); key = records[0].key
    workflow.create_sample_override(key)
    workflow.sync_records(records[1:])
    assert key not in workflow.sample_timeline_overrides


def test_workspace_timeline_overrides_are_isolated(synthetic_it_data):
    records = _records(synthetic_it_data); manager = WorkspaceManager()
    first = manager.active; first.it_workflow = _ready(records)
    first.it_workflow.create_sample_override(records[0].key)
    second = manager.create(); second.it_workflow = _ready(records)
    assert records[0].key in first.it_workflow.sample_timeline_overrides
    assert second.it_workflow.sample_timeline_overrides == {}


def test_record_specific_event_times_reach_windows(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    workflow.edit_event("event_1", time_s=35)
    workflow.confirm_timeline(records)
    result = execute_it_analysis(workflow.build_request(records))
    assert result.files[0].responses[0].event_time_s == 35
    assert result.files[1].responses[0].event_time_s == 31
    assert result.files[0].windows[0].requested_end_s == 35
    assert result.files[1].windows[0].requested_end_s == 31


def test_missing_override_event_does_not_index_shift_summary(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    workflow.delete_events(("event_2",)); workflow.confirm_timeline(records)
    result = execute_it_analysis(workflow.build_request(records))
    first_ids = tuple(row.event_id for row in result.files[0].responses)
    second_ids = tuple(row.event_id for row in result.files[1].responses)
    assert first_ids == ("event_1", "event_3")
    assert second_ids == ("event_1", "event_2", "event_3")
    assert {row.event_id for row in result.summaries} == {"event_1", "event_2", "event_3"}


def test_calibration_aligns_by_event_id_across_different_sample_times(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.create_sample_override(records[0].key)
    workflow.edit_event("event_1", time_s=35); workflow.confirm_timeline(records)
    workflow.set_calibration(True, ("event_1", "event_2"), "浓度", "µM")
    result = execute_it_analysis(workflow.build_request(records))
    assert all(item.calibration.event_ids == ("event_1", "event_2") for item in result.files)
    assert result.files[0].responses[0].event_time_s != result.files[1].responses[0].event_time_s


def test_unified_cjk_font_policy_prefers_windows_font():
    selected = configure_plotting_fonts(("DejaVu Sans", "Microsoft YaHei", "SimHei"))
    assert selected[:2] == ("Microsoft YaHei", "SimHei")
    assert mpl.rcParams["font.family"] == ["sans-serif"]


def test_cjk_labels_flow_through_all_it_figures(synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    workflow.update_metadata(records[0].key, "sample_id", "玻碳2")
    workflow.confirm_metadata()
    workflow.add_event(time_s=105, name="应激", value=25, unit="°C")
    workflow.add_event(time_s=110, name="样本事件", value=30, unit="μM")
    workflow.confirm_timeline(records)
    workflow.set_calibration(True, ("event_1", "event_2"), "应激", "µM")
    result = execute_it_analysis(workflow.build_request(records))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        figures = (build_it_event_figure(result), build_it_response_figure(result),
                   build_it_calibration_figure(result))
        for figure in figures:
            figure.canvas.draw()
    try:
        text = " ".join(label.get_text() for figure in figures for axis in figure.axes
                        for label in (*axis.texts, *axis.get_xticklabels(), *axis.get_legend().get_texts()))
        assert all(value in text for value in ("玻碳2", "光照开启", "温度变化", "应激", "样本事件", "°C", "μM"))
        assert not any("Glyph" in str(warning.message) and "missing from font" in str(warning.message)
                       for warning in caught)
    finally:
        for figure in figures: plt.close(figure)


def test_calibration_aware_plot_selector_and_fallback(tmp_path, synthetic_it_data):
    records = _records(synthetic_it_data); workflow = _ready(records)
    no_calibration = execute_it_analysis(workflow.build_request(records))
    assert available_it_result_plots(no_calibration) == ("Raw + Events", "Event Response")
    assert normalize_it_result_plot("Calibration", no_calibration) == "Raw + Events"
    exported = export_it_result(no_calibration, tmp_path)
    assert not any("calibration" in path.name.lower() for path in exported.generated_files)
    workflow.set_calibration(True, ("event_1", "event_2"), "X", "µM")
    calibrated = execute_it_analysis(workflow.build_request(records))
    assert available_it_result_plots(calibrated)[-1] == "Calibration"


def test_no_scientific_feature_creep():
    text = Path("src/chi_gui/it_workflow.py").read_text(encoding="utf-8").lower()
    for token in ("t90", "auc", "detect_event", "unit conversion", "peak current"):
        assert token not in text
