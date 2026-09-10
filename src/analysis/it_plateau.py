"""Deterministic i-t interval segmentation and plateau extraction."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from chi_parser import ITData

from .it_protocol import StepProtocol


SHORT_PLATEAU_WARNING = "Plateau window shorter than preferred 10 s."


class PlateauExtractionError(ValueError):
    """Raised when an interval cannot provide a defensible plateau."""


@dataclass(frozen=True, slots=True)
class IntervalDefinition:
    step_id: str
    concentration_uM: float
    include_in_calibration: bool
    interval_start_s: float
    interval_end_s: float
    end_inclusive: bool
    notes: str


@dataclass(frozen=True, slots=True)
class PlateauResult:
    source_file: str
    sample_id: str
    step_id: str
    concentration_uM: float
    include_in_calibration: bool
    interval_start_s: float
    interval_end_s: float
    end_inclusive: bool
    plateau_start_s: float
    plateau_end_s: float
    plateau_duration_s: float
    plateau_n_points: int
    plateau_mean_A: float
    plateau_mean_uA: float
    plateau_sd_A: float
    plateau_sd_uA: float
    plateau_sem_uA: float
    plateau_drift_uA_per_s: float
    warnings: tuple[str, ...]


def define_intervals(data: ITData, protocol: StepProtocol) -> tuple[IntervalDefinition, ...]:
    protocol.validate(
        recording_start_s=data.actual_first_time_s,
        recording_end_s=data.actual_last_time_s,
        time_tolerance_s=max(data.sample_interval_s * 1e-6, 1e-9),
    )
    intervals: list[IntervalDefinition] = []
    for index, step in enumerate(protocol.steps):
        last = index == len(protocol.steps) - 1
        end = (
            data.actual_last_time_s
            if last
            else protocol.steps[index + 1].addition_time_s
        )
        intervals.append(
            IntervalDefinition(
                step_id=step.step_id,
                concentration_uM=step.concentration_uM,
                include_in_calibration=step.include_in_calibration,
                interval_start_s=step.addition_time_s,
                interval_end_s=end,
                end_inclusive=last,
                notes=step.notes,
            )
        )
    return tuple(intervals)


def extract_plateaus(
    data: ITData,
    protocol: StepProtocol,
    *,
    sample_id: str,
    plateau_fraction: float = 0.20,
    preferred_min_plateau_duration_s: float = 10.0,
    minimum_plateau_points: int = 2,
) -> tuple[PlateauResult, ...]:
    if not math.isfinite(plateau_fraction) or not 0.0 < plateau_fraction <= 1.0:
        raise ValueError("plateau_fraction must be in (0, 1].")
    if preferred_min_plateau_duration_s < 0.0:
        raise ValueError("preferred_min_plateau_duration_s must be non-negative.")
    if minimum_plateau_points < 2:
        raise ValueError("minimum_plateau_points must be at least 2.")

    results: list[PlateauResult] = []
    for interval in define_intervals(data, protocol):
        if interval.end_inclusive:
            interval_mask = (
                (data.time_s >= interval.interval_start_s)
                & (data.time_s <= interval.interval_end_s)
            )
        else:
            interval_mask = (
                (data.time_s >= interval.interval_start_s)
                & (data.time_s < interval.interval_end_s)
            )
        interval_indices = np.flatnonzero(interval_mask)
        if interval_indices.size == 0:
            raise PlateauExtractionError(
                f"Step {interval.step_id} contains no recorded points."
            )
        count = max(1, int(math.ceil(interval_indices.size * plateau_fraction)))
        plateau_indices = interval_indices[-count:]
        if plateau_indices.size < minimum_plateau_points:
            raise PlateauExtractionError(
                f"Step {interval.step_id} plateau has {plateau_indices.size} points; "
                f"at least {minimum_plateau_points} are required."
            )

        plateau_time = data.time_s[plateau_indices]
        plateau_current_A = data.current_A[plateau_indices]
        mean_A = float(np.mean(plateau_current_A))
        sd_A = float(np.std(plateau_current_A, ddof=1))
        sem_uA = float(sd_A * 1e6 / math.sqrt(plateau_indices.size))
        drift = float(np.polyfit(plateau_time, plateau_current_A * 1e6, 1)[0])
        duration = float(plateau_indices.size * data.sample_interval_s)
        warnings: list[str] = []
        if duration < preferred_min_plateau_duration_s:
            warnings.append(SHORT_PLATEAU_WARNING)
        results.append(
            PlateauResult(
                source_file=data.file_name,
                sample_id=sample_id,
                step_id=interval.step_id,
                concentration_uM=interval.concentration_uM,
                include_in_calibration=interval.include_in_calibration,
                interval_start_s=interval.interval_start_s,
                interval_end_s=interval.interval_end_s,
                end_inclusive=interval.end_inclusive,
                plateau_start_s=float(plateau_time[0]),
                plateau_end_s=float(plateau_time[-1]),
                plateau_duration_s=duration,
                plateau_n_points=int(plateau_indices.size),
                plateau_mean_A=mean_A,
                plateau_mean_uA=mean_A * 1e6,
                plateau_sd_A=sd_A,
                plateau_sd_uA=sd_A * 1e6,
                plateau_sem_uA=sem_uA,
                plateau_drift_uA_per_s=drift,
                warnings=tuple(warnings),
            )
        )
    return tuple(results)


__all__ = [
    "IntervalDefinition",
    "PlateauExtractionError",
    "PlateauResult",
    "SHORT_PLATEAU_WARNING",
    "define_intervals",
    "extract_plateaus",
]
