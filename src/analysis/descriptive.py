"""Descriptive statistics for electrode-level responses."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class DescriptiveStatistics:
    n: int
    mean: float
    median: float
    sd: float
    sem: float
    cv_percent: float
    minimum: float
    maximum: float
    q1: float
    q3: float
    iqr: float


def describe_values(values: Iterable[float]) -> DescriptiveStatistics:
    array = np.asarray(tuple(values), dtype=np.float64)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("Descriptive statistics require finite, non-empty values.")
    sd = float(np.std(array, ddof=1)) if array.size > 1 else math.nan
    mean = float(np.mean(array))
    sem = sd / math.sqrt(array.size) if array.size > 1 else math.nan
    cv = sd / abs(mean) * 100.0 if array.size > 1 and mean != 0 else math.nan
    q1, q3 = np.quantile(array, [0.25, 0.75])
    return DescriptiveStatistics(
        n=int(array.size),
        mean=mean,
        median=float(np.median(array)),
        sd=sd,
        sem=sem,
        cv_percent=cv,
        minimum=float(np.min(array)),
        maximum=float(np.max(array)),
        q1=float(q1),
        q3=float(q3),
        iqr=float(q3 - q1),
    )
