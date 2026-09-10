from __future__ import annotations

import hashlib
import struct

import pytest

from chi_parser import (
    LSVParameterExpectation,
    validate_lsv_batch,
    write_batch_validation_csv,
    write_batch_validation_report,
)


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_multiple_valid_files_are_parsed_independently(lsv_path):
    result = validate_lsv_batch([lsv_path, lsv_path])

    assert result.total_files == 2
    assert result.successful_files == 2
    assert result.failed_files == 0
    assert all(item.parse_success for item in result.files)


def test_failure_in_the_middle_does_not_stop_later_files(tmp_path, lsv_path):
    broken = tmp_path / "broken.bin"
    broken.write_bytes(lsv_path.read_bytes()[:-4])

    result = validate_lsv_batch([lsv_path, broken, lsv_path])

    assert [item.parse_success for item in result.files] == [True, False, True]
    assert result.successful_files == 2
    assert result.failed_files == 1
    assert result.files[1].exception_type == "PointCountError"
    assert result.files[1].errors
    assert result.files[1].diagnostics is not None


def test_batch_validation_never_modifies_sources(tmp_path, lsv_path):
    copied = tmp_path / "source.bin"
    copied.write_bytes(lsv_path.read_bytes())
    before = _sha256(copied)

    result = validate_lsv_batch([copied])

    assert _sha256(copied) == before
    assert result.files[0].source_sha256 == before
    assert result.files[0].source_unchanged


def test_parameter_mismatch_is_qc_not_parse_failure(tmp_path, lsv_path):
    changed = bytearray(lsv_path.read_bytes())
    struct.pack_into("<f", changed, 853 + 16, 0.030)
    path = tmp_path / "different-rate.bin"
    path.write_bytes(changed)

    result = validate_lsv_batch([path])

    assert result.successful_files == 1
    assert result.parameter_mismatch_files == 1
    assert result.files[0].scan_rate_V_s == pytest.approx(0.030)
    assert "scan_rate_V_s" in result.files[0].parameter_mismatches[0]


def test_custom_parameter_expectation_is_supported(lsv_path):
    expected = LSVParameterExpectation(scan_rate_V_s=0.030)
    result = validate_lsv_batch([lsv_path], expected=expected)

    assert result.successful_files == 1
    assert result.parameter_mismatch_files == 1


def test_metadata_reports_have_one_row_per_file_and_no_current_data(tmp_path, lsv_path):
    result = validate_lsv_batch([lsv_path, lsv_path])
    csv_path = write_batch_validation_csv(result, tmp_path / "batch.csv")
    md_path = write_batch_validation_report(result, tmp_path / "batch.md")

    csv_text = csv_path.read_text(encoding="utf-8-sig")
    md_text = md_path.read_text(encoding="utf-8")
    assert len(csv_text.splitlines()) == 3
    assert "current_A" not in csv_text
    assert "Parsed successfully: 2" in md_text
    assert "LSV-裸-100uMROS-L1.bin" in md_text
