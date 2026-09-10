"""User-assigned experiment metadata kept separate from CHI binary metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal


Group = str
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
    file_path: str | None = None


@dataclass(frozen=True, slots=True)
class ExperimentManifest:
    entries: tuple[ManifestEntry, ...]
    errors: tuple[str, ...] = ()
    user_confirmed: bool = False
    source: str = "Unspecified"
    template_name: str | None = None

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def require_valid(self) -> None:
        if self.errors:
            raise MetadataResolutionError(self.errors)


def validate_generic_manifest(
    manifest: ExperimentManifest, *, require_confirmed: bool = True
) -> None:
    """Validate user metadata without imposing a particular experiment design."""

    errors = list(manifest.errors)
    if require_confirmed and not manifest.user_confirmed:
        errors.append("Formal Generic LSV analysis requires user_confirmed=True")
    if not manifest.entries:
        errors.append("Manifest contains no files")

    relative_paths: list[str] = []
    sample_keys: list[tuple[str, str]] = []
    for index, entry in enumerate(manifest.entries, start=1):
        label = entry.relative_path or entry.file_name or f"entry {index}"
        if not entry.file_name.strip():
            errors.append(f"{label}: file_name is empty")
        if not entry.relative_path.strip() and not (entry.file_path or "").strip():
            errors.append(f"{label}: relative_path or file_path is required")
        if entry.group is None or not entry.group.strip():
            errors.append(f"{label}: group is required")
        if entry.electrode_type not in {"Bare", "Material"}:
            errors.append(f"{label}: electrode_type must be Bare or Material")
        if entry.sample_id is None or not entry.sample_id.strip():
            errors.append(f"{label}: sample_id is required")
        if entry.relative_path:
            relative_paths.append(entry.relative_path)
        if entry.group and entry.sample_id:
            sample_keys.append((entry.group, entry.sample_id))

    if len(relative_paths) != len(set(relative_paths)):
        errors.append("Manifest contains duplicate relative_path values")
    if len(sample_keys) != len(set(sample_keys)):
        errors.append("Manifest contains duplicate sample_id values within a group")
    if not any(entry.electrode_type == "Material" for entry in manifest.entries):
        errors.append("Manifest contains no Material electrodes")
    if errors:
        raise MetadataResolutionError(tuple(dict.fromkeys(errors)))


def confirmed_generic_manifest(
    entries: Iterable[ManifestEntry], *, source: str = "User-confirmed metadata"
) -> ExperimentManifest:
    """Create and validate the immutable manifest used by formal Generic Mode."""

    manifest = ExperimentManifest(
        entries=tuple(entries),
        user_confirmed=True,
        source=source,
    )
    validate_generic_manifest(manifest)
    return manifest


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


def infer_current_pb42_manifest(
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
            file_path=str(path),
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

    return ExperimentManifest(
        entries=tuple(entries),
        errors=tuple(errors),
        user_confirmed=not errors,
        source="PB42 directory and filename inference with strict design validation",
        template_name="CURRENT_PB_42_TEMPLATE",
    )


def suggest_generic_manifest(
    paths: Iterable[str | Path], *, root: str | Path
) -> ExperimentManifest:
    """Return editable best-effort metadata; never authorize formal analysis."""

    root_path = Path(root)
    entries = []
    for supplied in paths:
        path = Path(supplied)
        relative_path = _relative(path, root_path)
        match = SAMPLE_ID_PATTERN.search(path.name)
        entries.append(
            ManifestEntry(
                file_name=path.name,
                relative_path=relative_path,
                group=_infer_group(relative_path),
                electrode_type=_infer_electrode_type(path.name),
                sample_id=match.group(1).upper() if match else None,
                file_path=str(path),
            )
        )
    return ExperimentManifest(
        entries=tuple(entries),
        user_confirmed=False,
        source="Editable filename/directory suggestions; user confirmation required",
    )


def validate_current_pb42_design(manifest: ExperimentManifest) -> None:
    """Reject any manifest that does not match the validated 42-file PB study."""

    manifest.require_valid()
    errors: list[str] = []
    if len(manifest.entries) != 42:
        errors.append(f"Expected 42 files, found {len(manifest.entries)}")
    for group in ("A", "B", "C"):
        rows = [entry for entry in manifest.entries if entry.group == group]
        bare = sum(entry.electrode_type == "Bare" for entry in rows)
        material = sum(entry.electrode_type == "Material" for entry in rows)
        if len(rows) != 14 or bare != 1 or material != 13:
            errors.append(
                f"Group {group}: expected 14 total (1 Bare, 13 Material), found "
                f"{len(rows)} total ({bare} Bare, {material} Material)"
            )
    if {entry.group for entry in manifest.entries} != {"A", "B", "C"}:
        errors.append("PB42 groups must be exactly A, B and C")
    if errors:
        raise MetadataResolutionError(tuple(errors))


def infer_experiment_manifest(
    paths: Iterable[str | Path], *, root: str | Path
) -> ExperimentManifest:
    """Backward-compatible alias for strict current PB42 inference."""

    return infer_current_pb42_manifest(paths, root=root)


__all__ = [
    "ElectrodeType",
    "ExperimentManifest",
    "Group",
    "ManifestEntry",
    "MetadataResolutionError",
    "confirmed_generic_manifest",
    "infer_current_pb42_manifest",
    "infer_experiment_manifest",
    "suggest_generic_manifest",
    "validate_current_pb42_design",
    "validate_generic_manifest",
]
