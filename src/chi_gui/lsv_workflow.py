"""Headless Generic LSV GUI workflow state and backend orchestration."""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from analysis import (
    AnalysisSettings,
    ComparisonDefinition,
    ExperimentManifest,
    LSVAnalysisResult,
    ManifestEntry,
    analyze_lsv_with_manifest,
    confirmed_generic_manifest,
    suggest_generic_manifest,
)

from .state import FileRecord


class GUIWorkflowValidationError(ValueError):
    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors if str(error)))
        super().__init__("；".join(self.errors))


class StaleAnalysisResultError(ValueError):
    """Raised when export is requested for settings that no longer match a result."""


@dataclass(slots=True)
class MetadataDraftRow:
    record_key: str
    file_path: str
    file_name: str
    relative_path: str
    include: bool = True
    sample_id: str = ""
    group: str = ""
    electrode_type: str = "Material"
    notes: str = ""

    def to_manifest_entry(self) -> ManifestEntry:
        return ManifestEntry(
            file_name=self.file_name,
            relative_path=self.relative_path,
            file_path=self.file_path,
            group=self.group.strip() or None,
            electrode_type=self.electrode_type if self.electrode_type in {"Material", "Bare"} else None,
            sample_id=self.sample_id.strip() or None,
            notes=self.notes,
        )


@dataclass(slots=True)
class ComparisonDraft:
    left_group: str
    right_group: str
    role: str = "Primary"
    holm_family: str = "primary"
    name: str = ""

    def to_definition(self) -> ComparisonDefinition:
        normalized_role = "primary" if self.role.lower().startswith("primary") else "exploratory"
        family = self.holm_family.strip() or None
        return ComparisonDefinition(
            left_group=self.left_group.strip(),
            right_group=self.right_group.strip(),
            role=normalized_role,
            holm_family=family,
            name=self.name.strip() or None,
        )


@dataclass(frozen=True, slots=True)
class LSVAnalysisRequest:
    manifest: ExperimentManifest
    comparisons: tuple[ComparisonDefinition, ...]
    settings: AnalysisSettings
    signature: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class LSVAnalysisCompleted:
    workspace_id: str
    request: LSVAnalysisRequest
    result: LSVAnalysisResult


def _common_root(paths: tuple[Path, ...]) -> Path:
    if not paths:
        return Path(".")
    common = Path(os.path.commonpath([str(path.resolve()) for path in paths]))
    return common.parent if common.is_file() else common


def _draft_signature(
    rows: Iterable[MetadataDraftRow],
    target_potential_V: float,
    analysis_metric: str,
    comparisons: Iterable[ComparisonDraft],
    bootstrap_seed: int,
    bootstrap_resamples: int,
    sign_zero_tolerance_A: float,
) -> tuple[object, ...]:
    return (
        tuple(
            (
                row.record_key,
                row.include,
                row.sample_id,
                row.group,
                row.electrode_type,
                row.notes,
            )
            for row in rows
        ),
        float(target_potential_V),
        analysis_metric,
        tuple(
            (item.left_group, item.right_group, item.role, item.holm_family, item.name)
            for item in comparisons
        ),
        int(bootstrap_seed),
        int(bootstrap_resamples),
        float(sign_zero_tolerance_A),
    )


