"""One CJK-capable Matplotlib font policy shared by GUI and exported figures."""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache

from matplotlib import font_manager, rcParams


PREFERRED_PLOTTING_FONTS = (
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Arial Unicode MS",
    "DejaVu Sans",
)


@lru_cache(maxsize=1)
def _installed_font_names() -> frozenset[str]:
    return frozenset(font.name for font in font_manager.fontManager.ttflist)


def configure_plotting_fonts(
    available_font_names: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Configure a CJK-capable sans-serif chain without bundling font files."""

    available = set(available_font_names) if available_font_names is not None else set(_installed_font_names())
    selected = tuple(name for name in PREFERRED_PLOTTING_FONTS if name in available)
    if not selected:
        selected = ("DejaVu Sans",)
    rcParams["font.family"] = "sans-serif"
    rcParams["font.sans-serif"] = list(selected)
    rcParams["axes.unicode_minus"] = False
    return selected


__all__ = ["PREFERRED_PLOTTING_FONTS", "configure_plotting_fonts"]
