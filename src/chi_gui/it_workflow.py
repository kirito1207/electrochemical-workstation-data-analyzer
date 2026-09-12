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
    ITAnalysisMode,
    ITEventBatchResult,
    ITEventInput,
    PlateauPolicy,
    analyze_it_continuous_batch,
    analyze_it_events,
    summarize_event_responses,
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
class ITMetadataBatchEdit:
    include: bool | None = None
    update_group: bool = False
    group: str = ""
    update_notes: bool = False
    notes: str = ""


@dataclass(slots=True)
class SampleTimelineOverride:
    """One record-local Timeline draft; keyed externally by stable record_key."""

    events: list[Event] = field(default_factory=list)
    confirmed: bool = False

    def timeline(self, source: str) -> EventTimeline:
        return EventTimeline(tuple(self.events), self.confirmed, source)


@dataclass(frozen=True, slots=True)
class ITAnalysisRequest:
    record_keys: tuple[str, ...]
    inputs: tuple[ITEventInput, ...]
    timeline: EventTimeline
    record_timelines: tuple[EventTimeline, ...]
    metric: str
    policy: PlateauPolicy
    calibration_selection: CalibrationSelection | None
    signature: tuple[object, ...]
    mode: ITAnalysisMode


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
    events: list[Event] = field(default_factory=list)  # Default Timeline
    timeline_confirmed: bool = False
    sample_timeline_overrides: dict[str, SampleTimelineOverride] = field(default_factory=dict)
    current_timeline_record_key: str | None = None
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

    @property
    def timeline(self) -> EventTimeline:
        return EventTimeline(tuple(self.events), self.timeline_confirmed, "GUI Default Event Timeline")

    @property
    def current_override(self) -> SampleTimelineOverride | None:
        return (None if self.current_timeline_record_key is None else
                self.sample_timeline_overrides.get(self.current_timeline_record_key))

    @property
    def current_events(self) -> list[Event]:
        override = self.current_override
        return override.events if override is not None else self.events

    @property
    def current_timeline_confirmed(self) -> bool:
        override = self.current_override
        return override.confirmed if override is not None else self.timeline_confirmed

    @property
    def current_timeline_is_inherited(self) -> bool:
        return self.current_timeline_record_key is not None and self.current_override is None

    @property
    def timeline_context_status(self) -> str:
        if self.current_timeline_record_key is None:
            return "默认 Timeline"
        row = self.metadata_row(self.current_timeline_record_key)
        label = row.sample_id.strip() or row.file_name
        kind = "继承默认 Timeline" if self.current_override is None else "样本专用 Timeline"
        return f"样本 {label}：{kind}"

    @property
    def included_timeline_contexts(self) -> tuple[tuple[str | None, str], ...]:
        return ((None, "默认 Timeline"),) + tuple(
            (row.record_key, f"{row.sample_id.strip() or row.file_name} — {row.file_name} [{index}]")
            for index, row in enumerate((row for row in self.metadata_rows if row.include), start=1)
        )

    @property
    def analysis_mode(self) -> ITAnalysisMode:
        if self.events:
            return ITAnalysisMode.EVENT
        included_keys = {row.record_key for row in self.metadata_rows if row.include}
        return (ITAnalysisMode.EVENT
                if any(key in included_keys and override.events
                       for key, override in self.sample_timeline_overrides.items())
                else ITAnalysisMode.CONTINUOUS)

    def metadata_row(self, record_key: str) -> ITMetadataDraftRow:
        return next(row for row in self.metadata_rows if row.record_key == record_key)

    def select_timeline_context(self, record_key: str | None) -> None:
        if record_key is not None and not any(row.record_key == record_key and row.include
                                               for row in self.metadata_rows):
            record_key = None
        self.current_timeline_record_key = record_key

    def current_signature(self) -> tuple[object, ...]:
        return (
            tuple((r.record_key, r.include, r.sample_id, r.group, r.notes) for r in self.metadata_rows),
            self.metadata_confirmed,
            tuple(_event_signature(event) for event in self.events), self.timeline_confirmed,
            tuple(sorted((key, tuple(_event_signature(event) for event in override.events),
                          override.confirmed)
                         for key, override in self.sample_timeline_overrides.items())),
            self.tail_fraction, self.analysis_metric, self.calibration_enabled,
            self.calibration_event_ids, self.calibration_x_label, self.calibration_x_unit,
        )

    @property
    def result_status(self) -> str:
        if self.analysis_result is None:
            return "尚未运行分析"
        if self.result_stale:
            return "设置已修改，当前结果已过期，需要重新分析"
        return "分析完成，结果与当前设置一致"

    def _changed(self, *, metadata: bool = False, timeline: bool = False) -> None:
        if metadata:
            self.metadata_confirmed = False
        if timeline:
            if self.current_override is not None:
                self.current_override.confirmed = False
            else:
                self.timeline_confirmed = False
        if self.analysis_result is not None:
            self.result_stale = True
        self._disable_calibration_for_continuous_mode()
        self.set_feedback("info", "设置已修改，请重新确认并运行分析")

    def _disable_calibration_for_continuous_mode(self) -> bool:
        if self.analysis_mode != ITAnalysisMode.CONTINUOUS:
            return False
        changed = bool(self.calibration_enabled or self.calibration_event_ids
                       or self.calibration_x_label or self.calibration_x_unit)
        self.calibration_enabled = False
        self.calibration_event_ids = ()
        self.calibration_x_label = ""
        self.calibration_x_unit = ""
        return changed

    def sync_records(self, records: Iterable[FileRecord]) -> None:
        usable = tuple(r for r in records if r.parse_success and r.experiment_type == "i-t")
        existing = {row.record_key: row for row in self.metadata_rows}
        keys = {record.key for record in usable}
        changed = set(existing) != keys
        self.metadata_rows = [existing.get(record.key) or ITMetadataDraftRow(
            record.key, record.path.name, sample_id=record.path.stem) for record in usable]
        self.sample_timeline_overrides = {
            key: override for key, override in self.sample_timeline_overrides.items() if key in keys
        }
        if self.current_timeline_record_key not in keys:
            self.current_timeline_record_key = None
        if changed:
            self.metadata_confirmed = False
            if self.analysis_result is not None:
                self.result_stale = True
            self.set_feedback("warning", "i-t 文件列表已变化，请检查并确认样本信息"
                              if usable else "尚未导入可分析的 i-t 文件")
        self._disable_calibration_for_continuous_mode()

    def update_metadata(self, record_key: str, field_name: str, value: object) -> None:
        if field_name not in {"include", "sample_id", "group", "notes"}:
            raise ValueError(f"Unsupported i-t metadata field: {field_name}")
        row = self.metadata_row(record_key)
        setattr(row, field_name, bool(value) if field_name == "include" else str(value))
        if not row.include and self.current_timeline_record_key == record_key:
            self.current_timeline_record_key = None
        self._changed(metadata=True)

    def batch_update_metadata(self, record_keys: Iterable[str],
                              edit: ITMetadataBatchEdit) -> None:
        """Validate a multi-row edit completely before changing any row."""

        keys = tuple(dict.fromkeys(record_keys))
        if not keys:
            raise ValueError("请先选择至少一个 i-t 样本。")
        existing = {row.record_key: row for row in self.metadata_rows}
        missing = tuple(key for key in keys if key not in existing)
        if missing:
            raise ValueError("批量编辑包含当前 Workspace 中不存在的样本。")
        if edit.include is not None and not isinstance(edit.include, bool):
            raise ValueError("Include 批量值必须为 True、False 或不修改。")
        if not any((edit.include is not None, edit.update_group, edit.update_notes)):
            raise ValueError("没有选择要批量修改的字段。")
        for key in keys:
            row = existing[key]
            if edit.include is not None:
                row.include = edit.include
            if edit.update_group:
                row.group = str(edit.group)
            if edit.update_notes:
                row.notes = str(edit.notes)
        if self.current_timeline_record_key in keys and not existing[
                self.current_timeline_record_key].include:
            self.current_timeline_record_key = None
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

    def create_sample_override(self, record_key: str) -> SampleTimelineOverride:
        self.metadata_row(record_key)
        if record_key not in self.sample_timeline_overrides:
            self.sample_timeline_overrides[record_key] = SampleTimelineOverride(list(self.events), False)
            self.current_timeline_record_key = record_key
            if self.analysis_result is not None:
                self.result_stale = True
            self.set_feedback("info", "已从默认 Timeline 创建样本专用副本；请编辑并确认")
        return self.sample_timeline_overrides[record_key]

    def restore_default_timeline(self, record_key: str) -> None:
        if self.sample_timeline_overrides.pop(record_key, None) is not None:
            self.current_timeline_record_key = record_key
            if self.analysis_result is not None:
                self.result_stale = True
            self.set_feedback("info", "已恢复使用默认 Timeline；设置已改变，请按需重新分析")

    def _editable_events(self) -> list[Event]:
        if self.current_timeline_is_inherited:
            raise ValueError("当前样本正在使用默认 Timeline。请先创建样本专用 Timeline，或切换到默认 Timeline 编辑。")
        return self.current_events

    def _new_event_id(self) -> str:
        used = {event.event_id for event in self.events}
        used.update(event.event_id for override in self.sample_timeline_overrides.values()
                    for event in override.events)
        while f"event_{self._next_event_number}" in used:
            self._next_event_number += 1
        value = f"event_{self._next_event_number}"
        self._next_event_number += 1
        return value

    def add_event(self, *, time_s: float, name: str, value: float | None = None,
                  unit: str | None = None, notes: str = "", event_id: str | None = None) -> Event:
        target = self._editable_events()
        if not math.isfinite(float(time_s)):
            raise ValueError("Event 时间必须是有限数值。")
        if any(event.time_s == float(time_s) for event in target):
            raise ValueError("Event 时间不能重复；请编辑现有 Event 或选择其他时间。")
        if not name.strip():
            raise ValueError("Event 名称不能为空。")
        event = Event(event_id or self._new_event_id(), float(time_s), name.strip(), value,
                      unit.strip() if unit else None, notes.strip())
        target.append(event)
        target.sort(key=lambda row: row.time_s)
        self._changed(timeline=True)
        return event

    def edit_event(self, event_id: str, **changes: object) -> Event:
        target = self._editable_events()
        old = next(event for event in target if event.event_id == event_id)
        values = {"time_s": old.time_s, "name": old.name, "value": old.value,
                  "unit": old.unit, "notes": old.notes}
        values.update(changes)
        time_s = float(values["time_s"])
        if any(event.event_id != event_id and event.time_s == time_s for event in target):
            raise ValueError("Event 时间不能重复；请编辑现有 Event 或选择其他时间。")
        if not str(values["name"]).strip():
            raise ValueError("Event 名称不能为空。")
        replacement = Event(event_id, time_s, str(values["name"]).strip(), values["value"],
                            str(values["unit"]).strip() if values["unit"] else None,
                            str(values["notes"]).strip())
        target[:] = [replacement if event.event_id == event_id else event for event in target]
        target.sort(key=lambda row: row.time_s)
        self._changed(timeline=True)
        return replacement

    def delete_events(self, event_ids: Iterable[str]) -> None:
        target = self._editable_events()
        removed = set(event_ids)
        if removed:
            target[:] = [event for event in target if event.event_id not in removed]
            if self.current_timeline_record_key is None:
                self.calibration_event_ids = tuple(value for value in self.calibration_event_ids
                                                   if value not in removed)
            self._changed(timeline=True)

    def confirm_timeline(self, records: Iterable[FileRecord]) -> EventTimeline:
        if self.current_timeline_is_inherited:
            raise GUIWorkflowValidationError((
                "当前样本正在继承默认 Timeline；请切换到默认 Timeline 确认，或先创建样本专用 Timeline。",
            ))
        target = self.current_events
        source = "GUI Default Event Timeline"
        start = end = None
        if self.current_timeline_record_key is not None:
            source = f"GUI sample override: {self.current_timeline_record_key}"
            by_key = {record.key: record for record in records}
            record = by_key.get(self.current_timeline_record_key)
            if record is None or not isinstance(record.data, ITData):
                raise GUIWorkflowValidationError(("当前样本专用 Timeline 无法定位对应 i-t record。",))
            start, end = record.data.actual_first_time_s, record.data.actual_last_time_s
        timeline = EventTimeline(tuple(target), True, source)
        try:
            timeline.validate(recording_start_s=start, recording_end_s=end)
        except EventAnalysisError as error:
            raise GUIWorkflowValidationError((str(error),)) from error
        if self.current_override is not None:
            self.current_override.confirmed = True
        else:
            self.timeline_confirmed = True
        self.set_feedback(
            "success",
            (f"{self.timeline_context_status} 已确认：{len(target)} 个 Event"
             if target else f"{self.timeline_context_status} 未定义 Event；Continuous mode 无需确认"),
        )
        return timeline

    def timeline_for_record_key(self, record_key: str) -> EventTimeline:
        override = self.sample_timeline_overrides.get(record_key)
        return (override.timeline(f"GUI sample override: {record_key}")
                if override is not None else self.timeline)

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
        if self.analysis_mode == ITAnalysisMode.CONTINUOUS:
            self._disable_calibration_for_continuous_mode()
            if enabled:
                self.set_feedback("warning", "Continuous mode 不提供 Calibration")
            return
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
        included = tuple(row for row in self.metadata_rows if row.include)
        inputs = tuple(ITEventInput(by_key[row.record_key].data, row.sample_id.strip(),
                                    row.group.strip(), True, row.notes) for row in included)
        timelines = tuple(self.timeline_for_record_key(row.record_key) for row in included)
        mode = self.analysis_mode
        calibration = (CalibrationSelection(self.calibration_event_ids,
                                            self.calibration_x_label,
                                            self.calibration_x_unit)
                       if self.calibration_enabled and mode == ITAnalysisMode.EVENT else None)
        return ITAnalysisRequest(tuple(row.record_key for row in included), inputs, self.timeline,
                                 timelines, self.analysis_metric,
                                 PlateauPolicy(fraction=self.tail_fraction), calibration,
                                 self.current_signature(), mode)

    def accept_result(self, request: ITAnalysisRequest, result: ITEventBatchResult) -> None:
        self.analysis_result = result
        self.result_signature = request.signature
        self.result_stale = self.current_signature() != request.signature
        self.analysis_running = False
        self.validation_errors = ()
        label = "Continuous" if result.mode == ITAnalysisMode.CONTINUOUS else "Event"
        self.set_feedback("success", f"Generic i-t {label} 分析完成")

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
    included = tuple(row for row in workflow.metadata_rows if row.include)
    by_key = {record.key: record for record in records}
    mode = workflow.analysis_mode
    for row in included:
        timeline = workflow.timeline_for_record_key(row.record_key)
        if mode == ITAnalysisMode.EVENT:
            if row.record_key in workflow.sample_timeline_overrides and not timeline.user_confirmed:
                errors.append(f"Sample {row.sample_id.strip() or row.file_name} 的样本专用 Timeline 尚未确认。")
            elif row.record_key not in workflow.sample_timeline_overrides and not workflow.timeline_confirmed:
                errors.append("已定义 Event，但默认 Event Timeline 尚未由用户确认。")
        record = by_key.get(row.record_key)
        if record is None or not isinstance(record.data, ITData):
            errors.append("已确认样本中存在当前 Workspace 无法定位的 i-t 文件。")
        if mode == ITAnalysisMode.EVENT and workflow.calibration_enabled:
            selection = CalibrationSelection(workflow.calibration_event_ids,
                                             workflow.calibration_x_label,
                                             workflow.calibration_x_unit)
            try:
                selection.validate(timeline)
            except EventAnalysisError as error:
                errors.append(f"Sample {row.sample_id.strip() or row.file_name}: {error}")
    try:
        PlateauPolicy(fraction=workflow.tail_fraction).validate()
    except EventAnalysisError as error:
        errors.append(str(error))
    if workflow.analysis_metric not in {"signed", "magnitude"}:
        errors.append("分析指标必须是 signed 或 magnitude。")
    return tuple(dict.fromkeys(errors))


