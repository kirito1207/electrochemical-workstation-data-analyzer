"""GUI-only Matplotlib font configuration for Chinese Windows previews."""

from __future__ import annotations

from collections.abc import Iterable

from matplotlib import font_manager, rcParams


PREFERRED_GUI_FONTS = (
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
    "DejaVu Sans",
)


def configure_gui_matplotlib_fonts(
    available_font_names: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Select installed Chinese-capable fonts with a safe cross-platform fallback."""

    available = set(
        available_font_names
        if available_font_names is not None
        else (font.name for font in font_manager.fontManager.ttflist)
    )
    selected = tuple(name for name in PREFERRED_GUI_FONTS if name in available)
    if not selected:
        selected = ("DejaVu Sans",)
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = list(selected)
    # ASCII minus remains visible even when a selected CJK font lacks U+2212.
    rcParams["axes.unicode_minus"] = False
    return selected


__all__ = ["PREFERRED_GUI_FONTS", "configure_gui_matplotlib_fonts"]
