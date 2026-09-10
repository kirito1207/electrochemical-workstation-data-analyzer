from __future__ import annotations

import hashlib
from pathlib import Path

import matplotlib as mpl
import numpy as np

from chi_gui.controller import GUIController
from chi_gui.matplotlib_config import configure_gui_matplotlib_fonts
from chi_gui.state import AppState, PreviewDisplayState
from chi_gui.widgets.plot_preview import downsample_for_display


def _copies(tmp_path: Path, source: Path, prefix: str, count: int) -> tuple[Path, ...]:
    raw = source.read_bytes()
    paths = []
    for index in range(count):
        path = tmp_path / f"{prefix}_{index + 1}.bin"
        path.write_bytes(raw)
        paths.append(path)
    return tuple(paths)


def _collection(records, technique, display, selected=None):
    return GUIController().build_preview_collection(
        records,
        experiment_type=technique,
        display_state=display,
        selected_key=selected,
    )


def test_windows_chinese_font_preference_and_minus_configuration():
    with mpl.rc_context():
        selected = configure_gui_matplotlib_fonts(
            ("DejaVu Sans", "SimHei", "Microsoft YaHei")
        )

        assert selected[:2] == ("Microsoft YaHei", "SimHei")
        assert mpl.rcParams["font.sans-serif"][:2] == ["Microsoft YaHei", "SimHei"]
        assert mpl.rcParams["axes.unicode_minus"] is False


def test_one_lsv_automatically_enters_preview_without_selection(lsv_path):
    records = GUIController().parse_many((lsv_path,))
    collection = _collection(records, "LSV", PreviewDisplayState())

    assert len(collection.curves) == 1
    assert collection.selected_key == records[0].key
    assert collection.curves[0].selected


def test_multiple_lsv_all_enter_same_lsv_preview(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "lsv", 4))
    collection = _collection(records, "LSV", PreviewDisplayState())

    assert len(collection.curves) == 4
    assert len(collection.visible_curves) == 4
    assert all(curve.data.experiment_type == "LSV" for curve in collection.curves)


def test_multiple_it_all_enter_same_it_preview(tmp_path, it_path):
    records = GUIController().parse_many(_copies(tmp_path, it_path, "it", 3))
    collection = _collection(records, "i-t", PreviewDisplayState())

    assert len(collection.curves) == 3
    assert all(curve.data.experiment_type == "i-t" for curve in collection.curves)


def test_lsv_and_it_are_never_in_same_preview_collection(lsv_path, it_path):
    records = GUIController().parse_many((lsv_path, it_path))
    display = PreviewDisplayState()
    lsv = _collection(records, "LSV", display)
    it = _collection(records, "i-t", display)

    assert len(lsv.curves) == len(it.curves) == 1
    assert {curve.data.experiment_type for curve in lsv.curves} == {"LSV"}
    assert {curve.data.experiment_type for curve in it.curves} == {"i-t"}


def test_selected_file_only_changes_highlight_not_curve_membership(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "sample", 3))
    display = PreviewDisplayState()
    before = _collection(records, "LSV", display)
    after = _collection(records, "LSV", display, selected=records[2].key)

    assert [curve.record_key for curve in before.curves] == [curve.record_key for curve in after.curves]
    assert len(after.curves) == 3
    assert [curve.selected for curve in after.curves] == [False, False, True]


def test_file_colors_remain_stable_across_refresh_and_selection(tmp_path, lsv_path):
    records = GUIController().parse_many(_copies(tmp_path, lsv_path, "stable", 5))
    display = PreviewDisplayState()
    first = _collection(records, "LSV", display)
    refreshed = _collection(tuple(reversed(records)), "LSV", display, selected=records[-1].key)

    first_colors = {curve.record_key: curve.color for curve in first.curves}
    refreshed_colors = {curve.record_key: curve.color for curve in refreshed.curves}
    assert first_colors == refreshed_colors
    assert len(set(first_colors.values())) == 5


def test_duplicate_import_does_not_create_duplicate_curve(lsv_path):
    records = GUIController().parse_many((lsv_path, lsv_path))
    state = AppState()
    state.add_records(records)
    state.add_records(records)

    assert len(_collection(state.records, "LSV", PreviewDisplayState()).curves) == 1


def test_remove_file_updates_preview_without_touching_disk(tmp_path, lsv_path):
    paths = _copies(tmp_path, lsv_path, "remove", 3)
    state = AppState()
    state.add_records(GUIController().parse_many(paths))
    state.remove([paths[1]])
    collection = _collection(state.records, "LSV", PreviewDisplayState())

    assert len(collection.curves) == 2
    assert paths[1].exists()


def test_clear_makes_preview_empty_without_deleting_files(tmp_path, lsv_path):
    paths = _copies(tmp_path, lsv_path, "clear", 2)
    state = AppState()
    state.add_records(GUIController().parse_many(paths))
    state.clear()

    assert _collection(state.records, "LSV", PreviewDisplayState()).curves == ()
    assert all(path.exists() for path in paths)


def test_preview_visibility_does_not_change_analysis_membership_or_raw_current(tmp_path, lsv_path):
    paths = _copies(tmp_path, lsv_path, "visibility", 2)
    state = AppState()
    state.add_records(GUIController().parse_many(paths))
    display = PreviewDisplayState()
    original_hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    original_currents = [record.data.current_A.copy() for record in state.records]

    display.set_visible(state.records[0].key, False)
    collection = _collection(state.records, "LSV", display)

    assert len(state.records) == 2
    assert len(collection.curves) == 2
    assert len(collection.visible_curves) == 1
    for record, expected in zip(state.records, original_currents, strict=True):
        np.testing.assert_array_equal(record.data.current_A, expected)
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths] == original_hashes


def test_large_preview_downsampling_is_display_only():
    x = np.linspace(0.0, 1000.0, 20_000)
    y = np.sin(x)
    x_before = x.copy()
    y_before = y.copy()

    shown_x, shown_y = downsample_for_display(x, y, max_points=5000)

    assert len(shown_x) == len(shown_y) == 5000
    assert shown_x[0] == x[0] and shown_x[-1] == x[-1]
    np.testing.assert_array_equal(x, x_before)
    np.testing.assert_array_equal(y, y_before)
