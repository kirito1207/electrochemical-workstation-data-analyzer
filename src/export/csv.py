"""Machine-readable CSV exports with one record per observation."""

from __future__ import annotations

import csv
import re
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Sequence

from analysis.lsv_analysis import LSVAnalysisResult


def _safe_filename_component(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or "unnamed"


def _write_rows(path: Path, rows: Sequence[Mapping[str, object]], fieldnames: Sequence[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def _selected_rows(result: LSVAnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "file_name": item.manifest.file_name,
            "relative_path": item.manifest.relative_path,
            "source_sha256": item.data.source_sha256,
            "group": item.manifest.group,
            "electrode_type": item.manifest.electrode_type,
            "sample_id": item.manifest.sample_id,
            "target_potential_V": item.selected.target_potential_V,
            "signed_current_A": item.selected.current_A,
            "signed_current_uA": item.selected.current_uA,
            "response_magnitude_uA": item.selected.response_magnitude_uA,
            "interpolated": item.selected.interpolated,
            "lower_potential_V": item.selected.lower_potential_V,
            "upper_potential_V": item.selected.upper_potential_V,
        }
        for item in result.files
    ]


def _summary_rows(result: LSVAnalysisResult) -> list[dict[str, object]]:
    rows = []
    for item in result.group_summaries:
        row = {
            "group": item.group,
            "analysis_metric": item.analysis_metric,
            "target_potential_V": result.settings.target_potential_V,
            "unit": item.unit,
        }
        row.update(asdict(item.statistics))
        rows.append(row)
    return rows


def _statistics_rows(result: LSVAnalysisResult) -> list[dict[str, object]]:
    return [
        {
            "target_potential_V": result.settings.target_potential_V,
            "analysis_metric": result.settings.analysis_metric,
            **asdict(item),
        }
        for item in result.comparisons
    ]


def export_csv_bundle(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated: list[Path] = []

    manifest_rows = [asdict(item.manifest) for item in result.files]
    generated.append(
        _write_rows(
            output / "experiment_manifest.csv",
            manifest_rows,
            (
                "file_name", "relative_path", "group", "electrode_type",
                "sample_id", "notes", "file_path",
            ),
        )
    )

    parameter_rows = [
        {
            "file_name": item.manifest.file_name,
            "relative_path": item.manifest.relative_path,
            "experiment_type": item.data.experiment_type,
            "file_size_bytes": item.data.file_size_bytes,
            "n_points": item.data.n_points,
            "configured_start_potential_V": item.data.configured_start_potential_V,
            "configured_final_potential_V": item.data.configured_final_potential_V,
            "actual_first_potential_V": item.data.actual_first_potential_V,
            "actual_last_potential_V": item.data.actual_last_potential_V,
            "scan_rate_V_s": item.data.scan_rate_V_s,
            "potential_increment_V": item.data.potential_increment_V,
            "data_start_byte": item.data.data_start_byte,
            "current_encoding": item.data.current_encoding,
            "validation_status": item.data.validation_status,
        }
        for item in result.files
    ]
    generated.append(
        _write_rows(
            output / "experiment_parameters.csv",
            parameter_rows,
            tuple(parameter_rows[0]),
        )
    )

    selected_rows = _selected_rows(result)
    generated.append(
        _write_rows(
            output / "selected_potential_data.csv",
            selected_rows,
            tuple(selected_rows[0]),
        )
    )
    summary_rows = _summary_rows(result)
    generated.append(
        _write_rows(output / "group_summary.csv", summary_rows, tuple(summary_rows[0]))
    )
    statistics_rows = _statistics_rows(result)
    generated.append(
        _write_rows(output / "statistics.csv", statistics_rows, tuple(statistics_rows[0]))
    )

    outlier_rows = [asdict(item) for item in result.outlier_flags]
    outlier_fields = (
        "file_name",
        "group",
        "sample_id",
        "target_potential_V",
        "response",
        "analysis_metric",
        "outlier_method",
        "outlier_reason",
        "status",
    )
    generated.append(_write_rows(output / "outlier_flags.csv", outlier_rows, outlier_fields))
    generated.append(
        _write_rows(
            output / "exclusion_log.csv",
            [{"status": "All data included", "file_name": "", "reason": ""}],
            ("status", "file_name", "reason"),
        )
    )

    parsed_dir = output / "parsed_lsv"
    for item in result.files:
        rows = [
            {
                "Potential_V": float(potential),
                "Current_A": float(current),
                "Current_uA": float(current * 1e6),
            }
            for potential, current in zip(
                item.data.potential_V, item.data.current_A, strict=True
            )
        ]
        name = (
            f"group_{_safe_filename_component(item.manifest.group or 'unresolved')}_"
            f"{_safe_filename_component(item.manifest.sample_id or 'unresolved')}_"
            f"{_safe_filename_component(Path(item.manifest.file_name).stem)}.csv"
        )
        generated.append(
            _write_rows(parsed_dir / name, rows, ("Potential_V", "Current_A", "Current_uA"))
        )
    return tuple(generated)


__all__ = ["export_csv_bundle", "_selected_rows", "_statistics_rows", "_summary_rows"]
