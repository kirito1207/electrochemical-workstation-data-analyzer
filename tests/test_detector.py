from __future__ import annotations

import pytest

from chi_parser import UnsupportedExperimentError, parse_file, parse_files
from chi_parser.detector import detect_experiment
from chi_parser.diagnostics import new_diagnostic


def test_detects_exact_supported_experiment_names(lsv_path, it_path):
    for path, expected in ((lsv_path, "LSV"), (it_path, "i-t")):
        raw = path.read_bytes()
        result = detect_experiment(raw, new_diagnostic(path.name, raw))
        assert result.experiment_type == expected


def test_unsupported_experiment_is_rejected(tmp_path, lsv_path):
    damaged = bytearray(lsv_path.read_bytes())
    damaged[8:11] = b"CV "
    path = tmp_path / "unsupported.bin"
    path.write_bytes(damaged)

    with pytest.raises(UnsupportedExperimentError) as exc_info:
        parse_file(path)

    assert "当前版本仅支持 CHI760E LSV 和 i-t 数据" in str(exc_info.value)
    assert "CV  / Linear Sweep Voltammetry" in exc_info.value.diagnostic.detected_experiment_text


def test_parse_files_supports_batch_call(lsv_path, it_path):
    results = parse_files([lsv_path, it_path])
    assert [result.experiment_type for result in results] == ["LSV", "i-t"]
    assert [result.n_points for result in results] == [400, 6156]