def execute_it_analysis(request: ITAnalysisRequest) -> ITEventBatchResult:
    if request.mode == ITAnalysisMode.CONTINUOUS:
        return analyze_it_continuous_batch(request.inputs, metric=request.metric)
    files = tuple(
        analyze_it_events(item.data, timeline, sample_id=item.sample_id, group=item.group,
                          metric=request.metric, policy=request.policy,
                          calibration_selection=request.calibration_selection)
        for item, timeline in zip(request.inputs, request.record_timelines)
    )
    summaries = summarize_event_responses(row for item in files for row in item.responses)
    return ITEventBatchResult(request.timeline, files, summaries, request.metric,
                              request.calibration_selection)


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


def continuous_display_rows(result: ITEventBatchResult) -> tuple[dict[str, object], ...]:
    return tuple({
        "sample_id": row.sample_id, "group": row.group, "duration_s": row.duration_s,
        "mean_current_uA": row.mean_current_uA, "sd_current_uA": row.sd_current_uA,
        "min_current_uA": row.min_current_uA, "max_current_uA": row.max_current_uA,
        "first_time_s": row.first_time_s, "last_time_s": row.last_time_s,
        "status": row.status,
    } for row in result.continuous_summaries)


def workflow_status_lines(workflow: ITWorkflowState) -> tuple[str, ...]:
    if workflow.analysis_mode == ITAnalysisMode.CONTINUOUS:
        timeline_status = "未定义（Continuous mode）"
    else:
        event_count = len(workflow.events)
        timeline_status = (f"已确认 {event_count} Events" if workflow.timeline_confirmed
                           else "未确认")
    return (
        f"① 样本信息：{'已确认' if workflow.metadata_confirmed else '未确认'}",
        f"② Event Timeline：{timeline_status}；专用 {len(workflow.sample_timeline_overrides)}",
        f"③ 响应设置：尾段 {workflow.tail_fraction:.0%}；{workflow.analysis_metric}",
        f"④ Calibration：{'开启' if workflow.calibration_enabled else '关闭'}",
        f"⑤ 正式分析：{workflow.result_status}",
    )


def result_summary_text(result: ITEventBatchResult) -> str:
    groups = tuple(dict.fromkeys(item.group for item in result.files))
    if result.mode == ITAnalysisMode.CONTINUOUS:
        return (f"✓ Continuous 分析完成｜Files：{len(result.files)}｜"
                f"Groups：{len(groups)}｜Events：0")
    event_ids = tuple(dict.fromkeys(row.event_id for item in result.files for row in item.responses))
    calibration = "开启" if result.calibration_selection is not None else "关闭"
    return (f"✓ 分析完成｜Files：{len(result.files)}｜Events：{len(event_ids)}｜"
            f"Groups：{len(groups)}｜指标：{result.analysis_metric}｜Calibration：{calibration}")


__all__ = ["ITAnalysisCompleted", "ITAnalysisRequest", "ITMetadataBatchEdit",
           "ITMetadataDraftRow", "ITWorkflowState",
           "SampleTimelineOverride", "calibration_display_rows", "execute_it_analysis",
           "continuous_display_rows", "response_display_rows", "result_summary_text", "summary_display_rows",
           "validate_it_workflow", "workflow_status_lines"]
