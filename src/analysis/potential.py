"""Exact or linearly interpolated LSV current extraction at a chosen potential."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from chi_parser import LSVData


class PotentialOutOfRangeError(ValueError):
    """Raised when extraction would require forbidden extrapolation."""


@dataclass(frozen=True, slots=True)
class CurrentAtPotential:
    source_file: str
    source_path: str
    target_potential_V: float
    current_A: float
    current_uA: float
    response_magnitude_uA: float
    interpolated: bool
    lower_potential_V: float
    upper_potential_V: float

    @property
    def signed_current_A(self) -> float:
        return self.current_A

    @property
    def signed_current_uA(self) -> float:
        return self.current_uA


def extract_current_at_potential(
    data: LSVData,
    target_potential_V: float = 0.0,
    *,
    absolute_tolerance_V: float | None = None,
) -> CurrentAtPotential:
    """Extract current without extrapolation or nearest-point substitution."""

    potential = data.potential_V
    current = data.current_A
    if len(potential) < 2 or not np.all(np.diff(potential) > 0):
        raise ValueError("LSV potential axis must contain at least two increasing points.")
    minimum_step = float(np.min(np.diff(potential)))
    tolerance = (
        float(absolute_tolerance_V)
        if absolute_tolerance_V is not None
        else max(1e-10, minimum_step * 1e-5)
    )
    target = float(target_potential_V)
    if target < potential[0] - tolerance or target > potential[-1] + tolerance:
        raise PotentialOutOfRangeError(
            f"Target potential {target:.12g} V is outside the recorded range "
            f"[{potential[0]:.12g}, {potential[-1]:.12g}] V; extrapolation is not allowed."
        )

    exact = np.flatnonzero(np.isclose(potential, target, rtol=0.0, atol=tolerance))
    if exact.size:
        index = int(exact[np.argmin(np.abs(potential[exact] - target))])
        value = float(current[index])
        lower = upper = float(potential[index])
        interpolated = False
    else:
        upper_index = int(np.searchsorted(potential, target, side="right"))
        if upper_index <= 0 or upper_index >= len(potential):
            raise PotentialOutOfRangeError(
                f"Target potential {target:.12g} V cannot be bracketed without extrapolation."
            )
        lower_index = upper_index - 1
        lower = float(potential[lower_index])
        upper = float(potential[upper_index])
        fraction = (target - lower) / (upper - lower)
        value = float(current[lower_index] + fraction * (current[upper_index] - current[lower_index]))
        interpolated = True

    current_uA = value * 1e6
    return CurrentAtPotential(
        source_file=data.file_name,
        source_path=str(data.file_path),
        target_potential_V=target,
        current_A=value,
        current_uA=current_uA,
        response_magnitude_uA=abs(current_uA),
        interpolated=interpolated,
        lower_potential_V=lower,
        upper_potential_V=upper,
    )
