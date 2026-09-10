from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from threading import get_ident

import numpy as np

from chi_gui.background import BackgroundRunner
from chi_gui.controller import GUIController, discover_bin_files
from chi_gui.formatting import (
    format_current_uA,
    format_increment,
    format_scan_rate,
    format_seconds,
    format_voltage,
    parameter_rows,
)
from chi_gui.state import AppState, FileStatus


def test_gui_package_and_tk_modules_import_without_creating_window():
    sys.modules.pop("presets.pb42", None)
    package = importlib.import_module("chi_gui")
    importlib.import_module("chi_gui.app")
    importlib.import_module("chi_gui.main_window")

    assert package.__version__ == "0.1.0"
    assert "presets.pb42" not in sys.modules


def test_generic_gui_starts_and_parses_when_pb42_import_is_blocked(lsv_path, it_path):
    script = r'''
import importlib.abc
import json
import os
import sys

class BlockPB42(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "presets.pb42":
            raise ModuleNotFoundError("PB42 preset intentionally unavailable")
        return None

sys.meta_path.insert(0, BlockPB42())
import chi_gui.app
from chi_gui.controller import GUIController
records = GUIController().parse_many(json.loads(os.environ["GUI_TEST_FILES"]))
assert [item.route for item in records] == ["LSV", "i-t"]
assert "presets.pb42" not in sys.modules
print("ok")
'''
    env = os.environ.copy()
    env["GUI_TEST_FILES"] = json.dumps([str(lsv_path), str(it_path)])
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_lsv_and_it_enter_distinct_routes(lsv_path, it_path):
    controller = GUIController()
    lsv = controller.parse_one(lsv_path)
    it = controller.parse_one(it_path)

    assert (lsv.status, lsv.route, lsv.experiment_type) == (FileStatus.PARSED, "LSV", "LSV")
    assert (it.status, it.route, it.experiment_type) == (FileStatus.PARSED, "i-t", "i-t")


def test_unsupported_experiment_is_not_routed_to_lsv_or_it(tmp_path, lsv_path):
    raw = bytearray(lsv_path.read_bytes())
    raw[8:11] = b"CV "
    path = tmp_path / "unsupported_cv.bin"
    path.write_bytes(raw)

    record = GUIController().parse_one(path)

    assert record.status is FileStatus.UNSUPPORTED
    assert record.route == "unsupported"
    assert record.experiment_type == "CV"
    assert record.error_type == "UnsupportedExperimentError"
    assert "当前版本仅支持" in (record.error_message or "")


def test_multi_file_import_and_mixed_technique_filtering(lsv_path, it_path):
    records = GUIController().parse_many((lsv_path, it_path))
    state = AppState()
    state.add_records(records)

    assert len(records) == 2
    assert len(state.for_route("LSV")) == 1
    assert len(state.for_route("i-t")) == 1
    assert state.summary().lsv == state.summary().it == 1


def test_duplicate_paths_are_suppressed(lsv_path):
    controller = GUIController()
    records = controller.parse_many((lsv_path, lsv_path, lsv_path.parent / "." / lsv_path.name))
    state = AppState()

    assert len(records) == 1
    assert state.add_records(records) == 1
    assert state.add_records(records) == 0
    assert len(state.records) == 1


def test_one_failed_file_does_not_block_later_files(tmp_path, lsv_path, it_path):
    broken = tmp_path / "a_broken.bin"
    broken.write_bytes(b"not a CHI file")
    records = GUIController().parse_many((broken, lsv_path, it_path))

    assert len(records) == 3
    assert sum(record.status is FileStatus.FAILED for record in records) == 1
    assert sum(record.status is FileStatus.PARSED for record in records) == 2


def test_chinese_space_path_and_recursive_folder_discovery(tmp_path, lsv_path):
    folder = tmp_path / "中文 数据文件夹" / "更深一层"
    folder.mkdir(parents=True)
    copied = folder / "电极 样本.bin"
    copied.write_bytes(lsv_path.read_bytes())

    discovered = discover_bin_files((tmp_path,))
    record = GUIController().parse_many((tmp_path,))[0]

    assert discovered == (copied.resolve(),)
    assert record.parse_success
    assert record.path == copied.resolve()


def test_gui_parameter_formatting_is_human_readable(lsv_path, it_path):
    controller = GUIController()
    lsv = controller.parse_one(lsv_path).data
    it = controller.parse_one(it_path).data

    assert format_voltage(-0.20000000298) == "-0.200 V"
    assert format_scan_rate(0.01999999955) == "20 mV/s"
    assert format_increment(0.00100000005) == "1 mV"
    assert format_seconds(615.6000001) == "615.6 s"
    assert format_current_uA(1.2344e-6) == "1.234 µA"
    assert ("实际末点电位", "+0.199 V") not in parameter_rows(lsv)
    assert dict(parameter_rows(lsv))["实际末点电位"] == "0.199 V"
    assert dict(parameter_rows(it))["采样间隔"] == "0.1 s"


def test_lsv_preview_references_raw_parser_arrays(lsv_path):
    controller = GUIController()
    record = controller.parse_one(lsv_path)
    preview = controller.preview_for(record)

    assert preview.x is record.data.potential_V
    assert preview.current_A is record.data.current_A
    assert preview.x_label == "Potential / V"
    np.testing.assert_array_equal(preview.current_uA, record.data.current_A * 1e6)


def test_it_preview_references_raw_parser_arrays(it_path):
    controller = GUIController()
    record = controller.parse_one(it_path)
    preview = controller.preview_for(record)

    assert preview.x is record.data.time_s
    assert preview.current_A is record.data.current_A
    assert preview.x_label == "Time / s"


def test_controller_does_not_modify_original_bin(lsv_path, it_path):
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    before = (digest(lsv_path), digest(it_path))
    GUIController().parse_many((lsv_path, it_path))
    after = (digest(lsv_path), digest(it_path))

    assert before == after


def test_background_worker_returns_progress_and_result_through_queue():
    runner = BackgroundRunner()
    main_thread = get_ident()

    def task(_cancel, emit):
        emit({"step": 1, "worker_thread": get_ident()})
        return ("done", get_ident())

    runner.submit(task)
    assert runner.join(timeout=5.0)
    events = runner.drain()

    assert [event.kind for event in events] == ["started", "progress", "result", "finished"]
    progress = next(event.payload for event in events if event.kind == "progress")
    result = next(event.payload for event in events if event.kind == "result")
    assert progress["worker_thread"] != main_thread
    assert result[1] != main_thread


def test_state_remove_and_clear_only_change_gui_collection(lsv_path, it_path):
    records = GUIController().parse_many((lsv_path, it_path))
    state = AppState()
    state.add_records(records)

    assert state.remove([lsv_path]) == 1
    assert lsv_path.exists()
    state.clear()
    assert state.records == ()
    assert it_path.exists()
