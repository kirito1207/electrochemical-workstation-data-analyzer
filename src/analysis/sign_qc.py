"""Direction-consistency QC for selected-potential Material currents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

import numpy as np


GroupLabel = Literal["A", "B", "C", "ALL"]
DEFAULT_SIGN_ZERO_TOLERANCE_A = 1e-12
MIXED_SIGN_WARNING = (
    "Selected-potential currents contain mixed signs. "
    "Absolute magnitude may conceal current-direction reversal. "
    "Inspect signed-current results before interpretation."
)


@dataclass(frozen=True, slots=True)
class CurrentSignQC:
    group: GroupLabel
    target_potential_V: float
    zero_tolerance_A: float
    negative_count: int
    positive_count: int
    near_zero_count: int
    total_count: int
    sign_consistent: bool
    warning: str


def evaluate_current_signs(
    currents_A: Iterable[float],
    *,
    group: GroupLabel,
    target_potential_V: float,
    analysis_metric: str,
    zero_tolerance_A: float = DEFAULT_SIGN_ZERO_TOLERANCE_A,
) -> CurrentSignQC:
    """Count current directions without modifying or filtering observations."""

    if not np.isfinite(zero_tolerance_A) or zero_tolerance_A < 0.0:
        raise ValueError("zero_tolerance_A must be a finite non-negative value.")
    values = np.asarray(tuple(currents_A), dtype=np.float64)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("Sign QC requires finite, non-empty current values.")

    negative_count = int(np.count_nonzero(values < -zero_tolerance_A))
    positive_count = int(np.count_nonzero(values > zero_tolerance_A))
    near_zero_count = int(values.size - negative_count - positive_count)
    sign_consistent = not (negative_count > 0 and positive_count > 0)
    warning = (
        MIXED_SIGN_WARNING
        if analysis_metric == "magnitude" and not sign_consistent
        else ""
    )
    return CurrentSignQC(
        group=group,
        target_potential_V=float(target_potential_V),
        zero_tolerance_A=float(zero_tolerance_A),
        negative_count=negative_count,
        positive_count=positive_count,
        near_zero_count=near_zero_count,
        total_count=int(values.size),
        sign_consistent=sign_consistent,
        warning=warning,
    )


__all__ = [
    "CurrentSignQC",
    "DEFAULT_SIGN_ZERO_TOLERANCE_A",
    "MIXED_SIGN_WARNING",
    "evaluate_current_signs",
]
