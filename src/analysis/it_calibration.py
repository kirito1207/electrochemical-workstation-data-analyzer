"""i-t ΔI calculation, OLS calibration, and replicate summaries."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np
from scipy import stats

from .it_plateau import PlateauResult


CalibrationMetric = Literal["signed", "magnitude"]


@dataclass(frozen=True, slots=True)
class DeltaIResult:
    source_file: str
    sample_id: str
    step_id: str
    concentration_uM: float
    include_in_calibration: bool
    plateau_mean_A: float
    plateau_mean_uA: float
    baseline_mean_A: float
    baseline_mean_uA: float
    signed_delta_I_A: float
    signed_delta_I_uA: float
    magnitude_delta_I_uA: float


@dataclass(frozen=True, slots=True)
class CalibrationResult:
    sample_id: str
    fit_basis: str
    analysis_metric: CalibrationMetric
    slope_uA_per_uM: float
    intercept_uA: float
    r_squared: float
    n_points: int
    included_concentrations_uM: tuple[float, ...]
    regression_method: str = "ordinary least squares"
    lod_status: str = "LOD not calculated"
    lod_reason: str = "Insufficient independent blank replicates for a defined σ_blank method."


@dataclass(frozen=True, slots=True)
class ConcentrationSummary:
    concentration_uM: float
    n: int
    mean_signed_delta_I_uA: float
    sd_signed_delta_I_uA: float
    sem_signed_delta_I_uA: float
    cv_signed_percent: float
    mean_magnitude_delta_I_uA: float
    sd_magnitude_delta_I_uA: float
    sem_magnitude_delta_I_uA: float
    cv_magnitude_percent: float
    included_count: int
    excluded_count: int
    include_in_group_calibration: bool


def calculate_delta_i(plateaus: Iterable[PlateauResult]) -> tuple[DeltaIResult, ...]:
    rows = tuple(plateaus)
    if not rows or rows[0].concentration_uM != 0.0:
        raise ValueError("The first plateau must be the 0 µM baseline.")
    baseline_A = rows[0].plateau_mean_A
    results = []
    for row in rows:
        signed_A = row.plateau_mean_A - baseline_A
        results.append(
            DeltaIResult(
                source_file=row.source_file,
                sample_id=row.sample_id,
                step_id=row.step_id,
                concentration_uM=row.concentration_uM,
                include_in_calibration=row.include_in_calibration,
                plateau_mean_A=row.plateau_mean_A,
                plateau_mean_uA=row.plateau_mean_uA,
                baseline_mean_A=baseline_A,
                baseline_mean_uA=baseline_A * 1e6,
                signed_delta_I_A=signed_A,
                signed_delta_I_uA=signed_A * 1e6,
                magnitude_delta_I_uA=abs(signed_A) * 1e6,
            )
        )
    return tuple(results)


def fit_calibration(
    rows: Iterable[DeltaIResult],
    *,
    analysis_metric: CalibrationMetric,
    sample_id: str,
    fit_basis: str = "individual electrode",
) -> CalibrationResult:
    if analysis_metric not in {"signed", "magnitude"}:
        raise ValueError("analysis_metric must be 'signed' or 'magnitude'.")
    selected = tuple(row for row in rows if row.include_in_calibration)
    if len(selected) < 2 or len({row.concentration_uM for row in selected}) < 2:
        raise ValueError("Calibration requires at least two included concentration values.")
    x = np.asarray([row.concentration_uM for row in selected], dtype=np.float64)
    y = np.asarray(
        [
            row.signed_delta_I_uA
            if analysis_metric == "signed"
            else row.magnitude_delta_I_uA
            for row in selected
        ],
        dtype=np.float64,
    )
    fitted = stats.linregress(x, y)
    return CalibrationResult(
        sample_id=sample_id,
        fit_basis=fit_basis,
        analysis_metric=analysis_metric,
        slope_uA_per_uM=float(fitted.slope),
        intercept_uA=float(fitted.intercept),
        r_squared=float(fitted.rvalue**2),
        n_points=len(selected),
        included_concentrations_uM=tuple(float(value) for value in x),
    )


def _spread(values: np.ndarray) -> tuple[float, float, float]:
    mean = float(np.mean(values))
    if values.size == 1:
        return mean, math.nan, math.nan
    sd = float(np.std(values, ddof=1))
    sem = sd / math.sqrt(values.size)
    return mean, sd, sem


def summarize_concentrations(
    rows: Iterable[DeltaIResult],
) -> tuple[ConcentrationSummary, ...]:
    records = tuple(rows)
    summaries: list[ConcentrationSummary] = []
    for concentration in sorted({row.concentration_uM for row in records}):
        selected = tuple(row for row in records if row.concentration_uM == concentration)
        signed = np.asarray([row.signed_delta_I_uA for row in selected])
        magnitude = np.asarray([row.magnitude_delta_I_uA for row in selected])
        signed_mean, signed_sd, signed_sem = _spread(signed)
        magnitude_mean, magnitude_sd, magnitude_sem = _spread(magnitude)
        included = sum(row.include_in_calibration for row in selected)
        summaries.append(
            ConcentrationSummary(
                concentration_uM=concentration,
                n=len(selected),
                mean_signed_delta_I_uA=signed_mean,
                sd_signed_delta_I_uA=signed_sd,
                sem_signed_delta_I_uA=signed_sem,
                cv_signed_percent=(signed_sd / abs(signed_mean) * 100.0)
                if len(selected) > 1 and signed_mean != 0.0
                else math.nan,
                mean_magnitude_delta_I_uA=magnitude_mean,
                sd_magnitude_delta_I_uA=magnitude_sd,
                sem_magnitude_delta_I_uA=magnitude_sem,
                cv_magnitude_percent=(magnitude_sd / abs(magnitude_mean) * 100.0)
                if len(selected) > 1 and magnitude_mean != 0.0
                else math.nan,
                included_count=included,
                excluded_count=len(selected) - included,
                include_in_group_calibration=included == len(selected),
            )
        )
    return tuple(summaries)


def fit_group_mean_calibration(
    summaries: Iterable[ConcentrationSummary],
    *,
    analysis_metric: CalibrationMetric,
) -> CalibrationResult:
    selected = tuple(row for row in summaries if row.include_in_group_calibration)
    synthetic = tuple(
        DeltaIResult(
            source_file="group mean",
            sample_id="GROUP_MEAN",
            step_id=str(index),
            concentration_uM=row.concentration_uM,
            include_in_calibration=True,
            plateau_mean_A=math.nan,
            plateau_mean_uA=math.nan,
            baseline_mean_A=math.nan,
            baseline_mean_uA=math.nan,
            signed_delta_I_A=row.mean_signed_delta_I_uA / 1e6,
            signed_delta_I_uA=row.mean_signed_delta_I_uA,
            magnitude_delta_I_uA=row.mean_magnitude_delta_I_uA,
        )
        for index, row in enumerate(selected)
    )
    return fit_calibration(
        synthetic,
        analysis_metric=analysis_metric,
        sample_id="GROUP_MEAN",
        fit_basis="group mean response",
    )


__all__ = [
    "CalibrationMetric",
    "CalibrationResult",
    "ConcentrationSummary",
    "DeltaIResult",
    "calculate_delta_i",
    "fit_calibration",
    "fit_group_mean_calibration",
    "summarize_concentrations",
]
