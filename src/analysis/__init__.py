"""Technique-aware analysis APIs without experiment-preset dependencies.

PB42 callers must import :mod:`presets.pb42` explicitly. Generic i-t callers
use the Event APIs; Stage 4 concentration APIs remain exported only for
backward-compatible historical workflows.
"""

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
    OmnibusTestResult,
    compare_defined_groups,
    compute_omnibus_tests,
    holm_adjust,
    kruskal_wallis,
    welch_anova,
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
from .it_events import (
    CalibrationSelection, Event, EventAnalysisError, EventCalibrationResult,
    EventResponse, EventResponseSummary, EventTimeline, ITAnalysisMode,
    ITContinuousSummary, ITEventBatchResult, ITEventFileResult,
    ITEventInput, PlateauPolicy, ResponseWindow, WindowStatistics,
    analyze_it_continuous_batch, analyze_it_event_batch, analyze_it_events, calculate_event_responses,
    define_response_windows, extract_window_statistics, fit_event_calibration,
    summarize_event_responses, summarize_it_continuous_record,
)
from .it_stability import (
    ContinuousGroupSummary, ContinuousInterruption, ContinuousSegmentResult,
    ContinuousStabilityResult, ContinuousStabilitySettings, InterruptionType,
    RETENTION_REFERENCE_EPSILON_A, analyze_continuous_record,
    analyze_it_continuous_batch, summarize_continuous_groups,
    validate_interruption_set,
)

__all__ = [
    "AnalysisSettings",
    "ComparisonResult",
    "ComparisonDefinition",
    "OmnibusTestResult",
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
    "compute_omnibus_tests",
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
    "kruskal_wallis",
    "suggest_generic_manifest",
    "confirmed_generic_manifest",
    "define_intervals",
    "evaluate_delta_direction",
    "run_lsv_analysis_with_manifest",
    "run_it_analysis",
    "suggest_addition_times",
    "summarize_concentrations",
    "validate_generic_manifest",
    "welch_anova",
    "TechniqueRoute",
    "TechniqueRoutingError",
    "route_for_experiment_type",
]

__all__ += [
    "CalibrationSelection", "Event", "EventAnalysisError", "EventCalibrationResult",
    "EventResponse", "EventResponseSummary", "EventTimeline", "ITAnalysisMode",
    "ITContinuousSummary", "ITEventBatchResult", "ITEventFileResult",
    "ITEventInput", "PlateauPolicy", "ResponseWindow", "WindowStatistics",
    "analyze_it_continuous_batch", "analyze_it_event_batch", "analyze_it_events", "calculate_event_responses",
    "define_response_windows", "extract_window_statistics", "fit_event_calibration",
    "summarize_event_responses", "summarize_it_continuous_record",
]

__all__ += [
    "ContinuousGroupSummary", "ContinuousInterruption", "ContinuousSegmentResult",
    "ContinuousStabilityResult", "ContinuousStabilitySettings", "InterruptionType",
    "RETENTION_REFERENCE_EPSILON_A", "analyze_continuous_record",
    "summarize_continuous_groups", "validate_interruption_set",
]
