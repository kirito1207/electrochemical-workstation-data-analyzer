from __future__ import annotations

from inspect import getsource

import pytest

from chi_gui.it_workflow import ITWorkflowState
from chi_gui.widgets.it_analysis import (
    FOOTER_MIN_TEXT_WRAP_PX,
    ITSettingsPanel,
    analysis_footer_wraplength,
    analysis_run_button_state,
    calibration_display_items,
    event_display_rows,
)


def test_deleted_internal_event_id_is_not_reused_but_display_indices_are_contiguous():
    workflow = ITWorkflowState()
    first = workflow.add_event(time_s=10, name="A")
    second = workflow.add_event(time_s=20, name="B")
    workflow.delete_events((first.event_id,))
    third = workflow.add_event(time_s=30, name="C")
    assert (first.event_id, second.event_id, third.event_id) == ("event_1", "event_2", "event_3")
    assert [row[0] for row in event_display_rows(workflow.events)] == [1, 2]
    assert len({event.event_id for event in workflow.events}) == len(workflow.events)


def test_sorting_changes_display_index_without_changing_internal_id():
    workflow = ITWorkflowState()
    first = workflow.add_event(time_s=10, name="First")
    second = workflow.add_event(time_s=20, name="Second")
    workflow.edit_event(second.event_id, time_s=5)
    assert [event.event_id for event in workflow.events] == [second.event_id, first.event_id]
    assert [row[0] for row in event_display_rows(workflow.events)] == [1, 2]
    assert next(event for event in workflow.events if event.name == "Second").event_id == second.event_id


def test_event_tree_hides_internal_id_but_uses_it_as_iid():
    init_source = getsource(ITSettingsPanel.__init__)
    render_source = getsource(ITSettingsPanel.render)
    assert 'columns=("index", "name", "time", "value", "unit", "notes")' in init_source
    assert 'iid=event.event_id' in render_source
    assert '"Event ID"' not in init_source


def test_override_display_indices_do_not_change_event_id_alignment():
    workflow = ITWorkflowState()
    workflow.add_event(time_s=10, name="A")
    workflow.add_event(time_s=20, name="B")
    workflow.add_event(time_s=30, name="C")
    # A minimal stable context is sufficient for presentation/state identity checks.
    from chi_gui.it_workflow import ITMetadataDraftRow
    workflow.metadata_rows.append(ITMetadataDraftRow("record-A", "A.bin", sample_id="A", group="G"))
    override = workflow.create_sample_override("record-A")
    workflow.delete_events(("event_2",))
    assert [event.event_id for event in override.events] == ["event_1", "event_3"]
    assert [row[0] for row in event_display_rows(override.events)] == [1, 2]


def test_override_delete_then_add_keeps_monotonic_ids_and_contiguous_display():
    workflow = ITWorkflowState()
    workflow.add_event(time_s=10, name="A")
    workflow.add_event(time_s=20, name="B")
    from chi_gui.it_workflow import ITMetadataDraftRow
    workflow.metadata_rows.append(ITMetadataDraftRow("record-A", "A.bin", sample_id="A", group="G"))
    override = workflow.create_sample_override("record-A")
    workflow.delete_events(("event_1",))
    added = workflow.add_event(time_s=30, name="C")
    assert added.event_id == "event_3"
    assert [event.event_id for event in override.events] == ["event_2", "event_3"]
    assert [row[0] for row in event_display_rows(override.events)] == [1, 2]


def test_calibration_labels_hide_internal_ids_but_mapping_retains_them():
    workflow = ITWorkflowState()
    first = workflow.add_event(time_s=10, name="H2O2", value=5, unit="µM")
    workflow.add_event(time_s=15, name="Light")
    third = workflow.add_event(time_s=20, name="H2O2", value=10, unit="µM")
    items = calibration_display_items(workflow.events)
    assert [event_id for event_id, _label in items] == [first.event_id, third.event_id]
    assert [label for _event_id, label in items] == ["1 | H2O2 | 5 µM", "3 | H2O2 | 10 µM"]
    assert all("event_" not in label for _event_id, label in items)


def test_footer_uses_grid_with_independent_action_column():
    source = getsource(ITSettingsPanel.__init__)
    assert "self.footer.columnconfigure(0, weight=1, minsize=0)" in source
    assert "self.footer.columnconfigure(1, weight=0)" in source
    assert 'self.footer_actions.grid(row=0, column=1, rowspan=2, sticky="e")' in source
    assert 'self.run_button.grid(row=0, column=0, sticky="e")' in source
    assert 'self.run_button.pack(' not in source


def test_long_status_feedback_and_narrow_width_use_bounded_wrapping():
    assert analysis_footer_wraplength(1000, 180) == 796
    assert analysis_footer_wraplength(360, 180) == FOOTER_MIN_TEXT_WRAP_PX
    source = getsource(ITSettingsPanel._footer_resized)
    assert "status_label.configure(wraplength=wraplength)" in source
    assert "feedback_label.configure(wraplength=wraplength)" in source


@pytest.mark.parametrize(
    ("scenario", "busy", "expected"),
    (
        ("normal short status", False, "normal"),
        ("stale long status " * 40, False, "normal"),
        ("long feedback " * 40, False, "normal"),
        ("validation error", False, "normal"),
        ("中文超长 Sample ID " * 40, False, "normal"),
        ("busy", True, "disabled"),
        ("analysis complete", False, "normal"),
        ("timeline override modification made result stale", False, "normal"),
    ),
)
def test_run_button_is_disabled_only_while_busy(scenario, busy, expected):
    assert scenario
    assert analysis_run_button_state(busy=busy) == expected
    source = getsource(ITSettingsPanel.render)
    assert "analysis_run_button_state(busy=busy)" in source
    assert "result_stale" not in source
    assert "validation_errors" not in source


def test_workspace_sequence_semantics_are_intentionally_unchanged():
    from chi_gui.workspaces import WorkspaceManager
    manager = WorkspaceManager()
    second = manager.create(); manager.close(second.workspace_id)
    third = manager.create()
    assert third.name == "工作区 3"
