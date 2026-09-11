from __future__ import annotations

from unittest.mock import Mock

import numpy as np
import pytest

from analysis import AnalysisSettings
from chi_gui.controller import GUIController
from chi_gui.cursor import (
    build_cursor_readings,
    format_cursor_input,
    parse_cursor_input,
    read_cursor_value,
    step_cursor_on_axis,
)
from chi_gui.main_window import MainWindow
from chi_gui.workspaces import WorkspaceManager


def _headless_window(records, route):
    window = object.__new__(MainWindow)
    window.controller = GUIController()
    window.workspace_manager = WorkspaceManager()
    window.workspace.current_route = route
    window.workspace.state.add_records(list(records))
    selected = next(record for record in records if record.experiment_type == route)
    window.workspace.selected_by_route[route] = selected.key
    window.current_record = selected
    window._render_technique_preview = Mock()
    return window


def _collection(window, route):
    return window.controller.build_preview_collection(
        window.state.records,
        experiment_type=route,
        display_state=window.preview_display,
        selected_key=window.selected_by_route[route],
    )


def test_lsv_numeric_exact_sample_input_uses_raw_point(lsv_path):
    record = GUIController().parse_one(lsv_path)
    exact = float(record.data.potential_V[150])
    window = _headless_window((record,), "LSV")

    window._cursor_submitted(format_cursor_input("LSV", exact))
    reading = read_cursor_value(record, window.workspace.cursor_by_route["LSV"].requested_x)

    assert window.workspace.cursor_by_route["LSV"].visible
    assert not reading.interpolated
    assert reading.actual_sampled_x == exact


def test_lsv_numeric_interpolated_input(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window((record,), "LSV")

    window._cursor_submitted("0.0255")
    reading = read_cursor_value(record, 0.0255)

    assert window.workspace.cursor_by_route["LSV"].requested_x == 0.0255
    assert reading.interpolated
    assert reading.lower_x < 0.0255 < reading.upper_x


def test_lsv_out_of_range_is_silent_and_has_no_reading(lsv_path, monkeypatch):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window((record,), "LSV")
    popup = Mock(side_effect=AssertionError("numeric cursor must not show a popup"))
    monkeypatch.setattr("chi_gui.main_window.messagebox.showerror", popup)
    monkeypatch.setattr("chi_gui.main_window.messagebox.showwarning", popup)
    monkeypatch.setattr("chi_gui.main_window.messagebox.showinfo", popup)

    assert window._apply_cursor_value(0.25, input_text="0.25") is False
    cursor = window.workspace.cursor_by_route["LSV"]
    readings = window._cursor_readings(_collection(window, "LSV"), "LSV")

    assert not cursor.visible
    assert cursor.requested_x is None
    assert cursor.validation_message == "超出范围"
    assert readings is None
    popup.assert_not_called()


def test_lsv_left_and_right_use_real_axis_samples():
    axis = np.array([-0.2, -0.13, -0.05, 0.025, 0.199])

    assert step_cursor_on_axis(axis, -0.05, -1) == -0.13
    assert step_cursor_on_axis(axis, -0.05, 1) == 0.025


def test_interpolated_position_steps_to_bracketing_real_samples():
    axis = np.array([-0.2, -0.13, -0.05, 0.025, 0.199])

    assert step_cursor_on_axis(axis, -0.09, -1) == -0.13
    assert step_cursor_on_axis(axis, -0.09, 1) == -0.05


def test_lsv_boundary_keys_remain_at_boundary():
    axis = np.array([-0.2, -0.13, -0.05, 0.025, 0.199])

    assert step_cursor_on_axis(axis, axis[0], -1) == axis[0]
    assert step_cursor_on_axis(axis, axis[-1], 1) == axis[-1]


def test_it_numeric_input_and_nearest_sample_are_separate(it_path):
    record = GUIController().parse_one(it_path)
    window = _headless_window((record,), "i-t")

    window._cursor_submitted("125.04")
    reading = read_cursor_value(record, 125.04)

    assert window.workspace.cursor_by_route["i-t"].requested_x == 125.04
    assert reading.requested_x == 125.04
    assert reading.actual_sampled_x == pytest.approx(125.0)


def test_it_left_and_right_use_real_time_samples():
    time_s = np.array([0.1, 0.2, 0.35, 0.5])

    assert step_cursor_on_axis(time_s, 0.28, -1) == 0.2
    assert step_cursor_on_axis(time_s, 0.28, 1) == 0.35
    assert step_cursor_on_axis(time_s, 0.1, -1) == 0.1
    assert step_cursor_on_axis(time_s, 0.5, 1) == 0.5


@pytest.mark.parametrize("text", ("", "not-a-number", "NaN", "inf", "-inf"))
def test_invalid_or_nonfinite_input_is_handled_silently(lsv_path, text):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window((record,), "LSV")

    window._cursor_submitted(text)
    cursor = window.workspace.cursor_by_route["LSV"]

    assert parse_cursor_input(text) is None
    assert not cursor.visible
    assert cursor.requested_x is None
    assert cursor.input_text == text
    assert cursor.validation_message == "请输入有限数值"


def test_workspace_cursor_and_input_text_are_isolated():
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    first.cursor_by_route["LSV"].set(-0.0505, input_text="-0.0505")
    second.cursor_by_route["LSV"].set(0.0255, input_text="0.0255")

    assert first.cursor_by_route["LSV"].input_text == "-0.0505"
    assert first.cursor_by_route["LSV"].requested_x == -0.0505
    assert second.cursor_by_route["LSV"].input_text == "0.0255"
    assert second.cursor_by_route["LSV"].requested_x == 0.0255


def test_main_window_step_from_interpolated_lsv_uses_neighbor_samples(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window((record,), "LSV")
    cursor = window.workspace.cursor_by_route["LSV"]
    cursor.set(-0.0505, input_text="-0.0505")

    window._cursor_step(-1)
    left = cursor.requested_x
    cursor.set(-0.0505, input_text="-0.0505")
    window._cursor_step(1)
    right = cursor.requested_x

    assert left == pytest.approx(-0.051)
    assert right == pytest.approx(-0.050)


def test_numeric_cursor_does_not_change_analysis_or_preview_membership(lsv_path):
    record = GUIController().parse_one(lsv_path)
    window = _headless_window((record,), "LSV")
    settings = AnalysisSettings(target_potential_V=-0.075)
    before = record.data.current_A.copy()

    window._cursor_submitted("0.0255")
    collection = _collection(window, "LSV")
    readings = build_cursor_readings(window.state.records, collection, 0.0255)

    assert settings.target_potential_V == -0.075
    assert len(collection.visible_curves) == len(readings.readings) == 1
    np.testing.assert_array_equal(record.data.current_A, before)
