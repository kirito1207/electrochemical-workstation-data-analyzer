"""End-to-end LSV analysis orchestration without GUI or parser coupling."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Sequence

import numpy as np

from chi_parser import LSVData, parse_lsv

from .descriptive import DescriptiveStatistics, describe_values
from .metadata import ExperimentManifest, ManifestEntry, infer_experiment_manifest
from .outliers import OutlierFlag, flag_mad_outliers
from .potential import CurrentAtPotential, extract_current_at_potential
from .sign_qc import CurrentSignQC, evaluate_current_signs
from .statistics import ComparisonResult, compare_groups


AnalysisMetric = Literal["magnitude", "signed"]


class PotentialGridMismatchError(ValueError):
    """Raised rather than silently averaging curves by index on different grids."""


@dataclass(frozen=True, slots=True)
class AnalysisSettings:
    target_potential_V: float = 0.0
    analysis_metric: AnalysisMetric = "magnitude"
    analysis_timestamp: str | None = None
    bootstrap_seed: int = 20260910
    bootstrap_resamples: int = 5000
    outlier_method: str = "MAD modified z-score"
    sign_zero_tolerance_A: float = 1e-12
    software_version: str = "0.2.1"

    def resolved(self) -> "AnalysisSettings":
        if self.analysis_metric not in {"magnitude", "signed"}:
            raise ValueError("analysis_metric must be 'magnitude' or 'signed'.")
        if self.bootstrap_resamples < 5000:
            raise ValueError("bootstrap_resamples must be at least 5000.")
        if not np.isfinite(self.sign_zero_tolerance_A) or self.sign_zero_tolerance_A < 0.0:
            raise ValueError("sign_zero_tolerance_A must be a finite non-negative value.")
        timestamp = self.analysis_timestamp or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return replace(self, analysis_timestamp=timestamp)


@dataclass(frozen=True, slots=True)
class AnalyzedLSVFile:
    manifest: ManifestEntry
    data: LSVData
    selected: CurrentAtPotential


@dataclass(frozen=True, slots=True)
class GroupSummary:
    group: str
    analysis_metric: AnalysisMetric
    unit: str
    statistics: DescriptiveStatistics


@dataclass(frozen=True, slots=True)
class LSVAnalysisResult:
    settings: AnalysisSettings
    manifest: ExperimentManifest
    files: tuple[AnalyzedLSVFile, ...]
    group_summaries: tuple[GroupSummary, ...]
    comparisons: tuple[ComparisonResult, ...]
    outlier_flags: tuple[OutlierFlag, ...]
    current_sign_qc: tuple[CurrentSignQC, ...]
    warnings: tuple[str, ...]
    exclusion_log: tuple[str, ...] = ()

    def summary(self, group: str, metric: AnalysisMetric) -> GroupSummary:
        return next(
            item
            for item in self.group_summaries
            if item.group == group and item.analysis_metric == metric
        )


@dataclass(frozen=True, slots=True)
class AnalysisRun:
    result: LSVAnalysisResult
    output_directory: Path
    generated_files: tuple[Path, ...]


def validate_common_potential_grid(
    datasets: Sequence[LSVData], *, absolute_tolerance_V: float = 1e-12
) -> np.ndarray:
    if not datasets:
        raise ValueError("No LSV datasets were supplied.")
    reference = datasets[0].potential_V
    for data in datasets[1:]:
        if len(data.potential_V) != len(reference) or not np.allclose(
            data.potential_V,
            reference,
            rtol=0.0,
            atol=absolute_tolerance_V,
        ):
            raise PotentialGridMismatchError(
                f"Potential grid differs for {data.file_name}; index-wise averaging is forbidden."
            )
    return reference.copy()


def _metric_value(item: AnalyzedLSVFile, metric: AnalysisMetric) -> float:
    return (
        item.selected.response_magnitude_uA
        if metric == "magnitude"
        else item.selected.current_uA
    )


def analyze_lsv_files(
    paths: Sequence[str | Path],
    *,
    root: str | Path,
    settings: AnalysisSettings | None = None,
) -> LSVAnalysisResult:
    """Parse, classify, extract and analyze a confirmed 42-file LSV experiment."""

    resolved = (settings or AnalysisSettings()).resolved()
    path_objects = tuple(Path(path) for path in paths)
    manifest = infer_experiment_manifest(path_objects, root=root)
    manifest.require_valid()

    parsed = tuple(parse_lsv(path) for path in path_objects)
    validate_common_potential_grid(parsed)
    analyzed = tuple(
        AnalyzedLSVFile(
            manifest=entry,
            data=data,
            selected=extract_current_at_potential(data, resolved.target_potential_V),
        )
        for entry, data in zip(manifest.entries, parsed, strict=True)
    )

    group_summaries: list[GroupSummary] = []
    grouped_primary: dict[str, list[float]] = {}
    outlier_flags: list[OutlierFlag] = []
    current_sign_qc: list[CurrentSignQC] = []
    all_material_currents_A: list[float] = []
    for group in ("A", "B", "C"):
        material = [
            item
            for item in analyzed
            if item.manifest.group == group and item.manifest.electrode_type == "Material"
        ]
        if len(material) != 13:
            raise ValueError(f"Group {group} does not contain exactly 13 Material electrodes.")
        signed_currents_A = [item.selected.current_A for item in material]
        all_material_currents_A.extend(signed_currents_A)
        current_sign_qc.append(
            evaluate_current_signs(
                signed_currents_A,
                group=group,
                target_potential_V=resolved.target_potential_V,
                analysis_metric=resolved.analysis_metric,
                zero_tolerance_A=resolved.sign_zero_tolerance_A,
            )
        )
        for metric in ("signed", "magnitude"):
            values = [_metric_value(item, metric) for item in material]
            group_summaries.append(
                GroupSummary(
                    group=group,
                    analysis_metric=metric,
                    unit="µA",
                    statistics=describe_values(values),
                )
            )
        chosen_values = [_metric_value(item, resolved.analysis_metric) for item in material]
        grouped_primary[group] = chosen_values
        outlier_flags.extend(
            flag_mad_outliers(
                [
                    (
                        item.manifest.file_name,
                        group,
                        item.manifest.sample_id or "",
                        _metric_value(item, resolved.analysis_metric),
                    )
                    for item in material
                ],
                target_potential_V=resolved.target_potential_V,
                analysis_metric=resolved.analysis_metric,
            )
        )

    current_sign_qc.append(
        evaluate_current_signs(
            all_material_currents_A,
            group="ALL",
            target_potential_V=resolved.target_potential_V,
            analysis_metric=resolved.analysis_metric,
            zero_tolerance_A=resolved.sign_zero_tolerance_A,
        )
    )
    warnings = tuple(
        f"Group {item.group}: {item.warning}"
        for item in current_sign_qc
        if item.group != "ALL" and item.warning
    )

    comparisons = compare_groups(
        grouped_primary,
        bootstrap_seed=resolved.bootstrap_seed,
        bootstrap_resamples=resolved.bootstrap_resamples,
    )
    return LSVAnalysisResult(
        settings=resolved,
        manifest=manifest,
        files=analyzed,
        group_summaries=tuple(group_summaries),
        comparisons=comparisons,
        outlier_flags=tuple(outlier_flags),
        current_sign_qc=tuple(current_sign_qc),
        warnings=warnings,
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


def run_lsv_analysis(
    input_root: str | Path,
    *,
    output_base: str | Path = "results",
    settings: AnalysisSettings | None = None,
) -> AnalysisRun:
    """Run analysis and export a new, non-overwriting result directory."""

    root = Path(input_root)
    paths = sorted(root.rglob("*.bin"))
    result = analyze_lsv_files(paths, root=root, settings=settings)
    output = _allocate_output_directory(Path(output_base), result.settings.analysis_timestamp or "")

    from export.csv import export_csv_bundle
    from export.excel import export_analysis_workbook
    from export.logging import export_analysis_settings
    from plotting.lsv_mean import plot_mean_lsv
    from plotting.lsv_raw import plot_raw_lsv
    from plotting.repeatability import plot_repeatability
    from plotting.selected_potential import plot_selected_potential

    generated: list[Path] = []
    generated.extend(export_csv_bundle(result, output / "LSV" / "csv"))
    generated.append(export_analysis_workbook(result, output / "LSV" / "excel" / "LSV_analysis.xlsx"))
    generated.append(export_analysis_settings(result, output / "LSV" / "logs" / "analysis_settings.json"))
    generated.extend(plot_raw_lsv(result, output / "LSV" / "raw_curves"))
    generated.extend(plot_mean_lsv(result, output / "LSV" / "mean_curves"))
    generated.extend(plot_selected_potential(result, output / "LSV" / "selected_potential"))
    generated.extend(plot_repeatability(result, output / "LSV" / "repeatability"))
    return AnalysisRun(result=result, output_directory=output, generated_files=tuple(generated))
