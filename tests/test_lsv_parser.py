from __future__ import annotations

import hashlib

import numpy as np
import pytest

from chi_parser import LSVData, parse_file, parse_lsv


EXPECTED_FIRST = [
    -9.989937553e-7,
    -9.900256828e-7,
    -9.811363952e-7,
    -9.720108665e-7,
    -9.633574791e-7,
]
EXPECTED_LAST = [
    2.072878544e-7,
    2.092545515e-7,
    2.099625505e-7,
    2.113785484e-7,
    2.129518890e-7,
]
EXPECTED_SHA256 = "f505c45e21eabb955c39148359ece2684a459fecc55314ac1c29e257a48e37fb"


def test_real_lsv_regression(lsv_path):
    data = parse_lsv(lsv_path)

    assert isinstance(data, LSVData)
    assert data.experiment_type == "LSV"
    assert data.file_size_bytes == 3053
    assert data.n_points == 400
    assert data.configured_start_potential_V == pytest.approx(-0.200)
    assert data.configured_final_potential_V == pytest.approx(0.200)
    assert data.actual_first_potential_V == pytest.approx(-0.200)
    assert data.actual_last_potential_V == pytest.approx(0.199)
    assert data.scan_rate_V_s == pytest.approx(0.020)
    assert data.potential_increment_V == pytest.approx(0.001)
    assert data.data_start_byte == 1453
    assert data.current_encoding == "little-endian IEEE 754 float32 (<f4)"
    assert len(data.potential_V) == len(data.current_A) == 400
    assert np.all(np.diff(data.potential_V) > 0)
    assert np.isfinite(data.potential_V).all()
    assert np.isfinite(data.current_A).all()
    assert data.validation_status == "valid"
    assert data.user_metadata is None
    np.testing.assert_allclose(data.current_A[:5], EXPECTED_FIRST, rtol=1e-7, atol=1e-15)
    np.testing.assert_allclose(data.current_A[-5:], EXPECTED_LAST, rtol=1e-7, atol=1e-15)


def test_lsv_source_hash_and_read_only_arrays(lsv_path):
    before = hashlib.sha256(lsv_path.read_bytes()).hexdigest()
    data = parse_file(lsv_path)
    after = hashlib.sha256(lsv_path.read_bytes()).hexdigest()

    assert before == after == EXPECTED_SHA256 == data.source_sha256
    assert not data.current_A.flags.writeable
    assert not data.potential_V.flags.writeable


def test_lsv_diagnostics_record_selected_structure(lsv_path):
    data = parse_lsv(lsv_path)
    diagnostic = data.diagnostics

    assert diagnostic.selected_n_points == 400
    assert diagnostic.data_start_candidate == 1453
    assert diagnostic.parameter_values["parameter_block_start"] == 853
    assert all(diagnostic.validation_checks.values())