@dataclass(slots=True)
class LSVWorkflowState:
    metadata_rows: list[MetadataDraftRow] = field(default_factory=list)
    manifest_status: str = "尚未生成样本信息建议"
    confirmed_manifest: ExperimentManifest | None = None
    target_potential_V: float = 0.0
    analysis_metric: str = "magnitude"
    comparisons: list[ComparisonDraft] = field(default_factory=list)
    bootstrap_seed: int = 20260910
    bootstrap_resamples: int = 5000
    sign_zero_tolerance_A: float = 1e-12
    analysis_result: LSVAnalysisResult | None = None
    result_stale: bool = False
    result_signature: tuple[object, ...] | None = None
    selected_result_plot: str = "Selected magnitude"
    selected_plot_group: str = "ALL"
    last_export_directory: str | None = None
    validation_errors: tuple[str, ...] = ()

    @property
    def groups(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(row.group.strip() for row in self.metadata_rows if row.include and row.group.strip()))

    @property
    def has_confirmed_manifest(self) -> bool:
        return self.confirmed_manifest is not None and self.confirmed_manifest.user_confirmed

    @property
    def result_status(self) -> str:
        if self.analysis_result is None:
            return "尚未运行分析"
        if self.result_stale:
            return "设置已修改，当前结果已过期，需要重新分析"
        return "分析完成，结果与当前设置一致"

    def current_signature(self) -> tuple[object, ...]:
        return _draft_signature(
            self.metadata_rows,
            self.target_potential_V,
            self.analysis_metric,
            self.comparisons,
            self.bootstrap_seed,
            self.bootstrap_resamples,
            self.sign_zero_tolerance_A,
        )

    def mark_changed(self, *, metadata_changed: bool = False) -> None:
        if metadata_changed:
            self.confirmed_manifest = None
            self.manifest_status = "样本信息已修改，尚未确认"
        if self.analysis_result is not None:
            self.result_stale = True

    def sync_records(self, records: Iterable[FileRecord]) -> None:
        lsv_records = tuple(
            record for record in records if record.parse_success and record.experiment_type == "LSV"
        )
        existing = {row.record_key: row for row in self.metadata_rows}
        paths = tuple(record.path for record in lsv_records)
        root = _common_root(paths)
        suggestions = suggest_generic_manifest(paths, root=root) if paths else None
        suggested_by_path = (
            {str(Path(entry.file_path or "").resolve()): entry for entry in suggestions.entries}
            if suggestions is not None
            else {}
        )
        changed = set(existing) != {record.key for record in lsv_records}
        rows: list[MetadataDraftRow] = []
        for record in lsv_records:
            if record.key in existing:
                rows.append(existing[record.key])
                continue
            suggestion = suggested_by_path.get(str(record.path.resolve()))
            rows.append(
                MetadataDraftRow(
                    record_key=record.key,
                    file_path=str(record.path),
                    file_name=record.path.name,
                    relative_path=suggestion.relative_path if suggestion else record.path.name,
                    sample_id=(suggestion.sample_id or "") if suggestion else "",
                    group=(suggestion.group or "") if suggestion else "",
                    electrode_type=(suggestion.electrode_type or "Material") if suggestion else "Material",
                    notes=suggestion.notes if suggestion else "",
                )
            )
        self.metadata_rows = rows
        if changed:
            self.confirmed_manifest = None
            self.manifest_status = (
                "自动建议，尚未确认" if rows else "尚未导入可分析的 LSV 文件"
            )
            if self.analysis_result is not None:
                self.result_stale = True

    def update_metadata(self, record_key: str, field_name: str, value: object) -> None:
        row = next(row for row in self.metadata_rows if row.record_key == record_key)
        if field_name not in {"include", "sample_id", "group", "electrode_type", "notes"}:
            raise ValueError(f"Unsupported metadata field: {field_name}")
        if field_name == "include":
            setattr(row, field_name, bool(value))
        else:
            setattr(row, field_name, str(value))
        self.mark_changed(metadata_changed=True)

    def batch_update(self, keys: Iterable[str], field_name: str, value: str) -> None:
        key_set = set(keys)
        for row in self.metadata_rows:
            if row.record_key in key_set:
                self.update_metadata(row.record_key, field_name, value)

    def confirm_metadata(self) -> ExperimentManifest:
        entries = tuple(row.to_manifest_entry() for row in self.metadata_rows if row.include)
        try:
            manifest = confirmed_generic_manifest(entries, source="GUI user-confirmed Generic LSV metadata")
        except ValueError as error:
            self.validation_errors = tuple(getattr(error, "errors", (str(error),)))
            raise GUIWorkflowValidationError(self.validation_errors) from error
        self.confirmed_manifest = manifest
        self.manifest_status = f"已确认：{len(entries)} 个文件"
        self.validation_errors = ()
        if self.analysis_result is not None and self.current_signature() != self.result_signature:
            self.result_stale = True
        return manifest

    def set_target_potential(self, value: float) -> None:
        if not math.isfinite(value):
            raise ValueError("分析电位必须是有限数值")
        if float(value) != self.target_potential_V:
            self.target_potential_V = float(value)
            self.mark_changed()

    def set_metric(self, metric: str) -> None:
        if metric not in {"signed", "magnitude"}:
            raise ValueError("分析指标必须是 signed 或 magnitude")
        if metric != self.analysis_metric:
            self.analysis_metric = metric
            self.mark_changed()

    def replace_comparisons(self, comparisons: Iterable[ComparisonDraft]) -> None:
        replacement = list(comparisons)
        if replacement != self.comparisons:
            self.comparisons = replacement
            self.mark_changed()

    def build_request(self, records: Iterable[FileRecord]) -> LSVAnalysisRequest:
        errors = validate_lsv_workflow(self, records)
        self.validation_errors = errors
        if errors:
            raise GUIWorkflowValidationError(errors)
        assert self.confirmed_manifest is not None
        settings = AnalysisSettings(
            target_potential_V=self.target_potential_V,
            analysis_metric=self.analysis_metric,
            bootstrap_seed=self.bootstrap_seed,
            bootstrap_resamples=self.bootstrap_resamples,
            sign_zero_tolerance_A=self.sign_zero_tolerance_A,
        )
        return LSVAnalysisRequest(
            manifest=self.confirmed_manifest,
            comparisons=tuple(item.to_definition() for item in self.comparisons),
            settings=settings,
            signature=self.current_signature(),
        )

    def accept_result(self, request: LSVAnalysisRequest, result: LSVAnalysisResult) -> None:
        self.analysis_result = result
        self.result_signature = request.signature
        self.result_stale = self.current_signature() != request.signature
        self.validation_errors = ()

    def require_exportable_result(self) -> LSVAnalysisResult:
        if self.analysis_result is None:
            raise StaleAnalysisResultError("尚无可导出的分析结果")
        if self.result_stale or self.current_signature() != self.result_signature:
            self.result_stale = True
            raise StaleAnalysisResultError("设置已修改，请重新分析后导出")
        return self.analysis_result


