"""Predeclared group comparisons and reproducible effect-size intervals."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

import numpy as np
from scipy import stats


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    comparison: str
    comparison_role: str
    holm_family: str | None
    test: str
    statistic: float
    raw_p: float
    holm_adjusted_p: float | None
    mean_difference: float
    mean_difference_ci_low: float
    mean_difference_ci_high: float
    hedges_g: float
    hedges_g_ci_low: float
    hedges_g_ci_high: float
    bootstrap_seed: int
    bootstrap_resamples: int


@dataclass(frozen=True, slots=True)
class ComparisonDefinition:
    left_group: str
    right_group: str
    role: str
    holm_family: str | None = None
    name: str | None = None

    @property
    def comparison_name(self) -> str:
        return self.name or f"{self.left_group}-{self.right_group}"


def holm_adjust(p_values: Sequence[float]) -> tuple[float, ...]:
    """Holm step-down family-wise error adjustment."""

    p = np.asarray(p_values, dtype=np.float64)
    if p.ndim != 1 or not np.isfinite(p).all() or np.any((p < 0) | (p > 1)):
        raise ValueError("Holm adjustment requires finite p values in [0, 1].")
    order = np.argsort(p)
    adjusted = np.empty_like(p)
    running = 0.0
    m = len(p)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (m - rank) * float(p[index])))
        adjusted[index] = running
    return tuple(float(value) for value in adjusted)


def hedges_g(x: np.ndarray, y: np.ndarray) -> float:
    n_x, n_y = len(x), len(y)
    if n_x < 2 or n_y < 2:
        return math.nan
    pooled_variance = (
        (n_x - 1) * np.var(x, ddof=1) + (n_y - 1) * np.var(y, ddof=1)
    ) / (n_x + n_y - 2)
    if pooled_variance <= 0:
        return math.nan
    d = (float(np.mean(x)) - float(np.mean(y))) / math.sqrt(float(pooled_variance))
    correction = 1.0 - 3.0 / (4.0 * (n_x + n_y) - 9.0)
    return correction * d


def _bootstrap_intervals(
    x: np.ndarray,
    y: np.ndarray,
    *,
    seed: int,
    resamples: int,
) -> tuple[float, float, float, float]:
    if resamples < 5000:
        raise ValueError("Effect-size bootstrap requires at least 5000 resamples.")
    rng = np.random.default_rng(seed)
    differences = np.empty(resamples, dtype=np.float64)
    effects = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        sampled_x = rng.choice(x, size=len(x), replace=True)
        sampled_y = rng.choice(y, size=len(y), replace=True)
        differences[index] = np.mean(sampled_x) - np.mean(sampled_y)
        effects[index] = hedges_g(sampled_x, sampled_y)
    diff_low, diff_high = np.quantile(differences, [0.025, 0.975])
    finite_effects = effects[np.isfinite(effects)]
    if not finite_effects.size:
        effect_low = effect_high = math.nan
    else:
        effect_low, effect_high = np.quantile(finite_effects, [0.025, 0.975])
    return float(diff_low), float(diff_high), float(effect_low), float(effect_high)


def _one_comparison(
    name: str,
    role: str,
    x: np.ndarray,
    y: np.ndarray,
    *,
    holm_family: str | None,
    seed: int,
    resamples: int,
) -> tuple[ComparisonResult, ComparisonResult]:
    welch = stats.ttest_ind(x, y, equal_var=False, nan_policy="raise")
    mann = stats.mannwhitneyu(x, y, alternative="two-sided", method="auto")
    difference = float(np.mean(x) - np.mean(y))
    effect = hedges_g(x, y)
    diff_low, diff_high, effect_low, effect_high = _bootstrap_intervals(
        x, y, seed=seed, resamples=resamples
    )
    shared = dict(
        comparison=name,
        comparison_role=role,
        holm_family=holm_family,
        holm_adjusted_p=None,
        mean_difference=difference,
        mean_difference_ci_low=diff_low,
        mean_difference_ci_high=diff_high,
        hedges_g=effect,
        hedges_g_ci_low=effect_low,
        hedges_g_ci_high=effect_high,
        bootstrap_seed=seed,
        bootstrap_resamples=resamples,
    )
    return (
        ComparisonResult(
            test="Welch independent-samples t-test",
            statistic=float(welch.statistic),
            raw_p=float(welch.pvalue),
            **shared,
        ),
        ComparisonResult(
            test="Mann-Whitney U (two-sided sensitivity analysis)",
            statistic=float(mann.statistic),
            raw_p=float(mann.pvalue),
            **shared,
        ),
    )


def compare_groups(
    grouped_values: Mapping[str, Sequence[float]],
    *,
    bootstrap_seed: int = 20260910,
    bootstrap_resamples: int = 5000,
) -> tuple[ComparisonResult, ...]:
    """Run fixed A-B/B-C primary and A-C exploratory comparisons."""

    definitions = (
        ComparisonDefinition(
            "A", "B", "primary: detection medium (water vs PBS), PB 10 cycles",
            "pb42_primary",
        ),
        ComparisonDefinition(
            "B", "C", "primary: PB deposition cycles (10 vs 20), PBS",
            "pb42_primary",
        ),
        ComparisonDefinition(
            "A", "C", "exploratory: medium and PB cycles both differ",
        ),
    )
    return compare_defined_groups(
        grouped_values,
        definitions,
        bootstrap_seed=bootstrap_seed,
        bootstrap_resamples=bootstrap_resamples,
    )


def compare_defined_groups(
    grouped_values: Mapping[str, Sequence[float]],
    definitions: Sequence[ComparisonDefinition],
    *,
    bootstrap_seed: int = 20260910,
    bootstrap_resamples: int = 5000,
) -> tuple[ComparisonResult, ...]:
    """Run only user-declared comparisons and adjust declared primary families."""

    names = [definition.comparison_name for definition in definitions]
    if len(names) != len(set(names)):
        raise ValueError("Comparison names must be unique.")
    results: list[ComparisonResult] = []
    result_families: list[str | None] = []
    for index, definition in enumerate(definitions):
        left = definition.left_group
        right = definition.right_group
        if not left.strip() or not right.strip() or left == right:
            raise ValueError("Comparison groups must be distinct, non-empty names.")
        if left not in grouped_values or right not in grouped_values:
            raise ValueError(
                f"Comparison {definition.comparison_name} references an unknown group."
            )
        if definition.holm_family and not definition.role.lower().startswith("primary"):
            raise ValueError("Holm families may contain only primary comparisons.")
        x = np.asarray(grouped_values[left], dtype=np.float64)
        y = np.asarray(grouped_values[right], dtype=np.float64)
        for group, values in ((left, x), (right, y)):
            if len(values) < 2 or not np.isfinite(values).all():
                raise ValueError(
                    f"Group {group} requires at least two finite observations for comparison."
                )
        pair = _one_comparison(
            definition.comparison_name,
            definition.role,
            x,
            y,
            holm_family=definition.holm_family,
            seed=bootstrap_seed + index,
            resamples=bootstrap_resamples,
        )
        results.extend(
            pair
        )
        result_families.extend((definition.holm_family, definition.holm_family))

    families = tuple(dict.fromkeys(family for family in result_families if family))
    for family in families:
        indices = [
            index
            for index, item in enumerate(results)
            if result_families[index] == family
            and item.test == "Welch independent-samples t-test"
        ]
        adjusted = holm_adjust([results[index].raw_p for index in indices])
        for index, value in zip(indices, adjusted, strict=True):
            results[index] = replace(results[index], holm_adjusted_p=value)
    return tuple(results)


__all__ = [
    "ComparisonDefinition",
    "ComparisonResult",
    "compare_defined_groups",
    "compare_groups",
    "hedges_g",
    "holm_adjust",
]
