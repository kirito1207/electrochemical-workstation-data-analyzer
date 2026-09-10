"""Configurable, traceable LSV analysis built on validated CHI parser output."""

from .descriptive import DescriptiveStatistics, describe_values
from .lsv_analysis import (
    AnalysisSettings,
    LSVAnalysisResult,
    PotentialGridMismatchError,
    analyze_lsv_files,
    run_lsv_analysis,
)
from .metadata import (
    ExperimentManifest,
    ManifestEntry,
    MetadataResolutionError,
    infer_experiment_manifest,
)
from .outliers import OutlierFlag, flag_mad_outliers
from .potential import (
    CurrentAtPotential,
    PotentialOutOfRangeError,
    extract_current_at_potential,
)
from .statistics import ComparisonResult, compare_groups, holm_adjust

__all__ = [
    "AnalysisSettings",
    "ComparisonResult",
    "CurrentAtPotential",
    "DescriptiveStatistics",
    "ExperimentManifest",
    "LSVAnalysisResult",
    "ManifestEntry",
    "MetadataResolutionError",
    "OutlierFlag",
    "PotentialGridMismatchError",
    "PotentialOutOfRangeError",
    "analyze_lsv_files",
    "compare_groups",
    "describe_values",
    "extract_current_at_potential",
    "flag_mad_outliers",
    "holm_adjust",
    "infer_experiment_manifest",
    "run_lsv_analysis",
]
