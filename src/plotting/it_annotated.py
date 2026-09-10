"""Confirmed addition times and actual plateau windows over raw i-t traces."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from analysis.it_analysis import ITBatchAnalysisResult
from export.figures import save_figure_formats

from .common import new_figure, style_axes


def plot_annotated_it(
    result: ITBatchAnalysisResult,
    output_dir: str | Path,
) -> tuple[Path, ...]:
    generated: list[Path] = []
    for item in result.files:
        figure, axis = new_figure(width=7.4, height=4.7)
        axis.plot(
            item.data.time_s,
            item.data.current_A * 1e6,
            color="#0072B2",
            linewidth=0.75,
            label="Raw current",
        )
        for index, (step, plateau) in enumerate(
            zip(item.protocol.steps, item.plateaus, strict=True)
        ):
            if index > 0:
                axis.axvline(step.addition_time_s, color="#D55E00", linewidth=0.9, linestyle="--")
                axis.text(
                    step.addition_time_s,
                    0.98,
                    f"{step.concentration_uM:g} µM",
                    transform=axis.get_xaxis_transform(),
                    rotation=90,
                    va="top",
                    ha="right",
                    fontsize=7,
                )
            axis.axvspan(
                plateau.plateau_start_s,
                plateau.plateau_end_s,
                color="#009E73",
                alpha=0.13,
                label="Plateau window" if index == 0 else None,
            )
        axis.set(
            title=f"Confirmed additions and plateau windows: {item.sample_id}",
            xlabel="Time / s",
            ylabel="Current / µA",
            xlim=(item.data.actual_first_time_s, item.data.actual_last_time_s),
        )
        style_axes(axis)
        axis.legend(frameon=False, loc="best")
        generated.extend(
            save_figure_formats(figure, Path(output_dir) / f"{item.sample_id}_annotated_it")
        )
        plt.close(figure)
    return tuple(generated)


__all__ = ["plot_annotated_it"]
