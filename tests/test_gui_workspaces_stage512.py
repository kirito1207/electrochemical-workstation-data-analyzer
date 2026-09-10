from __future__ import annotations

import importlib
import sys

from chi_gui.controller import GUIController
from chi_gui.workspaces import WorkspaceManager


def test_default_workspace_exists():
    manager = WorkspaceManager()

    assert len(manager.sessions) == 1
    assert manager.active.name == "工作区 1"
    assert manager.active.workspace_id == "workspace-1"


def test_create_and_switch_multiple_workspaces():
    manager = WorkspaceManager()
    second = manager.create()
    third = manager.create()

    assert [item.name for item in manager.sessions] == ["工作区 1", "工作区 2", "工作区 3"]
    assert manager.active is third
    assert manager.switch(second.workspace_id) is second


def test_file_state_is_isolated_between_workspaces(lsv_path, it_path):
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    first.state.add_records([GUIController().parse_one(lsv_path)])
    second.state.add_records([GUIController().parse_one(it_path)])

    assert [item.experiment_type for item in first.state.records] == ["LSV"]
    assert [item.experiment_type for item in second.state.records] == ["i-t"]


def test_selected_file_and_current_technique_are_workspace_local(lsv_path, it_path):
    controller = GUIController()
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    lsv = controller.parse_one(lsv_path)
    it = controller.parse_one(it_path)
    first.state.add_records([lsv])
    second.state.add_records([it])
    first.current_route = "LSV"
    first.selected_by_route["LSV"] = lsv.key
    second.current_route = "i-t"
    second.selected_by_route["i-t"] = it.key

    assert manager.switch(first.workspace_id).selected_by_route["LSV"] == lsv.key
    assert manager.active.current_route == "LSV"
    assert manager.switch(second.workspace_id).selected_by_route["i-t"] == it.key
    assert manager.active.current_route == "i-t"


def test_visibility_is_independent_between_workspaces(lsv_path):
    record = GUIController().parse_one(lsv_path)
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    first.state.add_records([record])
    second.state.add_records([record])

    first.preview_display.set_visible(record.key, False)

    assert not first.preview_display.is_visible(record.key)
    assert second.preview_display.is_visible(record.key)


def test_curve_colors_are_workspace_local_and_stable(lsv_path, it_path):
    controller = GUIController()
    lsv = controller.parse_one(lsv_path)
    it = controller.parse_one(it_path)
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()

    first_lsv_color = first.preview_display.color_for(lsv.key)
    first.preview_display.color_for(it.key)
    second_lsv_color = second.preview_display.color_for(lsv.key)

    assert first.preview_display.color_for(lsv.key) == first_lsv_color
    assert second.preview_display.color_for(lsv.key) == second_lsv_color
    first.preview_display.set_visible(lsv.key, False)
    assert second.preview_display.is_visible(lsv.key)


def test_clear_only_affects_current_workspace(lsv_path, it_path):
    controller = GUIController()
    manager = WorkspaceManager()
    first = manager.active
    first.state.add_records([controller.parse_one(lsv_path)])
    second = manager.create()
    second.state.add_records([controller.parse_one(it_path)])

    manager.active.clear_data()

    assert second.state.records == ()
    assert len(first.state.records) == 1
    assert lsv_path.exists() and it_path.exists()


def test_close_workspace_does_not_change_other_workspace(lsv_path, it_path):
    controller = GUIController()
    manager = WorkspaceManager()
    first = manager.active
    first.state.add_records([controller.parse_one(lsv_path)])
    second = manager.create()
    second.state.add_records([controller.parse_one(it_path)])

    removed = manager.close(first.workspace_id)

    assert removed is first
    assert manager.sessions == (second,)
    assert len(second.state.records) == 1
    assert lsv_path.exists()


def test_duplicate_path_is_suppressed_only_within_each_workspace(lsv_path):
    record = GUIController().parse_one(lsv_path)
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()

    assert first.state.add_records([record, record]) == 1
    assert first.state.add_records([record]) == 0
    assert second.state.add_records([record]) == 1
    assert len(first.state.records) == len(second.state.records) == 1


def test_same_source_file_can_be_used_in_different_workspaces(lsv_path):
    record = GUIController().parse_one(lsv_path)
    manager = WorkspaceManager()
    first = manager.active
    first.state.add_records([record])
    second = manager.create("独立复核")
    second.state.add_records([record])

    assert first.state.records[0].path == second.state.records[0].path
    first.state.clear()
    assert len(second.state.records) == 1
    assert lsv_path.exists()


def test_rename_logs_and_workspace_are_not_scientific_groups():
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    manager.rename(first.workspace_id, "LSV 初次检查")
    first.log_messages.append("workspace-one-only")
    second.log_messages.append("workspace-two-only")

    assert first.name == "LSV 初次检查"
    assert first.log_messages == ["workspace-one-only"]
    assert second.log_messages == ["workspace-two-only"]
    assert not hasattr(first, "group")


def test_workspace_gui_modules_do_not_import_pb42():
    sys.modules.pop("presets.pb42", None)
    importlib.import_module("chi_gui.workspaces")
    importlib.import_module("chi_gui.widgets.workspace_tabs")

    assert "presets.pb42" not in sys.modules
