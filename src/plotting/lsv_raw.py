"""Per-group raw LSV curves with a shared scale across all files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import (
    colors_for_groups,
    new_figure,
    potential_label,
    safe_filename_component,
    style_axes,
)


def _global_limits(result: LSVAnalysisResult) -> tuple[tuple[float, float], tuple[float, float]]:
    x_min = min(float(item.data.potential_V[0]) for item in result.files)
    x_max = max(float(item.data.potential_V[-1]) for item in result.files)
    y_min = min(float(np.min(item.data.current_A) * 1e6) for item in result.files)
    y_max = max(float(np.max(item.data.current_A) * 1e6) for item in result.files)
    margin = max((y_max - y_min) * 0.06, 0.05)
    return (x_min, x_max), (y_min - margin, y_max + margin)


def build_raw_lsv_figure(result: LSVAnalysisResult, group: str):
    """Build one group figure for file export or an embedded GUI preview."""

    x_limits, y_limits = _global_limits(result)
    target = result.settings.target_potential_V
    groups = result.groups
    colors = colors_for_groups(groups)
    if group not in groups:
        raise ValueError(f"Unknown group: {group}")
    figure, axis = new_figure()
    rows = [item for item in result.files if item.manifest.group == group]
    material_label_used = False
    bare_label_used = False
    material_count = sum(item.manifest.electrode_type == "Material" for item in rows)
    bare_count = sum(item.manifest.electrode_type == "Bare" for item in rows)
    for item in rows:
        x = item.data.potential_V
        y = item.data.current_A * 1e6
        if item.manifest.electrode_type == "Bare":
            label = f"Bare (n={bare_count})" if not bare_label_used else None
            axis.plot(x, y, color="#111111", linewidth=1.8, linestyle="--", label=label)
            bare_label_used = True
        else:
            label = f"Material electrodes (n={material_count})" if not material_label_used else None
            axis.plot(x, y, color=colors[group], linewidth=0.8, alpha=0.68, label=label)
            material_label_used = True
    axis.axvline(target, color="#666666", linestyle=":", linewidth=1.1,
                 label=f"Analysis potential = {potential_label(target)} V")
    axis.set(title=f"Group {group} raw LSV", xlabel="Potential / V", ylabel="Current / µA",
             xlim=x_limits, ylim=y_limits)
    style_axes(axis)
    axis.legend(frameon=False, loc="best")
    return figure


def plot_raw_lsv(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    generated: list[Path] = []
    for group in result.groups:
        figure = build_raw_lsv_figure(result, group)
        generated.extend(
            save_figure_formats(
                figure, output / f"group_{safe_filename_component(group)}_raw_lsv"
            )
        )
        plt.close(figure)
    return tuple(generated)


__all__ = ["build_raw_lsv_figure", "plot_raw_lsv"]