def validate_lsv_workflow(
    workflow: LSVWorkflowState,
    records: Iterable[FileRecord],
) -> tuple[str, ...]:
    errors: list[str] = []
    manifest = workflow.confirmed_manifest
    if manifest is None or not manifest.user_confirmed:
        errors.append("请先确认样本信息")
    material_counts: dict[str, int] = {}
    if manifest is not None:
        for entry in manifest.entries:
            if entry.group is None or not entry.group.strip():
                errors.append(f"{entry.file_name}：Group 不能为空")
            if entry.sample_id is None or not entry.sample_id.strip():
                errors.append(f"{entry.file_name}：Sample ID 不能为空")
            if entry.electrode_type == "Material" and entry.group:
                material_counts[entry.group] = material_counts.get(entry.group, 0) + 1
    if not material_counts:
        errors.append("至少需要一个 included Material electrode")

    if workflow.analysis_metric not in {"signed", "magnitude"}:
        errors.append("分析指标必须是 signed 或 magnitude")
    if not math.isfinite(workflow.target_potential_V):
        errors.append("分析电位必须是有限数值")
    if workflow.bootstrap_resamples < 5000:
        errors.append("Bootstrap resamples 不能少于 5000")
    if not math.isfinite(workflow.sign_zero_tolerance_A) or workflow.sign_zero_tolerance_A < 0:
        errors.append("Sign zero tolerance 必须是非负有限数值")

    definitions = [item.to_definition() for item in workflow.comparisons]
    names = [item.comparison_name for item in definitions]
    if len(names) != len(set(names)):
        errors.append("Comparison Name 不能重复")
    groups = set(material_counts)
    for definition in definitions:
        if not definition.left_group or not definition.right_group:
            errors.append("Comparison 的左右 Group 不能为空")
            continue
        if definition.left_group == definition.right_group:
            errors.append(f"{definition.comparison_name}：不能比较相同 Group")
        for group in (definition.left_group, definition.right_group):
            if group not in groups:
                errors.append(f"{definition.comparison_name}：引用了不存在的 Material Group {group}")
            elif material_counts[group] < 2:
                errors.append(f"{definition.comparison_name}：Group {group} 至少需要 2 个独立 Material 样本")
        if definition.holm_family and not definition.role.lower().startswith("primary"):
            errors.append(f"{definition.comparison_name}：Exploratory comparison 不能设置 Holm Family")

    if manifest is not None and math.isfinite(workflow.target_potential_V):
        records_by_path = {
            str(record.path.resolve()): record
            for record in records
            if record.parse_success and record.experiment_type == "LSV"
        }
        selected_records = [
            records_by_path.get(str(Path(entry.file_path or entry.relative_path).resolve()))
            for entry in manifest.entries
        ]
        if any(record is None for record in selected_records):
            errors.append("已确认 manifest 中存在当前 Workspace 无法定位的 LSV 文件")
        elif selected_records:
            lower = max(float(record.data.potential_V[0]) for record in selected_records)
            upper = min(float(record.data.potential_V[-1]) for record in selected_records)
            target = workflow.target_potential_V
            if target < lower - 1e-10 or target > upper + 1e-10:
                errors.append(
                    f"分析电位 {target:.9g} V 超出 included LSV 的共同范围 [{lower:.9g}, {upper:.9g}] V"
                )
    return tuple(dict.fromkeys(errors))


