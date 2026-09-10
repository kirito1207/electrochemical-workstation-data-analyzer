"""Shared structural and numerical validation for CHI parser v0.1."""

from __future__ import annotations

import math
import struct
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .diagnostics import (
    AmbiguousPointCountError,
    DataValidationError,
    DiagnosticReport,
    InvalidCHIFileError,
    PointCountError,
    fail,
)


CURRENT_DTYPE = np.dtype("<f4")
CURRENT_ENCODING = "little-endian IEEE 754 float32 (<f4)"
CURRENT_BYTES_PER_POINT = 4
MAX_REASONABLE_ABS_CURRENT_A = 1e20
MAX_POINT_COUNT = 100_000_000
MAX_STRUCTURE_SCAN_BYTES = 64 * 1024

# In the validated LSV, private i-t, public paired i-t, and cv_pro CV layouts,
# the current array starts 600 bytes after the technique parameter block starts.
# v0.1 treats this as a validated relative-layout signature, never as an
# absolute 1451/1453-byte data offset.
PARAMETER_BLOCK_TO_DATA_START_BYTES = 600


@dataclass(frozen=True, slots=True)
class SelectedPointCount:
    n_points: int
    data_start: int
    copy_offsets: tuple[int, ...]


CandidateValidator = Callable[[int, int], list[str]]
BlockPredicate = Callable[[tuple[float, ...]], bool]


def find_unique_float_block(
    raw: bytes,
    *,
    search_start: int,
    float_count: int,
    predicate: BlockPredicate,
    label: str,
    diagnostic: DiagnosticReport,
) -> tuple[int, tuple[float, ...]]:
    """Find one parameter block by validated relative field relationships."""

    block_size = float_count * 4
    latest = min(
        len(raw) - PARAMETER_BLOCK_TO_DATA_START_BYTES,
        MAX_STRUCTURE_SCAN_BYTES,
    )
    matches: list[tuple[int, tuple[float, ...]]] = []
    for offset in range(max(0, search_start), max(search_start, latest) + 1):
        if offset + block_size > len(raw):
            break
        values = struct.unpack_from(f"<{float_count}f", raw, offset)
        if predicate(values):
            matches.append((offset, values))

    diagnostic.parameter_values[f"{label}_block_candidates"] = [m[0] for m in matches]
    if not matches:
        fail(
            InvalidCHIFileError,
            f"No validated {label} parameter block was found.",
            diagnostic,
        )
    if len(matches) > 1:
        fail(
            InvalidCHIFileError,
            f"More than one {label} parameter block matched: {[m[0] for m in matches]}.",
            diagnostic,
        )
    diagnostic.validation_checks[f"{label}_parameter_block_unique"] = True
    return matches[0]


def _current_quality(raw: bytes, start: int, n_points: int) -> list[str]:
    reasons: list[str] = []
    if start < 0 or start + n_points * CURRENT_BYTES_PER_POINT != len(raw):
        reasons.append("tail length does not equal N×4")
        return reasons
    current = np.frombuffer(raw, dtype=CURRENT_DTYPE, count=n_points, offset=start)
    if len(current) != n_points:
        reasons.append("decoded current count does not equal N")
        return reasons
    if not np.isfinite(current).all():
        reasons.append("current contains NaN or Inf")
        return reasons
    if current.size and float(np.max(np.abs(current.astype(np.float64)))) > MAX_REASONABLE_ABS_CURRENT_A:
        reasons.append("current magnitude exceeds 1e20 A")
    return reasons


