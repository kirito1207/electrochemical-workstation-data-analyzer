"""User-assigned experiment metadata kept separate from CHI binary metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal


Group = Literal["A", "B", "C"]
ElectrodeType = Literal["Bare", "Material"]
SAMPLE_ID_PATTERN = re.compile(r"-(S\d+|Z\d+|L\d+)\.bin$", re.IGNORECASE)


class MetadataResolutionError(ValueError):
    """Raised before analysis when file grouping cannot be uniquely confirmed."""

    def __init__(self, errors: tuple[str, ...]):
        super().__init__("Metadata unresolved: " + " | ".join(errors))
        self.errors = errors


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    file_name: str
    relative_path: str
    group: Group | None
    electrode_type: ElectrodeType | None
    sample_id: str | None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    entries: tuple[ManifestEntry, ...]
    errors: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise MetadataResolutionError(self.errors)


def _infer_group(text: str) -> Group | None:
    water = "水" in text
    pbs = "PBS" in text.upper()
    ten = "10圈" in text
    twenty = "20圈" in text
    matches: list[Group] = []
    if water and ten:
        matches.append("A")
    if pbs and ten:
        matches.append("B")
    if pbs and twenty:
        matches.append("C")
    return matches[0] if len(matches) == 1 else None


def _infer_electrode_type(file_name: str) -> ElectrodeType | None:
    matches: list[ElectrodeType] = []
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


def infer_experiment_manifest(
    paths: Iterable[str | Path], *, root: str | Path
) -> ExperimentManifest:
    """Infer A/B/C and Bare/Material, then enforce the complete study design."""

    root_path = Path(root)
    path_objects = tuple(Path(supplied) for supplied in paths)
    relative_paths = tuple(_relative(path, root_path) for path in path_objects)
    folder_groups: dict[str, set[Group]] = {}
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
        entry = ManifestEntry(
            file_name=path.name,
            relative_path=relative_path,
            group=group,
            electrode_type=electrode_type,
            sample_id=sample_id,
        )
        entries.append(entry)
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

    for group in ("A", "B", "C"):
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

    return ExperimentManifest(tuple(entries), tuple(errors))
