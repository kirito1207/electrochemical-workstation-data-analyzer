"""Raw Current-Time figures with no smoothing or correction."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

from analysis.it_analysis import ITBatchAnalysisResult
from export.figures import save_figure_formats

from .common import new_figure, style_axes


def plot_raw_it(result: ITBatchAnalysisResult, output_dir: str | Path) -> tuple[Path, ...]:
    generated: list[Path] = []
    for item in result.files:
        figure, axis = new_figure(width=7.0, height=4.4)
        axis.plot(item.data.time_s, item.data.current_A * 1e6, color="#0072B2", linewidth=0.8)
        axis.set(
            title=f"Raw i-t: {item.sample_id}",
            xlabel="Time / s",
            ylabel="Current / µA",
            xlim=(item.data.actual_first_time_s, item.data.actual_last_time_s),
        )
        style_axes(axis)
        generated.extend(
            save_figure_formats(figure, Path(output_dir) / f"{item.sample_id}_raw_it")
        )
        plt.close(figure)
    return tuple(generated)


__all__ = ["plot_raw_it"]