def select_point_count(
    raw: bytes,
    diagnostic: DiagnosticReport,
    *,
    minimum_header_end: int,
    expected_data_start: int | None,
    candidate_validator: CandidateValidator | None = None,
) -> SelectedPointCount:
    """Select N only from equal uint32 copies eight bytes apart.

    Every candidate is checked against the tail size, header boundary,
    little-endian float32 quality, and optional technique-specific closure.
    Ambiguity is an error; candidate ordering is never used as a tiebreaker.
    """

    scan_end = min(
        expected_data_start if expected_data_start is not None else len(raw),
        MAX_STRUCTURE_SCAN_BYTES,
    )
    grouped: dict[int, set[int]] = {}
    for offset in range(max(0, minimum_header_end), max(minimum_header_end, scan_end - 11)):
        n_points = struct.unpack_from("<I", raw, offset)[0]
        duplicate = struct.unpack_from("<I", raw, offset + 8)[0]
        if n_points == duplicate and 0 < n_points <= MAX_POINT_COUNT:
            grouped.setdefault(n_points, set()).update((offset, offset + 8))

    accepted: list[SelectedPointCount] = []
    candidate_reports: list[dict[str, Any]] = []
    max_header_end = max(4096, int(len(raw) * 0.80))
    for n_points, offsets in sorted(grouped.items()):
        start = len(raw) - n_points * CURRENT_BYTES_PER_POINT
        reasons: list[str] = []
        if start < minimum_header_end:
            reasons.append("computed data start overlaps the header prefix")
        if start > max_header_end:
            reasons.append("computed header consumes an implausible fraction of the file")
        if expected_data_start is not None and start != expected_data_start:
            reasons.append(
                f"computed data start {start} does not match validated layout {expected_data_start}"
            )
        reasons.extend(_current_quality(raw, start, n_points))
        if candidate_validator is not None:
            reasons.extend(candidate_validator(n_points, start))
        report = {
            "n_points": n_points,
            "copy_offsets": sorted(offsets),
            "data_start": start,
            "accepted": not reasons,
            "rejection_reasons": reasons,
        }
        candidate_reports.append(report)
        if not reasons:
            accepted.append(
                SelectedPointCount(
                    n_points=n_points,
                    data_start=start,
                    copy_offsets=tuple(sorted(offsets)),
                )
            )

    diagnostic.point_count_candidates = candidate_reports
    if not accepted:
        fail(
            PointCountError,
            "No point-count candidate passed duplicate-field, layout, and numerical validation.",
            diagnostic,
        )
    if len(accepted) > 1:
        fail(
            AmbiguousPointCountError,
            f"Multiple point-count candidates remain valid: {[c.n_points for c in accepted]}.",
            diagnostic,
        )

    selected = accepted[0]
    diagnostic.selected_n_points = selected.n_points
    diagnostic.data_start_candidate = selected.data_start
    diagnostic.validation_checks.update(
        {
            "point_count_positive": selected.n_points > 0,
            "point_count_copies_agree": len(selected.copy_offsets) >= 2,
            "data_start_nonnegative": selected.data_start >= 0,
            "tail_size_equals_n_times_4": (
                selected.data_start + selected.n_points * CURRENT_BYTES_PER_POINT == len(raw)
            ),
        }
    )
    return selected


def decode_current(raw: bytes, selected: SelectedPointCount) -> NDArray[np.float64]:
    """Decode the validated current tail without rounding or unit conversion."""

    current = np.frombuffer(
        raw,
        dtype=CURRENT_DTYPE,
        count=selected.n_points,
        offset=selected.data_start,
    ).astype(np.float64, copy=True)
    return current


def validate_arrays(
    *,
    x: NDArray[np.float64],
    current: NDArray[np.float64],
    selected: SelectedPointCount,
    file_size: int,
    diagnostic: DiagnosticReport,
) -> None:
    """Apply common post-parse integrity checks."""

    checks = {
        "n_points_positive": selected.n_points > 0,
        "x_length_equals_n_points": len(x) == selected.n_points,
        "current_length_equals_n_points": len(current) == selected.n_points,
        "current_has_no_nan": not np.isnan(current).any(),
        "current_has_no_inf": not np.isinf(current).any(),
        "x_has_no_nan_or_inf": bool(np.isfinite(x).all()),
        "x_strictly_increasing": bool(np.all(np.diff(x) > 0)),
        "data_start_nonnegative_final": selected.data_start >= 0,
        "data_end_matches_file_size": (
            selected.data_start + selected.n_points * CURRENT_BYTES_PER_POINT == file_size
        ),
        "current_magnitude_not_obviously_corrupt": (
            current.size == 0 or float(np.max(np.abs(current))) <= MAX_REASONABLE_ABS_CURRENT_A
        ),
    }
    diagnostic.validation_checks.update(checks)
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        fail(
            DataValidationError,
            f"Parsed data failed validation checks: {', '.join(failures)}.",
            diagnostic,
        )


def close_float(left: float, right: float, *, absolute: float = 1e-6) -> bool:
    return math.isclose(left, right, rel_tol=1e-6, abs_tol=absolute)

