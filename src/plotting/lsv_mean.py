"""Material-electrode mean LSV curves and pointwise sample SD."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analysis.lsv_analysis import LSVAnalysisResult
from export.figures import save_figure_formats

from .common import GROUP_COLORS, new_figure, potential_label, style_axes


def _group_curve(result: LSVAnalysisResult, group: str):
    rows = [
        item
        for item in result.files
        if item.manifest.group == group and item.manifest.electrode_type == "Material"
    ]
    currents = np.vstack([item.data.current_A * 1e6 for item in rows])
    return rows[0].data.potential_V, np.mean(currents, axis=0), np.std(currents, axis=0, ddof=1)


def plot_mean_lsv(result: LSVAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    output = Path(output_dir)
    curves = {group: _group_curve(result, group) for group in ("A", "B", "C")}
    lower = min(float(np.min(mean - sd)) for _, mean, sd in curves.values())
    upper = max(float(np.max(mean + sd)) for _, mean, sd in curves.values())
    margin = max((upper - lower) * 0.06, 0.05)
    y_limits = (lower - margin, upper + margin)
    target = result.settings.target_potential_V
    generated: list[Path] = []

    for group, (potential, mean, sd) in curves.items():
        figure, axis = new_figure()
        axis.plot(potential, mean, color=GROUP_COLORS[group], linewidth=1.8, label="Mean (n=13)")
        axis.fill_between(potential, mean - sd, mean + sd, color=GROUP_COLORS[group], alpha=0.22, linewidth=0, label="± SD")
        axis.axvline(target, color="#666666", linestyle=":", linewidth=1.1, label=f"Analysis potential = {potential_label(target)} V")
        axis.set(
            title=f"Group {group} Material mean LSV ± SD",
            xlabel="Potential / V",
            ylabel="Current / µA",
            xlim=(float(potential[0]), float(potential[-1])),
            ylim=y_limits,
        )
        style_axes(axis)
        axis.legend(frameon=False)
        generated.extend(save_figure_formats(figure, output / f"group_{group}_mean_sd_lsv"))
        plt.close(figure)

    figure, axis = new_figure(width=6.6, height=4.6)
    for group, (potential, mean, _sd) in curves.items():
        axis.plot(potential, mean, color=GROUP_COLORS[group], linewidth=1.8, label=f"Group {group} mean (n=13)")
    axis.axvline(target, color="#666666", linestyle=":", linewidth=1.1, label=f"Analysis potential = {potential_label(target)} V")
    axis.set(
        title="Material mean LSV comparison",
        xlabel="Potential / V",
        ylabel="Current / µA",
        xlim=(float(next(iter(curves.values()))[0][0]), float(next(iter(curves.values()))[0][-1])),
        ylim=y_limits,
    )
    style_axes(axis)
    axis.legend(frameon=False)
    generated.extend(save_figure_formats(figure, output / "groups_ABC_mean_lsv_overlay"))
    plt.close(figure)
    return tuple(generated)
