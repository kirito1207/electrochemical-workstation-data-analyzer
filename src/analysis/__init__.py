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
from .sign_qc import (
    CurrentSignQC,
    DEFAULT_SIGN_ZERO_TOLERANCE_A,
    MIXED_SIGN_WARNING,
    evaluate_current_signs,
)
from .statistics import ComparisonResult, compare_groups, holm_adjust
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
    "analyze_lsv_files",
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
    "infer_experiment_manifest",
    "define_intervals",
    "evaluate_delta_direction",
    "run_lsv_analysis",
    "run_it_analysis",
    "suggest_addition_times",
    "summarize_concentrations",
]
