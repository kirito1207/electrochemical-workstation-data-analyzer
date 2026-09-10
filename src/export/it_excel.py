"""Excel workbook for traceable i-t step and calibration analysis."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from openpyxl import Workbook

from analysis.it_analysis import ITBatchAnalysisResult

from .excel import _append_table
from .it_csv import (
    _calibration_rows,
    _delta_rows,
    _interval_rows,
    _plateau_rows,
    _protocol_rows,
)


def _dict_table(sheet, rows, headers) -> None:
    _append_table(
        sheet,
        headers,
        ([row.get(header) for header in headers] for row in rows),
    )


def export_it_workbook(result: ITBatchAnalysisResult, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)

    included = (
        result.group_mean_calibration.included_concentrations_uM
        if result.group_mean_calibration is not None
        else ()
    )
    settings_rows = (
        ("analysis_timestamp", result.settings.analysis_timestamp),
        ("analysis_metric", result.settings.analysis_metric),
        ("plateau_fraction", result.settings.plateau_fraction),
        ("preferred_min_plateau_duration_s", result.settings.preferred_min_plateau_duration_s),
        ("minimum_plateau_points", result.settings.minimum_plateau_points),
        ("direction_zero_tolerance_A", result.settings.direction_zero_tolerance_A),
        ("step_protocol_source", "Per-file user-confirmed StepProtocol"),
        ("linear_regression_method", "ordinary least squares"),
        ("included_concentrations_uM", ", ".join(f"{value:g}" for value in included)),
        ("outlier_method", result.settings.outlier_method),
        ("lod", "LOD not calculated: insufficient independent blank replicates"),
        ("warnings", " | ".join(result.warnings) if result.warnings else "None"),
        ("exclusions", "All data included"),
        ("software_version", result.settings.software_version),
    )
    _append_table(
        workbook.create_sheet("Analysis_Settings"),
        ("Setting", "Value"),
        settings_rows,
    )

    success_by_sample = {item.sample_id: item for item in result.files}
    error_by_sample = {item.sample_id: item for item in result.errors}
    metadata_rows = []
    for item in result.inputs:
        success = success_by_sample.get(item.sample_id)
        error = error_by_sample.get(item.sample_id)
        metadata_rows.append(
            {
                "source_file": item.file_path.name,
                "sample_id": item.sample_id,
                "source_sha256": success.data.source_sha256 if success else "",
                "parse_success": success is not None,
                "applied_potential_V": success.data.applied_potential_V if success else None,
                "sample_interval_s": success.data.sample_interval_s if success else None,
                "n_points": success.data.n_points if success else None,
                "actual_last_time_s": success.data.actual_last_time_s if success else None,
                "protocol_confirmed": item.protocol.user_confirmed,
                "error_type": error.exception_type if error else "",
                "error": error.message if error else "",
            }
        )
    _dict_table(workbook.create_sheet("File_Metadata"), metadata_rows, tuple(metadata_rows[0]))

    tables = (
        ("Step_Protocol", _protocol_rows(result)),
        ("Interval_Definitions", _interval_rows(result)),
        ("Plateau_Results", _plateau_rows(result)),
        ("DeltaI_Data", _delta_rows(result)),
        ("Calibration", _calibration_rows(result)),
        ("Concentration_Summary", [asdict(row) for row in result.concentration_summary]),
        ("Outlier_Flags", [asdict(row) for row in result.outlier_flags]),
        ("Current_Direction_QC", [asdict(row) for row in result.current_direction_qc]),
    )
    fallback_headers = {
        "Interval_Definitions": (
            "source_file", "sample_id", "step_id", "concentration_uM",
            "include_in_calibration", "interval_start_s", "interval_end_s",
            "end_inclusive", "notes",
        ),
        "Plateau_Results": (
            "source_file", "sample_id", "step_id", "concentration_uM",
            "include_in_calibration", "interval_start_s", "interval_end_s",
            "end_inclusive", "plateau_start_s", "plateau_end_s", "plateau_duration_s",
            "plateau_n_points", "plateau_mean_A", "plateau_mean_uA", "plateau_sd_A",
            "plateau_sd_uA", "plateau_sem_uA", "plateau_drift_uA_per_s", "warnings",
        ),
        "DeltaI_Data": (
            "source_file", "sample_id", "step_id", "concentration_uM",
            "include_in_calibration", "plateau_mean_A", "plateau_mean_uA",
            "baseline_mean_A", "baseline_mean_uA", "signed_delta_I_A",
            "signed_delta_I_uA", "magnitude_delta_I_uA",
        ),
        "Calibration": (
            "sample_id", "fit_basis", "analysis_metric", "slope_uA_per_uM",
            "intercept_uA", "r_squared", "n_points", "included_concentrations_uM",
            "regression_method", "lod_status", "lod_reason",
        ),
        "Concentration_Summary": (
            "concentration_uM", "n", "mean_signed_delta_I_uA", "sd_signed_delta_I_uA",
            "sem_signed_delta_I_uA", "cv_signed_percent", "mean_magnitude_delta_I_uA",
            "sd_magnitude_delta_I_uA", "sem_magnitude_delta_I_uA",
            "cv_magnitude_percent", "included_count", "excluded_count",
            "include_in_group_calibration",
        ),
        "Outlier_Flags": (
            "source_file", "sample_id", "concentration_uM", "response_uA",
            "analysis_metric", "method", "reason", "status",
        ),
        "Current_Direction_QC": (
            "concentration_uM", "zero_tolerance_A", "negative_count", "positive_count",
            "near_zero_count", "total_count", "direction_consistent", "warning",
        ),
    }
    for title, rows in tables:
        headers = tuple(rows[0]) if rows else fallback_headers.get(title, ("status",))
        _dict_table(workbook.create_sheet(title), rows, headers)

    _append_table(
        workbook.create_sheet("Exclusion_Log"),
        ("status", "source_file", "reason"),
        (("All data included", "", ""),),
    )

    dark_tabs = {"Analysis_Settings", "Calibration", "Concentration_Summary", "Current_Direction_QC"}
    for sheet in workbook.worksheets:
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.sheet_properties.tabColor = "1F4E78" if sheet.title in dark_tabs else "9DC3E6"
    workbook.save(output)
    return output


__all__ = ["export_it_workbook"]
