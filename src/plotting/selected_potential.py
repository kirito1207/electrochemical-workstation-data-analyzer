"""Individual electrode responses with mean ± SD and adjusted primary p values."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from typing import Any

import matplotlib.pyplot as plt
import numpy as np

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import colors_for_groups, new_figure, potential_label, style_axes


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


@dataclass(frozen=True, slots=True)
class SelectedScatterPoint:
    group: str
    sample_id: str
    x: float
    current_uA: float


@dataclass(frozen=True, slots=True)
class SelectedScatterSeries:
    artist: Any
    points: tuple[SelectedScatterPoint, ...]


def _adjusted_primary_lines(result: LSVAnalysisResult) -> tuple[str, ...]:
    return tuple(
        f"Welch + Holm ({item.holm_family}): {item.comparison} adjusted p = {item.holm_adjusted_p:.4g}"
        for item in result.comparisons
        if item.test == "Welch independent-samples t-test"
        and item.holm_adjusted_p is not None
    )


def build_selected_potential_figure(
    result: LSVAnalysisResult,
    metric: str,
    *,
    include_hover_metadata: bool = False,
):
    if metric not in {"magnitude", "signed"}:
        raise ValueError("metric must be magnitude or signed")
    target_text = potential_label(result.settings.target_potential_V)
    groups = result.groups
    colors = colors_for_groups(groups)
    figure, axis = new_figure(width=5.7, height=4.7)
    hover_series: list[SelectedScatterSeries] = []
    for position, group in enumerate(groups):
        rows = [
            item for item in result.files
            if item.manifest.group == group and item.manifest.electrode_type == "Material"
        ]
        values = np.asarray(
            [item.selected.response_magnitude_uA if metric == "magnitude" else item.selected.current_uA for item in rows],
            dtype=np.float64,
        )
        jitter = np.linspace(-0.12, 0.12, len(values))
        x_values = np.full(len(values), position) + jitter
        artist = axis.scatter(x_values, values, s=26, color=colors[group], alpha=0.82,
                              edgecolor="white", linewidth=0.45, zorder=3, picker=5)
        hover_series.append(
            SelectedScatterSeries(
                artist=artist,
                points=tuple(
                    SelectedScatterPoint(
                        group=group,
                        sample_id=item.manifest.sample_id or "",
                        x=float(x),
                        current_uA=float(value),
                    )
                    for item, x, value in zip(rows, x_values, values, strict=True)
                ),
            )
        )
        axis.errorbar(position, np.mean(values), yerr=np.std(values, ddof=1), fmt="o",
                      markersize=6, color="#111111", ecolor="#111111", capsize=5,
                      linewidth=1.2, zorder=4)
    title_prefix = "Current magnitude" if metric == "magnitude" else "Signed current"
    axis.set(xlabel="Group",
             ylabel=("Absolute current magnitude / µA" if metric == "magnitude" else "Signed current / µA"),
             xticks=tuple(range(len(groups))), xticklabels=groups,
             xlim=(-0.45, len(groups) - 0.55))
    lines = _adjusted_primary_lines(result)
    axis.set_title(f"{title_prefix} at {target_text} V", pad=35 if lines else 8)
    if lines:
        axis.text(0.5, 1.01, "\n".join(lines), transform=axis.transAxes,
                  va="bottom", ha="center", fontsize=8)
    style_axes(axis)
    return (figure, tuple(hover_series)) if include_hover_metadata else figure


def plot_selected_potential(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    target_text = potential_label(result.settings.target_potential_V)
    generated: list[Path] = []
    for metric in ("magnitude", "signed"):
        figure = build_selected_potential_figure(result, metric)
        generated.extend(save_figure_formats(figure, output / f"selected_{metric}_{target_text.replace('-', 'minus').replace('.', 'p')}V"))
        plt.close(figure)
    return tuple(generated)


__all__ = [
    "SelectedScatterPoint",
    "SelectedScatterSeries",
    "build_selected_potential_figure",
    "plot_selected_potential",
]
