"""Complete JSON provenance log for i-t analysis."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from analysis.it_analysis import ITBatchAnalysisResult


def export_it_analysis_log(result: ITBatchAnalysisResult, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": asdict(result.settings),
        "regression_method": "ordinary least squares",
        "lod": {
            "status": "LOD not calculated",
            "reason": "Insufficient independent blank replicates for a defined σ_blank method.",
        },
        "files": [
            {
                "source_file": item.data.file_name,
                "source_sha256": item.data.source_sha256,
                "sample_id": item.sample_id,
                "applied_potential_V": item.data.applied_potential_V,
                "sample_interval_s": item.data.sample_interval_s,
                "step_protocol": asdict(item.protocol),
                "confirmed_addition_times_s": [
                    step.addition_time_s for step in item.protocol.steps
                ],
                "concentrations_uM": [step.concentration_uM for step in item.protocol.steps],
                "actual_plateau_windows": [asdict(row) for row in item.plateaus],
                "calibration": asdict(item.calibration),
                "warnings": list(item.warnings),
            }
            for item in result.files
        ],
        "errors": [asdict(item) for item in result.errors],
        "concentration_summary": [asdict(item) for item in result.concentration_summary],
        "group_mean_calibration": asdict(result.group_mean_calibration)
        if result.group_mean_calibration is not None
        else None,
        "current_direction_qc": [asdict(item) for item in result.current_direction_qc],
        "outlier_flags": [asdict(item) for item in result.outlier_flags],
        "warnings": list(result.warnings),
        "exclusion_log": "All data included",
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


__all__ = ["export_it_analysis_log"]
