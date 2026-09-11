from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from chi_gui.controller import GUIController
from chi_gui.lsv_workflow import (
    ComparisonDraft,
    ComparisonEditorDraft,
    GUIWorkflowValidationError,
    LSVWorkflowState,
    MetadataDraftRow,
    mad_result_status,
    result_summary_text,
    sign_qc_result_status,
    validate_metadata_draft,
    workflow_status_lines,
)
from chi_gui.main_window import MainWindow
from chi_gui.metadata_selection import MetadataSelectionModel
from chi_gui.workspaces import WorkspaceManager
from chi_gui.widgets.lsv_analysis import LSVResultPlotPanel
from plotting.selected_potential import (
    SelectedScatterPoint,
    SelectedScatterSeries,
    build_selected_potential_figure,
)


def _row(key: str, *, sample: str = "S1", group: str = "G1", electrode: str = "Material",
         include: bool = True, directory: str = "d") -> MetadataDraftRow:
    return MetadataDraftRow(
        record_key=key,
        file_path=f"/{directory}/{key}.bin",
        file_name=f"{key}.bin",
        relative_path=f"{directory}/{key}.bin",
        include=include,
        sample_id=sample,
        group=group,
        electrode_type=electrode,
    )


def _copy_records(tmp_path: Path, lsv_path: Path, count: int, *, folder: str = "data"):
    target = tmp_path / folder
    target.mkdir(parents=True, exist_ok=True)
    raw = lsv_path.read_bytes()
    paths = []
    for index in range(count):
        path = target / f"LSV-test-S{index + 1}.bin"
        changed = bytearray(raw)
        current = np.frombuffer(changed, dtype="<f4", count=400, offset=1453).copy()
        current += index * 0.02e-6
        changed[1453:] = current.astype("<f4").tobytes()
        path.write_bytes(changed)
        paths.append(path)
    return GUIController().parse_many(paths)


def _single_group_workflow(records):
    workflow = LSVWorkflowState(); workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"E{index + 1}")
        workflow.update_metadata(row.record_key, "group", "PB20_PBS")
        workflow.update_metadata(row.record_key, "electrode_type", "Material")
    workflow.confirm_metadata()
    return workflow


def test_confirm_failure_has_concise_chinese_feedback_data():
    rows = tuple(_row(f"f{i}", sample="" if i < 2 else f"S{i}", group="") for i in range(8))
    errors = validate_metadata_draft(rows)
    assert any("8 个纳入样本尚未设置 Group" in error for error in errors)
    assert any("2 个纳入样本缺少 Sample ID" in error for error in errors)
    assert len(errors) == 2


def test_confirm_success_feedback_is_inline_ready(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 3)
    workflow = _single_group_workflow(records)
    workflow.set_feedback("success", "样本信息已确认：3 个文件")
    assert workflow.feedback.text == "✓ 样本信息已确认：3 个文件"


def test_main_window_confirm_updates_visible_feedback_state(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 3)
    window = object.__new__(MainWindow); window.workspace_manager = WorkspaceManager()
    window.workspace.state.add_records(records)
    workflow = _single_group_workflow(records)
    window.workspace.lsv_workflow = workflow
    window._log = Mock(); window._refresh_lsv_workflow = Mock()
    window._confirm_lsv_metadata()
    assert workflow.feedback.level == "success"
    assert "3 个文件" in workflow.feedback.text
    window._refresh_lsv_workflow.assert_called_once()


def test_run_validation_feedback_is_not_log_only(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 2)
    window = object.__new__(MainWindow)
    window.workspace_manager = WorkspaceManager()
    window.workspace.state.add_records(records)
    window.workspace.lsv_workflow.sync_records(records)
    window._log = Mock(); window._refresh_lsv_workflow = Mock()
    window._run_lsv_analysis()
    assert window.workspace.lsv_workflow.feedback.level == "warning"
    assert "无法开始正式分析" in window.workspace.lsv_workflow.feedback.text
    window._refresh_lsv_workflow.assert_called_once()


