"""Group CV% comparison at the configured potential and metric."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import colors_for_groups, new_figure, potential_label, style_axes


def build_repeatability_figure(result: LSVAnalysisResult):
    groups = result.groups
    colors = colors_for_groups(groups)
    metric = result.settings.analysis_metric
    values = [result.summary(group, metric).statistics.cv_percent for group in groups]
    figure, axis = new_figure(width=5.5, height=4.4)
    bars = axis.bar(groups, values, color=[colors[group] for group in groups], width=0.62)
    for bar, value in zip(bars, values, strict=True):
        axis.text(bar.get_x() + bar.get_width() / 2, value, f"{value:.2f}%", ha="center", va="bottom", fontsize=8)
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
    axis.set_ylim(0.0, max(values) * 1.16)
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
