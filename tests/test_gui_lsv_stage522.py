from __future__ import annotations

from inspect import getsource
from pathlib import Path
from unittest.mock import Mock

import matplotlib.pyplot as plt
import numpy as np
import pytest

from analysis import AnalysisSettings, compare_defined_groups
from chi_gui.controller import GUIController
from chi_gui.layout import (
    CURVE_FILENAME_DISPLAY_CHARS,
    DATA_PAGE_LEFT_MIN_PX,
    DATA_PAGE_RIGHT_MIN_PX,
    DataPageLayoutState,
    compact_filename,
)
from chi_gui.lsv_workflow import (
    ComparisonDraft,
    LSVWorkflowState,
    comparison_draft_error,
    descriptive_display_rows,
    execute_lsv_analysis,
    result_summary_text,
)
from chi_gui.main_window import MainWindow
from chi_gui.workspaces import WorkspaceManager
from plotting.lsv_mean import build_mean_lsv_figure
from plotting.lsv_raw import build_raw_lsv_figure
from plotting.repeatability import build_repeatability_figure
from plotting.selected_potential import build_selected_potential_figure


def _copy_records(tmp_path: Path, lsv_path: Path, count: int):
    source = lsv_path.read_bytes()
    paths = []
    for index in range(count):
        path = tmp_path / f"stage522-{index + 1}.bin"
        raw = bytearray(source)
        current = np.frombuffer(raw, dtype="<f4", count=400, offset=1453).copy()
        current += index * 0.02e-6
        raw[1453:] = current.astype("<f4").tobytes()
        path.write_bytes(raw)
        paths.append(path)
    return GUIController().parse_many(paths)


def _confirmed_workflow(records, groups: tuple[str, ...], *, add_bare: bool = False):
    workflow = LSVWorkflowState()
    workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"Confirmed-S{index + 1}")
        workflow.update_metadata(row.record_key, "group", groups[index % len(groups)])
        workflow.update_metadata(row.record_key, "electrode_type", "Material")
    if add_bare:
        workflow.update_metadata(workflow.metadata_rows[-1].record_key, "electrode_type", "Bare")
    workflow.confirm_metadata()
    return workflow


@pytest.fixture()
def stage522_records(tmp_path, lsv_path):
    return _copy_records(tmp_path, lsv_path, 13)


@pytest.fixture()
def four_group_result(stage522_records):
    workflow = _confirmed_workflow(
        stage522_records[:12],
        ("Control", "PB10", "PB20", "Long condition name"),
    )
    return execute_lsv_analysis(workflow.build_request(stage522_records[:12]))


@pytest.mark.parametrize("groups", (("A",), ("A", "B"), ("A", "B", "C"),
                                     ("A", "B", "C", "D"),
                                     ("G1", "G2", "G3", "G4", "G5", "G6")))
def test_one_two_three_four_and_n_material_groups_are_accepted(stage522_records, groups):
    count = max(len(groups) * 2, 3)
    workflow = _confirmed_workflow(stage522_records[:count], groups)
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:count]))
    assert result.groups == groups
    assert workflow.comparisons == []


def test_confirmed_material_groups_are_not_truncated_in_comparison_candidates(stage522_records):
    groups = ("Water", "PBS", "HighSalt", "pH6", "pH8", "Day3")
    workflow = _confirmed_workflow(stage522_records[:12], groups)
    assert workflow.comparison_groups == groups


def test_same_left_and_right_group_is_rejected_inline(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:4], ("A", "B"))
    draft = ComparisonDraft("A", "A")
    assert comparison_draft_error(draft, workflow.comparison_groups) == (
        "Left Group 与 Right Group 不能相同。"
    )
    with pytest.raises(ValueError, match="不能相同"):
        workflow.add_comparison(draft)


