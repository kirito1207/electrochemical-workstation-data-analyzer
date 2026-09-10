"""Headless file discovery, parser routing and preview orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from analysis.techniques import TechniqueRoutingError, route_for_experiment_type
from chi_parser import (
    CHIParserError,
    ITData,
    LSVData,
    UnsupportedExperimentError,
    parse_file,
)

from .state import (
    FileRecord,
    FileStatus,
    PreviewCollection,
    PreviewCurve,
    PreviewData,
    PreviewDisplayState,
    canonical_path,
)


ProgressCallback = Callable[[int, int, Path], None]


_ERROR_HINTS = {
    "PointCountError": "文件点数无法可靠确定",
    "AmbiguousPointCountError": "存在多个无法排除的数据点数候选",
    "DataValidationError": "原始数值数据未通过完整性校验",
    "InvalidCHIFileError": "文件不符合当前已验证的 CHI 二进制结构",
    "UnsupportedExperimentError": "当前版本仅支持 CHI760E LSV 和 i-t 数据",
}


def discover_bin_files(selections: Iterable[str | Path]) -> tuple[Path, ...]:
    """Expand selected files/folders recursively without modifying inputs."""

    discovered: dict[str, Path] = {}
    for supplied in selections:
        path = Path(supplied).expanduser()
        candidates = (
            (item for item in path.rglob("*") if item.is_file() and item.suffix.lower() == ".bin")
            if path.is_dir()
            else (path,)
        )
        for candidate in candidates:
            if candidate.is_file() and candidate.suffix.lower() == ".bin":
                discovered.setdefault(canonical_path(candidate), candidate.resolve())
    return tuple(sorted(discovered.values(), key=lambda item: str(item).casefold()))


def _detected_short_name(diagnostic: dict[str, Any]) -> str:
    text = diagnostic.get("detected_experiment_text") or ""
    short_name = str(text).split("/", 1)[0].strip()
    return short_name or "未知"


def _friendly_error(error: Exception) -> str:
    technical = type(error).__name__
    hint = _ERROR_HINTS.get(technical, "文件解析失败，请查看详细诊断")
    return f"{hint}（{technical}）：{error}"


class GUIController:
    """Calls validated backends; contains no Tk widget code."""

    def parse_one(self, path: str | Path) -> FileRecord:
        file_path = Path(path).expanduser().resolve(strict=False)
        try:
            data = parse_file(file_path)
            route = route_for_experiment_type(data.experiment_type)
            return FileRecord(
                path=file_path,
                status=FileStatus.PARSED,
                experiment_type=data.experiment_type,
                route=route.experiment_type,
                data=data,
                warning_messages=tuple(data.warnings),
                diagnostic=data.diagnostics.to_dict(),
            )
        except CHIParserError as error:
            diagnostic = error.diagnostic.to_dict()
            experiment_type = _detected_short_name(diagnostic)
            unsupported = isinstance(error, UnsupportedExperimentError)
            return FileRecord(
                path=file_path,
                status=FileStatus.UNSUPPORTED if unsupported else FileStatus.FAILED,
                experiment_type=experiment_type,
                route="unsupported" if unsupported else "error",
                error_type=type(error).__name__,
                error_message=_friendly_error(error),
                diagnostic=diagnostic,
            )
        except Exception as error:
            # A single unexpected file-level failure must not abort the batch.
            return FileRecord(
                path=file_path,
                status=FileStatus.FAILED,
                experiment_type="未知",
                route="error",
                error_type=type(error).__name__,
                error_message=_friendly_error(error),
            )

    def parse_many(
        self,
        paths: Iterable[str | Path],
        *,
        progress: ProgressCallback | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> tuple[FileRecord, ...]:
        unique = discover_bin_files(paths)
        records: list[FileRecord] = []
        total = len(unique)
        for index, path in enumerate(unique, start=1):
            if should_cancel is not None and should_cancel():
                break
            records.append(self.parse_one(path))
            if progress is not None:
                progress(index, total, path)
        return tuple(records)

    def preview_for(self, record: FileRecord) -> PreviewData:
        if not record.parse_success or record.data is None:
            raise ValueError("只有解析成功的文件可以预览原始曲线。")
        if isinstance(record.data, LSVData):
            return PreviewData(
                source_file=record.path,
                experiment_type="LSV",
                x=record.data.potential_V,
                current_A=record.data.current_A,
                x_label="Potential / V",
            )
        if isinstance(record.data, ITData):
            return PreviewData(
                source_file=record.path,
                experiment_type="i-t",
                x=record.data.time_s,
                current_A=record.data.current_A,
                x_label="Time / s",
            )
        raise TechniqueRoutingError(
            f"No preview route for {record.data.experiment_type!r}."
        )

    def build_preview_collection(
        self,
        records: Iterable[FileRecord],
        *,
        experiment_type: str,
        display_state: PreviewDisplayState,
        selected_key: str | None = None,
    ) -> PreviewCollection:
        """Build one-technique preview; selection never changes membership."""

        matching = tuple(
            record
            for record in records
            if record.parse_success and record.experiment_type == experiment_type
        )
        matching_keys = {record.key for record in matching}
        effective_selected = selected_key if selected_key in matching_keys else None
        if effective_selected is None and matching:
            effective_selected = matching[0].key
        curves = tuple(
            PreviewCurve(
                record_key=record.key,
                file_name=record.path.name,
                data=self.preview_for(record),
                color=display_state.color_for(record.key),
                visible=display_state.is_visible(record.key),
                selected=record.key == effective_selected,
            )
            for record in matching
        )
        return PreviewCollection(
            experiment_type=experiment_type,
            curves=curves,
            selected_key=effective_selected,
        )
