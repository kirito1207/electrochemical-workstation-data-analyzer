"""Structured diagnostics and public parser exceptions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class DiagnosticReport:
    """Machine-readable details collected while parsing a CHI file."""

    file_name: str
    file_size: int
    detected_experiment_text: str | None = None
    point_count_candidates: list[dict[str, Any]] = field(default_factory=list)
    selected_n_points: int | None = None
    data_start_candidate: int | None = None
    parameter_values: dict[str, Any] = field(default_factory=dict)
    validation_checks: dict[str, bool] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    header_hex_preview: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Return a serialization-friendly copy of the diagnostic report."""

        return asdict(self)


class CHIParserError(ValueError):
    """Base class for expected CHI parsing failures."""

    def __init__(self, message: str, diagnostic: DiagnosticReport):
        super().__init__(message)
        self.diagnostic = diagnostic


class UnsupportedExperimentError(CHIParserError):
    """Raised when the detected technique is not supported by parser v0.1."""


class InvalidCHIFileError(CHIParserError):
    """Raised when the file does not satisfy the validated CHI structure."""


class PointCountError(InvalidCHIFileError):
    """Raised when no valid, repeated point-count field can be selected."""


class AmbiguousPointCountError(PointCountError):
    """Raised when more than one point-count candidate remains valid."""


class DataValidationError(InvalidCHIFileError):
    """Raised when parsed numerical data fails integrity checks."""


def new_diagnostic(file_name: str, raw: bytes) -> DiagnosticReport:
    """Create a diagnostic report without exposing the complete binary file."""

    preview = raw[:64].hex(" ")
    return DiagnosticReport(
        file_name=file_name,
        file_size=len(raw),
        header_hex_preview=preview,
    )


def fail(
    error_type: type[CHIParserError],
    message: str,
    diagnostic: DiagnosticReport,
) -> None:
    """Record and raise a structured parser error."""

    diagnostic.errors.append(message)
    raise error_type(message, diagnostic)

