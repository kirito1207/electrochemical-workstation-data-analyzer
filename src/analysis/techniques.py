"""Small routing contract for future technique-specific GUI pages."""

from __future__ import annotations

from dataclasses import dataclass


class TechniqueRoutingError(ValueError):
    """Raised when no implemented analysis route exists for an experiment."""


@dataclass(frozen=True, slots=True)
class TechniqueRoute:
    experiment_type: str
    analysis_module: str


_IMPLEMENTED_ROUTES = {
    "LSV": TechniqueRoute("LSV", "analysis.lsv_analysis"),
    "i-t": TechniqueRoute("i-t", "analysis.it_analysis"),
}
_FUTURE_TECHNIQUES = {"CV", "CA"}


def route_for_experiment_type(experiment_type: str) -> TechniqueRoute:
    """Return an implemented route; never coerce CV/CA into LSV analysis."""

    normalized = experiment_type.strip()
    if normalized in _IMPLEMENTED_ROUTES:
        return _IMPLEMENTED_ROUTES[normalized]
    if normalized.upper() in _FUTURE_TECHNIQUES:
        raise TechniqueRoutingError(
            f"{normalized.upper()} requires technique-specific parsing and analysis; "
            "it must not be routed through LSV assumptions."
        )
    raise TechniqueRoutingError(f"Unsupported experiment type: {experiment_type!r}")


__all__ = ["TechniqueRoute", "TechniqueRoutingError", "route_for_experiment_type"]
