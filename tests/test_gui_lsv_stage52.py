from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from time import sleep

import numpy as np
import pytest

from analysis import AnalysisSettings
from chi_gui.background import BackgroundRunner
from chi_gui.controller import GUIController
from chi_gui.lsv_export import export_lsv_result
from chi_gui.lsv_workflow import (
    ComparisonDraft,
    GUIWorkflowValidationError,
    LSVAnalysisCompleted,
    LSVWorkflowState,
    StaleAnalysisResultError,
    comparison_display_rows,
    descriptive_display_rows,
    execute_lsv_analysis,
    sign_qc_display_rows,
    validate_lsv_workflow,
)
from chi_gui.workspaces import WorkspaceManager
from plotting.lsv_mean import build_mean_lsv_figure
from plotting.lsv_raw import build_raw_lsv_figure
from plotting.repeatability import build_repeatability_figure
from plotting.selected_potential import build_selected_potential_figure


def _records(tmp_path: Path, source: Path, count: int = 4):
    raw = source.read_bytes()
    paths = []
    for index in range(count):
        path = tmp_path / f"样本 空格 {index + 1}.bin"
        changed = bytearray(raw)
        current = np.frombuffer(changed, dtype="<f4", count=400, offset=1453).copy()
        current += index * 0.05e-6
        changed[1453:] = current.astype("<f4").tobytes()
        path.write_bytes(changed)
        paths.append(path)
    return GUIController().parse_many(paths)


def _ready_workflow(records):
    workflow = LSVWorkflowState()
    workflow.sync_records(records)
    for index, row in enumerate(workflow.metadata_rows):
        workflow.update_metadata(row.record_key, "sample_id", f"E{index + 1}")
        workflow.update_metadata(row.record_key, "group", "Control" if index < 2 else "PB10")
        workflow.update_metadata(row.record_key, "electrode_type", "Material")
    workflow.confirm_metadata()
    workflow.replace_comparisons((ComparisonDraft("Control", "PB10", "Primary", "primary", "Control-PB10"),))
    return workflow


def test_sync_creates_unconfirmed_editable_suggestions(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path, 2)
    workflow = LSVWorkflowState()
    workflow.sync_records(records)
    assert len(workflow.metadata_rows) == 2
    assert all(row.include for row in workflow.metadata_rows)
    assert not workflow.has_confirmed_manifest
    assert "尚未确认" in workflow.manifest_status


def test_metadata_requires_explicit_confirmation(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path, 2)
    workflow = LSVWorkflowState(); workflow.sync_records(records)
    with pytest.raises(GUIWorkflowValidationError):
        workflow.build_request(records)


def test_edit_then_confirm_generic_manifest(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records)
    assert workflow.confirmed_manifest.user_confirmed
    assert {entry.group for entry in workflow.confirmed_manifest.entries} == {"Control", "PB10"}


def test_include_is_independent_and_excludes_only_manifest_row(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records)
    workflow.update_metadata(records[0].key, "include", False)
    workflow.confirm_metadata()
    assert len(workflow.metadata_rows) == 4
    assert len(workflow.confirmed_manifest.entries) == 3


def test_bare_allowed_but_not_counted_as_material(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path, 5)
    workflow = _ready_workflow(records[:4])
    workflow.sync_records(records)
    row = workflow.metadata_rows[-1]
    workflow.update_metadata(row.record_key, "sample_id", "Bare1")
    workflow.update_metadata(row.record_key, "group", "Control")
    workflow.update_metadata(row.record_key, "electrode_type", "Bare")
    workflow.confirm_metadata()
    request = workflow.build_request(records)
    result = execute_lsv_analysis(request)
    assert result.summary("Control", "magnitude").statistics.n == 2
    assert len(result.files) == 5


def test_generic_mode_allows_no_bare(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records)
    result = execute_lsv_analysis(workflow.build_request(records))
    assert all(item.manifest.electrode_type == "Material" for item in result.files)


@pytest.mark.parametrize("target", (0.0, -0.05, 0.0255))
def test_configurable_target_reaches_backend(tmp_path, lsv_path, target):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); workflow.set_target_potential(target)
    result = execute_lsv_analysis(workflow.build_request(records))
    assert result.settings.target_potential_V == pytest.approx(target)
    assert all(item.selected.target_potential_V == pytest.approx(target) for item in result.files)


def test_out_of_range_target_is_rejected_before_worker(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); workflow.set_target_potential(0.3)
    assert any("共同范围" in item for item in validate_lsv_workflow(workflow, records))


def test_signed_and_magnitude_are_forwarded(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); workflow.set_metric("signed")
    result = execute_lsv_analysis(workflow.build_request(records))
    assert result.settings.analysis_metric == "signed"
    assert all(item.selected.response_magnitude_uA == abs(item.selected.current_uA) for item in result.files)


