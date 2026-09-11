"""Small, testable policies for stable GUI geometry and compact labels."""

from __future__ import annotations

from dataclasses import dataclass


DATA_PAGE_LEFT_MIN_PX = 360
DATA_PAGE_RIGHT_MIN_PX = 280
DATA_PAGE_DEFAULT_LEFT_FRACTION = 0.62
DATA_PAGE_MIN_LEFT_FRACTION = 0.52
DATA_PAGE_MAX_LEFT_FRACTION = 0.74
DATA_PAGE_RIGHT_PREFERRED_PX = 360
PARAMETER_VALUE_WRAP_PX = 320
CURVE_FILENAME_DISPLAY_CHARS = 48


def compact_filename(value: str, *, limit: int = CURVE_FILENAME_DISPLAY_CHARS) -> str:
    """Bound list-label width without changing the underlying filename."""

    if limit < 5:
        raise ValueError("filename display limit must be at least 5 characters")
    if len(value) <= limit:
        return value
    head = (limit - 1) // 2
    tail = limit - head - 1
    return f"{value[:head]}…{value[-tail:]}"


@dataclass(slots=True)
class DataPageLayoutState:
    """Remember a bounded data-page sash fraction across maps and resizes."""

    left_fraction: float = DATA_PAGE_DEFAULT_LEFT_FRACTION
    last_width: int = 0

    def sash_position(self, total_width: int) -> int:
        width = max(1, int(total_width))
        if width <= DATA_PAGE_LEFT_MIN_PX + DATA_PAGE_RIGHT_MIN_PX:
            return max(1, width - DATA_PAGE_RIGHT_MIN_PX)
        preferred = round(width * self.left_fraction)
        return min(
            max(preferred, DATA_PAGE_LEFT_MIN_PX),
            width - DATA_PAGE_RIGHT_MIN_PX,
        )

    def remember(self, total_width: int, sash_position: int) -> None:
        width = int(total_width)
        if width <= 1:
            return
        fraction = float(sash_position) / width
        self.left_fraction = min(
            max(fraction, DATA_PAGE_MIN_LEFT_FRACTION),
            DATA_PAGE_MAX_LEFT_FRACTION,
        )
        self.last_width = width


__all__ = [
    "CURVE_FILENAME_DISPLAY_CHARS",
    "DATA_PAGE_LEFT_MIN_PX",
    "DATA_PAGE_RIGHT_MIN_PX",
    "DATA_PAGE_RIGHT_PREFERRED_PX",
    "DataPageLayoutState",
    "PARAMETER_VALUE_WRAP_PX",
    "compact_filename",
]
