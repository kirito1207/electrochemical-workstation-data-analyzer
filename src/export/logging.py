"""Analysis provenance log."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from analysis.lsv_analysis import LSVAnalysisResult


def export_analysis_settings(result: LSVAnalysisResult, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "settings": asdict(result.settings),
        "statistical_methods": {
            "primary_test": "Welch independent-samples t-test",
            "sensitivity_test": "Mann-Whitney U, two-sided",
            "multiple_comparison": "Holm adjustment for A-B and B-C Welch p values",
            "effect_size": "Hedges' g with percentile bootstrap 95% CI",
            "mean_difference_ci": "percentile bootstrap 95% CI",
            "outliers": result.settings.outlier_method,
            "exclusions": "All data included",
        },
        "source_files": [
            {
                "file_name": item.manifest.file_name,
                "relative_path": item.manifest.relative_path,
                "source_sha256": item.data.source_sha256,
                "group": item.manifest.group,
                "electrode_type": item.manifest.electrode_type,
                "sample_id": item.manifest.sample_id,
            }
            for item in result.files
        ],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
