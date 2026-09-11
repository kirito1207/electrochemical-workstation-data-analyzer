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
        "manifest": {
            "user_confirmed": result.manifest.user_confirmed,
            "source": result.manifest.source,
            "template_name": result.manifest.template_name,
        },
        "statistical_methods": {
            "overall_primary_test": "One-way Welch ANOVA using all Material Groups",
            "overall_sensitivity_test": "Kruskal-Wallis using all Material Groups",
            "primary_test": "Welch independent-samples t-test",
            "sensitivity_test": "Mann-Whitney U, two-sided",
            "multiple_comparison": (
                "Holm adjustment only within explicitly declared primary families"
            ),
            "effect_size": "Hedges' g with percentile bootstrap 95% CI",
            "mean_difference_ci": "percentile bootstrap 95% CI",
            "outliers": result.settings.outlier_method,
            "exclusions": "All data included",
        },
        "omnibus_tests": [asdict(item) for item in result.omnibus_tests],
        "current_sign_qc": [asdict(item) for item in result.current_sign_qc],
        "warnings": list(result.warnings),
        "source_files": [
            {
                "file_name": item.manifest.file_name,
                "relative_path": item.manifest.relative_path,
                "source_sha256": item.data.source_sha256,
                "group": item.manifest.group,
                "electrode_type": item.manifest.electrode_type,
                "sample_id": item.manifest.sample_id,
                "file_path": item.manifest.file_path,
            }
            for item in result.files
        ],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