def test_user_comparison_and_holm_family(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records)
    result = execute_lsv_analysis(workflow.build_request(records))
    welch = next(item for item in result.comparisons if item.test.startswith("Welch"))
    assert welch.comparison == "Control-PB10"
    assert welch.holm_family == "primary"
    assert welch.holm_adjusted_p is not None


def test_exploratory_holm_family_is_rejected(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records)
    workflow.replace_comparisons((ComparisonDraft("Control", "PB10", "Exploratory", "bad"),))
    assert any("Exploratory" in item for item in validate_lsv_workflow(workflow, records))


def test_result_becomes_stale_after_setting_change(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); request = workflow.build_request(records)
    workflow.accept_result(request, execute_lsv_analysis(request))
    workflow.set_target_potential(-0.05)
    assert workflow.result_stale
    with pytest.raises(StaleAnalysisResultError): workflow.require_exportable_result()


def test_result_display_tables_are_derived_from_backend_result(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); request = workflow.build_request(records)
    result = execute_lsv_analysis(request)
    assert len(descriptive_display_rows(result)) == 2
    assert len(comparison_display_rows(result)) == 1
    assert {row["group"] for row in sign_qc_display_rows(result)} == {"Control", "PB10", "ALL"}


def test_analysis_runs_through_background_queue(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    workflow = _ready_workflow(records); request = workflow.build_request(records)
    runner = BackgroundRunner()
    runner.submit(lambda _cancel, _emit: LSVAnalysisCompleted("workspace-1", request, execute_lsv_analysis(request)))
    assert runner.join(30)
    events = runner.drain()
    completed = next(event.payload for event in events if event.kind == "result")
    assert completed.workspace_id == "workspace-1"
    assert completed.result.settings.target_potential_V == 0.0


def test_workspace_lsv_workflows_are_isolated():
    manager = WorkspaceManager(); first = manager.active
    first.lsv_workflow.target_potential_V = -0.05
    second = manager.create(); second.lsv_workflow.target_potential_V = 0.025
    assert first.lsv_workflow.target_potential_V == -0.05
    assert second.lsv_workflow.target_potential_V == 0.025


def test_clear_workspace_clears_only_its_analysis_state():
    manager = WorkspaceManager(); first = manager.active
    first.lsv_workflow.target_potential_V = -0.05
    second = manager.create(); second.lsv_workflow.target_potential_V = 0.025
    second.clear_data()
    assert second.lsv_workflow.target_potential_V == 0.0
    assert first.lsv_workflow.target_potential_V == -0.05


def test_export_uses_current_result_without_reanalysis(tmp_path, synthetic_analysis_result):
    run = export_lsv_result(synthetic_analysis_result, tmp_path)
    assert run.result is synthetic_analysis_result
    assert (run.output_directory / "LSV/excel/LSV_analysis.xlsx").exists()
    assert (run.output_directory / "LSV/csv/selected_potential_data.csv").exists()
    assert any(path.suffix == ".svg" for path in run.generated_files)
    assert any(path.suffix == ".pdf" for path in run.generated_files)


def test_export_never_overwrites_timestamp_directory(tmp_path, synthetic_analysis_result):
    first = export_lsv_result(synthetic_analysis_result, tmp_path)
    second = export_lsv_result(synthetic_analysis_result, tmp_path)
    assert first.output_directory != second.output_directory


def test_all_result_figure_builders_accept_backend_result(synthetic_analysis_result):
    figures = (
        build_raw_lsv_figure(synthetic_analysis_result, "A"),
        build_mean_lsv_figure(synthetic_analysis_result, "A"),
        build_mean_lsv_figure(synthetic_analysis_result),
        build_selected_potential_figure(synthetic_analysis_result, "magnitude"),
        build_selected_potential_figure(synthetic_analysis_result, "signed"),
        build_repeatability_figure(synthetic_analysis_result),
    )
    try:
        assert all(figure.axes for figure in figures)
    finally:
        import matplotlib.pyplot as plt
        for figure in figures: plt.close(figure)


def test_workflow_does_not_import_pb42_preset():
    import sys
    sys.modules.pop("presets.pb42", None)
    __import__("chi_gui.lsv_workflow")
    assert "presets.pb42" not in sys.modules


def test_workflow_never_changes_source_bin(tmp_path, lsv_path):
    records = _records(tmp_path, lsv_path)
    before = {record.path: record.path.read_bytes() for record in records}
    workflow = _ready_workflow(records)
    execute_lsv_analysis(workflow.build_request(records))
    assert all(path.read_bytes() == raw for path, raw in before.items())
