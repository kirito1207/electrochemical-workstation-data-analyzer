"""Interruption-aware Continuous i-t stability analysis.

This module is intentionally separate from Event-response analysis.  It never
modifies, smooths, repairs, interpolates, or detrends the immutable raw arrays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

import numpy as np
from scipy import stats

from .descriptive import describe_values
from .it_events import (EventAnalysisError, EventTimeline, ITAnalysisMode,
                        ITContinuousSummary, ITEventBatchResult, ITEventFileResult,
                        ITEventInput, summarize_it_continuous_record)


RETENTION_REFERENCE_EPSILON_A = 1e-12


class InterruptionType(str, Enum):
    ACQUISITION_ERROR = "acquisition_error"
    MANUAL_PAUSE = "manual_pause"
    ELECTRODE_ADJUSTMENT = "electrode_adjustment"
    CONNECTION_ISSUE = "connection_issue"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class ContinuousInterruption:
    interval_id: str
    start_s: float
    end_s: float
    interruption_type: InterruptionType = InterruptionType.OTHER
    reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "interruption_type", InterruptionType(self.interruption_type))

    def validate(self) -> None:
        if not self.interval_id.strip():
            raise EventAnalysisError("Interruption interval_id must be non-empty.")
        if not (math.isfinite(self.start_s) and math.isfinite(self.end_s)):
            raise EventAnalysisError("Interruption bounds must be finite.")
        if self.start_s >= self.end_s:
            raise EventAnalysisError("Interruption start_s must be less than end_s.")
        try:
            InterruptionType(self.interruption_type)
        except ValueError as error:
            raise EventAnalysisError("Unknown interruption type.") from error


@dataclass(frozen=True, slots=True)
class ContinuousStabilitySettings:
    analysis_start_s: float | None = None
    analysis_end_s: float | None = None
    early_start_s: float | None = None
    early_end_s: float | None = None
    late_start_s: float | None = None
    late_end_s: float | None = None
    minimum_points: int = 2
    retention_reference_epsilon_A: float = RETENTION_REFERENCE_EPSILON_A

    def validate(self) -> None:
        for name in ("analysis", "early", "late"):
            start = getattr(self, f"{name}_start_s")
            end = getattr(self, f"{name}_end_s")
            if (start is None) != (end is None):
                raise EventAnalysisError(f"{name.title()} window requires both start and end.")
            if start is not None and (not math.isfinite(start) or not math.isfinite(end) or start >= end):
                raise EventAnalysisError(f"{name.title()} window requires finite start < end.")
        if self.minimum_points < 2:
            raise EventAnalysisError("Continuous windows require at least 2 real samples.")
        if not math.isfinite(self.retention_reference_epsilon_A) or self.retention_reference_epsilon_A <= 0:
            raise EventAnalysisError("Retention reference guard must be a positive finite value.")


@dataclass(frozen=True, slots=True)
class ContinuousSegmentResult:
    source_file: str
    sample_id: str
    group: str
    segment_id: str
    start_s: float
    end_s: float
    duration_s: float
    n_points: int
    mean_A: float | None
    sd_A: float | None
    slope_A_per_s: float | None
    intercept_A: float | None
    r_squared: float | None
    status: str


@dataclass(frozen=True, slots=True)
class ContinuousStabilityResult:
    source_file: str
    sample_id: str
    group: str
    record_start_s: float
    record_end_s: float
    duration_s: float
    analysis_start_s: float
    analysis_end_s: float
    early_window_start_s: float | None
    early_window_end_s: float | None
    early_mean_A: float | None
    early_sd_A: float | None
    late_window_start_s: float | None
    late_window_end_s: float | None
    late_mean_A: float | None
    late_sd_A: float | None
    delta_current_A: float | None
    delta_magnitude_A: float | None
    retention_magnitude_pct: float | None
    retention_continuity: str
    drift_slope_A_per_s: float | None
    drift_intercept_A: float | None
    drift_r_squared: float | None
    drift_n: int
    qc_status: str
    warnings: tuple[str, ...]
    interruptions: tuple[ContinuousInterruption, ...]


@dataclass(frozen=True, slots=True)
class ContinuousGroupSummary:
    group: str
    metric: str
    unit: str
    n: int
    mean: float
    sd: float
    sem: float
    cv_percent: float
    median: float
    minimum: float
    maximum: float


def validate_interruption_set(intervals: Sequence[ContinuousInterruption], *,
                              record_start_s: float | None = None,
                              record_end_s: float | None = None) -> tuple[ContinuousInterruption, ...]:
    ordered = tuple(sorted(intervals, key=lambda row: (row.start_s, row.end_s, row.interval_id)))
    ids = [row.interval_id for row in ordered]
    if len(ids) != len(set(ids)):
        raise EventAnalysisError("Interruption interval_id values must be unique per record.")
    for index, row in enumerate(ordered):
        row.validate()
        if record_start_s is not None and record_end_s is not None:
            if row.start_s < record_start_s or row.end_s > record_end_s:
                raise EventAnalysisError("Interruption must be inside the record time range.")
        if index and row.start_s < ordered[index - 1].end_s:
            raise EventAnalysisError("Overlapping interruption intervals are not allowed.")
    return ordered


def _overlaps(start: float, end: float, interruption: ContinuousInterruption) -> bool:
    return start < interruption.end_s and interruption.start_s < end


def _window_values(time_s, current_A, start, end, minimum_points):
    if start is None or end is None:
        return None, None, 0, "not_configured"
    if start < float(time_s[0]) or end > float(time_s[-1]):
        return None, None, 0, "outside_record"
    indices = np.flatnonzero((time_s >= start) & (time_s <= end))
    if indices.size < minimum_points:
        return None, None, int(indices.size), "insufficient_samples"
    values = current_A[indices]
    return float(np.mean(values)), float(np.std(values, ddof=1)), int(indices.size), "ok"


def _ols(time_s, current_A, minimum_points):
    if len(time_s) < minimum_points or len(set(float(x) for x in time_s)) < 2:
        return None, None, None, int(len(time_s))
    fit = stats.linregress(np.asarray(time_s, dtype=float), np.asarray(current_A, dtype=float))
    return float(fit.slope), float(fit.intercept), float(fit.rvalue ** 2), int(len(time_s))


def _segments(data, *, sample_id, group, analysis_start, analysis_end, interruptions,
              minimum_points):
    bounds = [(analysis_start, analysis_end)]
    for interval in interruptions:
        replacement = []
        for start, end in bounds:
            if not _overlaps(start, end, interval):
                replacement.append((start, end)); continue
            if start < interval.start_s:
                replacement.append((start, min(end, interval.start_s)))
            if interval.end_s < end:
                replacement.append((max(start, interval.end_s), end))
        bounds = replacement
    output = []
    times = np.asarray(data.time_s, dtype=float)
    currents = np.asarray(data.current_A, dtype=float)
    for index, (start, end) in enumerate(bounds, start=1):
        mask = (times >= start) & (times <= end)
        for interval in interruptions:
            mask &= ~((times >= interval.start_s) & (times <= interval.end_s))
        selected_t, selected_i = times[mask], currents[mask]
        slope, intercept, r2, n = _ols(selected_t, selected_i, minimum_points)
        status = "ok" if n >= minimum_points else "insufficient_samples"
        output.append(ContinuousSegmentResult(
            data.file_name, sample_id, group, f"segment_{index}", start, end, end - start, n,
            float(np.mean(selected_i)) if n else None,
            float(np.std(selected_i, ddof=1)) if n >= 2 else None,
            slope, intercept, r2, status,
        ))
    return tuple(output)


def analyze_continuous_record(data, *, sample_id: str, group: str = "",
                              settings: ContinuousStabilitySettings | None = None,
                              interruptions: Sequence[ContinuousInterruption] = ()):
    settings = settings or ContinuousStabilitySettings()
    settings.validate()
    times = np.asarray(data.time_s, dtype=float)
    currents = np.asarray(data.current_A, dtype=float)
    if times.size == 0 or currents.size != times.size or not np.isfinite(times).all() or not np.isfinite(currents).all():
        raise EventAnalysisError("Continuous analysis requires aligned finite non-empty raw arrays.")
    record_start, record_end = float(times[0]), float(times[-1])
    try:
        ordered = validate_interruption_set(interruptions, record_start_s=record_start,
                                            record_end_s=record_end)
    except EventAnalysisError as error:
        warning = str(error)
        row = ContinuousStabilityResult(
            data.file_name, sample_id, group, record_start, record_end, record_end-record_start,
            settings.analysis_start_s if settings.analysis_start_s is not None else record_start,
            settings.analysis_end_s if settings.analysis_end_s is not None else record_end,
            settings.early_start_s, settings.early_end_s, None, None,
            settings.late_start_s, settings.late_end_s, None, None, None, None, None,
            "unavailable", None, None, None, 0, "Invalid interruption metadata", (warning,), tuple(interruptions),
        )
        return row, ()
    analysis_start = record_start if settings.analysis_start_s is None else settings.analysis_start_s
    analysis_end = record_end if settings.analysis_end_s is None else settings.analysis_end_s
    warnings = list(data.warnings)
    analysis_available = analysis_start >= record_start and analysis_end <= record_end and analysis_start < analysis_end
    if not analysis_available:
        warnings.append("Analysis range is not fully covered by this record.")
    early_overlap = settings.early_start_s is not None and any(
        _overlaps(settings.early_start_s, settings.early_end_s, row) for row in ordered)
    late_overlap = settings.late_start_s is not None and any(
        _overlaps(settings.late_start_s, settings.late_end_s, row) for row in ordered)
    early_mean, early_sd, _early_n, early_status = _window_values(
        times, currents, settings.early_start_s, settings.early_end_s, settings.minimum_points)
    late_mean, late_sd, _late_n, late_status = _window_values(
        times, currents, settings.late_start_s, settings.late_end_s, settings.minimum_points)
    if early_overlap:
        early_mean = early_sd = None; early_status = "interruption_overlap"
        warnings.append("Early window overlaps an invalid/interruption interval; adjust the window.")
    elif early_status != "ok":
        warnings.append(f"Early window unavailable: {early_status}.")
    if late_overlap:
        late_mean = late_sd = None; late_status = "interruption_overlap"
        warnings.append("Late window overlaps an invalid/interruption interval; adjust the window.")
    elif late_status != "ok":
        warnings.append(f"Late window unavailable: {late_status}.")
    delta = late_mean - early_mean if early_mean is not None and late_mean is not None else None
    delta_magnitude = (abs(late_mean) - abs(early_mean)
                       if early_mean is not None and late_mean is not None else None)
    retention = None
    if early_mean is not None and late_mean is not None:
        if abs(early_mean) <= settings.retention_reference_epsilon_A:
            warnings.append("Early mean is too close to zero for reliable Retention.")
        else:
            retention = abs(late_mean) / abs(early_mean) * 100.0
    span_start = settings.early_start_s
    span_end = settings.late_end_s
    crosses_gap = bool(span_start is not None and span_end is not None and
                       any(_overlaps(span_start, span_end, row) for row in ordered))
    continuity = ("unavailable" if retention is None else
                  "interrupted" if crosses_gap else "continuous")
    if continuity == "interrupted":
        warnings.append("Retention crosses an acquisition interruption; it is a before/after window ratio, not fully continuous stability.")
    range_interruptions = tuple(row for row in ordered if _overlaps(analysis_start, analysis_end, row))
    slope = intercept = r2 = None; drift_n = 0
    if analysis_available and not range_interruptions:
        mask = (times >= analysis_start) & (times <= analysis_end)
        slope, intercept, r2, drift_n = _ols(times[mask], currents[mask], settings.minimum_points)
        if slope is None:
            warnings.append("Analysis range has insufficient real samples for OLS drift.")
    elif range_interruptions:
        warnings.append("Analysis range crosses an acquisition interruption; inspect valid-segment drift results.")
    segments = (_segments(data, sample_id=sample_id, group=group,
                          analysis_start=analysis_start, analysis_end=analysis_end,
                          interruptions=range_interruptions,
                          minimum_points=settings.minimum_points)
                if analysis_available else ())
    unavailable = sum(value is None for value in (early_mean, late_mean, retention, slope))
    if "insufficient_samples" in {early_status, late_status}:
        qc = "Insufficient samples; Partial metrics available"
    elif not analysis_available:
        qc = "Analysis range unavailable; Partial metrics available"
    elif ordered and unavailable:
        qc = "Interrupted; Partial metrics available"
    elif ordered:
        qc = "Interrupted"
    elif unavailable:
        qc = "Partial metrics available"
    else:
        qc = "Complete"
    if early_overlap or late_overlap:
        qc = "Window overlap; Partial metrics available"
    result = ContinuousStabilityResult(
        data.file_name, sample_id, group, record_start, record_end, record_end-record_start,
        analysis_start, analysis_end, settings.early_start_s, settings.early_end_s,
        early_mean, early_sd, settings.late_start_s, settings.late_end_s,
        late_mean, late_sd, delta, delta_magnitude, retention, continuity,
        slope, intercept, r2, drift_n, qc, tuple(dict.fromkeys(warnings)), ordered,
    )
    return result, segments


def summarize_continuous_groups(records: Sequence[ContinuousStabilityResult]):
    groups = tuple(dict.fromkeys(row.group for row in records))
    definitions = (
        ("Retention magnitude", "%", "retention_magnitude_pct"),
        ("Drift slope", "A/s", "drift_slope_A_per_s"),
        ("Early current", "A", "early_mean_A"),
        ("Late current", "A", "late_mean_A"),
    )
    output = []
    for group in groups:
        group_rows = [row for row in records if row.group == group]
        for metric, unit, attr in definitions:
            values = [getattr(row, attr) for row in group_rows if getattr(row, attr) is not None]
            if not values:
                output.append(ContinuousGroupSummary(group, metric, unit, 0, math.nan,
                                                     math.nan, math.nan, math.nan,
                                                     math.nan, math.nan, math.nan))
                continue
            d = describe_values(values)
            output.append(ContinuousGroupSummary(group, metric, unit, d.n, d.mean, d.sd,
                                                 d.sem, d.cv_percent, d.median,
                                                 d.minimum, d.maximum))
    return tuple(output)


def analyze_it_continuous_batch(inputs: Sequence[ITEventInput], *, metric: str = "signed",
                                settings: ContinuousStabilitySettings | None = None,
                                interruptions_by_sample: dict[str, Sequence[ContinuousInterruption]] | None = None):
    settings = settings or ContinuousStabilitySettings()
    settings.validate()
    included = tuple(row for row in inputs if row.include)
    ids = [row.sample_id for row in included]
    if not included or any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise EventAnalysisError("Included Sample IDs must be non-empty and unique.")
    interruption_map = interruptions_by_sample or {}
    stability = []
    segments = []
    basic = []
    empty_timeline = EventTimeline((), False, "No Events (Continuous mode)")
    files = []
    for item in included:
        basic.append(summarize_it_continuous_record(item.data, sample_id=item.sample_id, group=item.group))
        record, record_segments = analyze_continuous_record(
            item.data, sample_id=item.sample_id, group=item.group, settings=settings,
            interruptions=interruption_map.get(item.sample_id, ()),
        )
        stability.append(record); segments.extend(record_segments)
        files.append(ITEventFileResult(item.data, item.sample_id, item.group, empty_timeline,
                                       (), (), None, record.warnings))
    return ITEventBatchResult(
        empty_timeline, tuple(files), (), metric, None, ITAnalysisMode.CONTINUOUS,
        tuple(basic), tuple(stability), tuple(segments),
        summarize_continuous_groups(stability), settings,
    )


__all__ = [
    "ContinuousGroupSummary", "ContinuousInterruption", "ContinuousSegmentResult",
    "ContinuousStabilityResult", "ContinuousStabilitySettings", "InterruptionType",
    "RETENTION_REFERENCE_EPSILON_A", "analyze_continuous_record",
    "analyze_it_continuous_batch", "summarize_continuous_groups",
    "validate_interruption_set",
]