def test_arbitrary_pairwise_comparisons_and_multiple_rows_are_retained(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:8], ("A", "B", "C", "D"))
    declared = (
        ComparisonDraft("A", "B", "Primary", "primary", "A vs B"),
        ComparisonDraft("A", "D", "Primary", "primary", "A vs D"),
        ComparisonDraft("C", "D", "Exploratory", "", "C vs D"),
    )
    for draft in declared:
        workflow.add_comparison(draft)
    request = workflow.build_request(stage522_records[:8])
    assert [(item.left_group, item.right_group) for item in request.comparisons] == [
        ("A", "B"), ("A", "D"), ("C", "D")
    ]


def test_no_comparisons_is_valid_for_single_group(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:3], ("Only condition",))
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:3]))
    assert result.comparisons == ()
    assert result.summary("Only condition", "magnitude").statistics.n == 3


def test_single_material_group_with_one_sample_keeps_undefined_sd_cv_renderable(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:1], ("Only condition",))
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:1]))
    figures = (
        build_selected_potential_figure(result, "magnitude"),
        build_mean_lsv_figure(result, "ALL"),
        build_repeatability_figure(result),
    )
    try:
        assert np.isnan(result.summary("Only condition", "magnitude").statistics.sd)
        assert any(text.get_text() == "N/A" for text in figures[-1].axes[0].texts)
    finally:
        for figure in figures:
            plt.close(figure)


def test_three_group_descriptive_rows_include_every_group(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:9], ("A", "B", "C"))
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:9]))
    assert [row["group"] for row in descriptive_display_rows(result)] == ["A", "B", "C"]


@pytest.mark.parametrize("metric", ("magnitude", "signed"))
def test_four_group_selected_scatter_and_hover_metadata_include_all_groups(
    four_group_result, metric
):
    figure, series = build_selected_potential_figure(
        four_group_result, metric, include_hover_metadata=True
    )
    try:
        assert tuple(item.points[0].group for item in series) == four_group_result.groups
        assert sum(len(item.points) for item in series) == 12
        assert all(point.sample_id.startswith("Confirmed-S") for item in series for point in item.points)
    finally:
        plt.close(figure)


def test_four_group_mean_overlay_and_mean_sd_include_all_material_groups(four_group_result):
    overlay = build_mean_lsv_figure(four_group_result)
    mean_sd = build_mean_lsv_figure(four_group_result, "ALL")
    try:
        overlay_labels = {line.get_label() for line in overlay.axes[0].lines}
        assert all(any(f"Group {group} mean" in label for label in overlay_labels)
                   for group in four_group_result.groups)
        assert len(mean_sd.axes[0].collections) == 4
    finally:
        plt.close(overlay)
        plt.close(mean_sd)


def test_four_group_cv_plot_has_one_bar_per_group(four_group_result):
    figure = build_repeatability_figure(four_group_result)
    try:
        assert len(figure.axes[0].patches) == 4
        assert tuple(label.get_text() for label in figure.axes[0].get_xticklabels()) == four_group_result.groups
    finally:
        plt.close(figure)


def test_all_raw_plot_keeps_every_group_and_bare_control(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:13], ("A", "B", "C", "D"), add_bare=True)
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:13]))
    figure = build_raw_lsv_figure(result, "ALL")
    try:
        assert len(figure.axes[0].lines) == len(result.files) + 1  # curves + target line
        assert any(line.get_linestyle() == "--" for line in figure.axes[0].lines)
    finally:
        plt.close(figure)


def test_bare_same_group_is_allowed_but_excluded_from_material_summary(stage522_records):
    workflow = _confirmed_workflow(stage522_records[:4], ("Condition_A",), add_bare=True)
    result = execute_lsv_analysis(workflow.build_request(stage522_records[:4]))
    assert len(result.files) == 4
    assert result.summary("Condition_A", "magnitude").statistics.n == 3
    assert next(item for item in result.current_sign_qc if item.group == "Condition_A").total_count == 3


