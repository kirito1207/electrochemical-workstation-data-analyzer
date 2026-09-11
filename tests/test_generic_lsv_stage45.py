from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from analysis import (
    CURRENT_PB_42_TEMPLATE,
    AnalysisSettings,
    ComparisonDefinition,
    ExperimentManifest,
    ManifestEntry,
    MetadataResolutionError,
    analyze_lsv_files,
    analyze_lsv_with_manifest,
    compare_defined_groups,
    confirmed_generic_manifest,
    infer_current_pb42_manifest,
    run_lsv_analysis_with_manifest,
    suggest_generic_manifest,
    validate_current_pb42_design,
)


def _shifted_copy(source: Path, target: Path, shift_uA: float) -> None:
    raw = bytearray(source.read_bytes())
    current = np.frombuffer(raw, dtype="<f4", count=400, offset=1453).copy()
    current += shift_uA * 1e-6
    raw[1453:] = current.astype("<f4").tobytes()
    target.write_bytes(raw)


def _manifest(
    tmp_path: Path,
    lsv_path: Path,
    group_sizes: dict[str, int],
    *,
    include_bare: bool = False,
    confirmed: bool = True,
) -> ExperimentManifest:
    entries = []
    index = 0
    for group_index, (group, size) in enumerate(group_sizes.items()):
        for sample_index in range(size):
            index += 1
            path = tmp_path / f"arbitrary_{index}.bin"
            _shifted_copy(lsv_path, path, group_index * 0.25 + sample_index * 0.02)
            entries.append(
                ManifestEntry(
                    file_name=path.name,
                    relative_path=path.name,
                    group=group,
                    electrode_type="Material",
                    sample_id=f"{group}-custom-{sample_index + 1}",
                    notes="user edited and confirmed",
                    file_path=str(path),
                )
            )
        if include_bare:
            index += 1
            path = tmp_path / f"arbitrary_{index}.bin"
            _shifted_copy(lsv_path, path, 20.0)
            entries.append(
                ManifestEntry(
                    file_name=path.name,
                    relative_path=path.name,
                    group=group,
                    electrode_type="Bare",
                    sample_id=f"{group}-bare-reference",
                    file_path=str(path),
                )
            )
    return ExperimentManifest(
        entries=tuple(entries),
        user_confirmed=confirmed,
        source="GUI metadata table confirmation",
    )


def _settings(target: float = 0.0) -> AnalysisSettings:
    return AnalysisSettings(
        target_potential_V=target,
        analysis_metric="magnitude",
        analysis_timestamp="2026-09-10T18:00:00+00:00",
        bootstrap_seed=2468,
        bootstrap_resamples=5000,
    )


def test_generic_two_groups_with_three_material_each(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"Control": 3, "PB10": 3})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert result.groups == ("Control", "PB10")
    assert result.summary("Control", "magnitude").statistics.n == 3
    assert result.summary("PB10", "signed").statistics.n == 3


def test_generic_three_groups_may_have_different_material_counts(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"G1": 2, "G2": 3, "G3": 4})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert [result.summary(group, "magnitude").statistics.n for group in result.groups] == [2, 3, 4]


def test_generic_mode_allows_no_bare_electrodes(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"Control": 3, "Treatment": 3})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert all(item.manifest.electrode_type == "Material" for item in result.files)


def test_bare_is_retained_but_excluded_from_material_statistics(tmp_path, lsv_path):
    manifest = _manifest(
        tmp_path, lsv_path, {"Control": 3, "Treatment": 3}, include_bare=True
    )
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert len(result.files) == 8
    assert result.summary("Control", "magnitude").statistics.n == 3
    assert result.summary("Treatment", "magnitude").statistics.n == 3


def test_arbitrary_group_names_are_preserved(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"未处理对照": 2, "PB-新配方": 3})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert result.groups == ("未处理对照", "PB-新配方")


def test_arbitrary_sample_ids_are_preserved(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"G1": 2})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert [item.manifest.sample_id for item in result.files] == ["G1-custom-1", "G1-custom-2"]


