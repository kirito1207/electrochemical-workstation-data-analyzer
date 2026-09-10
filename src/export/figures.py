"""Consistent lossless/vector and publication-resolution figure export."""

from __future__ import annotations

from pathlib import Path

from matplotlib.figure import Figure


def save_figure_formats(figure: Figure, base_path: str | Path) -> tuple[Path, ...]:
    base = Path(base_path)
    base.parent.mkdir(parents=True, exist_ok=True)
    outputs = tuple(base.with_suffix(suffix) for suffix in (".png", ".svg", ".pdf"))
    figure.savefig(outputs[0], dpi=300, bbox_inches="tight", facecolor="white")
    figure.savefig(outputs[1], bbox_inches="tight", facecolor="white")
    figure.savefig(outputs[2], bbox_inches="tight", facecolor="white")
    return outputs
