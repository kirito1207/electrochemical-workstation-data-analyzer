"""Failure-isolated batch compatibility validation for CHI760E LSV files."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .diagnostics import CHIParserError
from .lsv import parse_lsv


@dataclass(frozen=True, slots=True)
class LSVParameterExpectation:
    """Expected acquisition settings used only for experiment QC."""

    configured_start_potential_V: float = -0.200
    configured_final_potential_V: float = 0.200
    scan_rate_V_s: float = 0.020
    potential_increment_V: float = 0.001
    potential_tolerance_V: float = 1e-6
    scan_rate_tolerance_V_s: float = 1e-6
    increment_tolerance_V: float = 1e-8


@dataclass(frozen=True, slots=True)
class FileValidationResult:
    """One file's result; numerical current arrays intentionally are not retained."""

    source_path: str
    file_name: str
    source_sha256: str | None
    source_unchanged: bool
    parse_success: bool
    experiment_type: str | None = None
    detected_experiment_text: str | None = None
    file_size_bytes: int | None = None
    header_size_bytes: int | None = None
    header_sha256: str | None = None
    n_points: int | None = None
    configured_start_potential_V: float | None = None
    configured_final_potential_V: float | None = None
    actual_first_potential_V: float | None = None
    actual_last_potential_V: float | None = None
    scan_rate_V_s: float | None = None
    potential_increment_V: float | None = None
    data_start_byte: int | None = None
    parameter_block_start: int | None = None
    parameter_block_to_data_start_bytes: int | None = None
    point_count_field_offsets: tuple[int, ...] = ()
    current_encoding: str | None = None
    validation_status: str = "failed"
    parameter_mismatches: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    exception_type: str | None = None
    diagnostics: dict[str, Any] | None = None

    @property
    def parameter_match(self) -> bool | None:
        if not self.parse_success:
            return None
        return not self.parameter_mismatches

    def to_csv_row(self) -> dict[str, str | int | float | bool | None]:
        """Return a flat row containing metadata and diagnostics, never current data."""

        return {
            "source_path": self.source_path,
            "file_name": self.file_name,
            "source_sha256": self.source_sha256,
            "source_unchanged": self.source_unchanged,
            "parse_success": self.parse_success,
            "experiment_type": self.experiment_type,
            "detected_experiment_text": self.detected_experiment_text,
            "file_size_bytes": self.file_size_bytes,
            "header_size_bytes": self.header_size_bytes,
            "header_sha256": self.header_sha256,
            "n_points": self.n_points,
            "configured_start_potential_V": self.configured_start_potential_V,
            "configured_final_potential_V": self.configured_final_potential_V,
            "actual_first_potential_V": self.actual_first_potential_V,
            "actual_last_potential_V": self.actual_last_potential_V,
            "scan_rate_V_s": self.scan_rate_V_s,
            "potential_increment_V": self.potential_increment_V,
            "data_start_byte": self.data_start_byte,
            "parameter_block_start": self.parameter_block_start,
            "parameter_block_to_data_start_bytes": self.parameter_block_to_data_start_bytes,
            "point_count_field_offsets": ";".join(map(str, self.point_count_field_offsets)),
            "current_encoding": self.current_encoding,
            "validation_status": self.validation_status,
            "parameter_match": self.parameter_match,
            "parameter_mismatches": " | ".join(self.parameter_mismatches),
            "warnings": " | ".join(self.warnings),
            "errors": " | ".join(self.errors),
            "exception_type": self.exception_type,
            "diagnostics_json": json.dumps(
                self.diagnostics, ensure_ascii=False, sort_keys=True
            ) if self.diagnostics is not None else "",
        }


@dataclass(frozen=True, slots=True)
class BatchValidationResult:
    """Aggregate counters and per-file results for one independent batch run."""

    files: tuple[FileValidationResult, ...]
    header_variation_byte_count: int | None = None
    header_variation_ranges: tuple[tuple[int, int], ...] = ()

    @property
    def total_files(self) -> int:
        return len(self.files)

    @property
    def successful_files(self) -> int:
        return sum(item.parse_success for item in self.files)

    @property
    def failed_files(self) -> int:
        return self.total_files - self.successful_files

    @property
    def warning_files(self) -> int:
        return sum(bool(item.warnings) for item in self.files)

    @property
    def warning_count(self) -> int:
        return sum(len(item.warnings) for item in self.files)

    @property
    def parameter_mismatch_files(self) -> int:
        return sum(bool(item.parameter_mismatches) for item in self.files)

    @property
    def success_rate(self) -> float:
        return self.successful_files / self.total_files if self.total_files else 0.0

    def unique_success_values(self, field_name: str) -> tuple[Any, ...]:
        values = {
            getattr(item, field_name)
            for item in self.files
            if item.parse_success and getattr(item, field_name) is not None
        }
        return tuple(sorted(values))


