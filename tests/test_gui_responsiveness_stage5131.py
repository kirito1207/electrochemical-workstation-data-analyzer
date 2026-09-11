from __future__ import annotations

from time import perf_counter
from unittest.mock import Mock

import pytest

from chi_gui.controller import GUIController
from chi_gui.cursor import build_cursor_readings
from chi_gui.main_window import MainWindow
from chi_gui.state import PreviewDisplayState
from chi_gui.widgets.file_table import FileTable, SelectionCallbackGate
from chi_gui.workspaces import WorkspaceManager


class FakeTree:
    """Minimal Treeview selection surface for display-free event tests."""

    def __init__(self, selection=()):
        self._selection = tuple(selection)
        self.selection_set_calls = 0
        self.selection_remove_calls = 0

    def selection(self):
        return self._selection

    def selection_set(self, key):
        self.selection_set_calls += 1
        self._selection = (key,)

    def selection_remove(self, _selection):
        self.selection_remove_calls += 1
        self._selection = ()

    def focus(self, _key):
        return None

    def see(self, _key):
        return None


class FileTableHarness:
    def __init__(self, records, callback, selection=()):
        self.tree = FakeTree(selection)
        self._records = {record.key: record for record in records}
        self._on_select = callback
        self._selection_gate = SelectionCallbackGate(last_token=tuple(selection))

    selected_records = FileTable.selected_records
    select_record = FileTable.select_record
    _selection_changed = FileTable._selection_changed


def _copy_files(tmp_path, source, prefix, count):
    raw = source.read_bytes()
    paths = []
    for index in range(count):
        path = tmp_path / f"{prefix}_{index + 1}.bin"
        path.write_bytes(raw)
        paths.append(path)
    return tuple(paths)


def _headless_window(record):
    window = object.__new__(MainWindow)
    window.workspace_manager = WorkspaceManager()
    window.workspace.current_route = "LSV"
    window.workspace.state.add_records([record])
    window.workspace.selected_by_route["LSV"] = record.key
    window.current_record = record
    window._render_technique_preview = Mock()
    window._render_parameters = Mock()
    return window


def test_programmatic_selection_of_selected_key_is_idempotent(lsv_path):
    record = GUIController().parse_one(lsv_path)
    table = FileTableHarness((record,), Mock(), selection=(record.key,))

    changed = table.select_record(record.key)

    assert changed is False
    assert table.tree.selection_set_calls == 0


def test_one_user_selection_change_produces_one_callback(tmp_path, lsv_path):
    records = GUIController().parse_many(_copy_files(tmp_path, lsv_path, "select", 2))
    callback = Mock()
    table = FileTableHarness(records, callback, selection=(records[0].key,))

    table.tree._selection = (records[1].key,)
    table._selection_changed(None)
    table._selection_changed(None)

    callback.assert_called_once_with(records[1])


def test_programmatic_selection_event_does_not_call_user_callback(lsv_path):
    record = GUIController().parse_one(lsv_path)
    callback = Mock()
    table = FileTableHarness((record,), callback)

    assert table.select_record(record.key) is True
    table._selection_changed(None)  # Simulate a delayed Windows <<TreeviewSelect>>.

    callback.assert_not_called()
    assert table.tree.selection_set_calls == 1


def test_selection_gate_blocks_synchronous_and_delayed_programmatic_events():
    gate = SelectionCallbackGate()

    gate.begin_programmatic_update()
    assert not gate.should_notify(("record-a",))
    gate.end_programmatic_update(("record-a",))

    assert not gate.should_notify(("record-a",))


def test_selected_render_does_not_recursively_reselect_same_record(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window(record)

    window._record_selected(record)

    window._render_technique_preview.assert_not_called()
    window._render_parameters.assert_not_called()


def test_switching_selected_records_causes_one_effective_render(tmp_path, lsv_path):
    records = GUIController().parse_many(_copy_files(tmp_path, lsv_path, "switch", 2))
    window = _headless_window(records[0])
    window.workspace.state.add_records([records[1]])

    window._record_selected(records[1])

    assert window.workspace.selected_by_route["LSV"] == records[1].key
    assert window.current_record == records[1]
    window._render_technique_preview.assert_called_once_with("LSV")


def test_import_initial_selection_and_delayed_event_do_not_repeat_render(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window(record)
    table = FileTableHarness((record,), window._record_selected)

    # The initial technique render has already chosen the first valid record.
    assert table.select_record(record.key) is True
    table._selection_changed(None)

    window._render_technique_preview.assert_not_called()
    assert table.tree.selection_set_calls == 1


def test_cursor_refresh_programmatic_reselection_cannot_recurse(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window(record)
    table = FileTableHarness((record,), window._record_selected, selection=(record.key,))

    # A cursor redraw synchronizes the same selected record at render completion.
    assert table.select_record(record.key) is False
    table._selection_changed(None)

    window._render_technique_preview.assert_not_called()


@pytest.mark.parametrize("count", (1, 14, 42))
def test_lsv_collection_and_cursor_scale_without_render_loop(tmp_path, lsv_path, count):
    paths = _copy_files(tmp_path, lsv_path, f"lsv_{count}", count)
    started = perf_counter()
    records = GUIController().parse_many(paths)
    collection = GUIController().build_preview_collection(
        records,
        experiment_type="LSV",
        display_state=PreviewDisplayState(),
    )
    readings = build_cursor_readings(records, collection, 0.0)
    elapsed = perf_counter() - started

    assert len(collection.curves) == count
    assert len(readings.readings) == count
    assert elapsed < 5.0


def test_multiple_it_files_build_preview_and_cursor_promptly(tmp_path, it_path):
    paths = _copy_files(tmp_path, it_path, "it_perf", 8)
    started = perf_counter()
    records = GUIController().parse_many(paths)
    collection = GUIController().build_preview_collection(
        records,
        experiment_type="i-t",
        display_state=PreviewDisplayState(),
    )
    readings = build_cursor_readings(records, collection, 125.0)
    elapsed = perf_counter() - started

    assert len(collection.curves) == len(readings.readings) == 8
    assert elapsed < 5.0
