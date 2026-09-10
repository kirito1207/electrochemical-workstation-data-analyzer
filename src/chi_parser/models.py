"""Typed parser outputs designed for later analysis and plotting layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from .diagnostics import DiagnosticReport


FloatArray = NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class UserMetadata:
    """Optional user-assigned metadata, kept separate from CHI metadata."""

    group: str | None = None
    electrode_type: str | None = None
    sample_id: str | None = None
    notes: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LSVData:
    """Validated raw Linear Sweep Voltammetry data."""

    file_name: str
    file_path: Path
    file_size_bytes: int
    source_sha256: str
    experiment_type: str
    n_points: int
    configured_start_potential_V: float
    configured_final_potential_V: float
    actual_first_potential_V: float
    actual_last_potential_V: float
    scan_rate_V_s: float
    potential_increment_V: float
    potential_V: FloatArray
    current_A: FloatArray
    data_start_byte: int
    current_encoding: str
    validation_status: str
    warnings: tuple[str, ...]
    diagnostics: DiagnosticReport
    user_metadata: UserMetadata | None = None

    def __post_init__(self) -> None:
        self.potential_V.setflags(write=False)
        self.current_A.setflags(write=False)


@dataclass(frozen=True, slots=True)
class ITData:
    """Validated raw Amperometric i-t data."""

    file_name: str
    file_path: Path
    file_size_bytes: int
    source_sha256: str
    experiment_type: str
    n_points: int
    sample_interval_s: float
    configured_run_time_s: float
    actual_first_time_s: float
    actual_last_time_s: float
    actual_recorded_duration_s: float
    applied_potential_V: float
    time_s: FloatArray
    current_A: FloatArray
    data_start_byte: int
    current_encoding: str
    validation_status: str
    warnings: tuple[str, ...]
    diagnostics: DiagnosticReport
    user_metadata: UserMetadata | None = None

    def __post_init__(self) -> None:
        self.time_s.setflags(write=False)
        self.current_A.setflags(write=False)


ExperimentData = LSVData | ITData

