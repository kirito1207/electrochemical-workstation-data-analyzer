"""Generic, user-confirmed event/window response analysis for i-t records."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Sequence

import numpy as np
from scipy import stats

from chi_parser import ITData


class EventAnalysisError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Event:
    event_id: str
    time_s: float
    name: str
    value: float | None = None
    unit: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class EventTimeline:
    events: tuple[Event, ...]
    user_confirmed: bool
    source: str = "Python API"

    def __post_init__(self) -> None:
        object.__setattr__(self, "events", tuple(sorted(self.events, key=lambda row: row.time_s)))

    def validate(self, *, recording_start_s=None, recording_end_s=None, require_confirmed=True):
        errors = []
        if require_confirmed and not self.user_confirmed:
            errors.append("Formal analysis requires EventTimeline.user_confirmed=True.")
        ids = [row.event_id for row in self.events]
        if any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
            errors.append("event_id values must be non-empty and unique.")
        if any(not row.name.strip() for row in self.events):
            errors.append("Event name must be non-empty.")
        times = [row.time_s for row in self.events]
        if any(not math.isfinite(value) for value in times):
            errors.append("Event time_s must be finite.")
        if len(times) != len(set(times)):
            errors.append("Event time_s must currently be unique.")
        if any(row.value is not None and not math.isfinite(row.value) for row in self.events):
            errors.append("Event value must be finite when supplied.")
        if recording_start_s is not None and recording_end_s is not None:
            outside = [row.event_id for row in self.events if not recording_start_s <= row.time_s <= recording_end_s]
            if outside:
                errors.append("Events outside recorded time range: " + ", ".join(outside))
        if errors:
            raise EventAnalysisError(" | ".join(errors))


@dataclass(frozen=True, slots=True)
class ResponseWindow:
    event_id: str | None
    start_time_s: float
    end_time_s: float
    kind: Literal["baseline", "plateau", "custom"]


@dataclass(frozen=True, slots=True)
class PlateauPolicy:
    mode: Literal["tail_fraction", "explicit"] = "tail_fraction"
    fraction: float = 0.20
    explicit_windows: tuple[ResponseWindow, ...] = ()

    def validate(self):
        if self.mode == "tail_fraction" and (not math.isfinite(self.fraction) or not 0 < self.fraction <= 1):
            raise EventAnalysisError("tail_fraction must be in (0, 1].")
        if self.mode == "explicit" and not self.explicit_windows:
            raise EventAnalysisError("Explicit policy requires ResponseWindow definitions.")
        if self.mode not in {"tail_fraction", "explicit"}:
            raise EventAnalysisError("Unknown PlateauPolicy mode.")


@dataclass(frozen=True, slots=True)
class WindowStatistics:
    event_id: str | None
    kind: str
    requested_start_s: float
    requested_end_s: float
    actual_start_s: float | None
    actual_end_s: float | None
    n: int
    mean_uA: float | None
    sd_uA: float | None
    status: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class EventResponse:
    source_file: str
    sample_id: str
    group: str
    event_id: str
    event_name: str
    event_time_s: float
    event_value: float | None
    event_unit: str | None
    baseline_mean_uA: float | None
    response_mean_uA: float | None
    delta_current_uA: float | None
    response_magnitude_uA: float | None
    baseline_sd_uA: float | None
    response_sd_uA: float | None
    baseline_n: int
    response_n: int
    response_window_start_s: float
    response_window_end_s: float
    status: str
    notes: str = ""


@dataclass(frozen=True, slots=True)
class EventResponseSummary:
    group: str
    event_id: str
    event_name: str
    n: int
    mean_delta_current_uA: float
    sd_delta_current_uA: float
    sem_delta_current_uA: float
    mean_response_magnitude_uA: float
    sd_response_magnitude_uA: float
    sem_response_magnitude_uA: float = math.nan
    cv_delta_percent: float = math.nan
    cv_magnitude_percent: float = math.nan


@dataclass(frozen=True, slots=True)
class CalibrationSelection:
    event_ids: tuple[str, ...]
    x_label: str
    x_unit: str

    def validate(self, timeline: EventTimeline):
        by_id = {row.event_id: row for row in timeline.events}
        if not self.event_ids or len(self.event_ids) != len(set(self.event_ids)):
            raise EventAnalysisError("Calibration event_ids must be non-empty and unique.")
        missing = [value for value in self.event_ids if value not in by_id]
        no_value = [value for value in self.event_ids if value in by_id and by_id[value].value is None]
        bad_unit = [value for value in self.event_ids if value in by_id and (by_id[value].unit or "") != self.x_unit]
        if missing:
            raise EventAnalysisError("Unknown calibration Events: " + ", ".join(missing))
        if no_value:
            raise EventAnalysisError("Calibration Events require numeric value: " + ", ".join(no_value))
        if not self.x_label.strip() or not self.x_unit.strip():
            raise EventAnalysisError("Calibration x_label and x_unit are required.")
        if bad_unit:
            raise EventAnalysisError("Calibration units differ; automatic conversion is forbidden: " + ", ".join(bad_unit))


@dataclass(frozen=True, slots=True)
class EventCalibrationResult:
    sample_id: str
    analysis_metric: str
    x_label: str
    x_unit: str
    slope_uA_per_x: float
    intercept_uA: float
    r_squared: float
    event_ids: tuple[str, ...]
    x_values: tuple[float, ...]
    regression_method: str = "ordinary least squares"
    lod_status: str = "LOD not calculated"


@dataclass(frozen=True, slots=True)
class ITEventFileResult:
    data: ITData
    sample_id: str
    group: str
    timeline: EventTimeline
    windows: tuple[WindowStatistics, ...]
    responses: tuple[EventResponse, ...]
    calibration: EventCalibrationResult | None
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ITEventInput:
    data: ITData
    sample_id: str
    group: str = ""
    include: bool = True
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ITEventBatchResult:
    timeline: EventTimeline
    files: tuple[ITEventFileResult, ...]
    summaries: tuple[EventResponseSummary, ...]
    analysis_metric: str
    calibration_selection: CalibrationSelection | None


def define_response_windows(data: ITData, timeline: EventTimeline) -> tuple[ResponseWindow, ...]:
    timeline.validate()
    events = timeline.events
    baseline_end = events[0].time_s if events else data.actual_last_time_s
    windows = [ResponseWindow(None, data.actual_first_time_s, baseline_end, "baseline")]
    for index, event in enumerate(events):
        end = events[index + 1].time_s if index + 1 < len(events) else data.actual_last_time_s
        windows.append(ResponseWindow(event.event_id, event.time_s, end, "plateau"))
    return tuple(windows)


def extract_window_statistics(data: ITData, timeline: EventTimeline, *, policy=None, minimum_points=2):
    policy = policy or PlateauPolicy()
    policy.validate()
    windows = policy.explicit_windows if policy.mode == "explicit" else define_response_windows(data, timeline)
    output = []
    for window in windows:
        mask = (data.time_s >= window.start_time_s) & (data.time_s < window.end_time_s)
        if window.end_time_s == data.actual_last_time_s:
            mask = (data.time_s >= window.start_time_s) & (data.time_s <= window.end_time_s)
        indices = np.flatnonzero(mask)
        if policy.mode == "tail_fraction" and indices.size:
            indices = indices[-max(1, math.ceil(indices.size * policy.fraction)):]
        if indices.size < minimum_points:
            output.append(WindowStatistics(window.event_id, window.kind, window.start_time_s, window.end_time_s, None, None, int(indices.size), None, None, "unavailable", f"Window has {indices.size} point(s); at least {minimum_points} required."))
            continue
        values = data.current_A[indices] * 1e6
        output.append(WindowStatistics(window.event_id, window.kind, window.start_time_s, window.end_time_s, float(data.time_s[indices[0]]), float(data.time_s[indices[-1]]), int(indices.size), float(np.mean(values)), float(np.std(values, ddof=1)), "ok"))
    return tuple(output)


def calculate_event_responses(data, timeline, windows, *, sample_id, group=""):
    baseline = next((row for row in windows if row.kind == "baseline"), None)
    by_id = {row.event_id: row for row in windows if row.event_id is not None}
    output = []
    for event in timeline.events:
        row = by_id.get(event.event_id)
        status = "ok" if baseline and row and baseline.status == row.status == "ok" else "unavailable"
        delta = row.mean_uA - baseline.mean_uA if status == "ok" else None
        notes = "" if status == "ok" else (row.notes if row else "No response window for this record.")
        output.append(EventResponse(data.file_name, sample_id, group, event.event_id, event.name, event.time_s, event.value, event.unit, baseline.mean_uA if baseline else None, row.mean_uA if row else None, delta, abs(delta) if delta is not None else None, baseline.sd_uA if baseline else None, row.sd_uA if row else None, baseline.n if baseline else 0, row.n if row else 0, row.requested_start_s if row else event.time_s, row.requested_end_s if row else event.time_s, status, notes))
    return tuple(output)


def fit_event_calibration(responses, timeline, selection, *, metric, sample_id):
    selection.validate(timeline)
    by_response = {row.event_id: row for row in responses if row.status == "ok"}
    if any(value not in by_response for value in selection.event_ids):
        raise EventAnalysisError("Selected calibration Event response is unavailable.")
    by_event = {row.event_id: row for row in timeline.events}
    x = np.asarray([by_event[value].value for value in selection.event_ids], dtype=float)
    if len(x) < 2 or len(set(x)) < 2:
        raise EventAnalysisError("Calibration requires at least two distinct selected x values.")
    y = np.asarray([by_response[value].delta_current_uA if metric == "signed" else by_response[value].response_magnitude_uA for value in selection.event_ids], dtype=float)
    fit = stats.linregress(x, y)
    return EventCalibrationResult(sample_id, metric, selection.x_label, selection.x_unit, float(fit.slope), float(fit.intercept), float(fit.rvalue**2), selection.event_ids, tuple(float(value) for value in x))


def analyze_it_events(data, timeline, *, sample_id, group="", metric="signed", policy=None, calibration_selection=None):
    timeline.validate()
    if metric not in {"signed", "magnitude"}:
        raise EventAnalysisError("metric must be signed or magnitude.")
    windows = extract_window_statistics(data, timeline, policy=policy)
    responses = calculate_event_responses(data, timeline, windows, sample_id=sample_id, group=group)
    calibration = fit_event_calibration(responses, timeline, calibration_selection, metric=metric, sample_id=sample_id) if calibration_selection else None
    warnings = tuple(f"Event {row.event_id}: {row.notes}" for row in responses if row.status != "ok")
    return ITEventFileResult(data, sample_id, group, timeline, windows, responses, calibration, tuple(data.warnings) + warnings)


def summarize_event_responses(responses):
    records = tuple(row for row in responses if row.status == "ok")
    keys = tuple(dict.fromkeys((row.group, row.event_id) for row in records))
    output = []
    for group, event_id in keys:
        selected = [row for row in records if row.group == group and row.event_id == event_id]
        signed = np.asarray([row.delta_current_uA for row in selected], dtype=float)
        magnitude = np.asarray([row.response_magnitude_uA for row in selected], dtype=float)
        sd_signed = float(np.std(signed, ddof=1)) if len(signed) > 1 else math.nan
        sd_magnitude = float(np.std(magnitude, ddof=1)) if len(magnitude) > 1 else math.nan
        output.append(EventResponseSummary(
            group, event_id, selected[0].event_name, len(selected), float(np.mean(signed)),
            sd_signed, sd_signed / math.sqrt(len(signed)) if len(signed) > 1 else math.nan,
            float(np.mean(magnitude)), sd_magnitude,
            sd_magnitude / math.sqrt(len(magnitude)) if len(magnitude) > 1 else math.nan,
            (sd_signed / abs(float(np.mean(signed))) * 100.0
             if len(signed) > 1 and float(np.mean(signed)) != 0 else math.nan),
            (sd_magnitude / float(np.mean(magnitude)) * 100.0
             if len(magnitude) > 1 and float(np.mean(magnitude)) != 0 else math.nan),
        ))
    return tuple(output)


def analyze_it_event_batch(inputs: Sequence[ITEventInput], timeline, *, metric="signed", policy=None, calibration_selection=None):
    timeline.validate()
    included = tuple(row for row in inputs if row.include)
    ids = [row.sample_id for row in included]
    if not included or any(not value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise EventAnalysisError("Included Sample IDs must be non-empty and unique.")
    files = tuple(analyze_it_events(row.data, timeline, sample_id=row.sample_id, group=row.group, metric=metric, policy=policy, calibration_selection=calibration_selection) for row in included)
    summaries = summarize_event_responses(row for item in files for row in item.responses)
    return ITEventBatchResult(timeline, files, summaries, metric, calibration_selection)


__all__ = [name for name in globals() if name.startswith(("Event", "ITEvent", "Plateau", "Response", "Window", "Calibration")) or name in {"analyze_it_events", "analyze_it_event_batch", "calculate_event_responses", "define_response_windows", "extract_window_statistics", "fit_event_calibration", "summarize_event_responses"}]
