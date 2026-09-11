"""Headless Generic i-t Event GUI workflow and backend orchestration."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from analysis.it_events import (
    CalibrationSelection,
    Event,
    EventAnalysisError,
    EventTimeline,
    ITEventBatchResult,
    ITEventInput,
    PlateauPolicy,
    analyze_it_event_batch,
)
from chi_parser import ITData

from .lsv_workflow import GUIWorkflowValidationError, StaleAnalysisResultError, WorkflowFeedback
from .state import FileRecord


@dataclass(slots=True)
class ITMetadataDraftRow:
    record_key: str
    file_name: str
    include: bool = True
    sample_id: str = ""
    group: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class ITAnalysisRequest:
    inputs: tuple[ITEventInput, ...]
    timeline: EventTimeline
    metric: str
    policy: PlateauPolicy
    calibration_selection: CalibrationSelection | None
    signature: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class ITAnalysisCompleted:
    workspace_id: str
    request: ITAnalysisRequest
    result: ITEventBatchResult


def _event_signature(event: Event) -> tuple[object, ...]:
    return (event.event_id, event.time_s, event.name, event.value, event.unit, event.notes)


@dataclass(slots=True)
class ITWorkflowState:
    metadata_rows: list[ITMetadataDraftRow] = field(default_factory=list)
    metadata_confirmed: bool = False
    events: list[Event] = field(default_factory=list)
    timeline_confirmed: bool = False
    tail_fraction: float = 0.20
    analysis_metric: str = "signed"
    calibration_enabled: bool = False
    calibration_event_ids: tuple[str, ...] = ()
    calibration_x_label: str = ""
    calibration_x_unit: str = ""
    analysis_result: ITEventBatchResult | None = None
    result_signature: tuple[object, ...] | None = None
    result_stale: bool = False
    analysis_running: bool = False
    selected_result_plot: str = "Raw + Events"
    last_export_directory: str | None = None
    feedback: WorkflowFeedback = field(default_factory=WorkflowFeedback)
    validation_errors: tuple[str, ...] = ()
    _next_event_number: int = 1

    def set_feedback(self, level: str, title: str, details: Iterable[str] = ()) -> None:
        self.feedback = WorkflowFeedback(level, title, tuple(details))

    def current_signature(self) -> tuple[object, ...]:
        return (
            tuple((r.record_key, r.include, r.sample_id, r.group, r.notes) for r in self.metadata_rows),
            self.metadata_confirmed,
            tuple(_event_signature(event) for event in self.events),
            self.timeline_confirmed,
            self.tail_fraction,
            self.analysis_metric,
            self.calibration_enabled,
            self.calibration_event_ids,
            self.calibration_x_label,
            self.calibration_x_unit,
        )

    @property
    def result_status(self) -> str:
        if self.analysis_result is None:
            return "尚未运行分析"
        if self.result_stale:
            return "设置已修改，当前结果已过期，需要重新分析"
        return "分析完成，结果与当前设置一致"

    @property
    def timeline(self) -> EventTimeline:
        return EventTimeline(tuple(self.events), self.timeline_confirmed, "GUI user-confirmed Event Timeline")

    def _changed(self, *, metadata: bool = False, timeline: bool = False) -> None:
        if metadata:
            self.metadata_confirmed = False
        if timeline:
            self.timeline_confirmed = False
        if self.analysis_result is not None:
            self.result_stale = True
        self.set_feedback("info", "设置已修改，请重新确认并运行分析")

    def sync_records(self, records: Iterable[FileRecord]) -> None:
        usable = tuple(r for r in records if r.parse_success and r.experiment_type == "i-t")
        existing = {row.record_key: row for row in self.metadata_rows}
        keys = {record.key for record in usable}
        changed = set(existing) != keys
        self.metadata_rows = [
            existing.get(record.key) or ITMetadataDraftRow(
                record.key, record.path.name, sample_id=record.path.stem
            )
            for record in usable
        ]
        if changed:
            self.metadata_confirmed = False
            if self.analysis_result is not None:
                self.result_stale = True
            self.set_feedback(
                "warning", "i-t 文件列表已变化，请检查并确认样本信息"
                if usable else "尚未导入可分析的 i-t 文件"
            )

    def update_metadata(self, record_key: str, field_name: str, value: object) -> None:
        if field_name not in {"include", "sample_id", "group", "notes"}:
            raise ValueError(f"Unsupported i-t metadata field: {field_name}")
        row = next(row for row in self.metadata_rows if row.record_key == record_key)
        setattr(row, field_name, bool(value) if field_name == "include" else str(value))
        self._changed(metadata=True)

    def confirm_metadata(self) -> None:
        included = [row for row in self.metadata_rows if row.include]
        errors = []
        if not included:
            errors.append("至少需要纳入 1 个已解析的 i-t 文件。")
        ids = [row.sample_id.strip() for row in included]
        if any(not value for value in ids):
            errors.append("所有纳入文件都必须填写 Sample ID。")
        if len(ids) != len(set(ids)):
            errors.append("纳入文件的 Sample ID 必须唯一。")
        if any(not row.group.strip() for row in included):
            errors.append("所有纳入文件都必须填写 Group。")
        if errors:
            raise GUIWorkflowValidationError(errors)
        self.metadata_confirmed = True
        self.set_feedback("success", f"样本信息已确认：{len(included)} 个文件")

    def _new_event_id(self) -> str:
        used = {event.event_id for event in self.events}
        while f"event_{self._next_event_number}" in used:
            self._next_event_number += 1
        value = f"event_{self._next_event_number}"
        self._next_event_number += 1
        return value

    def add_event(self, *, time_s: float, name: str, value: float | None = None,
                  unit: str | None = None, notes: str = "", event_id: str | None = None) -> Event:
        if not math.isfinite(float(time_s)):
            raise ValueError("Event 时间必须是有限数值。")
        if any(event.time_s == float(time_s) for event in self.events):
            raise ValueError("Event 时间不能重复；请编辑现有 Event 或选择其他时间。")
        if not name.strip():
            raise ValueError("Event 名称不能为空。")
        event = Event(event_id or self._new_event_id(), float(time_s), name.strip(), value,
                      unit.strip() if unit else None, notes.strip())
        self.events.append(event)
        self.events.sort(key=lambda row: row.time_s)
        self._changed(timeline=True)
        return event

    def edit_event(self, event_id: str, **changes: object) -> Event:
        old = next(event for event in self.events if event.event_id == event_id)
        values = {
            "time_s": old.time_s, "name": old.name, "value": old.value,
            "unit": old.unit, "notes": old.notes,
        }
        values.update(changes)
        time_s = float(values["time_s"])
        if any(event.event_id != event_id and event.time_s == time_s for event in self.events):
            raise ValueError("Event 时间不能重复；请编辑现有 Event 或选择其他时间。")
        if not str(values["name"]).strip():
            raise ValueError("Event 名称不能为空。")
        replacement = Event(event_id, time_s, str(values["name"]).strip(), values["value"],
                            str(values["unit"]).strip() if values["unit"] else None,
                            str(values["notes"]).strip())
        self.events = [replacement if event.event_id == event_id else event for event in self.events]
        self.events.sort(key=lambda row: row.time_s)
        self._changed(timeline=True)
        return replacement

    def delete_events(self, event_ids: Iterable[str]) -> None:
        removed = set(event_ids)
        if removed:
            self.events = [event for event in self.events if event.event_id not in removed]
            self.calibration_event_ids = tuple(value for value in self.calibration_event_ids if value not in removed)
            self._changed(timeline=True)

    def confirm_timeline(self, records: Iterable[FileRecord]) -> EventTimeline:
        if not self.events:
            raise GUIWorkflowValidationError(("Event Timeline 为空；仅可进行 raw preview，不能正式分析。",))
        timeline = EventTimeline(tuple(self.events), True, "GUI user-confirmed Event Timeline")
        try:
            timeline.validate()
        except EventAnalysisError as error:
            raise GUIWorkflowValidationError((str(error),)) from error
        self.timeline_confirmed = True
        self.set_feedback("success", f"Event Timeline 已确认：{len(self.events)} 个 Event")
        return self.timeline

    def set_tail_fraction(self, value: float) -> None:
        value = float(value)
        PlateauPolicy(fraction=value).validate()
        if value != self.tail_fraction:
            self.tail_fraction = value
            self._changed()

    def set_metric(self, metric: str) -> None:
        if metric not in {"signed", "magnitude"}:
            raise ValueError("分析指标必须是 signed 或 magnitude。")
        if metric != self.analysis_metric:
            self.analysis_metric = metric
            self._changed()

    def set_calibration(self, enabled: bool, event_ids: Iterable[str], x_label: str, x_unit: str) -> None:
        replacement = (bool(enabled), tuple(event_ids), x_label.strip(), x_unit.strip())
        current = (self.calibration_enabled, self.calibration_event_ids,
                   self.calibration_x_label, self.calibration_x_unit)
        if replacement != current:
            (self.calibration_enabled, self.calibration_event_ids,
             self.calibration_x_label, self.calibration_x_unit) = replacement
            self._changed()

    def build_request(self, records: Iterable[FileRecord]) -> ITAnalysisRequest:
        errors = list(validate_it_workflow(self, records))
        if errors:
            self.validation_errors = tuple(errors)
            self.set_feedback("warning", "无法开始正式分析", errors)
            raise GUIWorkflowValidationError(errors)
        by_key = {record.key: record for record in records}
        inputs = tuple(
            ITEventInput(by_key[row.record_key].data, row.sample_id.strip(), row.group.strip(), True, row.notes)
            for row in self.metadata_rows if row.include
        )
        calibration = None
        if self.calibration_enabled:
            calibration = CalibrationSelection(
                self.calibration_event_ids, self.calibration_x_label, self.calibration_x_unit
            )
        return ITAnalysisRequest(inputs, self.timeline, self.analysis_metric,
                                 PlateauPolicy(fraction=self.tail_fraction), calibration,
                                 self.current_signature())

    def accept_result(self, request: ITAnalysisRequest, result: ITEventBatchResult) -> None:
        self.analysis_result = result
        self.result_signature = request.signature
        self.result_stale = self.current_signature() != request.signature
        self.analysis_running = False
        self.validation_errors = ()
        self.set_feedback("success", "Generic i-t Event 分析完成")

    def require_exportable_result(self) -> ITEventBatchResult:
        if self.analysis_result is None:
            raise StaleAnalysisResultError("尚无可导出的 i-t 分析结果")
        if self.result_stale or self.current_signature() != self.result_signature:
            self.result_stale = True
            raise StaleAnalysisResultError("设置已修改，请重新分析后导出")
        return self.analysis_result


def validate_it_workflow(workflow: ITWorkflowState, records: Iterable[FileRecord]) -> tuple[str, ...]:
    errors: list[str] = []
    if not workflow.metadata_confirmed:
        errors.append("样本信息尚未由用户确认。")
    if not workflow.timeline_confirmed:
        errors.append("Event Timeline 尚未由用户确认。")
    if not workflow.events:
        errors.append("Event Timeline 为空；不能运行正式 Event 分析。")
    try:
        PlateauPolicy(fraction=workflow.tail_fraction).validate()
    except EventAnalysisError as error:
        errors.append(str(error))
    if workflow.analysis_metric not in {"signed", "magnitude"}:
        errors.append("分析指标必须是 signed 或 magnitude。")
    by_key = {record.key: record for record in records}
    if any(row.include and (row.record_key not in by_key or not isinstance(by_key[row.record_key].data, ITData))
           for row in workflow.metadata_rows):
        errors.append("已确认样本中存在当前 Workspace 无法定位的 i-t 文件。")
    if workflow.calibration_enabled:
        selection = CalibrationSelection(workflow.calibration_event_ids,
                                         workflow.calibration_x_label,
                                         workflow.calibration_x_unit)
        try:
            selection.validate(workflow.timeline)
        except EventAnalysisError as error:
            errors.append(str(error))
    return tuple(dict.fromkeys(errors))


def execute_it_analysis(request: ITAnalysisRequest) -> ITEventBatchResult:
    return analyze_it_event_batch(
        request.inputs, request.timeline, metric=request.metric, policy=request.policy,
        calibration_selection=request.calibration_selection,
    )


def response_display_rows(result: ITEventBatchResult) -> tuple[dict[str, object], ...]:
    return tuple({
        "sample_id": row.sample_id, "group": row.group, "event": row.event_name,
        "time_s": row.event_time_s, "baseline_mean": row.baseline_mean_uA,
        "response_mean": row.response_mean_uA, "signed_delta": row.delta_current_uA,
        "magnitude": row.response_magnitude_uA, "response_sd": row.response_sd_uA,
        "window_start": row.response_window_start_s, "window_end": row.response_window_end_s,
        "status": row.status if row.status == "ok" else f"{row.status}: {row.notes}",
    } for item in result.files for row in item.responses)


def summary_display_rows(result: ITEventBatchResult) -> tuple[dict[str, object], ...]:
    metric = result.analysis_metric
    return tuple({
        "group": row.group, "event": row.event_name, "n": row.n,
        "mean": row.mean_delta_current_uA if metric == "signed" else row.mean_response_magnitude_uA,
        "sd": row.sd_delta_current_uA if metric == "signed" else row.sd_response_magnitude_uA,
        "sem": row.sem_delta_current_uA if metric == "signed" else row.sem_response_magnitude_uA,
        "cv_percent": row.cv_delta_percent if metric == "signed" else row.cv_magnitude_percent,
    } for row in result.summaries)


def calibration_display_rows(result: ITEventBatchResult) -> tuple[dict[str, object], ...]:
    return tuple({
        "sample_id": item.sample_id, "metric": calibration.analysis_metric,
        "x_label": calibration.x_label, "x_unit": calibration.x_unit,
        "slope": calibration.slope_uA_per_x, "intercept": calibration.intercept_uA,
        "r_squared": calibration.r_squared, "events": ", ".join(calibration.event_ids),
        "method": calibration.regression_method,
    } for item in result.files if (calibration := item.calibration) is not None)


def workflow_status_lines(workflow: ITWorkflowState) -> tuple[str, ...]:
    return (
        f"① 样本信息：{'已确认' if workflow.metadata_confirmed else '未确认'}",
        f"② Event Timeline：{'已确认' if workflow.timeline_confirmed else '未确认'}（{len(workflow.events)}）",
        f"③ 响应设置：尾段 {workflow.tail_fraction:.0%}；{workflow.analysis_metric}",
        f"④ Calibration：{'开启' if workflow.calibration_enabled else '关闭'}",
        f"⑤ 正式分析：{workflow.result_status}",
    )


def result_summary_text(result: ITEventBatchResult) -> str:
    groups = tuple(dict.fromkeys(item.group for item in result.files))
    calibration = "开启" if result.calibration_selection is not None else "关闭"
    return (f"✓ 分析完成｜Files：{len(result.files)}｜Events：{len(result.timeline.events)}｜"
            f"Groups：{len(groups)}｜指标：{result.analysis_metric}｜Calibration：{calibration}")


__all__ = ["ITAnalysisCompleted", "ITAnalysisRequest", "ITMetadataDraftRow", "ITWorkflowState",
           "calibration_display_rows", "execute_it_analysis", "response_display_rows",
           "result_summary_text", "summary_display_rows", "validate_it_workflow",
           "workflow_status_lines"]
