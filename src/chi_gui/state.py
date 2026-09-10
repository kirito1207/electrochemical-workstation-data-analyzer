"""Headless GUI state models; no tkinter dependency."""

from __future__ import annotations

import os
import colorsys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from numpy.typing import NDArray
import numpy as np

from chi_parser import ExperimentData


class FileStatus(str, Enum):
    PARSED = "解析成功"
    FAILED = "解析失败"
    UNSUPPORTED = "不支持"


def canonical_path(path: str | Path) -> str:
    """Stable key for duplicate suppression, including Windows case folding."""

    return os.path.normcase(str(Path(path).expanduser().resolve(strict=False)))


@dataclass(frozen=True, slots=True)
class FileRecord:
    path: Path
    status: FileStatus
    experiment_type: str
    route: str
    data: ExperimentData | None = None
    warning_messages: tuple[str, ...] = ()
    error_type: str | None = None
    error_message: str | None = None
    diagnostic: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return canonical_path(self.path)

    @property
    def parse_success(self) -> bool:
        return self.status is FileStatus.PARSED and self.data is not None


@dataclass(frozen=True, slots=True)
class PreviewData:
    source_file: Path
    experiment_type: str
    x: NDArray[np.float64]
    current_A: NDArray[np.float64]
    x_label: str
    y_label: str = "Current / µA"

    @property
    def current_uA(self) -> NDArray[np.float64]:
        """Display conversion only; the parser's current_A remains untouched."""

        return self.current_A * 1e6


@dataclass(frozen=True, slots=True)
class PreviewCurve:
    record_key: str
    file_name: str
    data: PreviewData
    color: str
    visible: bool
    selected: bool


@dataclass(frozen=True, slots=True)
class PreviewCollection:
    experiment_type: str
    curves: tuple[PreviewCurve, ...]
    selected_key: str | None

    @property
    def visible_curves(self) -> tuple[PreviewCurve, ...]:
        return tuple(curve for curve in self.curves if curve.visible)


class PreviewDisplayState:
    """Session-only colors and visibility, separate from analysis membership."""

    def __init__(self) -> None:
        self._colors: dict[str, str] = {}
        self._hidden: set[str] = set()
        self._next_color_index = 0

    def color_for(self, key: str) -> str:
        if key not in self._colors:
            # Golden-ratio hue stepping gives stable, distinct colors for 42+ files.
            hue = (0.08 + self._next_color_index * 0.618033988749895) % 1.0
            red, green, blue = colorsys.hsv_to_rgb(hue, 0.68, 0.78)
            self._colors[key] = f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"
            self._next_color_index += 1
        return self._colors[key]

    def is_visible(self, key: str) -> bool:
        return key not in self._hidden

    def set_visible(self, key: str, visible: bool) -> None:
        if visible:
            self._hidden.discard(key)
        else:
            self._hidden.add(key)

    def reset_visibility(self) -> None:
        self._hidden.clear()


@dataclass(frozen=True, slots=True)
class StateSummary:
    total: int
    parsed: int
    failed: int
    unsupported: int
    lsv: int
    it: int


class AppState:
    """Ordered file collection mutated only by the GUI main thread."""

    def __init__(self) -> None:
        self._records: dict[str, FileRecord] = {}

    @property
    def records(self) -> tuple[FileRecord, ...]:
        return tuple(self._records.values())

    def contains(self, path: str | Path) -> bool:
        return canonical_path(path) in self._records

    def add_records(self, records: tuple[FileRecord, ...] | list[FileRecord]) -> int:
        added = 0
        for record in records:
            if record.key not in self._records:
                self._records[record.key] = record
                added += 1
        return added

    def remove(self, paths: tuple[str | Path, ...] | list[str | Path]) -> int:
        removed = 0
        for path in paths:
            if self._records.pop(canonical_path(path), None) is not None:
                removed += 1
        return removed

    def clear(self) -> None:
        self._records.clear()

    def for_route(self, route: str | None) -> tuple[FileRecord, ...]:
        if route in {None, "all"}:
            return self.records
        return tuple(record for record in self.records if record.route == route)

    def summary(self) -> StateSummary:
        records = self.records
        return StateSummary(
            total=len(records),
            parsed=sum(record.status is FileStatus.PARSED for record in records),
            failed=sum(record.status is FileStatus.FAILED for record in records),
            unsupported=sum(record.status is FileStatus.UNSUPPORTED for record in records),
            lsv=sum(record.experiment_type == "LSV" for record in records),
            it=sum(record.experiment_type == "i-t" for record in records),
        )
