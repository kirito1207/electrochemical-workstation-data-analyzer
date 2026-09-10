"""Strict CHI experiment-type detection."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .diagnostics import (
    DiagnosticReport,
    InvalidCHIFileError,
    UnsupportedExperimentError,
    fail,
)


CHI_MAGIC = b"\x80\xf2\x1c\x00"
MAX_EXPERIMENT_NAME_BYTES = 128
SUPPORTED_EXPERIMENTS = {
    ("LSV", "Linear Sweep Voltammetry"): "LSV",
    ("i-t", "Amperometric i-t Curve"): "i-t",
}


@dataclass(frozen=True, slots=True)
class DetectionResult:
    experiment_type: str
    short_name: str
    long_name: str
    header_prefix_end: int


def _read_ascii(raw: bytes, offset: int, length: int, diagnostic: DiagnosticReport) -> str:
    if length <= 0 or length > MAX_EXPERIMENT_NAME_BYTES:
        fail(
            InvalidCHIFileError,
            f"Invalid experiment-name length {length} at byte {offset - 4}.",
            diagnostic,
        )
    end = offset + length
    if end > len(raw):
        fail(InvalidCHIFileError, "File is truncated inside the experiment name.", diagnostic)
    try:
        value = raw[offset:end].decode("ascii")
    except UnicodeDecodeError:
        fail(InvalidCHIFileError, "Experiment name is not valid ASCII.", diagnostic)
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        fail(InvalidCHIFileError, "Experiment name contains non-printable bytes.", diagnostic)
    return value


def detect_experiment(raw: bytes, diagnostic: DiagnosticReport) -> DetectionResult:
    """Read the two length-prefixed experiment names and reject unknown techniques."""

    if len(raw) < 16:
        fail(InvalidCHIFileError, "File is too short to contain a CHI header.", diagnostic)
    if raw[:4] != CHI_MAGIC:
        fail(InvalidCHIFileError, "CHI header signature is not recognized.", diagnostic)

    short_length = struct.unpack_from("<I", raw, 4)[0]
    short_offset = 8
    short_name = _read_ascii(raw, short_offset, short_length, diagnostic)

    long_length_offset = short_offset + short_length
    if long_length_offset + 4 > len(raw):
        fail(InvalidCHIFileError, "File is truncated before the full experiment name.", diagnostic)
    long_length = struct.unpack_from("<I", raw, long_length_offset)[0]
    long_offset = long_length_offset + 4
    long_name = _read_ascii(raw, long_offset, long_length, diagnostic)

    diagnostic.detected_experiment_text = f"{short_name} / {long_name}"
    experiment_type = SUPPORTED_EXPERIMENTS.get((short_name, long_name))
    if experiment_type is None:
        fail(
            UnsupportedExperimentError,
            "当前版本仅支持 CHI760E LSV 和 i-t 数据。"
            f"检测到：{diagnostic.detected_experiment_text}",
            diagnostic,
        )

    diagnostic.validation_checks["experiment_type_supported"] = True
    return DetectionResult(
        experiment_type=experiment_type,
        short_name=short_name,
        long_name=long_name,
        header_prefix_end=long_offset + long_length,
    )