def _display_path(path: Path, root: Path | None) -> str:
    if root is None:
        return path.name
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def _parameter_mismatches(data: Any, expected: LSVParameterExpectation) -> tuple[str, ...]:
    checks = (
        (
            "configured_start_potential_V",
            data.configured_start_potential_V,
            expected.configured_start_potential_V,
            expected.potential_tolerance_V,
        ),
        (
            "configured_final_potential_V",
            data.configured_final_potential_V,
            expected.configured_final_potential_V,
            expected.potential_tolerance_V,
        ),
        (
            "scan_rate_V_s",
            data.scan_rate_V_s,
            expected.scan_rate_V_s,
            expected.scan_rate_tolerance_V_s,
        ),
        (
            "potential_increment_V",
            data.potential_increment_V,
            expected.potential_increment_V,
            expected.increment_tolerance_V,
        ),
    )
    return tuple(
        f"Parameter mismatch: {name}={actual:.12g}, expected={target:.12g}"
        for name, actual, target, tolerance in checks
        if not math.isclose(actual, target, rel_tol=0.0, abs_tol=tolerance)
    )


def _selected_point_offsets(diagnostics: dict[str, Any], n_points: int) -> tuple[int, ...]:
    for candidate in diagnostics.get("point_count_candidates", []):
        if candidate.get("accepted") and candidate.get("n_points") == n_points:
            return tuple(candidate.get("copy_offsets", ()))
    return ()


def _variation_ranges(headers: list[bytes]) -> tuple[int | None, tuple[tuple[int, int], ...]]:
    if not headers:
        return None, ()
    maximum = max(map(len, headers))
    varying = [
        offset
        for offset in range(maximum)
        if len({header[offset] if offset < len(header) else None for header in headers}) > 1
    ]
    if not varying:
        return 0, ()
    ranges: list[tuple[int, int]] = []
    start = previous = varying[0]
    for offset in varying[1:]:
        if offset != previous + 1:
            ranges.append((start, previous))
            start = offset
        previous = offset
    ranges.append((start, previous))
    return len(varying), tuple(ranges)


def validate_lsv_batch(
    paths: Iterable[str | Path],
    *,
    root: str | Path | None = None,
    expected: LSVParameterExpectation | None = None,
) -> BatchValidationResult:
    """Validate every path independently so one failure never stops the batch."""

    expected = expected or LSVParameterExpectation()
    root_path = Path(root) if root is not None else None
    results: list[FileValidationResult] = []
    successful_headers: list[bytes] = []

    for supplied_path in paths:
        path = Path(supplied_path)
        source_path = _display_path(path, root_path)
        raw_before: bytes | None = None
        source_hash: str | None = None
        file_size: int | None = None
        try:
            raw_before = path.read_bytes()
            source_hash = hashlib.sha256(raw_before).hexdigest()
            file_size = len(raw_before)
            data = parse_lsv(path)
            raw_after = path.read_bytes()
            after_hash = hashlib.sha256(raw_after).hexdigest()
            unchanged = after_hash == source_hash
            if not unchanged:
                raise RuntimeError("Source file changed during validation.")

            diagnostic = data.diagnostics.to_dict()
            block_start = diagnostic["parameter_values"]["parameter_block_start"]
            header = raw_before[:data.data_start_byte]
            successful_headers.append(header)
            results.append(
                FileValidationResult(
                    source_path=source_path,
                    file_name=path.name,
                    source_sha256=source_hash,
                    source_unchanged=True,
                    parse_success=True,
                    experiment_type=data.experiment_type,
                    detected_experiment_text=diagnostic["detected_experiment_text"],
                    file_size_bytes=data.file_size_bytes,
                    header_size_bytes=len(header),
                    header_sha256=hashlib.sha256(header).hexdigest(),
                    n_points=data.n_points,
                    configured_start_potential_V=data.configured_start_potential_V,
                    configured_final_potential_V=data.configured_final_potential_V,
                    actual_first_potential_V=data.actual_first_potential_V,
                    actual_last_potential_V=data.actual_last_potential_V,
                    scan_rate_V_s=data.scan_rate_V_s,
                    potential_increment_V=data.potential_increment_V,
                    data_start_byte=data.data_start_byte,
                    parameter_block_start=block_start,
                    parameter_block_to_data_start_bytes=data.data_start_byte - block_start,
                    point_count_field_offsets=_selected_point_offsets(
                        diagnostic, data.n_points
                    ),
                    current_encoding=data.current_encoding,
                    validation_status=data.validation_status,
                    parameter_mismatches=_parameter_mismatches(data, expected),
                    warnings=data.warnings,
                    diagnostics=diagnostic,
                )
            )
        except Exception as exc:  # isolation is the defining batch behavior
            diagnostic_obj = exc.diagnostic if isinstance(exc, CHIParserError) else None
            diagnostic = diagnostic_obj.to_dict() if diagnostic_obj is not None else None
            errors = tuple(diagnostic_obj.errors) if diagnostic_obj is not None else (str(exc),)
            warnings = tuple(diagnostic_obj.warnings) if diagnostic_obj is not None else ()
            detected = diagnostic_obj.detected_experiment_text if diagnostic_obj else None
            unchanged = False
            if raw_before is not None:
                try:
                    unchanged = hashlib.sha256(path.read_bytes()).hexdigest() == source_hash
                except OSError:
                    unchanged = False
            results.append(
                FileValidationResult(
                    source_path=source_path,
                    file_name=path.name,
                    source_sha256=source_hash,
                    source_unchanged=unchanged,
                    parse_success=False,
                    detected_experiment_text=detected,
                    file_size_bytes=file_size,
                    validation_status="failed",
                    warnings=warnings,
                    errors=errors,
                    exception_type=type(exc).__name__,
                    diagnostics=diagnostic,
                )
            )

    varying_count, varying_ranges = _variation_ranges(successful_headers)
    return BatchValidationResult(
        tuple(results),
        header_variation_byte_count=varying_count,
        header_variation_ranges=varying_ranges,
    )


