from __future__ import annotations

from dataclasses import replace
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
    from analysis import AnalysisSettings
    from presets.pb42 import analyze_lsv_files

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


@pytest.fixture(scope="session")
def synthetic_it_data(it_path):
    from chi_parser import parse_it

    base = parse_it(it_path)
    time_s = np.arange(1.0, 121.0, dtype=np.float64)
    current_uA = np.select(
        [time_s < 31.0, time_s < 61.0, time_s < 91.0],
        [2.0, 1.0, -1.5],
        default=-4.5,
    )
    return replace(
        base,
        file_name="synthetic_it.bin",
        n_points=len(time_s),
        sample_interval_s=1.0,
        configured_run_time_s=120.0,
        actual_first_time_s=1.0,
        actual_last_time_s=120.0,
        actual_recorded_duration_s=120.0,
        time_s=time_s,
        current_A=np.asarray(current_uA * 1e-6, dtype=np.float64),
        validation_status="valid",
        warnings=(),
    )


@pytest.fixture(scope="session")
def synthetic_it_protocol():
    from analysis import StepDefinition, StepProtocol

    return StepProtocol(
        user_confirmed=True,
        source="synthetic test protocol",
        steps=(
            StepDefinition("baseline", 0.0, 1.0, True, "baseline"),
            StepDefinition("s1", 2.0, 31.0, True),
            StepDefinition("s2", 7.0, 61.0, True),
            StepDefinition("s3", 13.0, 91.0, False, "excluded linear-range point"),
        ),
    )


@pytest.fixture(scope="session")
def synthetic_it_result(synthetic_it_data, synthetic_it_protocol):
    from analysis import ITAnalysisSettings, analyze_it_data

    return analyze_it_data(
        synthetic_it_data,
        synthetic_it_protocol,
        sample_id="E1",
        settings=ITAnalysisSettings(
            analysis_metric="signed",
            analysis_timestamp="2026-09-10T17:00:00+00:00",
        ),
    )


@pytest.fixture(scope="session")
def synthetic_it_batch_result(it_path, synthetic_it_data, synthetic_it_protocol):
    from analysis import (
        ITAnalysisInput,
        ITAnalysisSettings,
        ITBatchAnalysisResult,
        analyze_it_data,
        evaluate_delta_direction,
        fit_group_mean_calibration,
        summarize_concentrations,
    )

    settings = ITAnalysisSettings(
        analysis_metric="signed",
        analysis_timestamp="2026-09-10T17:00:00+00:00",
    ).resolved()
    inputs = tuple(
        ITAnalysisInput(it_path, f"E{index}", synthetic_it_protocol)
        for index in range(1, 4)
    )
    files = []
    for index, scale in enumerate((0.9, 1.0, 1.1), start=1):
        data = replace(
            synthetic_it_data,
            file_name=f"synthetic_E{index}.bin",
            current_A=np.asarray(synthetic_it_data.current_A * scale, dtype=np.float64),
        )
        files.append(
            analyze_it_data(
                data,
                synthetic_it_protocol,
                sample_id=f"E{index}",
                settings=settings,
            )
        )
    all_delta = tuple(row for item in files for row in item.delta_i)
    summary = summarize_concentrations(all_delta)
    return ITBatchAnalysisResult(
        settings=settings,
        inputs=inputs,
        files=tuple(files),
        errors=(),
        concentration_summary=summary,
        group_mean_calibration=fit_group_mean_calibration(summary, analysis_metric="signed"),
        outlier_flags=(),
        current_direction_qc=evaluate_delta_direction(all_delta, analysis_metric="signed"),
        warnings=(),
    )
