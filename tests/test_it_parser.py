from __future__ import annotations

import hashlib

import numpy as np
import pytest

from chi_parser import ITData, parse_file, parse_it


EXPECTED_FIRST = [
    -5.564580761e-7,
    -5.601397675e-7,
    -5.713735618e-7,
    -5.621221817e-7,
    -5.328574844e-7,
]
EXPECTED_LAST = [
    -1.216611622e-6,
    -1.232093496e-6,
    -1.217555678e-6,
    -1.164879336e-6,
    -1.175169018e-6,
]
EXPECTED_SHA256 = "c3022e4a26f5c66f7f59746b47bb6c563f68d40f29f7044d3ddaa324b5fcf3f5"


def test_real_it_regression(it_path):
    data = parse_it(it_path)

    assert isinstance(data, ITData)
    assert data.experiment_type == "i-t"
    assert data.file_size_bytes == 26075
    assert data.n_points == 6156
    assert data.sample_interval_s == pytest.approx(0.100)
    assert data.configured_run_time_s == pytest.approx(1000.0, rel=1e-6)
    assert data.applied_potential_V == pytest.approx(0.000)
    assert data.actual_first_time_s == pytest.approx(0.1)
    assert data.actual_last_time_s == pytest.approx(615.6, rel=1e-6)
    assert data.actual_recorded_duration_s == pytest.approx(615.6, rel=1e-6)
    assert data.data_start_byte == 1451
    assert data.current_encoding == "little-endian IEEE 754 float32 (<f4)"
    assert len(data.time_s) == len(data.current_A) == 6156
    assert np.all(np.diff(data.time_s) > 0)
    assert np.isfinite(data.time_s).all()
    assert np.isfinite(data.current_A).all()
    assert data.validation_status == "valid_with_warnings"
    assert "记录可能在设定运行时间前结束。" in data.warnings
    np.testing.assert_allclose(data.current_A[:5], EXPECTED_FIRST, rtol=1e-7, atol=1e-15)
    np.testing.assert_allclose(data.current_A[-5:], EXPECTED_LAST, rtol=1e-7, atol=1e-15)


def test_it_source_hash_and_read_only_arrays(it_path):
    before = hashlib.sha256(it_path.read_bytes()).hexdigest()
    data = parse_file(it_path)
    after = hashlib.sha256(it_path.read_bytes()).hexdigest()

    assert before == after == EXPECTED_SHA256 == data.source_sha256
    assert not data.current_A.flags.writeable
    assert not data.time_s.flags.writeable


def test_it_diagnostics_record_selected_structure(it_path):
    data = parse_it(it_path)
    diagnostic = data.diagnostics

    assert diagnostic.selected_n_points == 6156
    assert diagnostic.data_start_candidate == 1451
    assert diagnostic.parameter_values["parameter_block_start"] == 851
    assert all(diagnostic.validation_checks.values())