def test_duplicate_group_sample_id_is_clear_chinese():
    errors = validate_metadata_draft((_row("a", sample="S1"), _row("b", sample="S1")))
    assert errors == ("Group G1 中 Sample ID S1 重复",)


def test_same_sample_id_in_different_groups_is_allowed():
    assert validate_metadata_draft((_row("a", sample="S1", group="A"), _row("b", sample="S1", group="B"))) == ()


def test_excluded_rows_do_not_require_metadata():
    assert validate_metadata_draft((_row("a"), _row("b", sample="", group="", electrode="", include=False))) == ()


def test_multiple_source_directories_and_same_filename_are_supported(tmp_path, lsv_path):
    paths = []
    for folder in ("第一组", "第二组"):
        directory = tmp_path / folder; directory.mkdir()
        path = directory / "same-S1.bin"; path.write_bytes(lsv_path.read_bytes()); paths.append(path)
    records = GUIController().parse_many(paths)
    workflow = LSVWorkflowState(); workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"S{index + 1}")
        workflow.update_metadata(row.record_key, "group", "G")
    manifest = workflow.confirm_metadata()
    assert len({entry.file_path for entry in manifest.entries}) == 2
    assert len({entry.relative_path for entry in manifest.entries}) == 2


def test_single_group_without_comparison_runs(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 3)
    workflow = _single_group_workflow(records)
    request = workflow.build_request(records)
    from chi_gui.lsv_workflow import execute_lsv_analysis
    result = execute_lsv_analysis(request)
    assert result.summary("PB20_PBS", "magnitude").statistics.n == 3
    assert result.comparisons == ()


def test_bare_same_group_stays_out_of_material_qc_and_statistics(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 4)
    workflow = _single_group_workflow(records)
    workflow.update_metadata(records[-1].key, "electrode_type", "Bare")
    workflow.confirm_metadata()
    from chi_gui.lsv_workflow import execute_lsv_analysis
    result = execute_lsv_analysis(workflow.build_request(records))
    assert result.summary("PB20_PBS", "magnitude").statistics.n == 3
    group_qc = next(item for item in result.current_sign_qc if item.group == "PB20_PBS")
    assert group_qc.total_count == 3
    assert all(flag.sample_id != "E4" for flag in result.outlier_flags)


def test_workflow_status_reports_running_and_stale():
    workflow = LSVWorkflowState(analysis_running=True)
    assert workflow_status_lines(workflow)[-1].endswith("正在分析")


def test_comparison_editor_draft_clears_on_workspace_switch():
    draft = ComparisonEditorDraft("workspace-1", "A", "B", "Exploratory", "family-x", "A-B")
    assert draft.synchronize("workspace-2", ())
    assert (draft.left_group, draft.right_group, draft.name) == ("", "", "")
    assert (draft.role, draft.holm_family) == ("Primary", "primary")


def test_comparison_editor_removes_nonexistent_group_without_workspace_switch():
    draft = ComparisonEditorDraft("workspace-1", "A", "old", "Primary", "primary", "name")
    assert not draft.synchronize("workspace-1", ("A", "B"))
    assert draft.left_group == "A"
    assert draft.right_group == ""


def test_formal_comparisons_remain_workspace_isolated():
    manager = WorkspaceManager(); first = manager.active
    first.lsv_workflow.comparisons.append(ComparisonDraft("A", "B", name="A-B"))
    second = manager.create()
    assert second.lsv_workflow.comparisons == []
    manager.switch(first.workspace_id)
    assert first.lsv_workflow.comparisons[0].name == "A-B"


@pytest.mark.parametrize("start,end", (("r2", "r6"), ("r6", "r2")))
def test_drag_selects_contiguous_rows_in_both_directions(start, end):
    model = MetadataSelectionModel(); keys = tuple(f"r{i}" for i in range(1, 8)); model.reset(keys)
    model.begin_drag(start, 10)
    selection = model.drag_to(end, 40)
    assert selection == ("r2", "r3", "r4", "r5", "r6")
    assert model.finish_drag()


