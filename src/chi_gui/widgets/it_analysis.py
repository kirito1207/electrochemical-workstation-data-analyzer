"""Tkinter panels for the Generic i-t Event workflow."""

from __future__ import annotations

from math import isfinite
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from time import monotonic
from typing import Callable

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from analysis.it_events import ITAnalysisMode
from chi_gui.it_workflow import (ITMetadataBatchEdit, ITWorkflowState,
                                 calibration_display_rows, continuous_display_rows,
                                 response_display_rows, result_summary_text,
                                 summary_display_rows, workflow_status_lines)
from chi_gui.metadata_selection import MetadataSelectionModel
from plotting.it_events import (ITResponseScatterPoint, build_it_calibration_figure,
                                build_it_event_figure, build_it_response_figure)


IT_HOVER_RADIUS_PX = 10.0
FOOTER_MIN_TEXT_WRAP_PX = 180
FOOTER_INITIAL_TEXT_WRAP_PX = 430


def available_it_result_plots(result) -> tuple[str, ...]:
    if result is not None and result.mode == ITAnalysisMode.CONTINUOUS:
        return ("Raw i-t / Continuous",)
    plots = ("Raw + Events", "Event Response")
    has_calibration = result is not None and any(item.calibration is not None for item in result.files)
    return plots + (("Calibration",) if has_calibration else ())


def normalize_it_result_plot(selected: str, result) -> str:
    choices = available_it_result_plots(result)
    return selected if selected in choices else choices[0]


def event_double_click_edits(column: str) -> bool:
    """Event ID is immutable; every other visible Event column opens the row editor."""

    return column in {"#2", "#3", "#4", "#5", "#6"}


def event_display_rows(events) -> tuple[tuple[object, ...], ...]:
    """Return presentation-only indices; Treeview iid remains the real event_id."""

    return tuple((index, event.name, f"{event.time_s:.9g}",
                  "" if event.value is None else f"{event.value:g}",
                  event.unit or "", event.notes)
                 for index, event in enumerate(events, start=1))


def calibration_display_items(events) -> tuple[tuple[str, str], ...]:
    """Map presentation labels to stable event_id without parsing display text."""

    return tuple((event.event_id,
                  f"{display_index} | {event.name} | {event.value:g} {event.unit or ''}")
                 for display_index, event in enumerate(events, start=1)
                 if event.value is not None)


def analysis_footer_wraplength(total_width: int, action_width: int) -> int:
    return max(FOOTER_MIN_TEXT_WRAP_PX, int(total_width) - int(action_width) - 24)


def analysis_run_button_state(*, busy: bool) -> str:
    """Keep reanalysis available for every non-busy workflow state."""

    return "disabled" if busy else "normal"


def nearest_it_response_point(series, axis, event_x: float, event_y: float,
                              radius_px: float = IT_HOVER_RADIUS_PX):
    if not (isfinite(event_x) and isfinite(event_y)):
        return None
    best = None
    best_distance = radius_px * radius_px
    for item in series:
        for point in item.points:
            x, y = axis.transData.transform((point.x, point.value_uA))
            distance = (float(x) - event_x) ** 2 + (float(y) - event_y) ** 2
            if distance <= best_distance and (best is None or distance < best_distance):
                best, best_distance = point, distance
    return best


