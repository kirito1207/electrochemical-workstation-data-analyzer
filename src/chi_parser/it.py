"""Parser for the validated CHI760E Amperometric i-t layout."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from types import MappingProxyType

import numpy as np

from .detector import DetectionResult, detect_experiment
from .diagnostics import DiagnosticReport, InvalidCHIFileError, fail, new_diagnostic
from .models import ITData
from .validation import (
    CURRENT_ENCODING,
    PARAMETER_BLOCK_TO_DATA_START_BYTES,
    close_float,
    decode_current,
    find_unique_float_block,
    select_point_count,
    validate_arrays,
)


# Relative float32 locations inside the validated i-t parameter block.
# The layout was cross-checked against a public CHI760E bin/text pair whose
# exported Init E, interval, run time, quiet time, and sensitivity are known.
IT_PARAMETER_OFFSETS = MappingProxyType(
    {
        "applied_potential_V": 0,
        "applied_potential_copy_V": 8,
        "sample_interval_s": 16,
        "sample_interval_copy_1_s": 32,
        "sample_interval_copy_2_s": 36,
        "sensitivity_A_V": 40,
        "quiet_time_s": 44,
        "configured_run_time_s": 56,
    }
)
IT_PARAMETER_FLOAT_COUNT = 15


def _valid_it_block(values: tuple[float, ...]) -> bool:
    applied = values[0]
    applied_copy = values[2]
    interval = values[4]
    interval_copy_1 = values[8]
    interval_copy_2 = values[9]
    sensitivity = values[10]
    quiet = values[11]
    run_time = values[14]
    finite = all(math.isfinite(v) for v in values)
    if not finite or not abs(applied) <= 100:
        return False
    if not close_float(applied, applied_copy):
        return False
    if not (close_float(values[1], 0.0) and close_float(values[3], 0.0)):
        return False
    if not (0 < interval <= 1e9):
        return False
    if not close_float(interval, interval_copy_1, absolute=1e-9):
        return False
    if not close_float(interval, interval_copy_2, absolute=1e-9):
        return False
    if not close_float(values[7], 1.0):
        return False
    if not (0 < sensitivity <= 1e20 and 0 <= quiet <= 1e9):
        return False
    return run_time >= interval


def _parse_it_bytes(
    path: Path,
    raw: bytes,
    detection: DetectionResult,
    diagnostic: DiagnosticReport,
) -> ITData:
    block_offset, values = find_unique_float_block(
        raw,
        search_start=detection.header_prefix_end,
        float_count=IT_PARAMETER_FLOAT_COUNT,
        predicate=_valid_it_block,
        label="it",
        diagnostic=diagnostic,
    )
    applied = values[0]
    applied_copy = values[2]
    interval = values[4]
    interval_copy_1 = values[8]
    interval_copy_2 = values[9]
    sensitivity = values[10]
    quiet = values[11]
    run_time = values[14]
    expected_data_start = block_offset + PARAMETER_BLOCK_TO_DATA_START_BYTES

    diagnostic.parameter_values.update(
        {
            "parameter_block_start": block_offset,
            "applied_potential_V": applied,
            "applied_potential_copy_V": applied_copy,
            "sample_interval_s": interval,
            "sample_interval_copy_1_s": interval_copy_1,
            "sample_interval_copy_2_s": interval_copy_2,
            "sensitivity_A_V": sensitivity,
            "quiet_time_s": quiet,
            "configured_run_time_s": run_time,
            "expected_data_start_from_relative_layout": expected_data_start,
        }
    )

    def validate_candidate(n_points: int, _start: int) -> list[str]:
        actual_last = n_points * interval
        tolerance = max(interval, 1e-6)
        if actual_last > run_time + tolerance:
            return [
                f"N×sample_interval ({actual_last}) exceeds configured run time ({run_time})"
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
    time = np.arange(1, selected.n_points + 1, dtype=np.float64) * interval
    validate_arrays(
        x=time,
        current=current,
        selected=selected,
        file_size=len(raw),
        diagnostic=diagnostic,
    )

    actual_last = float(time[-1])
    if actual_last < run_time - max(interval, 1e-6):
        diagnostic.warnings.append("记录可能在设定运行时间前结束。")
    status = "valid_with_warnings" if diagnostic.warnings else "valid"
    return ITData(
        file_name=path.name,
        file_path=path.resolve(),
        file_size_bytes=len(raw),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        experiment_type="i-t",
        n_points=selected.n_points,
        sample_interval_s=float(interval),
        configured_run_time_s=float(run_time),
        actual_first_time_s=float(time[0]),
        actual_last_time_s=actual_last,
        actual_recorded_duration_s=actual_last,
        applied_potential_V=float(applied),
        time_s=time,
        current_A=current,
        data_start_byte=selected.data_start,
        current_encoding=CURRENT_ENCODING,
        validation_status=status,
        warnings=tuple(diagnostic.warnings),
        diagnostics=diagnostic,
    )


def parse_it(path: str | Path) -> ITData:
    """Parse one CHI760E Amperometric i-t file."""

    file_path = Path(path)
    raw = file_path.read_bytes()
    diagnostic = new_diagnostic(file_path.name, raw)
    detection = detect_experiment(raw, diagnostic)
    if detection.experiment_type != "i-t":
        fail(InvalidCHIFileError, "The file is not an Amperometric i-t experiment.", diagnostic)
    return _parse_it_bytes(file_path, raw, detection, diagnostic)

