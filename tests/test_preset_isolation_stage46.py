from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from analysis import TechniqueRoutingError, route_for_experiment_type


def _shifted_copy(source: Path, target: Path, shift_uA: float) -> None:
    raw = bytearray(source.read_bytes())
    current = np.frombuffer(raw, dtype="<f4", count=400, offset=1453).copy()
    current += shift_uA * 1e-6
    raw[1453:] = current.astype("<f4").tobytes()
    target.write_bytes(raw)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generic_full_run_succeeds_when_pb42_import_is_blocked(tmp_path, lsv_path):
    input_paths = []
    for group_index, group in enumerate(("Control", "Treatment")):
        for sample_index in range(3):
            path = tmp_path / f"{group}_{sample_index + 1}.bin"
            _shifted_copy(lsv_path, path, group_index * 0.2 + sample_index * 0.01)
            input_paths.append(path)
    hashes_before = {str(path): _sha256(path) for path in input_paths}

    script = r'''
import importlib.abc
import json
import os
from pathlib import Path
import sys

class BlockPB42(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in {"presets.pb42", "analysis.lsv_templates"}:
            raise ModuleNotFoundError(f"blocked optional preset: {fullname}")
        return None

sys.meta_path.insert(0, BlockPB42())
from analysis import (
    AnalysisSettings,
    ComparisonDefinition,
    ManifestEntry,
    confirmed_generic_manifest,
    run_lsv_analysis_with_manifest,
)
assert "presets.pb42" not in sys.modules

paths = [Path(value) for value in json.loads(os.environ["STAGE46_INPUT_PATHS"])]
entries = []
for index, path in enumerate(paths):
    group = "Control" if index < 3 else "Treatment"
    entries.append(
        ManifestEntry(
            file_name=path.name,
            relative_path=path.name,
            file_path=str(path),
            group=group,
            electrode_type="Material",
            sample_id=f"{group}-{index % 3 + 1}",
        )
    )
manifest = confirmed_generic_manifest(entries, source="Stage 4.6 isolation test")
run = run_lsv_analysis_with_manifest(
    manifest,
    comparisons=(
        ComparisonDefinition("Control", "Treatment", "primary", "declared_family"),
    ),
    output_base=os.environ["STAGE46_OUTPUT_BASE"],
    settings=AnalysisSettings(
        target_potential_V=0.0255,
        analysis_metric="magnitude",
        analysis_timestamp="2026-09-10T20:00:00+00:00",
        bootstrap_seed=4600,
        bootstrap_resamples=5000,
    ),
)
suffixes = {path.suffix for path in run.generated_files}
assert {".csv", ".xlsx", ".json", ".png", ".svg", ".pdf"} <= suffixes
assert all(item.selected.interpolated for item in run.result.files)
assert len(run.result.comparisons) == 2
assert "presets.pb42" not in sys.modules
print(json.dumps({"generated": len(run.generated_files), "groups": run.result.groups}))
'''
    env = os.environ.copy()
    env["STAGE46_INPUT_PATHS"] = json.dumps([str(path) for path in input_paths])
    env["STAGE46_OUTPUT_BASE"] = str(tmp_path / "results")
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    assert payload["groups"] == ["Control", "Treatment"]
    assert payload["generated"] > 0
    assert {str(path): _sha256(path) for path in input_paths} == hashes_before


def test_technique_routing_keeps_future_cv_and_ca_out_of_lsv():
    assert route_for_experiment_type("LSV").analysis_module == "analysis.lsv_analysis"
    assert route_for_experiment_type("i-t").analysis_module == "analysis.it_analysis"

    for future_type in ("CV", "CA"):
        with pytest.raises(TechniqueRoutingError, match="technique-specific"):
            route_for_experiment_type(future_type)