def test_small_pointer_motion_remains_edit_click_not_drag():
    model = MetadataSelectionModel(); model.reset(("a", "b")); model.begin_drag("a", 10)
    assert model.drag_to("b", 12) is None
    assert not model.finish_drag()


def test_ctrl_and_shift_selection_semantics_remain_available():
    model = MetadataSelectionModel(); model.reset(("a", "b", "c", "d"))
    assert model.click("a") == ("a",)
    assert model.click("c", ctrl=True) == ("a", "c")
    assert model.click("d", shift=True) == ("c", "d")


def test_ctrl_a_and_select_all_cover_every_metadata_row():
    model = MetadataSelectionModel(); model.reset(("a", "b", "c"))
    assert model.select_all() == ("a", "b", "c")


def test_batch_group_and_electrode_apply_only_selected_rows():
    workflow = LSVWorkflowState(metadata_rows=[_row("a"), _row("b"), _row("c")])
    workflow.batch_update(("a", "c"), "group", "PB20")
    workflow.batch_update(("c",), "electrode_type", "Bare")
    assert [row.group for row in workflow.metadata_rows] == ["PB20", "G1", "PB20"]
    assert [row.electrode_type for row in workflow.metadata_rows] == ["Material", "Material", "Bare"]


def test_mad_empty_state_is_explicit(synthetic_analysis_result):
    no_flags = synthetic_analysis_result.__class__(
        settings=synthetic_analysis_result.settings,
        manifest=synthetic_analysis_result.manifest,
        files=synthetic_analysis_result.files,
        group_summaries=synthetic_analysis_result.group_summaries,
        comparisons=synthetic_analysis_result.comparisons,
        outlier_flags=(),
        current_sign_qc=synthetic_analysis_result.current_sign_qc,
        warnings=synthetic_analysis_result.warnings,
    )
    assert "未发现 MAD Possible outlier" in mad_result_status(no_flags)
    assert "所有 Material 样本仍纳入" in mad_result_status(no_flags)


def test_sign_qc_normal_and_mixed_states_are_explicit(synthetic_analysis_result):
    status = sign_qc_result_status(synthetic_analysis_result)
    assert status.startswith(("✓", "⚠"))
    if synthetic_analysis_result.warnings:
        assert "magnitude" in status


def test_result_summary_reports_material_groups_and_comparisons(synthetic_analysis_result):
    text = result_summary_text(synthetic_analysis_result)
    assert "Material 样本数：39" in text
    assert "Groups：3" in text
    assert "Group names：A, B, C" in text
    assert "Comparisons：3" in text


@pytest.mark.parametrize("metric", ("magnitude", "signed"))
def test_selected_scatter_hover_metadata_uses_confirmed_manifest(synthetic_analysis_result, metric):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, metric, include_hover_metadata=True
    )
    try:
        points = tuple(point for item in series for point in item.points)
        material = tuple(item for item in synthetic_analysis_result.files if item.manifest.electrode_type == "Material")
        expected = {
            (item.manifest.group, item.manifest.sample_id):
            item.selected.response_magnitude_uA if metric == "magnitude" else item.selected.current_uA
            for item in material
        }
        assert {(point.group, point.sample_id) for point in points} == set(expected)
        np.testing.assert_allclose(
            [point.current_uA for point in points],
            [expected[(point.group, point.sample_id)] for point in points],
        )
    finally:
        import matplotlib.pyplot as plt
        plt.close(figure)


def test_bare_and_mean_marker_have_no_scatter_hover_metadata(synthetic_analysis_result):
    figure, series = build_selected_potential_figure(
        synthetic_analysis_result, "magnitude", include_hover_metadata=True
    )
    try:
        point_count = sum(len(item.points) for item in series)
        material_count = sum(item.manifest.electrode_type == "Material" for item in synthetic_analysis_result.files)
        assert point_count == material_count == 39
        assert all("Bare" not in point.sample_id for item in series for point in item.points)
        assert len(series) == len(synthetic_analysis_result.groups)
    finally:
        import matplotlib.pyplot as plt
        plt.close(figure)


