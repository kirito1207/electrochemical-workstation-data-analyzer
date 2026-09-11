"""Export a completed, non-stale GUI LSV result without rerunning analysis."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from analysis.lsv_analysis import AnalysisRun, LSVAnalysisResult, _allocate_output_directory
from export.csv import export_csv_bundle
from export.excel import export_analysis_workbook
from export.logging import export_analysis_settings
from plotting.lsv_mean import plot_mean_lsv
from plotting.lsv_raw import plot_raw_lsv
from plotting.repeatability import plot_repeatability
from plotting.selected_potential import plot_selected_potential

from .lsv_workflow import LSVWorkflowState


def export_lsv_result(result: LSVAnalysisResult, output_base: str | Path) -> AnalysisRun:
    """Export exactly *result* into a fresh timestamped directory."""

    output = _allocate_output_directory(
        Path(output_base), result.settings.analysis_timestamp or ""
    )
    generated: list[Path] = []
    generated.extend(export_csv_bundle(result, output / "LSV" / "csv"))
    generated.append(
        export_analysis_workbook(result, output / "LSV" / "excel" / "LSV_analysis.xlsx")
    )
    generated.append(
        export_analysis_settings(result, output / "LSV" / "logs" / "analysis_settings.json")
    )
    generated.extend(plot_raw_lsv(result, output / "LSV" / "raw_curves"))
    generated.extend(plot_mean_lsv(result, output / "LSV" / "mean_curves"))
    generated.extend(plot_selected_potential(result, output / "LSV" / "selected_potential"))
    generated.extend(plot_repeatability(result, output / "LSV" / "repeatability"))
    return AnalysisRun(result=result, output_directory=output, generated_files=tuple(generated))


def open_output_directory(path: str | Path) -> None:
    """Open a result directory with the host platform's normal file manager."""

    directory = Path(path)
    if not directory.is_dir():
        raise FileNotFoundError(directory)
    if sys.platform == "win32":
        os.startfile(str(directory))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(("open", str(directory)))
    else:
        subprocess.Popen(("xdg-open", str(directory)))


__all__ = ["export_lsv_result", "open_output_directory"]


def export_workflow_result(
    workflow: LSVWorkflowState, output_base: str | Path
) -> AnalysisRun:
    run = export_lsv_result(workflow.require_exportable_result(), output_base)
    workflow.last_export_directory = str(run.output_directory)
    return run


def open_output_directory(path: str | Path) -> None:
    """Open a directory with the platform shell; no Windows-only imports."""

    target = str(Path(path).resolve())
    if sys.platform == "win32":
        os.startfile(target)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(("open", target))
    else:
        subprocess.Popen(("xdg-open", target))


__all__ = ["export_lsv_result", "export_workflow_result", "open_output_directory"]
