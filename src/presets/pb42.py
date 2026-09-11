"""Optional preset for the validated 42-file PB/H2O2 LSV experiment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from analysis.lsv_analysis import (
    AnalysisRun,
    AnalysisSettings,
    LSVAnalysisResult,
    analyze_lsv_with_manifest,
    run_lsv_analysis_with_manifest,
)
from analysis.metadata import (
    ExperimentManifest,
    ManifestEntry,
    MetadataResolutionError,
)
from analysis.statistics import ComparisonDefinition


SAMPLE_ID_PATTERN = re.compile(r"-(S\d+|Z\d+|L\d+)\.bin$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class GroupDesign:
    group: str
    description: str
    expected_bare: int
    expected_material: int


@dataclass(frozen=True, slots=True)
class PB42ExperimentTemplate:
    name: str
    groups: tuple[GroupDesign, ...]
    comparisons: tuple[ComparisonDefinition, ...]

    @property
    def group_order(self) -> tuple[str, ...]:
        return tuple(item.group for item in self.groups)


CURRENT_PB_42_TEMPLATE = PB42ExperimentTemplate(
    name="CURRENT_PB_42_TEMPLATE",
    groups=(
        GroupDesign("A", "PB 10 cycles; water; 100 µM H2O2", 1, 13),
        GroupDesign("B", "PB 10 cycles; PBS; 100 µM H2O2", 1, 13),
        GroupDesign("C", "PB 20 cycles; PBS; 100 µM H2O2", 1, 13),
    ),
    comparisons=(
        ComparisonDefinition(
            left_group="A",
            right_group="B",
            role="primary: detection medium (water vs PBS), PB 10 cycles",
            holm_family="pb42_primary",
        ),
        ComparisonDefinition(
            left_group="B",
            right_group="C",
            role="primary: PB deposition cycles (10 vs 20), PBS",
            holm_family="pb42_primary",
        ),
        ComparisonDefinition(
            left_group="A",
            right_group="C",
            role="exploratory: medium and PB cycles both differ",
        ),
    ),
)


def _infer_group(text: str) -> str | None:
    matches: list[str] = []
    if "水" in text and "10圈" in text:
        matches.append("A")
    if "PBS" in text.upper() and "10圈" in text:
        matches.append("B")
    if "PBS" in text.upper() and "20圈" in text:
        matches.append("C")
    return matches[0] if len(matches) == 1 else None


def _infer_electrode_type(file_name: str) -> str | None:
    matches: list[str] = []
    if "裸" in file_name:
        matches.append("Bare")
    if "PB" in file_name.upper():
        matches.append("Material")
    return matches[0] if len(matches) == 1 else None


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def infer_current_pb42_manifest(
    paths: Iterable[str | Path], *, root: str | Path
) -> ExperimentManifest:
    """Infer A/B/C and Bare/Material, then enforce the PB42 design."""

    root_path = Path(root)
    path_objects = tuple(Path(supplied) for supplied in paths)
    relative_paths = tuple(_relative(path, root_path) for path in path_objects)
    folder_groups: dict[str, set[str]] = {}
    for relative_path in relative_paths:
        inferred = _infer_group(relative_path)
        if inferred is not None:
            folder_groups.setdefault(str(Path(relative_path).parent), set()).add(inferred)

    entries: list[ManifestEntry] = []
    errors: list[str] = []
    for path, relative_path in zip(path_objects, relative_paths, strict=True):
        group = _infer_group(relative_path)
        if group is None:
            inherited = folder_groups.get(str(Path(relative_path).parent), set())
            if len(inherited) == 1:
                group = next(iter(inherited))
        electrode_type = _infer_electrode_type(path.name)
        match = SAMPLE_ID_PATTERN.search(path.name)
        sample_id = match.group(1).upper() if match else None
        entries.append(
            ManifestEntry(
                file_name=path.name,
                relative_path=relative_path,
                group=group,
                electrode_type=electrode_type,  # type: ignore[arg-type]
                sample_id=sample_id,
                file_path=str(path),
            )
        )
        unresolved = [
            name
            for name, value in (
                ("group", group),
                ("electrode_type", electrode_type),
                ("sample_id", sample_id),
            )
            if value is None
        ]
        if unresolved:
            errors.append(f"{relative_path}: unresolved {', '.join(unresolved)}")

    if len(entries) != 42:
        errors.append(f"Expected 42 files, found {len(entries)}")
    for group in CURRENT_PB_42_TEMPLATE.group_order:
        group_entries = [item for item in entries if item.group == group]
        bare = [item for item in group_entries if item.electrode_type == "Bare"]
        material = [item for item in group_entries if item.electrode_type == "Material"]
        if len(group_entries) != 14 or len(bare) != 1 or len(material) != 13:
            errors.append(
                f"Group {group}: expected 14 total (1 Bare, 13 Material), found "
                f"{len(group_entries)} total ({len(bare)} Bare, {len(material)} Material)"
            )
        sample_ids = [item.sample_id for item in group_entries if item.sample_id is not None]
        if len(sample_ids) != len(set(sample_ids)):
            errors.append(f"Group {group}: duplicate sample_id")
    manifest_paths = [item.relative_path for item in entries]
    if len(manifest_paths) != len(set(manifest_paths)):
        errors.append("Manifest contains duplicate relative_path values")

    return ExperimentManifest(
        entries=tuple(entries),
        errors=tuple(errors),
        user_confirmed=not errors,
        source="PB42 directory and filename inference with strict design validation",
        template_name=CURRENT_PB_42_TEMPLATE.name,
    )


def validate_current_pb42_design(manifest: ExperimentManifest) -> None:
    """Reject manifests that do not match the validated 42-file PB study."""

    manifest.require_valid()
    errors: list[str] = []
    if len(manifest.entries) != 42:
        errors.append(f"Expected 42 files, found {len(manifest.entries)}")
    for design in CURRENT_PB_42_TEMPLATE.groups:
        rows = [entry for entry in manifest.entries if entry.group == design.group]
        bare = sum(entry.electrode_type == "Bare" for entry in rows)
        material = sum(entry.electrode_type == "Material" for entry in rows)
        if (
            len(rows) != design.expected_bare + design.expected_material
            or bare != design.expected_bare
            or material != design.expected_material
        ):
            errors.append(
                f"Group {design.group}: expected 14 total (1 Bare, 13 Material), found "
                f"{len(rows)} total ({bare} Bare, {material} Material)"
            )
    if {entry.group for entry in manifest.entries} != set(CURRENT_PB_42_TEMPLATE.group_order):
        errors.append("PB42 groups must be exactly A, B and C")
    if errors:
        raise MetadataResolutionError(tuple(errors))


def analyze_lsv_files(
    paths: Sequence[str | Path],
    *,
    root: str | Path,
    settings: AnalysisSettings | None = None,
) -> LSVAnalysisResult:
    """Run the strict, optional PB42 analysis preset."""

    manifest = infer_current_pb42_manifest(paths, root=root)
    validate_current_pb42_design(manifest)
    return analyze_lsv_with_manifest(
        manifest,
        comparisons=CURRENT_PB_42_TEMPLATE.comparisons,
        settings=settings,
        group_order=CURRENT_PB_42_TEMPLATE.group_order,
    )


def run_lsv_analysis(
    input_root: str | Path,
    *,
    output_base: str | Path = "results",
    settings: AnalysisSettings | None = None,
) -> AnalysisRun:
    """Run and export the strict, optional PB42 analysis preset."""

    root = Path(input_root)
    manifest = infer_current_pb42_manifest(sorted(root.rglob("*.bin")), root=root)
    validate_current_pb42_design(manifest)
    return run_lsv_analysis_with_manifest(
        manifest,
        comparisons=CURRENT_PB_42_TEMPLATE.comparisons,
        output_base=output_base,
        settings=settings,
    )


__all__ = [
    "CURRENT_PB_42_TEMPLATE",
    "GroupDesign",
    "PB42ExperimentTemplate",
    "analyze_lsv_files",
    "infer_current_pb42_manifest",
    "run_lsv_analysis",
    "validate_current_pb42_design",
]
