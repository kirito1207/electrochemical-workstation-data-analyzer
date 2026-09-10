"""Non-destructive i-t response QC and unconfirmed addition-time suggestions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
from scipy.signal import find_peaks

from chi_parser import ITData

from .it_calibration import DeltaIResult


MIXED_DELTA_WARNING = "Absolute ΔI may conceal mixed response directions."
SUGGESTION_STATUS = "Suggested only / 未确认"


@dataclass(frozen=True, slots=True)
class DeltaDirectionQC:
    concentration_uM: float
    zero_tolerance_A: float
    negative_count: int
    positive_count: int
    near_zero_count: int
    total_count: int
    direction_consistent: bool
    warning: str


@dataclass(frozen=True, slots=True)
class ITOutlierFlag:
    source_file: str
    sample_id: str
    concentration_uM: float
    response_uA: float
    analysis_metric: str
    method: str
    reason: str
    status: str = "Possible outlier"


@dataclass(frozen=True, slots=True)
class AdditionTimeSuggestion:
    candidate_time_s: float
    score_uA: float
    robust_z: float
    status: str = SUGGESTION_STATUS
    concentration_uM: None = None


def evaluate_delta_direction(
    rows: Iterable[DeltaIResult],
    *,
    analysis_metric: str,
    zero_tolerance_A: float = 1e-12,
) -> tuple[DeltaDirectionQC, ...]:
    if not math.isfinite(zero_tolerance_A) or zero_tolerance_A < 0.0:
        raise ValueError("zero_tolerance_A must be finite and non-negative.")
    records = tuple(rows)
    results: list[DeltaDirectionQC] = []
    for concentration in sorted({row.concentration_uM for row in records}):
        values = np.asarray(
            [row.signed_delta_I_A for row in records if row.concentration_uM == concentration]
        )
        negative = int(np.count_nonzero(values < -zero_tolerance_A))
        positive = int(np.count_nonzero(values > zero_tolerance_A))
        near_zero = int(values.size - negative - positive)
        consistent = not (negative > 0 and positive > 0)
        warning = (
            MIXED_DELTA_WARNING
            if analysis_metric == "magnitude" and not consistent
            else ""
        )
        results.append(
            DeltaDirectionQC(
                concentration_uM=concentration,
                zero_tolerance_A=zero_tolerance_A,
                negative_count=negative,
                positive_count=positive,
                near_zero_count=near_zero,
                total_count=int(values.size),
                direction_consistent=consistent,
                warning=warning,
            )
        )
    return tuple(results)


def flag_delta_outliers(
    rows: Iterable[DeltaIResult],
    *,
    analysis_metric: str,
    threshold: float = 3.5,
) -> tuple[ITOutlierFlag, ...]:
    records = tuple(rows)
    flags: list[ITOutlierFlag] = []
    for concentration in sorted({row.concentration_uM for row in records}):
        selected = tuple(row for row in records if row.concentration_uM == concentration)
        if len(selected) < 3:
            continue
        values = np.asarray(
            [
                row.signed_delta_I_uA
                if analysis_metric == "signed"
                else row.magnitude_delta_I_uA
                for row in selected
            ],
            dtype=np.float64,
        )
        median = float(np.median(values))
        mad = float(np.median(np.abs(values - median)))
        if mad == 0.0:
            scores = np.where(values == median, 0.0, np.inf)
        else:
            scores = 0.6744897501960817 * (values - median) / mad
        for row, value, score in zip(selected, values, scores, strict=True):
            if abs(score) > threshold:
                flags.append(
                    ITOutlierFlag(
                        source_file=row.source_file,
                        sample_id=row.sample_id,
                        concentration_uM=concentration,
                        response_uA=float(value),
                        analysis_metric=analysis_metric,
                        method="MAD modified z-score",
                        reason=(
                            f"|modified z|={abs(score):.6g} > {threshold}; "
                            f"median={median:.12g}, MAD={mad:.12g}"
                        ),
                    )
                )
    return tuple(flags)


def suggest_addition_times(
    data: ITData,
    *,
    comparison_window_s: float = 2.0,
    minimum_separation_s: float = 15.0,
    threshold_robust_z: float = 6.0,
    max_candidates: int = 10,
) -> tuple[AdditionTimeSuggestion, ...]:
    """Suggest step boundaries using temporary adjacent-window means only."""

    if comparison_window_s <= 0.0 or minimum_separation_s <= 0.0:
        raise ValueError("Suggestion windows must be positive.")
    if max_candidates < 1:
        raise ValueError("max_candidates must be positive.")
    window = max(2, int(round(comparison_window_s / data.sample_interval_s)))
    if data.n_points < window * 2 + 1:
        return ()

    current_uA = np.asarray(data.current_A, dtype=np.float64) * 1e6
    cumulative = np.concatenate(([0.0], np.cumsum(current_uA)))
    boundaries = np.arange(window, data.n_points - window)
    before = (cumulative[boundaries] - cumulative[boundaries - window]) / window
    after = (cumulative[boundaries + window] - cumulative[boundaries]) / window
    scores = np.abs(after - before)
    median = float(np.median(scores))
    mad = float(np.median(np.abs(scores - median)))
    scale = 1.482602218505602 * mad
    if scale == 0.0:
        scale = float(np.std(scores))
    if scale == 0.0:
        return ()
    robust_z = (scores - median) / scale
    distance = max(1, int(round(minimum_separation_s / data.sample_interval_s)))
    peaks, properties = find_peaks(
        robust_z,
        height=threshold_robust_z,
        distance=distance,
    )
    ranked = sorted(peaks, key=lambda index: scores[index], reverse=True)[:max_candidates]
    chosen = sorted(ranked)
    return tuple(
        AdditionTimeSuggestion(
            candidate_time_s=float(data.time_s[boundaries[index]]),
            score_uA=float(scores[index]),
            robust_z=float(properties["peak_heights"][np.where(peaks == index)[0][0]]),
        )
        for index in chosen
    )


__all__ = [
    "AdditionTimeSuggestion",
    "DeltaDirectionQC",
    "ITOutlierFlag",
    "MIXED_DELTA_WARNING",
    "SUGGESTION_STATUS",
    "evaluate_delta_direction",
    "flag_delta_outliers",
    "suggest_addition_times",
]
