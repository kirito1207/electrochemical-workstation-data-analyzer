"""Export one completed, non-stale Generic i-t Event GUI result."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt

from analysis.it_events import ITEventBatchResult
from export.figures import save_figure_formats
from export.it_events import export_it_event_csv_bundle
from plotting.it_events import (build_it_calibration_figure, build_it_event_figure,
                                build_it_response_figure)


@dataclass(frozen=True, slots=True)
class ITExportRun:
    result: ITEventBatchResult
    output_directory: Path
    generated_files: tuple[Path, ...]


def _new_output_directory(base: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    candidate = base / f"it_event_analysis_{stamp}"
    suffix = 1
    while candidate.exists():
        candidate = base / f"it_event_analysis_{stamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True)
    return candidate


def export_it_result(result: ITEventBatchResult, output_base: str | Path) -> ITExportRun:
    """Export exactly ``result`` without rerunning parsing or analysis."""

    output = _new_output_directory(Path(output_base))
    generated = list(export_it_event_csv_bundle(result, output / "i-t" / "csv"))
    figures = (
        ("raw_with_events", build_it_event_figure(result)),
        ("event_responses", build_it_response_figure(result)),
    )
    if result.calibration_selection is not None:
        figures += (("calibration", build_it_calibration_figure(result)),)
    try:
        for name, figure in figures:
            generated.extend(save_figure_formats(figure, output / "i-t" / "figures" / name))
    finally:
        for _name, figure in figures:
            plt.close(figure)
    return ITExportRun(result, output, tuple(generated))


__all__ = ["ITExportRun", "export_it_result"]