def test_holm_family_still_adjusts_only_declared_primary_welch(monkeypatch):
    monkeypatch.setattr(
        "analysis.statistics._bootstrap_intervals",
        lambda *args, **kwargs: (0.0, 0.0, 0.0, 0.0),
    )
    values = {name: np.linspace(index, index + 1, 5) for index, name in enumerate(("A", "B", "C", "D"))}
    definitions = tuple(
        draft.to_definition()
        for draft in (
            ComparisonDraft("A", "B", "Primary", "primary", "A-B"),
            ComparisonDraft("A", "C", "Primary", "primary", "A-C"),
            ComparisonDraft("C", "D", "Exploratory", "", "C-D"),
        )
    )
    results = compare_defined_groups(values, definitions, bootstrap_resamples=5000)
    welch = [item for item in results if item.test.startswith("Welch")]
    assert all(item.holm_adjusted_p is not None for item in welch[:2])
    assert welch[2].holm_adjusted_p is None


def test_summary_reports_group_count_names_and_comparison_count(four_group_result):
    text = result_summary_text(four_group_result)
    assert "Material 样本数：12" in text
    assert "Groups：4" in text
    assert "Group names：Control, PB10, PB20, Long condition name" in text
    assert "Comparisons：0" in text


def test_layout_policy_bounds_both_panes_and_remembers_user_fraction():
    state = DataPageLayoutState()
    assert state.sash_position(1000) == 620
    assert state.sash_position(500) == 220
    state.remember(1000, 700)
    assert state.sash_position(1200) == 840
    assert state.sash_position(700) >= DATA_PAGE_LEFT_MIN_PX
    assert 700 - state.sash_position(700) >= DATA_PAGE_RIGHT_MIN_PX


def test_long_filename_display_is_bounded_without_changing_source_value():
    source = "very-long-user-defined-electrochemical-file-name-" * 5 + ".bin"
    display = compact_filename(source)
    assert len(display) == CURVE_FILENAME_DISPLAY_CHARS
    assert display.startswith(source[:10]) and display.endswith(".bin")
    assert len(source) > len(display)


def test_workflow_pages_have_independent_layout_responsibility():
    source = getsource(MainWindow._build_layout)
    assert "self.data_panes = tk.PanedWindow" in source
    assert "frame.grid_propagate(False)" in source
    assert "minsize=DATA_PAGE_LEFT_MIN_PX" in source
    assert "minsize=DATA_PAGE_RIGHT_MIN_PX" in source


def test_result_refresh_does_not_modify_data_page_sash():
    window = object.__new__(MainWindow)
    window.workspace_manager = WorkspaceManager()
    window.lsv_settings = Mock()
    window.lsv_results = Mock()
    window.lsv_figures = Mock()
    window.data_panes = Mock()
    window.runner = Mock(busy=False)
    window.current_route = "LSV"
    window.workflow_tabs = Mock()
    window.figures_tab = object()
    window.workflow_tabs.select.return_value = "data-page"
    window._refresh_lsv_workflow()
    window.data_panes.sash_place.assert_not_called()


def test_data_tab_switch_restores_layout_without_rendering_result_page():
    window = object.__new__(MainWindow)
    window.workspace_manager = WorkspaceManager()
    window.current_route = "LSV"
    window.workflow_tabs = Mock()
    window.data_tab = object()
    window.figures_tab = object()
    window.workflow_tabs.select.return_value = str(window.data_tab)
    window._schedule_data_layout = Mock()
    window.lsv_figures = Mock()
    window._workflow_tab_changed()
    window._schedule_data_layout.assert_called_once_with(force=True)
    window.lsv_figures.render.assert_not_called()


def test_workspace_multi_group_states_remain_isolated(stage522_records):
    manager = WorkspaceManager()
    first = manager.active
    first.lsv_workflow = _confirmed_workflow(stage522_records[:6], ("A", "B", "C"))
    first.lsv_workflow.add_comparison(ComparisonDraft("A", "C", name="A-C"))
    second = manager.create()
    second.lsv_workflow = _confirmed_workflow(stage522_records[6:10], ("X", "Y"))
    assert first.lsv_workflow.comparison_groups == ("A", "B", "C")
    assert second.lsv_workflow.comparison_groups == ("X", "Y")
    assert [item.name for item in first.lsv_workflow.comparisons] == ["A-C"]
    assert second.lsv_workflow.comparisons == []
