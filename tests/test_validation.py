from __future__ import annotations

import struct

import pytest

from chi_parser import (
    AmbiguousPointCountError,
    CHIParserError,
    InvalidCHIFileError,
    PointCountError,
    parse_file,
    parse_lsv,
)
from chi_parser.diagnostics import new_diagnostic
from chi_parser.validation import select_point_count


def _write(tmp_path, name: str, raw: bytes | bytearray):
    path = tmp_path / name
    path.write_bytes(raw)
    return path


def test_truncated_file_is_rejected(tmp_path, lsv_path):
    path = _write(tmp_path, "truncated.bin", lsv_path.read_bytes()[:1000])
    with pytest.raises(InvalidCHIFileError):
        parse_file(path)


def test_tail_missing_four_bytes_is_rejected(tmp_path, lsv_path):
    path = _write(tmp_path, "missing-one-point.bin", lsv_path.read_bytes()[:-4])
    with pytest.raises(PointCountError):
        parse_lsv(path)


def test_point_count_copy_mismatch_is_rejected(tmp_path, lsv_path):
    damaged = bytearray(lsv_path.read_bytes())
    struct.pack_into("<I", damaged, 505, 399)
    path = _write(tmp_path, "count-mismatch.bin", damaged)
    with pytest.raises(PointCountError):
        parse_lsv(path)


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf")])
def test_nonfinite_current_is_rejected(tmp_path, lsv_path, bad_value):
    damaged = bytearray(lsv_path.read_bytes())
    struct.pack_into("<f", damaged, 1453, bad_value)
    path = _write(tmp_path, "nonfinite.bin", damaged)
    with pytest.raises(CHIParserError):
        parse_lsv(path)


def test_obviously_impossible_current_is_rejected(tmp_path, lsv_path):
    damaged = bytearray(lsv_path.read_bytes())
    struct.pack_into("<f", damaged, 1453, 1e30)
    path = _write(tmp_path, "huge-current.bin", damaged)
    with pytest.raises(CHIParserError):
        parse_lsv(path)


def test_big_endian_encoded_tail_is_rejected(tmp_path, lsv_path):
    damaged = bytearray(lsv_path.read_bytes())
    for offset in range(1453, len(damaged), 4):
        damaged[offset : offset + 4] = reversed(damaged[offset : offset + 4])
    path = _write(tmp_path, "big-endian-tail.bin", damaged)
    with pytest.raises(CHIParserError):
        parse_lsv(path)


def test_ambiguous_point_counts_are_never_guessed():
    raw = bytearray(2000)
    struct.pack_into("<I", raw, 100, 100)
    struct.pack_into("<I", raw, 108, 100)
    struct.pack_into("<I", raw, 200, 120)
    struct.pack_into("<I", raw, 208, 120)
    diagnostic = new_diagnostic("ambiguous.bin", raw)

    with pytest.raises(AmbiguousPointCountError):
        select_point_count(
            bytes(raw),
            diagnostic,
            minimum_header_end=16,
            expected_data_start=None,
        )

    # Byte-wise scanning may also expose overlapping integer interpretations;
    # the important guarantee is that both deliberately valid candidates are
    # retained and ambiguity is reported instead of resolved by ordering.
    reported = {item["n_points"] for item in diagnostic.point_count_candidates}
    assert {100, 120} <= reported


def test_failure_contains_bounded_structured_diagnostics(tmp_path, lsv_path):
    path = _write(tmp_path, "short.bin", lsv_path.read_bytes()[:32])
    with pytest.raises(CHIParserError) as exc_info:
        parse_file(path)

    diagnostic = exc_info.value.diagnostic
    assert diagnostic.file_name == "short.bin"
    assert diagnostic.file_size == 32
    assert len(diagnostic.header_hex_preview.split()) <= 64
    assert diagnostic.errors