def write_batch_validation_csv(result: BatchValidationResult, path: str | Path) -> Path:
    """Write one metadata-only CSV row per input file."""

    output = Path(path)
    rows = [item.to_csv_row() for item in result.files]
    if not rows:
        raise ValueError("Cannot write a batch CSV for an empty result.")
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return output


def _format_unique(values: tuple[Any, ...]) -> str:
    return ", ".join(str(value) for value in values) if values else "none"


def write_batch_validation_report(result: BatchValidationResult, path: str | Path) -> Path:
    """Write a concise Markdown compatibility report without raw current values."""

    output = Path(path)
    lines = [
        "# CHI760E LSV batch compatibility validation",
        "",
        "## Summary",
        "",
        f"- Total files: {result.total_files}",
        f"- Parsed successfully: {result.successful_files}",
        f"- Failed: {result.failed_files}",
        f"- Files with warnings: {result.warning_files}",
        f"- Total warnings: {result.warning_count}",
        f"- Parameter mismatch files: {result.parameter_mismatch_files}",
        f"- Success rate: {result.success_rate:.2%}",
        "",
        "## Structural variants",
        "",
        f"- Unique file sizes: {_format_unique(result.unique_success_values('file_size_bytes'))}",
        f"- Unique header sizes: {_format_unique(result.unique_success_values('header_size_bytes'))}",
        f"- Unique header SHA-256 count: {len(result.unique_success_values('header_sha256'))}",
        f"- Header bytes that vary across successful files: {result.header_variation_byte_count}",
        f"- Header variation ranges: {_format_unique(result.header_variation_ranges)}",
        f"- Unique N values: {_format_unique(result.unique_success_values('n_points'))}",
        f"- Unique parameter block offsets: {_format_unique(result.unique_success_values('parameter_block_start'))}",
        f"- Unique data start offsets: {_format_unique(result.unique_success_values('data_start_byte'))}",
        "- Unique parameter block → data start distances: "
        f"{_format_unique(result.unique_success_values('parameter_block_to_data_start_bytes'))}",
        f"- Unique point-count field offsets: {_format_unique(result.unique_success_values('point_count_field_offsets'))}",
        "",
        "## Per-file results",
        "",
        "| File | Parsed | N | Start V | Final V | Actual last V | Scan V/s | Increment V | Parameter block | Data start | Distance | QC | Warnings / errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for item in result.files:
        details = " | ".join((*item.parameter_mismatches, *item.warnings, *item.errors))
        if item.parameter_match is None:
            qc = "not assessed"
        else:
            qc = "match" if item.parameter_match else "Parameter mismatch"
        values = (
            item.source_path,
            "yes" if item.parse_success else "no",
            item.n_points,
            item.configured_start_potential_V,
            item.configured_final_potential_V,
            item.actual_last_potential_V,
            item.scan_rate_V_s,
            item.potential_increment_V,
            item.parameter_block_start,
            item.data_start_byte,
            item.parameter_block_to_data_start_bytes,
            qc,
            details,
        )
        lines.append("| " + " | ".join("" if value is None else str(value) for value in values) + " |")
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output
