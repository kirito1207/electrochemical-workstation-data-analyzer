from __future__ import annotations

import importlib
import sys

import numpy as np
import pytest

from analysis import AnalysisSettings
from analysis.potential import PotentialOutOfRangeError, extract_current_at_potential
from chi_gui.controller import GUIController
from chi_gui.cursor import build_cursor_readings, read_cursor_value
from chi_gui.state import PreviewDisplayState
from chi_gui.workspaces import WorkspaceManager


def _collection(records, technique, display, selected=None):
    return GUIController().build_preview_collection(
        records,
        experiment_type=technique,
        display_state=display,
        selected_key=selected,
    )


def _copies(tmp_path, source, prefix, count):
    raw = source.read_bytes()
    paths = []
    for index in range(count):
        path = tmp_path / f"{prefix}_{index + 1}.bin"
        path.write_bytes(raw)
        paths.append(path)
    return tuple(paths)


def test_lsv_raw_point_cursor_uses_existing_extraction(lsv_path):
    record = GUIController().parse_one(lsv_path)
    requested = float(record.data.potential_V[150])

    reading = read_cursor_value(record, requested)
    expected = extract_current_at_potential(record.data, requested)

    assert reading.current_A == expected.current_A
    assert reading.actual_sampled_x == requested
    assert not reading.interpolated


def test_lsv_interpolated_cursor_uses_existing_extraction(lsv_path):
    record = GUIController().parse_one(lsv_path)

    reading = read_cursor_value(record, 0.0255)
    expected = extract_current_at_potential(record.data, 0.0255)

    assert reading.current_A == expected.current_A
    assert reading.interpolated
    assert reading.actual_sampled_x is None
    assert reading.lower_x == expected.lower_potential_V
    assert reading.upper_x == expected.upper_potential_V


def test_lsv_cursor_forbids_out_of_range_extrapolation(lsv_path):
    record = GUIController().parse_one(lsv_path)

    with pytest.raises(PotentialOutOfRangeError):
        read_cursor_value(record, 0.25)


def test_multiple_visible_curves_return_inline_readings(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "multi", 3))
    collection = _collection(records, "LSV", PreviewDisplayState())

    readings = build_cursor_readings(records, collection, 0.0)

    assert len(readings.readings) == 3
    assert all(reading.available for reading in readings.readings)


def test_invisible_curve_is_absent_from_cursor_readings(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "hidden", 3))
    display = PreviewDisplayState()
    display.set_visible(records[1].key, False)
    collection = _collection(records, "LSV", display)

    readings = build_cursor_readings(records, collection, 0.0)

    assert {item.record_key for item in readings.readings} == {records[0].key, records[2].key}


def test_selected_file_does_not_change_other_cursor_readings(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "selected", 3))
    display = PreviewDisplayState()
    before = build_cursor_readings(records, _collection(records, "LSV", display), -0.05)
    after = build_cursor_readings(
        records,
        _collection(records, "LSV", display, selected=records[2].key),
        -0.05,
    )

    assert before.readings == after.readings


def test_it_cursor_uses_nearest_sample_and_retains_both_times(it_path):
    record = GUIController().parse_one(it_path)
    requested = 125.04

    reading = read_cursor_value(record, requested)
    index = int(np.argmin(np.abs(record.data.time_s - requested)))

    assert reading.requested_x == requested
    assert reading.actual_sampled_x == pytest.approx(record.data.time_s[index])
    assert reading.current_A == pytest.approx(record.data.current_A[index])
    assert not reading.interpolated


def test_inspection_cursor_does_not_change_formal_analysis_setting(lsv_path):
    settings = AnalysisSettings(target_potential_V=-0.05)
    record = GUIController().parse_one(lsv_path)

    read_cursor_value(record, 0.0255)

    assert settings.target_potential_V == -0.05


def test_cursor_reading_does_not_modify_raw_arrays(lsv_path, it_path):
    records = (GUIController().parse_one(lsv_path), GUIController().parse_one(it_path))
    originals = [
        (item.data.potential_V if item.experiment_type == "LSV" else item.data.time_s).copy()
        for item in records
    ]
    currents = [item.data.current_A.copy() for item in records]

    read_cursor_value(records[0], 0.0255)
    read_cursor_value(records[1], 125.04)

    for record, x_before, current_before in zip(records, originals, currents, strict=True):
        x_after = record.data.potential_V if record.experiment_type == "LSV" else record.data.time_s
        np.testing.assert_array_equal(x_after, x_before)
        np.testing.assert_array_equal(record.data.current_A, current_before)


def test_workspace_cursor_positions_are_independent():
    manager = WorkspaceManager()
    first = manager.active
    second = manager.create()
    first.cursor_by_route["LSV"].set(-0.05)
    second.cursor_by_route["LSV"].set(0.025)
    second.cursor_by_route["i-t"].set(125.0)

    assert first.cursor_by_route["LSV"].requested_x == -0.05
    assert not first.cursor_by_route["i-t"].visible
    assert second.cursor_by_route["LSV"].requested_x == 0.025
    assert second.cursor_by_route["i-t"].requested_x == 125.0


def test_remove_file_synchronizes_reading_list(tmp_path, lsv_path):
    paths = _copies(tmp_path, lsv_path, "remove_cursor", 3)
    manager = WorkspaceManager()
    session = manager.active
    session.state.add_records(GUIController().parse_many(paths))
    session.cursor_by_route["LSV"].set(0.0)
    removed_key = session.state.records[1].key
    session.state.remove([paths[1]])
    collection = _collection(session.state.records, "LSV", session.preview_display)

    readings = build_cursor_readings(session.state.records, collection, 0.0)

    assert len(readings.readings) == 2
    assert removed_key not in {item.record_key for item in readings.readings}


def test_clear_workspace_clears_cursor_and_readings(lsv_path):
    manager = WorkspaceManager()
    session = manager.active
    session.state.add_records([GUIController().parse_one(lsv_path)])
    session.cursor_by_route["LSV"].set(0.0)

    session.clear_data()
    collection = _collection(session.state.records, "LSV", session.preview_display)

    assert collection.curves == ()
    assert not session.cursor_by_route["LSV"].visible
    assert session.cursor_by_route["LSV"].requested_x is None


def test_curve_colors_stay_stable_after_cursor_updates(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "colors", 3))
    display = PreviewDisplayState()
    collection = _collection(records, "LSV", display)
    colors_before = {curve.record_key: curve.color for curve in collection.curves}

    build_cursor_readings(records, collection, -0.05)
    refreshed = _collection(records, "LSV", display, selected=records[-1].key)

    assert {curve.record_key: curve.color for curve in refreshed.curves} == colors_before


def test_cursor_gui_import_does_not_load_pb42_preset():
    sys.modules.pop("presets.pb42", None)
    importlib.import_module("chi_gui.cursor")
    importlib.import_module("chi_gui.main_window")

    assert "presets.pb42" not in sys.modules
