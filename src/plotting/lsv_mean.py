"""Material-electrode mean LSV curves and pointwise sample SD."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import (
    colors_for_groups,
    group_figure_width,
    legend_columns,
    new_figure,
    potential_label,
    safe_filename_component,
    style_axes,
)


def _group_curve(result: LSVAnalysisResult, group: str):
    rows = [
        item
        for item in result.files
        if item.manifest.group == group and item.manifest.electrode_type == "Material"
    ]
    currents = np.vstack([item.data.current_A * 1e6 for item in rows])
    sd = (
        np.std(currents, axis=0, ddof=1)
        if len(rows) > 1
        else np.full(currents.shape[1], np.nan, dtype=np.float64)
    )
    return rows[0].data.potential_V, np.mean(currents, axis=0), sd


def _curve_limits(curves) -> tuple[float, float]:
    values = []
    for _potential, mean, sd in curves.values():
        values.append(mean)
        finite_sd = np.isfinite(sd)
        if finite_sd.any():
            values.extend((mean[finite_sd] - sd[finite_sd], mean[finite_sd] + sd[finite_sd]))
    lower = min(float(np.min(value)) for value in values)
    upper = max(float(np.max(value)) for value in values)
    margin = max((upper - lower) * 0.06, 0.05)
    return lower - margin, upper + margin


def build_mean_lsv_figure(result: LSVAnalysisResult, group: str | None = None):
    """Build a group mean±SD figure, or the all-group mean overlay."""

    groups = result.groups
    colors = colors_for_groups(groups)
    curves = {name: _group_curve(result, name) for name in groups}
    y_limits = _curve_limits(curves)
    target = result.settings.target_potential_V
    if group is not None and group != "ALL":
        potential, mean, sd = curves[group]
        n = result.summary(group, "signed").statistics.n
        figure, axis = new_figure()
        axis.plot(potential, mean, color=colors[group], linewidth=1.8, label=f"Mean (n={n})")
        axis.fill_between(potential, mean - sd, mean + sd, color=colors[group], alpha=0.22, linewidth=0, label="± SD")
        title = f"Group {group} Material mean LSV ± SD"
    else:
        figure, axis = new_figure(width=group_figure_width(groups, base=6.6), height=4.6)
        for name, (potential, mean, _sd) in curves.items():
            n = result.summary(name, "signed").statistics.n
            axis.plot(potential, mean, color=colors[name], linewidth=1.8, label=f"Group {name} mean (n={n})")
            if group == "ALL":
                sd = curves[name][2]
                axis.fill_between(
                    potential,
                    mean - sd,
                    mean + sd,
                    color=colors[name],
                    alpha=0.12,
                    linewidth=0,
                )
        potential = next(iter(curves.values()))[0]
        title = "Material mean LSV ± SD" if group == "ALL" else "Material mean LSV comparison"
    axis.axvline(target, color="#666666", linestyle=":", linewidth=1.1, label=f"Analysis potential = {potential_label(target)} V")
    axis.set(title=title, xlabel="Potential / V", ylabel="Current / µA",
             xlim=(float(potential[0]), float(potential[-1])), ylim=y_limits)
    style_axes(axis)
    axis.legend(
        frameon=False,
        ncol=1 if group is not None and group != "ALL" else legend_columns(len(groups)),
    )
    return figure


def plot_mean_lsv(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    groups = result.groups
    colors = colors_for_groups(groups)
    curves = {group: _group_curve(result, group) for group in groups}
    y_limits = _curve_limits(curves)
    target = result.settings.target_potential_V
    generated: list[Path] = []

    for group, (potential, mean, sd) in curves.items():
        figure = build_mean_lsv_figure(result, group)
        generated.extend(
            save_figure_formats(
                figure, output / f"group_{safe_filename_component(group)}_mean_sd_lsv"
            )
        )
        plt.close(figure)

    figure = build_mean_lsv_figure(result)
    group_stem = (
        "ABC"
        if groups == ("A", "B", "C")
        else "_".join(safe_filename_component(group) for group in groups)
    )
    generated.extend(save_figure_formats(figure, output / f"groups_{group_stem}_mean_lsv_overlay"))
    plt.close(figure)
    return tuple(generated)


__all__ = ["build_mean_lsv_figure", "plot_mean_lsv"]
