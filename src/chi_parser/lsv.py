"""Parser for the validated CHI760E Linear Sweep Voltammetry layout."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from .detector import DetectionResult, detect_experiment
from .diagnostics import DiagnosticReport, InvalidCHIFileError, fail, new_diagnostic
from .models import LSVData
from .validation import (
    CURRENT_ENCODING,
    PARAMETER_BLOCK_TO_DATA_START_BYTES,
    close_float,
    decode_current,
    find_unique_float_block,
    select_point_count,
    validate_arrays,
)


# Relative float32 locations inside the validated LSV parameter block.
# Absolute positions vary with CHI header strings and metadata.
LSV_PARAMETER_OFFSETS = MappingProxyType(
    {
        "configured_start_potential_V": 0,
        "configured_final_potential_V": 4,
        "high_potential_V": 8,
        "low_potential_V": 12,
        "scan_rate_V_s": 16,
        "initial_direction_flag": 24,
        "segment_count": 28,
        "potential_increment_V": 32,
        "potential_increment_copy_V": 36,
        "sensitivity_A_V": 40,
        "quiet_time_s": 44,
    }
)
LSV_PARAMETER_FLOAT_COUNT = 12


def _valid_lsv_block(values: tuple[float, ...]) -> bool:
    init, final, high, low, scan_rate = values[:5]
    direction, segments, increment, increment_copy, sensitivity, quiet = values[6:12]
    finite = all(math.isfinite(v) for v in values)
    if not finite or init >= final:
        return False
    if not all(abs(v) <= 100 for v in (init, final, high, low)):
        return False
    if not close_float(high, final) or not close_float(low, init):
        return False
    if not (0 < scan_rate <= 1e6 and 0 < increment <= final - init):
        return False
    if not close_float(increment, increment_copy, absolute=1e-9):
        return False
    if not (close_float(direction, 1.0) and close_float(segments, 1.0)):
        return False
    if not (0 < sensitivity <= 1e20 and 0 <= quiet <= 1e9):
        return False
    expected_points = (final - init) / increment
    return expected_points >= 2 and close_float(expected_points, round(expected_points), absolute=1e-3)


def _parse_lsv_bytes(
    path: Path,
    raw: bytes,
    detection: DetectionResult,
    diagnostic: DiagnosticReport,
) -> LSVData:
    block_offset, values = find_unique_float_block(
        raw,
        search_start=detection.header_prefix_end,
        float_count=LSV_PARAMETER_FLOAT_COUNT,
        predicate=_valid_lsv_block,
        label="lsv",
        diagnostic=diagnostic,
    )
    init, final, _high, _low, scan_rate = values[:5]
    increment, increment_copy, sensitivity, quiet = values[8:12]
    expected_data_start = block_offset + PARAMETER_BLOCK_TO_DATA_START_BYTES

    diagnostic.parameter_values.update(
        {
            "parameter_block_start": block_offset,
            "configured_start_potential_V": init,
            "configured_final_potential_V": final,
            "scan_rate_V_s": scan_rate,
            "potential_increment_V": increment,
            "potential_increment_copy_V": increment_copy,
            "sensitivity_A_V": sensitivity,
            "quiet_time_s": quiet,
            "expected_data_start_from_relative_layout": expected_data_start,
        }
    )

    def validate_candidate(n_points: int, _start: int) -> list[str]:
        expected_points = (final - init) / increment
        if not close_float(float(n_points), expected_points, absolute=1e-3):
            return [
                f"N={n_points} does not close the LSV range/increment relation "
                f"({expected_points})"
            ]
        return []

    selected = select_point_count(
        raw,
        diagnostic,
        minimum_header_end=detection.header_prefix_end,
        expected_data_start=expected_data_start,
        candidate_validator=validate_candidate,
    )
    current = decode_current(raw, selected)
    potential = init + np.arange(selected.n_points, dtype=np.float64) * increment

    expected_boundary = init + selected.n_points * increment
    if not close_float(expected_boundary, final, absolute=1e-5):
        fail(
            InvalidCHIFileError,
            "LSV configured final potential is inconsistent with start + N×increment.",
            diagnostic,
        )
    diagnostic.validation_checks["lsv_configured_boundary_closes"] = True
    validate_arrays(
        x=potential,
        current=current,
        selected=selected,
        file_size=len(raw),
        diagnostic=diagnostic,
    )

    status = "valid_with_warnings" if diagnostic.warnings else "valid"
    return LSVData(
        file_name=path.name,
        file_path=path.resolve(),
        file_size_bytes=len(raw),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        experiment_type="LSV",
        n_points=selected.n_points,
        configured_start_potential_V=float(init),
        configured_final_potential_V=float(final),
        actual_first_potential_V=float(potential[0]),
        actual_last_potential_V=float(potential[-1]),
        scan_rate_V_s=float(scan_rate),
        potential_increment_V=float(increment),
        potential_V=potential,
        current_A=current,
        data_start_byte=selected.data_start,
        current_encoding=CURRENT_ENCODING,
        validation_status=status,
        warnings=tuple(diagnostic.warnings),
        diagnostics=diagnostic,
    )


def parse_lsv(path: str | Path) -> LSVData:
    """Parse one CHI760E LSV file and return unrounded numerical arrays."""

    file_path = Path(path)
    raw = file_path.read_bytes()
    diagnostic = new_diagnostic(file_path.name, raw)
    detection = detect_experiment(raw, diagnostic)
    if detection.experiment_type != "LSV":
        fail(InvalidCHIFileError, "The file is not an LSV experiment.", diagnostic)
    return _parse_lsv_bytes(file_path, raw, detection, diagnostic)

