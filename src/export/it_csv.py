"""Traceable CSV exports for i-t step and calibration analysis."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

from analysis.it_analysis import ITBatchAnalysisResult


def _write_rows(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    fieldnames: Sequence[str],
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _protocol_rows(result: ITBatchAnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "source_file": item.file_path.name,
            "sample_id": item.sample_id,
            "protocol_source": item.protocol.source,
            "user_confirmed": item.protocol.user_confirmed,
            **asdict(step),
        }
        for item in result.inputs
        for step in item.protocol.steps
    ]


def _interval_rows(result: ITBatchAnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "source_file": item.data.file_name,
            "sample_id": item.sample_id,
            **asdict(interval),
        }
        for item in result.files
        for interval in item.intervals
    ]


def _plateau_rows(result: ITBatchAnalysisResult) -> list[dict[str, object]]:
    rows = []
    for item in result.files:
        for plateau in item.plateaus:
            row = asdict(plateau)
            row["warnings"] = " | ".join(plateau.warnings)
            rows.append(row)
    return rows


def _delta_rows(result: ITBatchAnalysisResult) -> list[dict[str, object]]:
    return [asdict(row) for item in result.files for row in item.delta_i]


def _calibration_rows(result: ITBatchAnalysisResult) -> list[dict[str, object]]:
    calibrations = [item.calibration for item in result.files]
    if result.group_mean_calibration is not None:
        calibrations.append(result.group_mean_calibration)
    rows = []
    for calibration in calibrations:
        row = asdict(calibration)
        row["included_concentrations_uM"] = ", ".join(
            f"{value:g}" for value in calibration.included_concentrations_uM
        )
        rows.append(row)
    return rows


def export_it_csv_bundle(
    result: ITBatchAnalysisResult,
    output_dir: str | Path,
) -> tuple[Path, ...]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    protocol_rows = _protocol_rows(result)
    generated.append(
        _write_rows(output / "step_protocol.csv", protocol_rows, tuple(protocol_rows[0]))
    )
    interval_rows = _interval_rows(result)
    generated.append(
        _write_rows(
            output / "interval_definitions.csv",
            interval_rows,
            tuple(interval_rows[0]) if interval_rows else ("source_file", "sample_id"),
        )
    )
    plateau_rows = _plateau_rows(result)
    generated.append(
        _write_rows(
            output / "plateau_results.csv",
            plateau_rows,
            tuple(plateau_rows[0]) if plateau_rows else ("source_file", "sample_id"),
        )
    )
    delta_rows = _delta_rows(result)
    generated.append(
        _write_rows(
            output / "deltaI_data.csv",
            delta_rows,
            tuple(delta_rows[0]) if delta_rows else ("source_file", "sample_id"),
        )
    )
    calibration_rows = _calibration_rows(result)
    generated.append(
        _write_rows(
            output / "calibration.csv",
            calibration_rows,
            tuple(calibration_rows[0]) if calibration_rows else ("sample_id", "fit_basis"),
        )
    )
    summary_rows = [asdict(row) for row in result.concentration_summary]
    generated.append(
        _write_rows(
            output / "concentration_summary.csv",
            summary_rows,
            tuple(summary_rows[0]) if summary_rows else ("concentration_uM", "n"),
        )
    )
    outlier_rows = [asdict(row) for row in result.outlier_flags]
    outlier_fields = (
        "source_file",
        "sample_id",
        "concentration_uM",
        "response_uA",
        "analysis_metric",
        "method",
        "reason",
        "status",
    )
    generated.append(_write_rows(output / "outlier_flags.csv", outlier_rows, outlier_fields))
    direction_rows = [asdict(row) for row in result.current_direction_qc]
    generated.append(
        _write_rows(
            output / "current_direction_qc.csv",
            direction_rows,
            tuple(direction_rows[0]) if direction_rows else ("concentration_uM",),
        )
    )
    generated.append(
        _write_rows(
            output / "exclusion_log.csv",
            [{"status": "All data included", "source_file": "", "reason": ""}],
            ("status", "source_file", "reason"),
        )
    )

    raw_dir = output / "raw_it"
    for item in result.files:
        rows = [
            {
                "Time_s": float(time),
                "Current_A": float(current),
                "Current_uA": float(current * 1e6),
            }
            for time, current in zip(item.data.time_s, item.data.current_A, strict=True)
        ]
        generated.append(
            _write_rows(
                raw_dir / f"{item.sample_id}_{Path(item.data.file_name).stem}.csv",
                rows,
                ("Time_s", "Current_A", "Current_uA"),
            )
        )
    return tuple(generated)


__all__ = [
    "export_it_csv_bundle",
    "_calibration_rows",
    "_delta_rows",
    "_interval_rows",
    "_plateau_rows",
    "_protocol_rows",
]
