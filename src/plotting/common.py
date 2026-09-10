"""Shared, restrained scientific plot styling."""

from __future__ import annotations

import matplotlib.pyplot as plt


GROUP_COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}


def potential_label(value: float) -> str:
    return "0.000" if abs(value) < 0.0005 else f"{value:.3f}"


def new_figure(*, width: float = 6.2, height: float = 4.4):
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "legend.fontsize": 8,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    return plt.subplots(figsize=(width, height), constrained_layout=True)


def style_axes(axis) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(direction="out", width=0.8)
    axis.grid(False)