def test_confirmed_manifest_constructor_records_provenance(tmp_path, lsv_path):
    draft = _manifest(tmp_path, lsv_path, {"G1": 2}, confirmed=False)
    confirmed = confirmed_generic_manifest(draft.entries, source="reviewed by researcher")

    assert confirmed.user_confirmed
    assert confirmed.source == "reviewed by researcher"


def test_unconfirmed_manifest_is_rejected_before_formal_analysis(tmp_path, lsv_path):
    draft = _manifest(tmp_path, lsv_path, {"G1": 2}, confirmed=False)

    with pytest.raises(MetadataResolutionError, match="user_confirmed=True"):
        analyze_lsv_with_manifest(draft, settings=_settings())


def test_automatic_metadata_is_only_an_unconfirmed_suggestion(tmp_path, lsv_path):
    path = tmp_path / "LSV-PB-10圈-100uMROS-S2.bin"
    _shifted_copy(lsv_path, path, 0.0)
    suggested = suggest_generic_manifest([path], root=tmp_path)

    assert not suggested.user_confirmed
    assert suggested.entries[0].electrode_type == "Material"
    assert suggested.entries[0].sample_id == "S2"
    with pytest.raises(MetadataResolutionError, match="user_confirmed=True"):
        analyze_lsv_with_manifest(suggested, settings=_settings())


def test_only_user_declared_comparisons_are_run(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"Control": 3, "PB10": 3, "PB20": 3})
    definition = ComparisonDefinition(
        "Control", "PB10", "primary: prespecified treatment comparison", "efficacy"
    )
    result = analyze_lsv_with_manifest(
        manifest, comparisons=(definition,), settings=_settings()
    )

    assert {item.comparison for item in result.comparisons} == {"Control-PB10"}
    assert len(result.comparisons) == 2


def test_holm_adjustment_is_scoped_to_declared_primary_family():
    values = {
        "G1": np.linspace(1.0, 2.0, 6),
        "G2": np.linspace(1.2, 2.2, 6),
        "G3": np.linspace(1.8, 2.8, 6),
        "G4": np.linspace(2.5, 3.5, 6),
    }
    definitions = (
        ComparisonDefinition("G1", "G2", "primary", "family_alpha"),
        ComparisonDefinition("G2", "G3", "primary", "family_alpha"),
        ComparisonDefinition("G3", "G4", "primary", "family_beta"),
    )
    results = compare_defined_groups(values, definitions, bootstrap_seed=90, bootstrap_resamples=5000)
    welch = [item for item in results if item.test.startswith("Welch")]

    alpha = [item for item in welch if item.holm_family == "family_alpha"]
    beta = [item for item in welch if item.holm_family == "family_beta"]
    assert len(alpha) == 2 and all(item.holm_adjusted_p >= item.raw_p for item in alpha)
    assert len(beta) == 1 and beta[0].holm_adjusted_p == pytest.approx(beta[0].raw_p)


def test_target_potential_remains_configurable(tmp_path, lsv_path):
    result = analyze_lsv_with_manifest(
        _manifest(tmp_path, lsv_path, {"G1": 2}), settings=_settings(-0.05)
    )

    assert result.settings.target_potential_V == -0.05
    assert all(item.selected.target_potential_V == -0.05 for item in result.files)


def test_non_grid_target_still_uses_linear_interpolation(tmp_path, lsv_path):
    result = analyze_lsv_with_manifest(
        _manifest(tmp_path, lsv_path, {"G1": 2}), settings=_settings(0.0255)
    )

    assert all(item.selected.interpolated for item in result.files)
    assert all(item.selected.lower_potential_V < 0.0255 < item.selected.upper_potential_V for item in result.files)

    from plotting.common import potential_label

    assert potential_label(0.0255) == "0.0255"
    assert potential_label(-0.05) == "-0.050"


def test_generic_sign_qc_covers_each_group_and_all_material(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"Control": 3, "PB10": 4})
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert [item.group for item in result.current_sign_qc] == ["Control", "PB10", "ALL"]
    assert [item.total_count for item in result.current_sign_qc] == [3, 4, 7]


