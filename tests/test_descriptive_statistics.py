from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest
from scipy import stats

from analysis import ComparisonDefinition, compare_defined_groups, describe_values, flag_mad_outliers, holm_adjust
from analysis.lsv_analysis import validate_common_potential_grid
from chi_parser import parse_lsv
from analysis import PotentialGridMismatchError


def test_descriptive_statistics_mean_sd_sem_cv_and_quartiles():
    values = np.arange(1.0, 14.0)
    summary = describe_values(values)

    assert summary.n == 13
    assert summary.mean == pytest.approx(np.mean(values))
    assert summary.sd == pytest.approx(np.std(values, ddof=1))
    assert summary.sem == pytest.approx(stats.sem(values))
    assert summary.cv_percent == pytest.approx(summary.sd / abs(summary.mean) * 100)
    assert summary.q1 == pytest.approx(np.quantile(values, 0.25))
    assert summary.q3 == pytest.approx(np.quantile(values, 0.75))


def test_material_statistics_exclude_bare(synthetic_analysis_result):
    for group in "ABC":
        assert synthetic_analysis_result.summary(group, "magnitude").statistics.n == 13
        assert synthetic_analysis_result.summary(group, "signed").statistics.n == 13


def test_welch_mann_whitney_holm_and_comparison_roles():
    values = {
        "A": np.linspace(1.0, 2.2, 13),
        "B": np.linspace(1.4, 2.6, 13),
        "C": np.linspace(2.0, 3.2, 13),
    }
    definitions = (
        ComparisonDefinition("A", "B", "primary", "historical_primary"),
        ComparisonDefinition("B", "C", "primary", "historical_primary"),
        ComparisonDefinition("A", "C", "exploratory"),
    )
    results = compare_defined_groups(values, definitions, bootstrap_seed=77, bootstrap_resamples=5000)

    assert len(results) == 6
    assert {item.test for item in results} == {
        "Welch independent-samples t-test",
        "Mann-Whitney U (two-sided sensitivity analysis)",
    }
    primary_welch = [
        item for item in results
        if item.comparison in {"A-B", "B-C"} and item.test.startswith("Welch")
    ]
    assert all(item.holm_adjusted_p is not None for item in primary_welch)
    exploratory = [item for item in results if item.comparison == "A-C"]
    assert all(item.comparison_role.startswith("exploratory") for item in exploratory)
    assert all(item.holm_adjusted_p is None for item in exploratory)
    assert holm_adjust((0.01, 0.04)) == pytest.approx((0.02, 0.04))


def test_hedges_g_bootstrap_is_reproducible():
    values = {
        "A": np.linspace(1.0, 2.2, 13),
        "B": np.linspace(1.4, 2.6, 13),
        "C": np.linspace(2.0, 3.2, 13),
    }
    definitions = (
        ComparisonDefinition("A", "B", "primary", "historical_primary"),
        ComparisonDefinition("B", "C", "primary", "historical_primary"),
        ComparisonDefinition("A", "C", "exploratory"),
    )
    first = compare_defined_groups(values, definitions, bootstrap_seed=991, bootstrap_resamples=5000)
    second = compare_defined_groups(values, definitions, bootstrap_seed=991, bootstrap_resamples=5000)

    assert first == second
    assert np.isfinite(first[0].hedges_g)
    assert first[0].hedges_g_ci_low < first[0].hedges_g_ci_high
    assert first[0].mean_difference_ci_low < first[0].mean_difference_ci_high


def test_mad_outlier_is_flagged_but_input_is_not_removed():
    records = [(f"f{i}.bin", "A", f"S{i}", value) for i, value in enumerate([1.0] * 12 + [9.0])]
    flags = flag_mad_outliers(records, target_potential_V=0.0, analysis_metric="magnitude")

    assert len(records) == 13
    assert len(flags) == 1
    assert flags[0].status == "Possible outlier"
    assert flags[0].response == 9.0


def test_potential_grid_mismatch_is_not_silently_averaged(lsv_path):
    first = parse_lsv(lsv_path)
    shifted = first.potential_V.copy()
    shifted[10] += 1e-5
    second = replace(first, potential_V=shifted)

    with pytest.raises(PotentialGridMismatchError):
        validate_common_potential_grid([first, second])
