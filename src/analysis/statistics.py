"""Predeclared group comparisons and reproducible effect-size intervals."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal, Mapping, Sequence

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


OmnibusStatus = Literal["ok", "not_applicable", "unavailable"]


@dataclass(frozen=True, slots=True)
class OmnibusTestResult:
    """One overall multi-group test, including structured non-result states."""

    test: str
    statistic: float | None
    df1: float | None
    df2: float | None
    p_value: float | None
    group_count: int
    total_n: int
    status: OmnibusStatus
    notes: str = ""


def _omnibus_arrays(
    grouped_values: Mapping[str, Sequence[float]],
) -> tuple[tuple[str, ...], tuple[np.ndarray, ...], int]:
    names = tuple(grouped_values)
    arrays = tuple(np.asarray(grouped_values[name], dtype=np.float64) for name in names)
    if any(values.ndim != 1 for values in arrays):
        raise ValueError("Omnibus tests require one-dimensional group observations.")
    return names, arrays, sum(len(values) for values in arrays)


def _omnibus_precheck(
    test: str,
    names: tuple[str, ...],
    arrays: tuple[np.ndarray, ...],
    total_n: int,
) -> OmnibusTestResult | None:
    group_count = len(names)
    if group_count < 3:
        return OmnibusTestResult(
            test, None, None, None, None, group_count, total_n, "not_applicable",
            "Overall multi-group testing requires at least 3 Material Groups.",
        )
    short = [name for name, values in zip(names, arrays, strict=True) if len(values) < 2]
    if short:
        details = ", ".join(
            f"{name} (n={len(values)})"
            for name, values in zip(names, arrays, strict=True)
            if len(values) < 2
        )
        return OmnibusTestResult(
            test, None, float(group_count - 1), None, None, group_count, total_n,
            "unavailable", f"Each Material Group requires n >= 2; insufficient: {details}.",
        )
    invalid = [
        name for name, values in zip(names, arrays, strict=True)
        if not np.isfinite(values).all()
    ]
    if invalid:
        return OmnibusTestResult(
            test, None, float(group_count - 1), None, None, group_count, total_n,
            "unavailable", "Non-finite observations in Group(s): " + ", ".join(invalid) + ".",
        )
    return None


def welch_anova(
    grouped_values: Mapping[str, Sequence[float]],
) -> OmnibusTestResult:
    """Calculate standard one-way Welch ANOVA without equal variances.

    This uses weights ``w_i = n_i / s_i**2`` and the Welch (1951)
    correction. SciPy's F survival function is used only to convert the
    statistic and degrees of freedom to a p-value. This remains compatible
    with SciPy versions before ``f_oneway`` gained ``equal_var``.
    """

    names, arrays, total_n = _omnibus_arrays(grouped_values)
    precheck = _omnibus_precheck("Welch ANOVA", names, arrays, total_n)
    if precheck is not None:
        return precheck
    group_count = len(arrays)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        variances = np.asarray(
            [np.var(values, ddof=1) for values in arrays], dtype=np.float64
        )
    zero_variance = [
        name for name, variance in zip(names, variances, strict=True)
        if not math.isfinite(float(variance)) or variance <= 0.0
    ]
    if zero_variance:
        return OmnibusTestResult(
            "Welch ANOVA", None, float(group_count - 1), None, None,
            group_count, total_n, "unavailable",
            "Welch ANOVA is undefined for zero within-group variance: "
            + ", ".join(zero_variance) + ".",
        )

    sizes = np.asarray([len(values) for values in arrays], dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        means = np.asarray([np.mean(values) for values in arrays], dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        weights = sizes / variances
        weight_sum = float(np.sum(weights))
        weighted_mean = float(np.sum(weights * means) / weight_sum)
        adjustment_sum = float(
            np.sum(((1.0 - weights / weight_sum) ** 2) / (sizes - 1.0))
        )
    if not math.isfinite(adjustment_sum) or adjustment_sum <= 0.0:
        return OmnibusTestResult(
            "Welch ANOVA", None, float(group_count - 1), None, None,
            group_count, total_n, "unavailable",
            "Welch ANOVA denominator degrees of freedom could not be calculated.",
        )
    numerator = float(np.sum(weights * (means - weighted_mean) ** 2) / (group_count - 1))
    correction = 1.0 + (
        2.0 * (group_count - 2.0) / (group_count**2 - 1.0)
    ) * adjustment_sum
    statistic = numerator / correction
    df1 = float(group_count - 1)
    df2 = float((group_count**2 - 1.0) / (3.0 * adjustment_sum))
    p_value = float(stats.f.sf(statistic, df1, df2))
    if not all(math.isfinite(value) for value in (statistic, df1, df2, p_value)):
        return OmnibusTestResult(
            "Welch ANOVA", None, df1, df2, None, group_count, total_n,
            "unavailable", "Welch ANOVA produced a non-finite result.",
        )
    return OmnibusTestResult(
        "Welch ANOVA", statistic, df1, df2, p_value,
        group_count, total_n, "ok",
    )


def kruskal_wallis(
    grouped_values: Mapping[str, Sequence[float]],
) -> OmnibusTestResult:
    """Calculate the Kruskal-Wallis rank-based sensitivity analysis."""

    names, arrays, total_n = _omnibus_arrays(grouped_values)
    precheck = _omnibus_precheck("Kruskal-Wallis", names, arrays, total_n)
    if precheck is not None:
        return precheck
    group_count = len(arrays)
    pooled = np.concatenate(arrays)
    if np.all(pooled == pooled[0]):
        return OmnibusTestResult(
            "Kruskal-Wallis", None, float(group_count - 1), None, None,
            group_count, total_n, "unavailable",
            "All observations are identical; the rank statistic is undefined.",
        )
    try:
        result = stats.kruskal(*arrays, nan_policy="raise")
    except ValueError as error:
        return OmnibusTestResult(
            "Kruskal-Wallis", None, float(group_count - 1), None, None,
            group_count, total_n, "unavailable", str(error),
        )
    statistic = float(result.statistic)
    p_value = float(result.pvalue)
    if not math.isfinite(statistic) or not math.isfinite(p_value):
        return OmnibusTestResult(
            "Kruskal-Wallis", None, float(group_count - 1), None, None,
            group_count, total_n, "unavailable",
            "Kruskal-Wallis produced a non-finite result.",
        )
    return OmnibusTestResult(
        "Kruskal-Wallis", statistic, float(group_count - 1), None, p_value,
        group_count, total_n, "ok",
    )


def compute_omnibus_tests(
    grouped_values: Mapping[str, Sequence[float]],
) -> tuple[OmnibusTestResult, OmnibusTestResult]:
    """Report both fixed omnibus tests without gating pairwise comparisons."""

    return welch_anova(grouped_values), kruskal_wallis(grouped_values)


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
    "OmnibusTestResult",
    "compute_omnibus_tests",
    "compare_defined_groups",
    "hedges_g",
    "holm_adjust",
    "kruskal_wallis",
    "welch_anova",
]
