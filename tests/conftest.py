from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "sample_data"
LSV_NAME = "LSV-裸-100uMROS-L1.bin"
IT_NAME = "玻碳2-AuNPs-PB-5,10,20,40,80uMROS-ph6.5.bin"


@pytest.fixture(scope="session")
def lsv_path() -> Path:
    return SAMPLE_DIR / LSV_NAME


@pytest.fixture(scope="session")
def it_path() -> Path:
    return SAMPLE_DIR / IT_NAME


@pytest.fixture(scope="session")
def synthetic_study_root(tmp_path_factory, lsv_path) -> Path:
    """Build 42 temporary valid files; formal research files are never test fixtures."""

    root = tmp_path_factory.mktemp("synthetic-lsv-study")
    groups = {
        "A": ("2026.9.4 水溶剂", "10圈", 0.0),
        "B": ("2026.9.9 PBS7.4", "10圈", 0.15),
        "C": ("2026.9.5 PBS7.4", "20圈", 0.30),
    }
    sample_ids = ("S2", "S3", "S4", "S5", "S6", "S8", "S9", "S11", "S12", "S13", "Z2", "Z3", "Z4")
    source = lsv_path.read_bytes()
    for group_index, (_group, (folder_name, cycles, group_shift_uA)) in enumerate(groups.items()):
        folder = root / folder_name
        folder.mkdir()
        for index, sample_id in enumerate(sample_ids):
            raw = bytearray(source)
            current = np.frombuffer(raw, dtype="<f4", count=400, offset=1453).copy()
            current += (group_shift_uA + index * 0.015) * 1e-6
            raw[1453:] = current.astype("<f4").tobytes()
            (folder / f"LSV-PB-{cycles}-100uMROS-{sample_id}.bin").write_bytes(raw)
        (folder / "LSV-裸-100uMROS-L1.bin").write_bytes(source)
    return root


@pytest.fixture(scope="session")
def synthetic_analysis_result(synthetic_study_root):
    from analysis import AnalysisSettings, analyze_lsv_files

    return analyze_lsv_files(
        sorted(synthetic_study_root.rglob("*.bin")),
        root=synthetic_study_root,
        settings=AnalysisSettings(
            target_potential_V=0.0,
            analysis_metric="magnitude",
            analysis_timestamp="2026-09-10T12:00:00+00:00",
            bootstrap_seed=12345,
            bootstrap_resamples=5000,
        ),
    )
