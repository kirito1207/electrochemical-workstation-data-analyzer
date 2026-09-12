from __future__ import annotations

from inspect import getsource
import tkinter as tk
from tkinter import simpledialog

import pytest

from chi_gui.it_workflow import ITMetadataDraftRow, ITWorkflowState
from chi_gui.widgets.it_analysis import ITSettingsPanel, it_group_choices


def _workflow():
    return ITWorkflowState(metadata_rows=[
        ITMetadataDraftRow(f"r{i}", f"sample-{i}.bin", sample_id=f"S{i}",
                           group="A" if i <= 2 else "B")
        for i in range(1, 6)
    ])


@pytest.fixture
def panel_harness():
    root = tk.Tk(); root.geometry("1000x760")
    workflow = _workflow()
    holder = {}

    def changed(action, *values):
        assert action == "batch_metadata"
        workflow.batch_update_metadata(*values)
        holder["panel"].render(workflow, workspace_token="workspace-1")

    panel = ITSettingsPanel(
        root, on_change=changed, on_confirm_metadata=lambda: None,
        on_confirm_timeline=lambda: None, on_add_cursor_event=lambda: None,
        on_run=lambda: None,
    )
    holder["panel"] = panel
    panel.pack(fill="both", expand=True)
    panel.render(workflow, workspace_token="workspace-1")
    root.update()
    try:
        yield root, panel, workflow
    finally:
        root.destroy()


def test_inline_bar_matches_lsv_control_direction_and_removes_generic_dialog():
    source = getsource(ITSettingsPanel.__init__)
    for label in ("全选", "取消选择", "设置 Group", "纳入", "不纳入", "设置备注"):
        assert label in source
    assert 'text="批量设置选中行"' not in source
    assert "ITMetadataBatchDialog" not in source
    assert 'state="normal"' in source  # editable Group Combobox


def test_multi_row_group_apply_preserves_selection_on_combobox_focus(panel_harness):
    root, panel, workflow = panel_harness
    selected = ("r1", "r2", "r3")
    panel.metadata.selection_set(selected)
    panel.batch_group.focus_set(); root.update()
    assert panel.metadata.selection() == selected
    panel.batch_group.set("PB_A")
    panel._batch_group()
    assert [row.group for row in workflow.metadata_rows] == ["PB_A", "PB_A", "PB_A", "B", "B"]
    assert panel.metadata.selection() == selected
    assert "PB_A" in tuple(panel.batch_group["values"])


def test_one_row_group_apply_and_empty_group_match_lsv_semantics(panel_harness):
    _root, panel, workflow = panel_harness
    panel.metadata.selection_set(("r4",))
    panel.batch_group.set("C"); panel._batch_group()
    assert workflow.metadata_row("r4").group == "C"
    panel.batch_group.set(""); panel._batch_group()
    assert workflow.metadata_row("r4").group == ""
    assert all(row.sample_id == f"S{i}" for i, row in enumerate(workflow.metadata_rows, start=1))


def test_no_selection_group_apply_has_clear_inline_feedback(panel_harness):
    _root, panel, workflow = panel_harness
    panel.clear_selection(); panel.batch_group.set("C"); panel._batch_group()
    assert "请先选择要设置的样本" in workflow.feedback.text


def test_group_combobox_lists_existing_groups(panel_harness):
    _root, panel, workflow = panel_harness
    assert it_group_choices(workflow.metadata_rows) == ("A", "B")
    assert tuple(panel.batch_group["values"]) == ("A", "B")


def test_inline_include_true_false_changes_only_selected(panel_harness):
    _root, panel, workflow = panel_harness
    panel.metadata.selection_set(("r2", "r4")); panel._batch_include(False)
    assert [row.include for row in workflow.metadata_rows] == [True, False, True, False, True]
    panel._batch_include(True)
    assert all(row.include for row in workflow.metadata_rows)


def test_notes_dialog_applies_only_selected_and_can_clear(monkeypatch, panel_harness):
    _root, panel, workflow = panel_harness
    panel.metadata.selection_set(("r1", "r5"))
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "同一条件")
    panel._batch_notes()
    assert [row.notes for row in workflow.metadata_rows] == ["同一条件", "", "", "", "同一条件"]
    monkeypatch.setattr(simpledialog, "askstring", lambda *a, **k: "")
    panel._batch_notes()
    assert all(row.notes == "" for row in workflow.metadata_rows)


def test_batch_invalidation_stale_override_and_sample_id_invariants(panel_harness):
    _root, panel, workflow = panel_harness
    workflow.metadata_confirmed = True
    workflow.analysis_result = object()
    override = workflow.create_sample_override("r1")
    sample_ids = tuple(row.sample_id for row in workflow.metadata_rows)
    panel.metadata.selection_set(("r1", "r2")); panel.batch_group.set("C"); panel._batch_group()
    assert not workflow.metadata_confirmed
    assert workflow.result_stale
    assert workflow.sample_timeline_overrides["r1"] is override
    assert tuple(row.sample_id for row in workflow.metadata_rows) == sample_ids
    assert "样本信息已修改，请重新确认并运行分析" in workflow.feedback.text


def test_ctrl_a_and_clear_selection_remain_lsv_consistent(panel_harness):
    _root, panel, _workflow_state = panel_harness
    assert panel._select_all() == "break"
    assert panel.metadata.selection() == ("r1", "r2", "r3", "r4", "r5")
    panel.clear_selection()
    assert panel.metadata.selection() == ()
