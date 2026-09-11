"""Legacy Stage 4 concentration orchestration retained for regression compatibility."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import math
from pathlib import Path
from typing import Sequence

from chi_parser import ITData, parse_it

from .it_calibration import (
    CalibrationMetric,
    CalibrationResult,
    ConcentrationSummary,
    DeltaIResult,
    calculate_delta_i,
    fit_calibration,
    fit_group_mean_calibration,
    summarize_concentrations,
)
from .it_plateau import IntervalDefinition, PlateauResult, define_intervals, extract_plateaus
from .it_protocol import StepProtocol
from .it_qc import (
    DeltaDirectionQC,
    ITOutlierFlag,
    evaluate_delta_direction,
    flag_delta_outliers,
)


@dataclass(frozen=True, slots=True)
class ITAnalysisSettings:
    analysis_metric: CalibrationMetric = "signed"
    plateau_fraction: float = 0.20
    preferred_min_plateau_duration_s: float = 10.0
    minimum_plateau_points: int = 2
    direction_zero_tolerance_A: float = 1e-12
    analysis_timestamp: str | None = None
    outlier_method: str = "MAD modified z-score"
    software_version: str = "0.3.0"

    def resolved(self) -> "ITAnalysisSettings":
        if self.analysis_metric not in {"signed", "magnitude"}:
            raise ValueError("analysis_metric must be 'signed' or 'magnitude'.")
        if not 0.0 < self.plateau_fraction <= 1.0:
            raise ValueError("plateau_fraction must be in (0, 1].")
        if not math.isfinite(self.preferred_min_plateau_duration_s) or self.preferred_min_plateau_duration_s < 0.0:
            raise ValueError("preferred_min_plateau_duration_s must be finite and non-negative.")
        if self.minimum_plateau_points < 2:
            raise ValueError("minimum_plateau_points must be at least 2.")
        if not math.isfinite(self.direction_zero_tolerance_A) or self.direction_zero_tolerance_A < 0.0:
            raise ValueError("direction_zero_tolerance_A must be finite and non-negative.")
        timestamp = self.analysis_timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return replace(self, analysis_timestamp=timestamp)


@dataclass(frozen=True, slots=True)
class ITAnalysisInput:
    file_path: Path
    sample_id: str
    protocol: StepProtocol


@dataclass(frozen=True, slots=True)
class ITFileAnalysis:
    data: ITData
    sample_id: str
    protocol: StepProtocol
    intervals: tuple[IntervalDefinition, ...]
    plateaus: tuple[PlateauResult, ...]
    delta_i: tuple[DeltaIResult, ...]
    calibration: CalibrationResult
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ITFileAnalysisError:
    file_name: str
    sample_id: str
    exception_type: str
    message: str


@dataclass(frozen=True, slots=True)
class ITBatchAnalysisResult:
    settings: ITAnalysisSettings
    inputs: tuple[ITAnalysisInput, ...]
    files: tuple[ITFileAnalysis, ...]
    errors: tuple[ITFileAnalysisError, ...]
    concentration_summary: tuple[ConcentrationSummary, ...]
    group_mean_calibration: CalibrationResult | None
    outlier_flags: tuple[ITOutlierFlag, ...]
    current_direction_qc: tuple[DeltaDirectionQC, ...]
    warnings: tuple[str, ...]
    exclusion_log: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ITAnalysisRun:
    result: ITBatchAnalysisResult
    output_directory: Path
    generated_files: tuple[Path, ...]


def analyze_it_data(
    data: ITData,
    protocol: StepProtocol,
    *,
    sample_id: str,
    settings: ITAnalysisSettings | None = None,
) -> ITFileAnalysis:
    resolved = (settings or ITAnalysisSettings()).resolved()
    intervals = define_intervals(data, protocol)
    plateaus = extract_plateaus(
        data,
        protocol,
        sample_id=sample_id,
        plateau_fraction=resolved.plateau_fraction,
        preferred_min_plateau_duration_s=resolved.preferred_min_plateau_duration_s,
        minimum_plateau_points=resolved.minimum_plateau_points,
    )
    delta_i = calculate_delta_i(plateaus)
    calibration = fit_calibration(
        delta_i,
        analysis_metric=resolved.analysis_metric,
        sample_id=sample_id,
    )
    warnings = tuple(data.warnings) + tuple(
        f"Step {row.step_id}: {warning}"
        for row in plateaus
        for warning in row.warnings
    )
    return ITFileAnalysis(
        data=data,
        sample_id=sample_id,
        protocol=protocol,
        intervals=intervals,
        plateaus=plateaus,
        delta_i=delta_i,
        calibration=calibration,
        warnings=warnings,
    )


def analyze_it_file(
    path: str | Path,
    protocol: StepProtocol,
    *,
    sample_id: str,
    settings: ITAnalysisSettings | None = None,
) -> ITFileAnalysis:
    return analyze_it_data(
        parse_it(path),
        protocol,
        sample_id=sample_id,
        settings=settings,
    )


def analyze_it_batch(
    inputs: Sequence[ITAnalysisInput],
    *,
    settings: ITAnalysisSettings | None = None,
) -> ITBatchAnalysisResult:
    if not inputs:
        raise ValueError("At least one i-t analysis input is required.")
    sample_ids = [item.sample_id for item in inputs]
    if any(not sample_id.strip() for sample_id in sample_ids) or len(sample_ids) != len(set(sample_ids)):
        raise ValueError("sample_id values must be non-empty and unique within a batch.")
    resolved = (settings or ITAnalysisSettings()).resolved()
    successes: list[ITFileAnalysis] = []
    errors: list[ITFileAnalysisError] = []
    for item in inputs:
        try:
            successes.append(
                analyze_it_file(
                    item.file_path,
                    item.protocol,
                    sample_id=item.sample_id,
                    settings=resolved,
                )
            )
        except Exception as exc:
            errors.append(
                ITFileAnalysisError(
                    file_name=item.file_path.name,
                    sample_id=item.sample_id,
                    exception_type=type(exc).__name__,
                    message=str(exc),
                )
            )

    all_delta = tuple(row for result in successes for row in result.delta_i)
    summaries = summarize_concentrations(all_delta) if all_delta else ()
    warnings: list[str] = [
        f"{result.sample_id}: {warning}"
        for result in successes
        for warning in result.warnings
    ]
    group_calibration: CalibrationResult | None = None
    if summaries:
        try:
            group_calibration = fit_group_mean_calibration(
                summaries,
                analysis_metric=resolved.analysis_metric,
            )
        except ValueError as exc:
            warnings.append(f"Group mean calibration not calculated: {exc}")
    direction_qc = evaluate_delta_direction(
        all_delta,
        analysis_metric=resolved.analysis_metric,
        zero_tolerance_A=resolved.direction_zero_tolerance_A,
    ) if all_delta else ()
    warnings.extend(
        f"{row.concentration_uM:g} µM: {row.warning}"
        for row in direction_qc
        if row.warning
    )
    outliers = flag_delta_outliers(
        all_delta,
        analysis_metric=resolved.analysis_metric,
    ) if all_delta else ()
    return ITBatchAnalysisResult(
        settings=resolved,
        inputs=tuple(inputs),
        files=tuple(successes),
        errors=tuple(errors),
        concentration_summary=summaries,
        group_mean_calibration=group_calibration,
        outlier_flags=outliers,
        current_direction_qc=direction_qc,
        warnings=tuple(warnings),
    )


def _allocate_output_directory(base: Path, timestamp: str) -> Path:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    stem = parsed.strftime("%Y%m%d_%H%M%S")
    candidate = base / stem
    suffix = 1
    while candidate.exists():
        candidate = base / f"{stem}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def run_it_analysis(
    inputs: Sequence[ITAnalysisInput],
    *,
    output_base: str | Path = "results",
    settings: ITAnalysisSettings | None = None,
) -> ITAnalysisRun:
    result = analyze_it_batch(inputs, settings=settings)
    output = _allocate_output_directory(
        Path(output_base), result.settings.analysis_timestamp or ""
    )

    from export.it_csv import export_it_csv_bundle
    from export.it_excel import export_it_workbook
    from export.it_logging import export_it_analysis_log
    from plotting.it_annotated import plot_annotated_it
    from plotting.it_calibration import plot_it_calibrations
    from plotting.it_raw import plot_raw_it

    generated: list[Path] = []
    generated.extend(export_it_csv_bundle(result, output / "IT" / "csv"))
    generated.append(export_it_workbook(result, output / "IT" / "excel" / "IT_analysis.xlsx"))
    generated.append(export_it_analysis_log(result, output / "IT" / "logs" / "analysis_settings.json"))
    generated.extend(plot_raw_it(result, output / "IT" / "raw"))
    generated.extend(plot_annotated_it(result, output / "IT" / "annotated"))
    generated.extend(plot_it_calibrations(result, output / "IT" / "calibration"))
    return ITAnalysisRun(result, output, tuple(generated))


__all__ = [
    "ITAnalysisInput",
    "ITAnalysisRun",
    "ITAnalysisSettings",
    "ITBatchAnalysisResult",
    "ITFileAnalysis",
    "ITFileAnalysisError",
    "analyze_it_batch",
    "analyze_it_data",
    "analyze_it_file",
    "run_it_analysis",
]
