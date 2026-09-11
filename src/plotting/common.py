"""Shared, restrained scientific plot styling."""

from __future__ import annotations

import matplotlib.pyplot as plt
import re


GROUP_COLORS = {"A": "#0072B2", "B": "#D55E00", "C": "#009E73"}
GENERIC_PALETTE = (
    "#0072B2", "#D55E00", "#009E73", "#CC79A7",
    "#E69F00", "#56B4E9", "#F0E442", "#332288",
    "#88CCEE", "#44AA99", "#117733", "#999933",
    "#DDCC77", "#CC6677", "#882255", "#AA4499",
    "#661100", "#6699CC", "#AA4466", "#4477AA",
)


def colors_for_groups(groups: tuple[str, ...]) -> dict[str, str]:
    """Keep PB42 colors stable and assign deterministic colors to other groups."""

    return {
        group: GROUP_COLORS.get(group, GENERIC_PALETTE[index % len(GENERIC_PALETTE)])
        for index, group in enumerate(groups)
    }


def safe_filename_component(value: str) -> str:
    """Keep user labels in figures while preventing them from changing paths."""

    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("._")
    return cleaned or "unnamed"


def potential_label(value: float) -> str:
    if abs(value) < 5e-7:
        return "0.000"
    three_decimals = f"{value:.3f}"
    if abs(value - float(three_decimals)) <= 5e-7:
        return three_decimals
    return f"{value:.6f}".rstrip("0").rstrip(".")


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


def group_figure_width(groups: tuple[str, ...], *, base: float = 5.5) -> float:
    """Grow categorical figures enough for N labels without runaway size."""

    longest = max((len(group) for group in groups), default=0)
    return min(
        14.0,
        max(base, 4.4 + 0.72 * len(groups), 5.0 + 0.025 * longest * len(groups)),
    )


def configure_group_ticks(axis, groups: tuple[str, ...]) -> None:
    """Use readable categorical labels while preserving user-defined order."""

    axis.set_xticks(tuple(range(len(groups))), labels=groups)
    if len(groups) > 4 or any(len(group) > 10 for group in groups):
        axis.tick_params(axis="x", labelrotation=30)
        for label in axis.get_xticklabels():
            label.set_horizontalalignment("right")


def legend_columns(group_count: int) -> int:
    return 1 if group_count <= 4 else 2 if group_count <= 10 else 3


def style_axes(axis) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(direction="out", width=0.8)
    axis.grid(False)
