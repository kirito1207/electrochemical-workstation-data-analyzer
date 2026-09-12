"""Compatibility wrapper for the shared plotting font policy."""

from __future__ import annotations

from collections.abc import Iterable

from plotting.font_config import PREFERRED_PLOTTING_FONTS, configure_plotting_fonts


PREFERRED_GUI_FONTS = PREFERRED_PLOTTING_FONTS


def configure_gui_matplotlib_fonts(
    available_font_names: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Select installed Chinese-capable fonts with a safe cross-platform fallback."""

    return configure_plotting_fonts(available_font_names)


__all__ = ["PREFERRED_GUI_FONTS", "configure_gui_matplotlib_fonts"]
