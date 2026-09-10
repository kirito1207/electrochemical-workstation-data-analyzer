"""Technique-aware analysis APIs without experiment-preset dependencies.

PB42 names remain available through lazy compatibility lookup, but they are
not imported by Generic LSV or i-t analysis. New PB42 callers should import
from :mod:`presets.pb42` explicitly.
"""

from importlib import import_module
from typing import Any

from .descriptive import DescriptiveStatistics, describe_values
from .lsv_analysis import (
    AnalysisSettings,
    LSVAnalysisResult,
    PotentialGridMismatchError,
    analyze_lsv_with_manifest,
    run_lsv_analysis_with_manifest,
)
from .metadata import (
    ExperimentManifest,
    ManifestEntry,
    MetadataResolutionError,
    confirmed_generic_manifest,
    suggest_generic_manifest,
    validate_generic_manifest,
)
from .outliers import OutlierFlag, flag_mad_outliers
from .potential import (
    CurrentAtPotential,
    PotentialOutOfRangeError,
    extract_current_at_potential,
)
from .sign_qc import (
    CurrentSignQC,
    DEFAULT_SIGN_ZERO_TOLERANCE_A,
    MIXED_SIGN_WARNING,
    evaluate_current_signs,
)
from .statistics import (
    ComparisonDefinition,
    ComparisonResult,
    compare_defined_groups,
    compare_groups,
    holm_adjust,
)
from .techniques import (
    TechniqueRoute,
    TechniqueRoutingError,
    route_for_experiment_type,
)
from .it_analysis import (
    ITAnalysisInput,
    ITAnalysisRun,
    ITAnalysisSettings,
    ITBatchAnalysisResult,
    ITFileAnalysis,
    ITFileAnalysisError,
    analyze_it_batch,
    analyze_it_data,
    analyze_it_file,
    run_it_analysis,
)
from .it_calibration import (
    CalibrationResult,
    ConcentrationSummary,
    DeltaIResult,
    calculate_delta_i,
    fit_calibration,
    fit_group_mean_calibration,
    summarize_concentrations,
)
from .it_plateau import (
    IntervalDefinition,
    PlateauExtractionError,
    PlateauResult,
    define_intervals,
    extract_plateaus,
)
from .it_protocol import StepDefinition, StepProtocol, StepProtocolError
from .it_qc import (
    AdditionTimeSuggestion,
    DeltaDirectionQC,
    ITOutlierFlag,
    evaluate_delta_direction,
    flag_delta_outliers,
    suggest_addition_times,
)

__all__ = [
    "AnalysisSettings",
    "ComparisonResult",
    "ComparisonDefinition",
    "CurrentAtPotential",
    "CurrentSignQC",
    "DEFAULT_SIGN_ZERO_TOLERANCE_A",
    "DescriptiveStatistics",
    "ExperimentManifest",
    "LSVAnalysisResult",
    "ITAnalysisInput",
    "ITAnalysisRun",
    "ITAnalysisSettings",
    "ITBatchAnalysisResult",
    "ITFileAnalysis",
    "ITFileAnalysisError",
    "ITOutlierFlag",
    "AdditionTimeSuggestion",
    "CalibrationResult",
    "ConcentrationSummary",
    "DeltaDirectionQC",
    "DeltaIResult",
    "IntervalDefinition",
    "ManifestEntry",
    "MetadataResolutionError",
    "MIXED_SIGN_WARNING",
    "OutlierFlag",
    "PlateauExtractionError",
    "PlateauResult",
    "PotentialGridMismatchError",
    "PotentialOutOfRangeError",
    "StepDefinition",
    "StepProtocol",
    "StepProtocolError",
    "analyze_it_batch",
    "analyze_it_data",
    "analyze_it_file",
    "analyze_lsv_with_manifest",
    "compare_defined_groups",
    "compare_groups",
    "calculate_delta_i",
    "describe_values",
    "extract_current_at_potential",
    "extract_plateaus",
    "evaluate_current_signs",
    "flag_mad_outliers",
    "flag_delta_outliers",
    "fit_calibration",
    "fit_group_mean_calibration",
    "holm_adjust",
    "suggest_generic_manifest",
    "confirmed_generic_manifest",
    "define_intervals",
    "evaluate_delta_direction",
    "run_lsv_analysis_with_manifest",
    "run_it_analysis",
    "suggest_addition_times",
    "summarize_concentrations",
    "validate_generic_manifest",
    "TechniqueRoute",
    "TechniqueRoutingError",
    "route_for_experiment_type",
]


_LEGACY_PB42_EXPORTS = {
    "CURRENT_PB_42_TEMPLATE",
    "GroupDesign",
    "PB42ExperimentTemplate",
    "analyze_lsv_files",
    "infer_current_pb42_manifest",
    "infer_experiment_manifest",
    "run_lsv_analysis",
    "validate_current_pb42_design",
}


def __getattr__(name: str) -> Any:
    """Resolve legacy PB42 package-level names without an eager dependency."""

    if name in _LEGACY_PB42_EXPORTS:
        return getattr(import_module("presets.pb42"), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
