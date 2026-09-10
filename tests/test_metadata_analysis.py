from __future__ import annotations

from pathlib import Path

import pytest

from analysis import MetadataResolutionError, infer_experiment_manifest


def test_manifest_confirms_three_groups_and_electrode_counts(synthetic_study_root):
    manifest = infer_experiment_manifest(
        sorted(synthetic_study_root.rglob("*.bin")), root=synthetic_study_root
    )

    assert manifest.is_valid
    assert len(manifest.entries) == 42
    for group in "ABC":
        rows = [item for item in manifest.entries if item.group == group]
        assert len([item for item in rows if item.electrode_type == "Bare"]) == 1
        assert len([item for item in rows if item.electrode_type == "Material"]) == 13


def test_bare_inherits_only_a_uniquely_confirmed_parent_group(synthetic_study_root):
    manifest = infer_experiment_manifest(
        sorted(synthetic_study_root.rglob("*.bin")), root=synthetic_study_root
    )
    bare = [item for item in manifest.entries if item.electrode_type == "Bare"]

    assert {item.group for item in bare} == {"A", "B", "C"}


def test_unresolved_metadata_blocks_analysis(tmp_path):
    path = tmp_path / "unknown.bin"
    path.write_bytes(b"")
    manifest = infer_experiment_manifest([path], root=tmp_path)

    assert not manifest.is_valid
    with pytest.raises(MetadataResolutionError, match="Metadata unresolved"):
        manifest.require_valid()
