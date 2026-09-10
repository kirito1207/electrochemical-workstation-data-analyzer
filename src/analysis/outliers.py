"""Non-destructive possible-outlier flags."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


@dataclass(frozen=True, slots=True)
class OutlierFlag:
    file_name: str
    group: str
    sample_id: str
    target_potential_V: float
    response: float
    analysis_metric: str
    outlier_method: str
    outlier_reason: str
    status: str = "Possible outlier"


def flag_mad_outliers(
    records: Iterable[tuple[str, str, str, float]],
    *,
    target_potential_V: float,
    analysis_metric: str,
    threshold: float = 3.5,
) -> tuple[OutlierFlag, ...]:
    """Flag observations by modified z score; never remove observations."""

    rows = tuple(records)
    if not rows:
        return ()
    values = np.asarray([row[3] for row in rows], dtype=np.float64)
    if not np.isfinite(values).all():
        raise ValueError("MAD outlier detection requires finite values.")
    median = float(np.median(values))
    deviations = np.abs(values - median)
    mad = float(np.median(deviations))
    if mad == 0.0:
        flagged = deviations > 0.0
        reasons = [
            f"MAD=0 and response differs from group median {median:.12g}"
            for _ in rows
        ]
    else:
        scores = 0.6744897501960817 * (values - median) / mad
        flagged = np.abs(scores) > threshold
        reasons = [
            f"|modified z|={abs(score):.6g} > {threshold:g}; median={median:.12g}, MAD={mad:.12g}"
            for score in scores
        ]
    return tuple(
        OutlierFlag(
            file_name=file_name,
            group=group,
            sample_id=sample_id,
            target_potential_V=target_potential_V,
            response=float(value),
            analysis_metric=analysis_metric,
            outlier_method="MAD modified z-score",
            outlier_reason=reasons[index],
        )
        for index, ((file_name, group, sample_id, value), is_flagged) in enumerate(
            zip(rows, flagged, strict=True)
        )
        if is_flagged
    )
