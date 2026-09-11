"""Headless, read-only inspection cursor calculations for GUI previews."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from analysis.potential import PotentialOutOfRangeError, extract_current_at_potential
from chi_parser import ITData, LSVData

from .state import FileRecord, PreviewCollection


@dataclass(frozen=True, slots=True)
class CursorReading:
    """One visible curve's value at a shared inspection cursor position."""

    record_key: str
    file_name: str
    experiment_type: str
    requested_x: float
    actual_sampled_x: float | None
    current_A: float | None
    interpolated: bool
    lower_x: float | None = None
    upper_x: float | None = None
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.current_A is not None and self.error is None

    @property
    def current_uA(self) -> float | None:
        return None if self.current_A is None else self.current_A * 1e6


@dataclass(frozen=True, slots=True)
class CursorReadingSet:
    experiment_type: str
    requested_x: float
    readings: tuple[CursorReading, ...]

    def by_record_key(self) -> dict[str, CursorReading]:
        return {reading.record_key: reading for reading in self.readings}


@dataclass(slots=True)
class InspectionCursorState:
    """Workspace-local display state, unrelated to formal analysis settings."""

    requested_x: float | None = None
    visible: bool = False
    input_text: str = ""
    validation_message: str = ""

    def set(self, value: float, *, input_text: str | None = None) -> None:
        self.requested_x = float(value)
        self.visible = True
        self.input_text = input_text if input_text is not None else str(float(value))
        self.validation_message = ""

    def invalidate(self, input_text: str, message: str) -> None:
        self.requested_x = None
        self.visible = False
        self.input_text = input_text
        self.validation_message = message

    def clear(self) -> None:
        self.requested_x = None
        self.visible = False
        self.input_text = ""
        self.validation_message = ""


def parse_cursor_input(text: str) -> float | None:
    """Parse a finite cursor value without raising a GUI-facing exception."""

    try:
        value = float(text.strip())
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def format_cursor_input(experiment_type: str, value: float) -> str:
    """Compact display text while retaining useful sub-sample precision."""

    minimum_decimals = 3 if experiment_type == "LSV" else 1
    text = f"{float(value):.9f}".rstrip("0").rstrip(".")
    if "." not in text:
        return f"{text}.{'0' * minimum_decimals}"
    integer, decimals = text.split(".", 1)
    return f"{integer}.{decimals.ljust(minimum_decimals, '0')}"


def step_cursor_on_axis(
    axis: np.ndarray,
    current_x: float | None,
    direction: int,
) -> float:
    """Move to a real neighboring sample, clamping silently at boundaries."""

    if direction not in {-1, 1}:
        raise ValueError("direction must be -1 or 1")
    values = np.asarray(axis, dtype=np.float64)
    if values.ndim != 1 or len(values) == 0:
        raise ValueError("cursor axis must be a non-empty one-dimensional array")
    if not np.all(np.isfinite(values)) or (len(values) > 1 and not np.all(np.diff(values) > 0)):
        raise ValueError("cursor axis must contain finite, strictly increasing values")

    if current_x is None or not np.isfinite(current_x):
        return float(values[0] if direction > 0 else values[-1])

    if len(values) == 1:
        return float(values[0])
    tolerance = max(1e-12, float(np.min(np.diff(values))) * 1e-5)
    exact = np.flatnonzero(np.isclose(values, current_x, rtol=0.0, atol=tolerance))
    if exact.size:
        current_index = int(exact[np.argmin(np.abs(values[exact] - current_x))])
        target_index = current_index + direction
    elif direction < 0:
        target_index = int(np.searchsorted(values, current_x, side="left")) - 1
    else:
        target_index = int(np.searchsorted(values, current_x, side="right"))
    return float(values[min(max(target_index, 0), len(values) - 1)])


def read_cursor_value(record: FileRecord, requested_x: float) -> CursorReading:
    """Read one parsed curve without altering parser arrays or analysis settings."""

    if not record.parse_success or record.data is None:
        raise ValueError("只有解析成功的文件可以读取游标值。")
    requested = float(requested_x)
    if not np.isfinite(requested):
        raise ValueError("游标位置必须是有限数值。")

    if isinstance(record.data, LSVData):
        selected = extract_current_at_potential(record.data, requested)
        actual = selected.lower_potential_V if not selected.interpolated else None
        return CursorReading(
            record_key=record.key,
            file_name=record.path.name,
            experiment_type="LSV",
            requested_x=requested,
            actual_sampled_x=actual,
            current_A=selected.current_A,
            interpolated=selected.interpolated,
            lower_x=selected.lower_potential_V,
            upper_x=selected.upper_potential_V,
        )

    if isinstance(record.data, ITData):
        time = record.data.time_s
        if len(time) == 0:
            raise ValueError("i-t 时间轴为空。")
        if requested < float(time[0]) or requested > float(time[-1]):
            raise PotentialOutOfRangeError(
                f"Requested time {requested:.12g} s is outside the recorded range "
                f"[{time[0]:.12g}, {time[-1]:.12g}] s."
            )
        upper = int(np.searchsorted(time, requested, side="left"))
        if upper == 0:
            index = 0
        elif upper == len(time):
            index = len(time) - 1
        else:
            lower = upper - 1
            index = (
                lower
                if requested - float(time[lower]) <= float(time[upper]) - requested
                else upper
            )
        actual = float(time[index])
        return CursorReading(
            record_key=record.key,
            file_name=record.path.name,
            experiment_type="i-t",
            requested_x=requested,
            actual_sampled_x=actual,
            current_A=float(record.data.current_A[index]),
            interpolated=False,
            lower_x=actual,
            upper_x=actual,
        )

    raise ValueError(f"当前游标不支持实验类型：{record.experiment_type}")


def build_cursor_readings(
    records: Iterable[FileRecord],
    collection: PreviewCollection,
    requested_x: float,
) -> CursorReadingSet:
    """Read every visible preview curve; one unavailable curve does not abort others."""

    records_by_key = {record.key: record for record in records}
    readings: list[CursorReading] = []
    for curve in collection.visible_curves:
        record = records_by_key[curve.record_key]
        try:
            readings.append(read_cursor_value(record, requested_x))
        except (PotentialOutOfRangeError, ValueError) as error:
            readings.append(
                CursorReading(
                    record_key=record.key,
                    file_name=record.path.name,
                    experiment_type=collection.experiment_type,
                    requested_x=float(requested_x),
                    actual_sampled_x=None,
                    current_A=None,
                    interpolated=False,
                    error=str(error),
                )
            )
    return CursorReadingSet(
        experiment_type=collection.experiment_type,
        requested_x=float(requested_x),
        readings=tuple(readings),
    )


__all__ = [
    "CursorReading",
    "CursorReadingSet",
    "InspectionCursorState",
    "build_cursor_readings",
    "format_cursor_input",
    "parse_cursor_input",
    "read_cursor_value",
    "step_cursor_on_axis",
]
