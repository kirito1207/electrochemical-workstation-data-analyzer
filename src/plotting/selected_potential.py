"""Individual electrode responses with mean ± SD and adjusted primary p values."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import GROUP_COLORS, new_figure, potential_label, style_axes


def _values(result: LSVAnalysisResult, group: str, metric: str) -> np.ndarray:
    rows = [
        item
        for item in result.files
        if item.manifest.group == group and item.manifest.electrode_type == "Material"
    ]
    return np.asarray(
        [
            item.selected.response_magnitude_uA if metric == "magnitude" else item.selected.current_uA
            for item in rows
        ],
        dtype=np.float64,
    )


def _adjusted_primary(result: LSVAnalysisResult, comparison: str) -> float:
    adjusted = next(
        item.holm_adjusted_p
        for item in result.comparisons
        if item.comparison == comparison and item.test == "Welch independent-samples t-test"
    )
    if adjusted is None:
        raise ValueError(f"Missing Holm-adjusted p value for primary comparison {comparison}.")
    return adjusted


def plot_selected_potential(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    target_text = potential_label(result.settings.target_potential_V)
    generated: list[Path] = []
    for metric in ("magnitude", "signed"):
        figure, axis = new_figure(width=5.7, height=4.7)
        all_values: list[float] = []
        for position, group in enumerate(("A", "B", "C")):
            values = _values(result, group, metric)
            all_values.extend(values)
            jitter = np.linspace(-0.12, 0.12, len(values))
            axis.scatter(
                np.full(len(values), position) + jitter,
                values,
                s=26,
                color=GROUP_COLORS[group],
                alpha=0.82,
                edgecolor="white",
                linewidth=0.45,
                zorder=3,
            )
            axis.errorbar(
                position,
                np.mean(values),
                yerr=np.std(values, ddof=1),
                fmt="o",
                markersize=6,
                color="#111111",
                ecolor="#111111",
                capsize=5,
                linewidth=1.2,
                zorder=4,
            )
        title_prefix = "Current magnitude" if metric == "magnitude" else "Signed current"
        axis.set(
            xlabel="Group",
            ylabel=("Absolute current magnitude / µA" if metric == "magnitude" else "Signed current / µA"),
            xticks=(0, 1, 2),
            xticklabels=("A", "B", "C"),
            xlim=(-0.45, 2.45),
        )
        axis.set_title(f"{title_prefix} at {target_text} V", pad=35)
        axis.text(
            0.5,
            1.01,
            f"Welch + Holm: A–B adjusted p = {_adjusted_primary(result, 'A-B'):.4g}\n"
            f"Welch + Holm: B–C adjusted p = {_adjusted_primary(result, 'B-C'):.4g}",
            transform=axis.transAxes,
            va="bottom",
            ha="center",
            fontsize=8,
        )
        style_axes(axis)
        generated.extend(save_figure_formats(figure, output / f"selected_{metric}_{target_text.replace('-', 'minus').replace('.', 'p')}V"))
        plt.close(figure)
    return tuple(generated)