def test_static_selected_plot_has_no_permanent_sample_labels(synthetic_analysis_result):
    figure = build_selected_potential_figure(synthetic_analysis_result, "magnitude")
    try:
        text_values = {text.get_text() for axis in figure.axes for text in axis.texts}
        sample_ids = {item.manifest.sample_id for item in synthetic_analysis_result.files}
        assert not text_values.intersection(sample_ids)
    finally:
        import matplotlib.pyplot as plt
        plt.close(figure)


def test_hover_updates_only_annotation_without_rebuilding_figure():
    panel = object.__new__(LSVResultPlotPanel)
    axis = Mock()
    axis.transData.transform.return_value = (20.0, 30.0)
    axis.bbox.x0 = 0.0; axis.bbox.y0 = 0.0
    axis.bbox.width = 100.0; axis.bbox.height = 100.0
    artist = Mock()
    point = SelectedScatterPoint("G", "Confirmed-S11", 0.2, -2.314)
    panel._hover_series = (SelectedScatterSeries(artist, (point,)),)
    panel._hover_annotation = Mock(); panel._hover_annotation.get_visible.return_value = False
    panel.canvas = Mock(); panel.figure = Mock(axes=[axis])
    event = Mock(inaxes=axis, x=20.0, y=30.0)
    panel._hover_motion(event)
    panel._hover_annotation.set_text.assert_called_once_with("Confirmed-S11\n-2.314 µA")
    artist.contains.assert_not_called()
    panel.canvas.draw_idle.assert_called_once()


def test_hover_leave_hides_existing_annotation():
    panel = object.__new__(LSVResultPlotPanel)
    axis = object(); artist = Mock()
    panel._hover_series = (SelectedScatterSeries(artist, (SelectedScatterPoint("G", "S1", 0.0, 1.0),)),)
    panel._hover_annotation = Mock(); panel._hover_annotation.get_visible.return_value = True
    panel.canvas = Mock(); panel.figure = Mock(axes=[axis])
    panel._hover_motion(Mock(inaxes=None))
    panel._hover_annotation.set_visible.assert_called_once_with(False)
    panel.canvas.draw_idle.assert_called_once()


def test_preview_visibility_remains_independent_from_include(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 2)
    manager = WorkspaceManager(); manager.active.state.add_records(records)
    manager.active.lsv_workflow.sync_records(records)
    manager.active.preview_display.set_visible(records[0].key, False)
    assert manager.active.lsv_workflow.metadata_rows[0].include
    manager.active.lsv_workflow.update_metadata(records[1].key, "include", False)
    assert manager.active.preview_display.is_visible(records[1].key)


def test_changed_metadata_keeps_stale_result_behavior(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 3)
    workflow = _single_group_workflow(records)
    request = workflow.build_request(records)
    from chi_gui.lsv_workflow import execute_lsv_analysis
    workflow.accept_result(request, execute_lsv_analysis(request))
    workflow.update_metadata(records[0].key, "sample_id", "ConfirmedNewID")
    assert workflow.result_stale
    assert not workflow.has_confirmed_manifest


def test_changed_confirmed_sample_id_is_used_by_hover_after_reanalysis(tmp_path, lsv_path):
    records = _copy_records(tmp_path, lsv_path, 3)
    workflow = _single_group_workflow(records)
    workflow.update_metadata(records[0].key, "sample_id", "UserConfirmedID")
    workflow.confirm_metadata()
    from chi_gui.lsv_workflow import execute_lsv_analysis
    result = execute_lsv_analysis(workflow.build_request(records))
    figure, series = build_selected_potential_figure(result, "signed", include_hover_metadata=True)
    try:
        assert "UserConfirmedID" in {point.sample_id for item in series for point in item.points}
    finally:
        import matplotlib.pyplot as plt
        plt.close(figure)