class ITMetadataBatchDialog(simpledialog.Dialog):
    """Explicit atomic batch edit; Sample ID intentionally remains per-row."""

    def __init__(self, parent, selected_count: int):
        self.selected_count = selected_count
        self.result: ITMetadataBatchEdit | None = None
        super().__init__(parent, title="批量设置选中行")

    def body(self, master):
        ttk.Label(master, text=f"已选择：{self.selected_count} 个样本").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )
        ttk.Label(master, text="Include：").grid(row=1, column=0, sticky="e")
        self.include = tk.StringVar(value="不修改")
        ttk.Combobox(master, textvariable=self.include,
                     values=("不修改", "纳入", "不纳入"), state="readonly", width=12).grid(
            row=1, column=1, sticky="w"
        )
        self.update_group = tk.BooleanVar(value=False)
        ttk.Checkbutton(master, text="修改 Group", variable=self.update_group).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        self.group = tk.StringVar()
        group_entry = ttk.Entry(master, textvariable=self.group, width=28)
        group_entry.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.update_notes = tk.BooleanVar(value=False)
        ttk.Checkbutton(master, text="修改 Notes", variable=self.update_notes).grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )
        self.notes = tk.StringVar()
        ttk.Entry(master, textvariable=self.notes, width=28).grid(
            row=3, column=1, columnspan=2, sticky="ew", pady=(6, 0)
        )
        ttk.Label(master, text="勾选后留空表示清空；未勾选表示不修改。Sample ID 需逐行保持唯一。",
                  foreground="#555555", wraplength=360).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(8, 0)
        )
        return group_entry

    def validate(self):
        if (self.include.get() == "不修改" and not self.update_group.get()
                and not self.update_notes.get()):
            messagebox.showwarning("没有修改", "请至少选择一个要修改的字段。", parent=self)
            return False
        return True

    def apply(self):
        include = {"不修改": None, "纳入": True, "不纳入": False}[self.include.get()]
        self.result = ITMetadataBatchEdit(
            include=include,
            update_group=self.update_group.get(), group=self.group.get(),
            update_notes=self.update_notes.get(), notes=self.notes.get(),
        )


