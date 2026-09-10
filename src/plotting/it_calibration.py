"""Step-response and single-/multi-electrode i-t calibration figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from analysis.it_analysis import ITBatchAnalysisResult, ITFileAnalysis
from export.figures import save_figure_formats

from .common import new_figure, style_axes


def _save_response(
    item: ITFileAnalysis,
    output: Path,
    *,
    values: np.ndarray,
    ylabel: str,
    title: str,
    stem: str,
) -> tuple[Path, ...]:
    x = np.asarray([row.concentration_uM for row in item.delta_i])
    figure, axis = new_figure(width=5.6, height=4.3)
    axis.plot(x, values, marker="o", color="#0072B2", linewidth=1.0)
    axis.set(title=f"{title}: {item.sample_id}", xlabel="Concentration / µM", ylabel=ylabel)
    style_axes(axis)
    generated = save_figure_formats(figure, output / f"{item.sample_id}_{stem}")
    plt.close(figure)
    return generated


def _plot_individual_calibration(
    item: ITFileAnalysis,
    output: Path,
) -> tuple[Path, ...]:
    metric = item.calibration.analysis_metric
    x = np.asarray([row.concentration_uM for row in item.delta_i])
    y = np.asarray(
        [
            row.signed_delta_I_uA if metric == "signed" else row.magnitude_delta_I_uA
            for row in item.delta_i
        ]
    )
    included = np.asarray([row.include_in_calibration for row in item.delta_i], dtype=bool)
    figure, axis = new_figure(width=5.8, height=4.5)
    axis.scatter(x[included], y[included], color="#0072B2", label="Included", zorder=3)
    if np.any(~included):
        axis.scatter(
            x[~included], y[~included], facecolor="none", edgecolor="#777777",
            label="Excluded by protocol", zorder=3,
        )
    fit_x = np.linspace(float(np.min(x[included])), float(np.max(x[included])), 100)
    fit_y = item.calibration.intercept_uA + item.calibration.slope_uA_per_uM * fit_x
    axis.plot(fit_x, fit_y, color="#D55E00", linewidth=1.2, label="OLS fit")
    axis.set(
        title=f"Individual calibration: {item.sample_id}",
        xlabel="Concentration / µM",
        ylabel=("Signed ΔI / µA" if metric == "signed" else "Absolute ΔI magnitude / µA"),
    )
    axis.text(
        0.03, 0.97,
        f"y = {item.calibration.slope_uA_per_uM:.5g}x + {item.calibration.intercept_uA:.5g}\n"
        f"R² = {item.calibration.r_squared:.5f}",
        transform=axis.transAxes, va="top", fontsize=8,
    )
    style_axes(axis)
    axis.legend(frameon=False, loc="best")
    generated = save_figure_formats(figure, output / f"{item.sample_id}_calibration_{metric}")
    plt.close(figure)
    return generated


def _plot_multi_calibration(
    result: ITBatchAnalysisResult,
    output: Path,
) -> tuple[Path, ...]:
    if result.group_mean_calibration is None:
        return ()
    metric = result.settings.analysis_metric
    figure, axis = new_figure(width=6.0, height=4.7)
    concentrations = sorted({row.concentration_uM for item in result.files for row in item.delta_i})
    for concentration in concentrations:
        rows = [
            row for item in result.files for row in item.delta_i
            if row.concentration_uM == concentration
        ]
        included = all(row.include_in_calibration for row in rows)
        values = np.asarray([
            row.signed_delta_I_uA if metric == "signed" else row.magnitude_delta_I_uA
            for row in rows
        ])
        jitter = np.linspace(-0.6, 0.6, len(values)) if len(values) > 1 else np.zeros(1)
        axis.scatter(
            np.full(len(values), concentration) + jitter,
            values,
            color="#0072B2" if included else "none",
            edgecolor="#0072B2" if included else "#777777",
            alpha=0.75,
            s=24,
            zorder=3,
            label=(
                "Individual electrodes"
                if concentration == concentrations[0]
                else "Excluded by protocol"
                if not included
                else None
            ),
        )
    summary = [row for row in result.concentration_summary]
    x = np.asarray([row.concentration_uM for row in summary])
    means = np.asarray([
        row.mean_signed_delta_I_uA if metric == "signed" else row.mean_magnitude_delta_I_uA
        for row in summary
    ])
    sd = np.asarray([
        row.sd_signed_delta_I_uA if metric == "signed" else row.sd_magnitude_delta_I_uA
        for row in summary
    ])
    summary_included = np.asarray([row.include_in_group_calibration for row in summary], dtype=bool)
    axis.errorbar(
        x[summary_included], means[summary_included], yerr=sd[summary_included],
        fmt="o", color="#111111", capsize=4, label="Mean ± SD", zorder=4,
    )
    if np.any(~summary_included):
        axis.errorbar(
            x[~summary_included], means[~summary_included], yerr=sd[~summary_included],
            fmt="o", markerfacecolor="none", color="#777777", capsize=4,
            label="Excluded mean ± SD", zorder=4,
        )
    fit = result.group_mean_calibration
    fit_x = np.linspace(min(fit.included_concentrations_uM), max(fit.included_concentrations_uM), 100)
    axis.plot(fit_x, fit.intercept_uA + fit.slope_uA_per_uM * fit_x, color="#D55E00", label="Group-mean OLS fit")
    axis.set(
        title="Multi-electrode calibration",
        xlabel="Concentration / µM",
        ylabel=("Signed ΔI / µA" if metric == "signed" else "Absolute ΔI magnitude / µA"),
    )
    style_axes(axis)
    axis.legend(frameon=False, loc="best")
    generated = save_figure_formats(figure, output / f"multi_electrode_calibration_{metric}")
    plt.close(figure)
    return generated


def plot_it_calibrations(
    result: ITBatchAnalysisResult,
    output_dir: str | Path,
) -> tuple[Path, ...]:
    output = Path(output_dir)
    generated: list[Path] = []
    for item in result.files:
        plateau = np.asarray([row.plateau_mean_uA for row in item.delta_i])
        signed = np.asarray([row.signed_delta_I_uA for row in item.delta_i])
        magnitude = np.asarray([row.magnitude_delta_I_uA for row in item.delta_i])
        generated.extend(_save_response(item, output, values=plateau, ylabel="Plateau current / µA", title="Plateau current", stem="plateau_current"))
        generated.extend(_save_response(item, output, values=signed, ylabel="Signed ΔI / µA", title="Signed step response", stem="signed_deltaI"))
        generated.extend(_save_response(item, output, values=magnitude, ylabel="Absolute ΔI magnitude / µA", title="Magnitude step response", stem="magnitude_deltaI"))
        generated.extend(_plot_individual_calibration(item, output))
    generated.extend(_plot_multi_calibration(result, output))
    return tuple(generated)


__all__ = ["plot_it_calibrations"]