def test_generic_mad_flags_without_removing_material(tmp_path, lsv_path):
    manifest = _manifest(tmp_path, lsv_path, {"G1": 5})
    entries = list(manifest.entries)
    outlier_path = Path(entries[-1].file_path or "")
    _shifted_copy(lsv_path, outlier_path, 10.0)
    result = analyze_lsv_with_manifest(manifest, settings=_settings())

    assert result.summary("G1", "magnitude").statistics.n == 5
    assert len(result.files) == 5
    assert len(result.outlier_flags) == 1
    assert result.outlier_flags[0].status == "Possible outlier"


def test_pb42_template_keeps_strict_design_and_comparisons(synthetic_study_root):
    paths = sorted(synthetic_study_root.rglob("*.bin"))
    manifest = infer_current_pb42_manifest(paths, root=synthetic_study_root)
    validate_current_pb42_design(manifest)

    assert manifest.template_name == CURRENT_PB_42_TEMPLATE.name
    assert CURRENT_PB_42_TEMPLATE.group_order == ("A", "B", "C")
    assert [item.comparison_name for item in CURRENT_PB_42_TEMPLATE.comparisons] == [
        "A-B", "B-C", "A-C"
    ]


def test_pb42_zero_volt_regression_matches_pre_stage45_snapshot(synthetic_study_root):
    result = analyze_lsv_files(
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

    expected_means = {
        "A": 0.06911415631258513,
        "B": 0.08732201396154639,
        "C": 0.23683510837949703,
    }
    for group, expected in expected_means.items():
        assert result.summary(group, "magnitude").statistics.mean == pytest.approx(expected)
    welch = [item for item in result.comparisons if item.test.startswith("Welch")]
    assert [item.comparison for item in welch] == ["A-B", "B-C", "A-C"]
    assert [item.raw_p for item in welch] == pytest.approx(
        [0.40055453912991107, 8.551421299961716e-07, 5.357329647619794e-08]
    )
    assert [item.holm_adjusted_p for item in welch[:2]] == pytest.approx(
        [0.40055453912991107, 1.7102842599923433e-06]
    )
    assert len(result.files) == 42
    selected_payload = "\n".join(
        (
            f"{item.manifest.relative_path}|{item.manifest.group}|{item.manifest.sample_id}|"
            f"{item.selected.current_A.hex()}|"
            f"{item.selected.response_magnitude_uA.hex()}|{item.selected.interpolated}"
        )
        for item in result.files
    )
    assert hashlib.sha256(selected_payload.encode()).hexdigest() == (
        "088610ab1736411c441fdf8b3cc2199160f7a30058d2939ace328450d3482fc8"
    )
    assert len(result.outlier_flags) == 0
    assert [(item.group, item.negative_count, item.positive_count) for item in result.current_sign_qc] == [
        ("A", 11, 2), ("B", 1, 12), ("C", 0, 13), ("ALL", 12, 27)
    ]


def test_comparison_rejects_groups_with_insufficient_observations():
    with pytest.raises(ValueError, match="at least two"):
        compare_defined_groups(
            {"G1": [1.0], "G2": [2.0, 3.0]},
            (ComparisonDefinition("G1", "G2", "primary", "family"),),
            bootstrap_resamples=5000,
        )


def test_generic_confirmed_manifest_runs_traceable_exports_and_figures(tmp_path, lsv_path):
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    manifest = _manifest(input_dir, lsv_path, {"Control group": 3, "PB/10": 3})
    comparison = ComparisonDefinition(
        "Control group", "PB/10", "primary: user declared", "primary_family"
    )
    run = run_lsv_analysis_with_manifest(
        manifest,
        comparisons=(comparison,),
        output_base=tmp_path / "results",
        settings=_settings(-0.05),
    )

    assert len(run.generated_files) == 40
    assert any(path.name == "omnibus_statistics.csv" for path in run.generated_files)
    assert all(path.exists() and path.stat().st_size > 0 for path in run.generated_files)
    assert (run.output_directory / "LSV" / "excel" / "LSV_analysis.xlsx").exists()
    assert list((run.output_directory / "LSV" / "raw_curves").glob("group_PB_10_raw_lsv.*"))