class ITSettingsPanel(ttk.Frame):
    def __init__(self, master, *, on_change: Callable, on_confirm_metadata: Callable,
                 on_confirm_timeline: Callable, on_add_cursor_event: Callable,
                 on_run: Callable):
        super().__init__(master, padding=6)
        self.on_change = on_change
        self.on_confirm_metadata = on_confirm_metadata
        self.on_confirm_timeline = on_confirm_timeline
        self.on_add_cursor_event = on_add_cursor_event
        self.on_run = on_run
        self._state = None
        self._workspace_token = None
        self._selection_model = MetadataSelectionModel()
        self._suppress_edit_until = 0.0
        self._calibration_event_ids_by_index = ()
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        panes = ttk.Panedwindow(self, orient="vertical"); panes.grid(row=0, column=0, sticky="nsew")

        metadata_frame = ttk.LabelFrame(panes, text="① 样本信息")
        metadata_frame.columnconfigure(0, weight=1); metadata_frame.rowconfigure(0, weight=1)
        self.metadata = ttk.Treeview(metadata_frame, columns=("include", "file", "sample", "group", "notes"), show="headings", selectmode="extended", height=5)
        for key, label, width in (("include", "纳入", 55), ("file", "文件", 210),
                                  ("sample", "Sample ID", 130), ("group", "Group", 120),
                                  ("notes", "Notes", 180)):
            self.metadata.heading(key, text=label); self.metadata.column(key, width=width, stretch=key in {"file", "notes"})
        self.metadata.grid(row=0, column=0, sticky="nsew")
        self.metadata.bind("<Double-1>", self._edit_metadata)
        self.metadata.bind("<ButtonPress-1>", self._drag_begin, add="+")
        self.metadata.bind("<B1-Motion>", self._drag_motion, add="+")
        self.metadata.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.metadata.bind("<Control-a>", self._select_all)
        self.metadata.bind("<Control-A>", self._select_all)
        metadata_scroll = ttk.Scrollbar(metadata_frame, orient="vertical", command=self.metadata.yview)
        metadata_scroll.grid(row=0, column=1, sticky="ns")
        metadata_xscroll = ttk.Scrollbar(metadata_frame, orient="horizontal", command=self.metadata.xview)
        metadata_xscroll.grid(row=1, column=0, sticky="ew")
        self.metadata.configure(yscrollcommand=metadata_scroll.set, xscrollcommand=metadata_xscroll.set)
        batch = ttk.Frame(metadata_frame)
        batch.grid(row=2, column=0, columnspan=2, sticky="ew", pady=3)
        ttk.Label(batch, text="批量设置选中行：").pack(side="left")
        ttk.Button(batch, text="全选", command=self.select_all_rows).pack(side="left", padx=(0, 4))
        ttk.Button(batch, text="取消选择", command=self.clear_selection).pack(side="left", padx=(0, 6))
        ttk.Button(batch, text="批量设置选中行", command=self._batch_metadata).pack(side="left")
        ttk.Button(metadata_frame, text="确认样本信息", command=on_confirm_metadata).grid(
            row=3, column=0, columnspan=2, sticky="e", pady=3
        )
        panes.add(metadata_frame, weight=2)

        event_frame = ttk.LabelFrame(panes, text="② Event Timeline（用户明确定义并确认）")
        event_frame.columnconfigure(0, weight=1); event_frame.rowconfigure(1, weight=1)
        context_bar = ttk.Frame(event_frame)
        context_bar.grid(row=0, column=0, columnspan=6, sticky="ew", pady=(2, 4))
        ttk.Label(context_bar, text="应用对象：").pack(side="left")
        self.timeline_context = tk.StringVar(value="默认 Timeline")
        self.timeline_context_combo = ttk.Combobox(
            context_bar, textvariable=self.timeline_context, state="readonly", width=34
        )
        self.timeline_context_combo.pack(side="left")
        self.timeline_context_combo.bind("<<ComboboxSelected>>", self._select_timeline_context)
        self.timeline_context_status = tk.StringVar(value="当前：默认 Timeline")
        ttk.Label(context_bar, textvariable=self.timeline_context_status, foreground="#355f7c").pack(
            side="left", padx=8
        )
        self.create_override_button = ttk.Button(
            context_bar, text="创建样本专用 Timeline", command=self._create_override
        )
        self.create_override_button.pack(side="right")
        self.restore_default_button = ttk.Button(
            context_bar, text="恢复使用默认 Timeline", command=self._restore_default
        )
        self._timeline_context_keys = {}
        self.events = ttk.Treeview(event_frame, columns=("index", "name", "time", "value", "unit", "notes"), show="headings", height=6)
        for key, label, width in (("index", "#", 42), ("name", "Event", 130), ("time", "Time / s", 90),
                                  ("value", "Value", 80), ("unit", "Unit", 70), ("notes", "Notes", 180)):
            self.events.heading(key, text=label); self.events.column(key, width=width, stretch=key in {"name", "notes"})
        self.events.grid(row=1, column=0, columnspan=6, sticky="nsew")
        self.events.bind("<Double-1>", self._double_edit_event)
        ttk.Button(event_frame, text="手动添加", command=self._add_event).grid(row=2, column=0, sticky="w", pady=3)
        ttk.Button(event_frame, text="从当前游标添加草稿", command=on_add_cursor_event).grid(row=2, column=1, sticky="w")
        self.edit_event_button = ttk.Button(event_frame, text="编辑", command=self._edit_event)
        self.edit_event_button.grid(row=2, column=2, sticky="w")
        ttk.Button(event_frame, text="删除", command=self._delete_events).grid(row=2, column=3, sticky="w")
        ttk.Button(event_frame, text="确认 Timeline", command=on_confirm_timeline).grid(row=2, column=5, sticky="e")
        panes.add(event_frame, weight=3)

        settings = ttk.LabelFrame(panes, text="③ 响应设置与 ④ 可选 Calibration")
        self.tail = tk.StringVar(value="0.20"); self.metric = tk.StringVar(value="signed")
        ttk.Label(settings, text="平台尾段比例 (0 < f ≤ 1)：").grid(row=0, column=0, sticky="w")
        ttk.Entry(settings, textvariable=self.tail, width=9).grid(row=0, column=1, sticky="w")
        ttk.Button(settings, text="应用", command=self._set_response).grid(row=0, column=2, sticky="w", padx=3)
        ttk.Label(settings, text="指标：").grid(row=0, column=3, sticky="e")
        ttk.Combobox(settings, textvariable=self.metric, values=("signed", "magnitude"), state="readonly", width=11).grid(row=0, column=4, sticky="w")
        ttk.Label(settings, text="Baseline = 记录起点至首个 Event；每个 Event 的 segment 延续到下一 Event/记录末尾，取尾段样本统计。",
                  foreground="#555555", wraplength=850).grid(row=1, column=0, columnspan=6, sticky="w", pady=3)
        self.calibration_enabled = tk.BooleanVar(value=False)
        self.calibration_toggle = ttk.Checkbutton(
            settings, text="启用 Calibration（仅显式选择有数值且单位一致的 Events）",
            variable=self.calibration_enabled, command=self._set_calibration
        )
        self.calibration_toggle.grid(row=2, column=0, columnspan=3, sticky="w")
        self.x_label = tk.StringVar(); self.x_unit = tk.StringVar()
        ttk.Label(settings, text="x label").grid(row=3, column=0, sticky="e")
        self.x_label_entry = ttk.Entry(settings, textvariable=self.x_label, width=16)
        self.x_label_entry.grid(row=3, column=1, sticky="w")
        ttk.Label(settings, text="x unit").grid(row=3, column=2, sticky="e")
        self.x_unit_entry = ttk.Entry(settings, textvariable=self.x_unit, width=12)
        self.x_unit_entry.grid(row=3, column=3, sticky="w")
        self.calibration_events = tk.Listbox(settings, selectmode="extended", exportselection=False, height=3, width=35)
        self.calibration_events.grid(row=2, column=4, rowspan=2, sticky="ew", padx=5)
        self.calibration_apply = ttk.Button(settings, text="应用 Calibration 设置", command=self._set_calibration)
        self.calibration_apply.grid(row=3, column=5, sticky="w")
        panes.add(settings, weight=2)

        self.footer = ttk.Frame(self)
        self.footer.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.footer.columnconfigure(0, weight=1, minsize=0)
        self.footer.columnconfigure(1, weight=0)
        self.status = tk.StringVar()
        self.status_label = ttk.Label(
            self.footer, textvariable=self.status, foreground="#174a7e", justify="left",
            wraplength=FOOTER_INITIAL_TEXT_WRAP_PX,
        )
        self.status_label.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.feedback = tk.StringVar()
        self.feedback_label = ttk.Label(
            self.footer, textvariable=self.feedback, foreground="#9a4d00", justify="left",
            wraplength=FOOTER_INITIAL_TEXT_WRAP_PX,
        )
        self.feedback_label.grid(row=1, column=0, sticky="ew", padx=(0, 8), pady=(2, 0))
        self.footer_actions = ttk.Frame(self.footer)
        self.footer_actions.grid(row=0, column=1, rowspan=2, sticky="e")
        self.run_button = ttk.Button(
            self.footer_actions, text="开始正式 i-t 分析", command=on_run
        )
        self.run_button.grid(row=0, column=0, sticky="e")
        self.footer.bind("<Configure>", self._footer_resized, add="+")

    def render(self, state: ITWorkflowState, *, busy=False, workspace_token="default"):
        self._state = state
        same_workspace = workspace_token == self._workspace_token
        selected = self.metadata.selection() if same_workspace else ()
        self._workspace_token = workspace_token
        self.metadata.delete(*self.metadata.get_children())
        for row in state.metadata_rows:
            self.metadata.insert("", "end", iid=row.record_key, values=("✓" if row.include else "—", row.file_name, row.sample_id, row.group, row.notes))
        current_keys = tuple(row.record_key for row in state.metadata_rows)
        self._selection_model.reset(current_keys, selected)
        if selected:
            self.metadata.selection_set(self._selection_model.selection())
        contexts = state.included_timeline_contexts
        self._timeline_context_keys = {label: key for key, label in contexts}
        labels = tuple(label for _key, label in contexts)
        self.timeline_context_combo.configure(values=labels)
        selected_label = next((label for key, label in contexts
                               if key == state.current_timeline_record_key), "默认 Timeline")
        self.timeline_context.set(selected_label)
        self.timeline_context_status.set(f"当前：{state.timeline_context_status}")
        self.create_override_button.pack_forget()
        self.restore_default_button.pack_forget()
        if state.current_timeline_record_key is not None:
            if state.current_override is None:
                self.create_override_button.pack(side="right")
            else:
                self.restore_default_button.pack(side="right")
        self.events.delete(*self.events.get_children())
        for event, values in zip(state.current_events, event_display_rows(state.current_events)):
            self.events.insert("", "end", iid=event.event_id, values=values)
        self.tail.set(f"{state.tail_fraction:.6g}"); self.metric.set(state.analysis_metric)
        self.calibration_enabled.set(state.calibration_enabled); self.x_label.set(state.calibration_x_label); self.x_unit.set(state.calibration_x_unit)
        calibration_state = "disabled" if state.analysis_mode == ITAnalysisMode.CONTINUOUS else "normal"
        self.calibration_toggle.configure(state=calibration_state)
        self.x_label_entry.configure(state=calibration_state)
        self.x_unit_entry.configure(state=calibration_state)
        self.calibration_events.configure(state=calibration_state)
        self.calibration_apply.configure(state=calibration_state)
        self.calibration_events.delete(0, "end")
        calibration_items = calibration_display_items(state.events)
        self._calibration_event_ids_by_index = tuple(event_id for event_id, _label in calibration_items)
        for list_index, (event_id, label) in enumerate(calibration_items):
            self.calibration_events.insert("end", label)
            if event_id in state.calibration_event_ids:
                self.calibration_events.selection_set(list_index)
        self.status.set("    ".join(workflow_status_lines(state)))
        self.feedback.set(state.feedback.text)
        self.run_button.configure(state=analysis_run_button_state(busy=busy))

    def _footer_resized(self, event):
        wraplength = analysis_footer_wraplength(
            int(getattr(event, "width", 0)), self.footer_actions.winfo_reqwidth()
        )
        self.status_label.configure(wraplength=wraplength)
        self.feedback_label.configure(wraplength=wraplength)

    def _edit_metadata(self, event):
        if self._state is None or monotonic() < self._suppress_edit_until: return
        key = self.metadata.identify_row(event.y); column = self.metadata.identify_column(event.x)
        field = {"#1": "include", "#3": "sample_id", "#4": "group", "#5": "notes"}.get(column)
        if not key or not field: return
        row = next(row for row in self._state.metadata_rows if row.record_key == key)
        value = not row.include if field == "include" else simpledialog.askstring("编辑 i-t 样本信息", field, initialvalue=getattr(row, field), parent=self)
        if value is not None: self.on_change("metadata", key, field, value)

    def _drag_begin(self, event):
        key = self.metadata.identify_row(event.y)
        self._selection_model.begin_drag(key, event.y, self.metadata.selection())

    def _drag_motion(self, event):
        key = self.metadata.identify_row(event.y)
        selection = self._selection_model.drag_to(key, event.y)
        if selection is None:
            return None
        self.metadata.selection_set(selection)
        if event.y < 20:
            self.metadata.yview_scroll(-1, "units")
        elif event.y > self.metadata.winfo_height() - 20:
            self.metadata.yview_scroll(1, "units")
        return "break"

    def _drag_end(self, _event):
        if self._selection_model.finish_drag():
            self._suppress_edit_until = monotonic() + 0.45

    def _select_all(self, _event=None):
        self.select_all_rows()
        return "break"

    def select_all_rows(self):
        self.metadata.selection_set(self._selection_model.select_all())
        self.metadata.focus_set()

    def clear_selection(self):
        self._selection_model.clear()
        self.metadata.selection_remove(self.metadata.selection())

    def _batch_metadata(self):
        keys = tuple(self.metadata.selection())
        if not keys:
            if self._state is not None:
                self._state.set_feedback("warning", "无法批量设置", ("请先选择至少一个样本。",))
                self.feedback.set(self._state.feedback.text)
            return
        dialog = ITMetadataBatchDialog(self, len(keys))
        if dialog.result is not None:
            self.on_change("batch_metadata", keys, dialog.result)

    def _event_values(self, old=None):
        name = simpledialog.askstring("Event", "Event 名称：", initialvalue=old.name if old else "", parent=self)
        if name is None: return None
        time_text = simpledialog.askstring("Event", "Time / s：", initialvalue=str(old.time_s) if old else "", parent=self)
        if time_text is None: return None
        value_text = simpledialog.askstring("Event", "Value（可空）：", initialvalue="" if old is None or old.value is None else str(old.value), parent=self)
        if value_text is None: return None
        unit = simpledialog.askstring("Event", "Unit（可空）：", initialvalue="" if old is None or old.unit is None else old.unit, parent=self)
        if unit is None: return None
        notes = simpledialog.askstring("Event", "Notes（可空）：", initialvalue="" if old is None else old.notes, parent=self)
        if notes is None: return None
        try: return float(time_text), name, (None if not value_text.strip() else float(value_text)), unit, notes
        except ValueError:
            self._state.set_feedback("warning", "Event 未保存", ("Time 与非空 Value 必须是数值。",)); self.feedback.set(self._state.feedback.text); return None

    def _add_event(self):
        if not self._ensure_editable_context(): return
        values = self._event_values()
        if values is not None: self.on_change("add_event", *values)

    def _edit_event(self):
        if self._state is None or not self.events.selection() or not self._ensure_editable_context(): return
        event = next(row for row in self._state.current_events if row.event_id == self.events.selection()[0])
        values = self._event_values(event)
        if values is not None: self.on_change("edit_event", event.event_id, *values)

    def _double_edit_event(self, event):
        row = self.events.identify_row(event.y)
        column = self.events.identify_column(event.x)
        if row and event_double_click_edits(column):
            self.events.selection_set(row)
            self.events.focus(row)
            self._edit_event()
            return "break"
        return None

    def _select_timeline_context(self, _event=None):
        self.on_change("timeline_context", self._timeline_context_keys.get(self.timeline_context.get()))

    def _create_override(self):
        if self._state is not None and self._state.current_timeline_record_key is not None:
            self.on_change("create_override", self._state.current_timeline_record_key)

    def _restore_default(self):
        if self._state is not None and self._state.current_timeline_record_key is not None:
            self.on_change("restore_default", self._state.current_timeline_record_key)

    def _delete_events(self):
        if self.events.selection() and self._ensure_editable_context():
            self.on_change("delete_events", tuple(self.events.selection()))

    def _ensure_editable_context(self):
        if self._state is not None and self._state.current_timeline_is_inherited:
            self.on_change("inherited_timeline_blocked")
            return False
        return True

    def _set_response(self):
        try: fraction = float(self.tail.get())
        except ValueError:
            if self._state: self._state.set_feedback("warning", "响应设置未更新", ("尾段比例必须是数值。",))
            return
        self.on_change("response", fraction, self.metric.get())

    def _set_calibration(self):
        if self._state is None: return
        ids = tuple(self._calibration_event_ids_by_index[index]
                    for index in self.calibration_events.curselection())
        self.on_change("calibration", self.calibration_enabled.get(), ids, self.x_label.get(), self.x_unit.get())


class ITResultsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=6); self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.status = tk.StringVar(value="尚未运行分析"); ttk.Label(self, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.notebook = ttk.Notebook(self); self.notebook.grid(row=1, column=0, sticky="nsew")
        definitions = {
            "Continuous Summary": (("sample_id", "Sample ID"), ("group", "Group"),
                                   ("duration_s", "Duration / s"),
                                   ("mean_current_uA", "Mean current / µA"),
                                   ("sd_current_uA", "SD / µA"),
                                   ("min_current_uA", "Min / µA"),
                                   ("max_current_uA", "Max / µA"),
                                   ("first_time_s", "First time / s"),
                                   ("last_time_s", "Last time / s"),
                                   ("status", "Status")),
            "Event Response": (("sample_id", "Sample ID"), ("group", "Group"), ("event", "Event"), ("time_s", "Time/s"), ("baseline_mean", "Baseline mean"), ("response_mean", "Response mean"), ("signed_delta", "Signed ΔI"), ("magnitude", "Magnitude"), ("response_sd", "Response SD"), ("window_start", "Window start"), ("window_end", "Window end"), ("status", "Status")),
            "Event Summary": (("group", "Group"), ("event", "Event"), ("n", "n"), ("mean", "Mean"), ("sd", "SD"), ("sem", "SEM"), ("cv_percent", "CV%")),
            "Calibration": (("sample_id", "Sample ID"), ("metric", "Metric"), ("x_label", "x label"), ("x_unit", "x unit"), ("slope", "Slope"), ("intercept", "Intercept"), ("r_squared", "R²"), ("events", "Events"), ("method", "Method")),
        }
        self.tables = {}; self.table_messages = {}; self.table_frames = {}
        for title, columns in definitions.items():
            frame = ttk.Frame(self.notebook); frame.columnconfigure(0, weight=1); frame.rowconfigure(1, weight=1)
            message = tk.StringVar()
            ttk.Label(frame, textvariable=message, foreground="#355f7c").grid(row=0, column=0, sticky="w")
            tree = ttk.Treeview(frame, columns=tuple(key for key, _ in columns), show="headings")
            for key, label in columns: tree.heading(key, text=label); tree.column(key, width=105, stretch=True)
            tree.grid(row=1, column=0, sticky="nsew"); ttk.Scrollbar(frame, orient="horizontal", command=tree.xview).grid(row=2, column=0, sticky="ew")
            self.notebook.add(frame, text=title); self.tables[title] = tree
            self.table_messages[title] = message; self.table_frames[title] = frame
        warnings_frame = ttk.Frame(self.notebook); warnings_frame.columnconfigure(0, weight=1); warnings_frame.rowconfigure(0, weight=1)
        self.warnings = tk.Text(warnings_frame, wrap="word"); self.warnings.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(warnings_frame, text="Warnings / QC")
        self.notebook.tab(self.table_frames["Continuous Summary"], state="hidden")

    def render(self, state: ITWorkflowState):
        self.status.set(result_summary_text(state.analysis_result) if state.analysis_result else state.result_status)
        getters = (("Continuous Summary", continuous_display_rows),
                   ("Event Response", response_display_rows),
                   ("Event Summary", summary_display_rows),
                   ("Calibration", calibration_display_rows))
        for title, getter in getters:
            tree = self.tables[title]; tree.delete(*tree.get_children())
            if state.analysis_result:
                for index, row in enumerate(getter(state.analysis_result)): tree.insert("", "end", iid=str(index), values=tuple(row.values()))
        continuous = bool(state.analysis_result and
                          state.analysis_result.mode == ITAnalysisMode.CONTINUOUS)
        self.notebook.tab(self.table_frames["Continuous Summary"],
                          state="normal" if continuous else "hidden")
        for title in ("Event Response", "Event Summary", "Calibration"):
            self.notebook.tab(self.table_frames[title], state="hidden" if continuous else "normal")
        self.table_messages["Calibration"].set(
            "" if state.analysis_result and any(item.calibration is not None for item in state.analysis_result.files)
            else "本次分析未启用 Calibration。" if state.analysis_result else "尚未运行分析"
        )
        self.warnings.delete("1.0", "end")
        if state.analysis_result:
            lines = [
                "原始 i-t 不平滑；Continuous Summary 使用完整 record。"
                if continuous else
                "原始 i-t 不平滑；Unavailable rows 保留；Calibration 仅使用用户显式选择的 Events。"
            ]
            lines.extend(warning for item in state.analysis_result.files for warning in item.warnings)
            if state.result_stale: lines.insert(0, "设置已修改：当前结果已过期，禁止导出。")
            self.warnings.insert("1.0", "\n".join(lines))


class ITResultPlotPanel(ttk.Frame):
    def __init__(self, master, *, on_export: Callable, on_open_folder: Callable):
        super().__init__(master, padding=6); self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.state = None; self.figure = None; self.canvas = None; self.series = (); self.annotation = None
        toolbar = ttk.Frame(self); toolbar.grid(row=0, column=0, sticky="ew")
        self.plot_type = tk.StringVar(value="Raw + Events")
        self.plot_combo = ttk.Combobox(toolbar, textvariable=self.plot_type, state="readonly", width=20)
        self.plot_combo.pack(side="left"); self.plot_combo.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        ttk.Button(toolbar, text="导出当前完整分析结果", command=on_export).pack(side="right")
        ttk.Button(toolbar, text="打开结果文件夹", command=on_open_folder).pack(side="right", padx=5)
        self.host = ttk.Frame(self); self.host.grid(row=1, column=0, sticky="nsew")
        self.export_status = tk.StringVar(); ttk.Label(self, textvariable=self.export_status).grid(row=2, column=0, sticky="w")

    def render(self, state: ITWorkflowState | None):
        self.state = state
        for child in self.host.winfo_children():
            child.destroy()
        self.canvas = None
        if self.figure: plt.close(self.figure); self.figure = None
        self.series = (); self.annotation = None
        self.export_status.set(f"最近导出：{state.last_export_directory}" if state and state.last_export_directory else "尚未导出")
        if state is None or state.analysis_result is None:
            self.plot_combo.configure(values=available_it_result_plots(None))
            self.plot_type.set("Raw + Events")
            ttk.Label(self.host, text="完成正式 i-t 分析后可查看结果图。", padding=12).pack(); return
        choices = available_it_result_plots(state.analysis_result)
        self.plot_combo.configure(values=choices)
        kind = normalize_it_result_plot(state.selected_result_plot, state.analysis_result)
        state.selected_result_plot = kind
        self.plot_type.set(kind)
        if kind == "Event Response": self.figure, self.series = build_it_response_figure(state.analysis_result, include_hover_metadata=True)
        elif kind == "Calibration": self.figure = build_it_calibration_figure(state.analysis_result)
        else: self.figure = build_it_event_figure(state.analysis_result)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.host)
        if self.series:
            axis = self.figure.axes[0]; self.annotation = axis.annotate("", xy=(0, 0), xytext=(9, 9), textcoords="offset points", bbox={"boxstyle": "round", "fc": "white", "alpha": .92})
            self.annotation.set_visible(False); self.canvas.mpl_connect("motion_notify_event", self._hover)
        self.canvas.draw_idle(); self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _changed(self):
        if self.state: self.state.selected_result_plot = self.plot_type.get()
        self.render(self.state)

    def _hover(self, event):
        if not self.annotation or not self.canvas: return
        point = nearest_it_response_point(self.series, self.figure.axes[0], float(event.x), float(event.y)) if event.inaxes is self.figure.axes[0] and event.x is not None and event.y is not None else None
        if point:
            self.annotation.xy = (point.x, point.value_uA); self.annotation.set_text(f"{point.sample_id}\n{point.group}\n{point.event_name}: {point.value_uA:.4g} µA"); self.annotation.set_visible(True)
        else: self.annotation.set_visible(False)
        self.canvas.draw_idle()


__all__ = ["ITResultPlotPanel", "ITResultsPanel", "ITSettingsPanel",
           "analysis_footer_wraplength", "analysis_run_button_state", "available_it_result_plots",
           "calibration_display_items", "event_display_rows", "event_double_click_edits",
           "nearest_it_response_point", "normalize_it_result_plot"]