def execute_lsv_analysis(request: LSVAnalysisRequest) -> LSVAnalysisResult:
    """Call the validated scientific backend without reimplementing calculations."""

    return analyze_lsv_with_manifest(
        request.manifest,
        comparisons=request.comparisons,
        settings=request.settings,
    )


def format_number(value: float, *, digits: int = 6) -> str:
    if value is None or not math.isfinite(float(value)):
        return "—"
    absolute = abs(float(value))
    if absolute and (absolute < 1e-4 or absolute >= 1e5):
        return f"{value:.3e}"
    return f"{value:.{digits}g}"


def descriptive_display_rows(result: LSVAnalysisResult) -> tuple[dict[str, object], ...]:
    rows = []
    for group in result.groups:
        stats = result.summary(group, result.settings.analysis_metric).statistics
        rows.append(
            {
                "group": group,
                "n": stats.n,
                "mean": format_number(stats.mean),
                "median": format_number(stats.median),
                "sd": format_number(stats.sd),
                "sem": format_number(stats.sem),
                "cv_percent": format_number(stats.cv_percent),
                "minimum": format_number(stats.minimum),
                "q1": format_number(stats.q1),
                "q3": format_number(stats.q3),
                "maximum": format_number(stats.maximum),
            }
        )
    return tuple(rows)


def comparison_display_rows(result: LSVAnalysisResult) -> tuple[dict[str, object], ...]:
    grouped: dict[str, dict[str, object]] = {}
    for item in result.comparisons:
        row = grouped.setdefault(
            item.comparison,
            {
                "comparison": item.comparison,
                "role": item.comparison_role,
                "welch_p": "—",
                "holm_p": "—",
                "mann_whitney_p": "—",
                "mean_difference": format_number(item.mean_difference),
                "mean_difference_ci": (
                    f"[{format_number(item.mean_difference_ci_low)}, "
                    f"{format_number(item.mean_difference_ci_high)}]"
                ),
                "hedges_g": format_number(item.hedges_g),
                "hedges_g_ci": (
                    f"[{format_number(item.hedges_g_ci_low)}, "
                    f"{format_number(item.hedges_g_ci_high)}]"
                ),
            },
        )
        if item.test.startswith("Welch"):
            row["welch_p"] = format_number(item.raw_p)
            row["holm_p"] = format_number(item.holm_adjusted_p)
        elif item.test.startswith("Mann-Whitney"):
            row["mann_whitney_p"] = format_number(item.raw_p)
    return tuple(grouped.values())


def sign_qc_display_rows(result: LSVAnalysisResult) -> tuple[dict[str, object], ...]:
    return tuple(
        {
            "group": item.group,
            "negative": item.negative_count,
            "positive": item.positive_count,
            "near_zero": item.near_zero_count,
            "consistent": "是" if item.sign_consistent else "否",
            "warning": item.warning,
        }
        for item in result.current_sign_qc
    )


def outlier_display_rows(result: LSVAnalysisResult) -> tuple[dict[str, object], ...]:
    rows = []
    for item in result.outlier_flags:
        match = re.search(r"\|modified z\|=([0-9.eE+-]+)", item.outlier_reason)
        rows.append(
            {
                "sample_id": item.sample_id,
                "group": item.group,
                "current": format_number(item.response),
                "mad_score": match.group(1) if match else "—",
                "status": item.status,
            }
        )
    return tuple(rows)


__all__ = [
    "ComparisonDraft",
    "GUIWorkflowValidationError",
    "LSVAnalysisRequest",
    "LSVAnalysisCompleted",
    "LSVWorkflowState",
    "MetadataDraftRow",
    "StaleAnalysisResultError",
    "comparison_display_rows",
    "descriptive_display_rows",
    "execute_lsv_analysis",
    "format_number",
    "outlier_display_rows",
    "sign_qc_display_rows",
    "validate_lsv_workflow",
]
