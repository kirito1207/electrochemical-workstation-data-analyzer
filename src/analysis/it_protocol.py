"""User-confirmed concentration and addition-time protocols for i-t analysis."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path


class StepProtocolError(ValueError):
    """Raised when user metadata cannot define valid i-t intervals."""


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "included"}:
        return True
    if normalized in {"0", "false", "no", "n", "excluded"}:
        return False
    raise StepProtocolError(f"Invalid include_in_calibration value: {value!r}")


@dataclass(frozen=True, slots=True)
class StepDefinition:
    step_id: str
    concentration_uM: float
    addition_time_s: float
    include_in_calibration: bool = True
    notes: str = ""


@dataclass(frozen=True, slots=True)
class StepProtocol:
    steps: tuple[StepDefinition, ...]
    user_confirmed: bool
    source: str = "Python API"

    def validate(
        self,
        *,
        recording_start_s: float,
        recording_end_s: float,
        time_tolerance_s: float = 1e-9,
        require_confirmed: bool = True,
    ) -> None:
        errors: list[str] = []
        if require_confirmed and not self.user_confirmed:
            errors.append("Formal analysis requires StepProtocol.user_confirmed=True.")
        if len(self.steps) < 2:
            errors.append("At least a 0 µM baseline and one non-zero step are required.")
        ids = [step.step_id for step in self.steps]
        if any(not step_id.strip() for step_id in ids) or len(ids) != len(set(ids)):
            errors.append("step_id values must be non-empty and unique.")

        concentrations = [step.concentration_uM for step in self.steps]
        times = [step.addition_time_s for step in self.steps]
        if any(not math.isfinite(value) or value < 0.0 for value in concentrations):
            errors.append("concentration_uM values must be finite and non-negative.")
        if any(not math.isfinite(value) for value in times):
            errors.append("addition_time_s values must be finite.")
        if any(later <= earlier for earlier, later in zip(times, times[1:])):
            errors.append("addition_time_s values must be strictly increasing.")
        if times and (
            times[0] < recording_start_s - time_tolerance_s
            or times[-1] > recording_end_s + time_tolerance_s
        ):
            errors.append("All addition_time_s values must lie within the recorded time range.")
        if times and not math.isclose(
            times[0], recording_start_s, rel_tol=0.0, abs_tol=time_tolerance_s
        ):
            errors.append(
                "The baseline step must begin at the first recorded time point."
            )
        if concentrations and concentrations[0] != 0.0:
            errors.append("The first StepDefinition must be the 0 µM baseline.")
        if concentrations and not any(value > 0.0 for value in concentrations[1:]):
            errors.append("At least one non-zero concentration step is required.")
        if errors:
            raise StepProtocolError(" | ".join(errors))

    @property
    def included_concentrations_uM(self) -> tuple[float, ...]:
        return tuple(
            step.concentration_uM
            for step in self.steps
            if step.include_in_calibration
        )

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        user_confirmed: bool,
    ) -> "StepProtocol":
        source = Path(path)
        with source.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {
                "step_id",
                "concentration_uM",
                "addition_time_s",
                "include_in_calibration",
                "notes",
            }
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise StepProtocolError(
                    "Protocol CSV must contain: " + ", ".join(sorted(required))
                )
            steps = tuple(
                StepDefinition(
                    step_id=row["step_id"].strip(),
                    concentration_uM=float(row["concentration_uM"]),
                    addition_time_s=float(row["addition_time_s"]),
                    include_in_calibration=_parse_bool(row["include_in_calibration"]),
                    notes=row["notes"].strip(),
                )
                for row in reader
            )
        return cls(steps=steps, user_confirmed=user_confirmed, source=str(source))


__all__ = ["StepDefinition", "StepProtocol", "StepProtocolError"]
