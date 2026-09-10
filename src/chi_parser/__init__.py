"""Public API for validated CHI760E parser v0.1."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from .detector import detect_experiment
from .diagnostics import (
    AmbiguousPointCountError,
    CHIParserError,
    DataValidationError,
    DiagnosticReport,
    InvalidCHIFileError,
    PointCountError,
    UnsupportedExperimentError,
    new_diagnostic,
)
from .it import _parse_it_bytes, parse_it
from .lsv import _parse_lsv_bytes, parse_lsv
from .models import ExperimentData, ITData, LSVData, UserMetadata

__all__ = [
    "AmbiguousPointCountError",
    "CHIParserError",
    "DataValidationError",
    "DiagnosticReport",
    "ExperimentData",
    "ITData",
    "InvalidCHIFileError",
    "LSVData",
    "PointCountError",
    "UnsupportedExperimentError",
    "UserMetadata",
    "parse_file",
    "parse_files",
    "parse_it",
    "parse_lsv",
]


def parse_file(path: str | Path) -> ExperimentData:
    """Detect and parse one supported CHI760E binary file."""

    file_path = Path(path)
    raw = file_path.read_bytes()
    diagnostic = new_diagnostic(file_path.name, raw)
    detection = detect_experiment(raw, diagnostic)
    if detection.experiment_type == "LSV":
        return _parse_lsv_bytes(file_path, raw, detection, diagnostic)
    return _parse_it_bytes(file_path, raw, detection, diagnostic)


def parse_files(paths: Iterable[str | Path]) -> list[ExperimentData]:
    """Parse multiple independent files without embedding grouping logic."""

    return [parse_file(path) for path in paths]

