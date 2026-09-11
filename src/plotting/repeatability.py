"""Group CV% comparison at the configured potential and metric."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import (
    colors_for_groups,
    configure_group_ticks,
    group_figure_width,
    new_figure,
    potential_label,
    style_axes,
)


def build_repeatability_figure(result: LSVAnalysisResult):
    groups = result.groups
    colors = colors_for_groups(groups)
    metric = result.settings.analysis_metric
    values = [result.summary(group, metric).statistics.cv_percent for group in groups]
    display_values = [value if np.isfinite(value) else 0.0 for value in values]
    figure, axis = new_figure(width=group_figure_width(groups), height=4.4)
    positions = tuple(range(len(groups)))
    bars = axis.bar(positions, display_values, color=[colors[group] for group in groups], width=0.62)
    for bar, value in zip(bars, values, strict=True):
        label = f"{value:.2f}%" if np.isfinite(value) else "N/A"
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            label,
            ha="center",
            va="bottom",
            fontsize=8,
        )
    target = potential_label(result.settings.target_potential_V)
    metric_label = "absolute magnitude" if metric == "magnitude" else "signed current"
    axis.set(
        title=(
            f"Material electrode repeatability at {target} V\n"
            f"Metric: {metric_label}; Material n shown by group"
        ),
        xlabel="User-defined group",
        ylabel="CV / %",
    )
    configure_group_ticks(axis, groups)
    finite = [value for value in values if np.isfinite(value)]
    axis.set_ylim(0.0, max(finite) * 1.16 if finite and max(finite) > 0 else 1.0)
    style_axes(axis)
    return figure


def plot_repeatability(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    figure = build_repeatability_figure(result)
    metric = result.settings.analysis_metric
    target = potential_label(result.settings.target_potential_V)
    generated = save_figure_formats(figure, Path(output_dir) / f"cv_percent_{metric}_{target.replace('-', 'minus').replace('.', 'p')}V")
    plt.close(figure)
    return generated


__all__ = ["build_repeatability_figure", "plot_repeatability"]
