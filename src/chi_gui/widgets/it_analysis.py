"""Tkinter panels for the Generic i-t Event workflow."""

from __future__ import annotations

from math import isfinite
import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable

import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from chi_gui.it_workflow import (ITWorkflowState, calibration_display_rows,
                                 response_display_rows, result_summary_text, summary_display_rows,
                                 workflow_status_lines)
from plotting.it_events import (ITResponseScatterPoint, build_it_calibration_figure,
                                build_it_event_figure, build_it_response_figure)


IT_HOVER_RADIUS_PX = 10.0


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
        self.columnconfigure(0, weight=1); self.rowconfigure(0, weight=1)
        panes = ttk.Panedwindow(self, orient="vertical"); panes.grid(row=0, column=0, sticky="nsew")

        metadata_frame = ttk.LabelFrame(panes, text="① 样本信息（i-t 不使用 Bare / Material）")
        metadata_frame.columnconfigure(0, weight=1); metadata_frame.rowconfigure(0, weight=1)
        self.metadata = ttk.Treeview(metadata_frame, columns=("include", "file", "sample", "group", "notes"), show="headings", height=5)
        for key, label, width in (("include", "纳入", 55), ("file", "文件", 210),
                                  ("sample", "Sample ID", 130), ("group", "Group", 120),
                                  ("notes", "Notes", 180)):
            self.metadata.heading(key, text=label); self.metadata.column(key, width=width, stretch=key in {"file", "notes"})
        self.metadata.grid(row=0, column=0, sticky="nsew")
        self.metadata.bind("<Double-1>", self._edit_metadata)
        ttk.Scrollbar(metadata_frame, orient="horizontal", command=self.metadata.xview).grid(row=1, column=0, sticky="ew")
        ttk.Button(metadata_frame, text="确认样本信息", command=on_confirm_metadata).grid(row=2, column=0, sticky="e", pady=3)
        panes.add(metadata_frame, weight=2)

        event_frame = ttk.LabelFrame(panes, text="② Event Timeline（用户明确定义并确认）")
        event_frame.columnconfigure(0, weight=1); event_frame.rowconfigure(0, weight=1)
        self.events = ttk.Treeview(event_frame, columns=("id", "name", "time", "value", "unit", "notes"), show="headings", height=6)
        for key, label, width in (("id", "Event ID", 90), ("name", "Event", 130), ("time", "Time / s", 90),
                                  ("value", "Value", 80), ("unit", "Unit", 70), ("notes", "Notes", 180)):
            self.events.heading(key, text=label); self.events.column(key, width=width, stretch=key in {"name", "notes"})
        self.events.grid(row=0, column=0, columnspan=6, sticky="nsew")
        ttk.Button(event_frame, text="手动添加", command=self._add_event).grid(row=1, column=0, sticky="w", pady=3)
        ttk.Button(event_frame, text="从当前游标添加草稿", command=on_add_cursor_event).grid(row=1, column=1, sticky="w")
        ttk.Button(event_frame, text="编辑", command=self._edit_event).grid(row=1, column=2, sticky="w")
        ttk.Button(event_frame, text="删除", command=self._delete_events).grid(row=1, column=3, sticky="w")
        ttk.Button(event_frame, text="确认 Timeline", command=on_confirm_timeline).grid(row=1, column=5, sticky="e")
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
        ttk.Checkbutton(settings, text="启用 Calibration（仅显式选择有数值且单位一致的 Events）",
                        variable=self.calibration_enabled, command=self._set_calibration).grid(row=2, column=0, columnspan=3, sticky="w")
        self.x_label = tk.StringVar(); self.x_unit = tk.StringVar()
        ttk.Label(settings, text="x label").grid(row=3, column=0, sticky="e"); ttk.Entry(settings, textvariable=self.x_label, width=16).grid(row=3, column=1, sticky="w")
        ttk.Label(settings, text="x unit").grid(row=3, column=2, sticky="e"); ttk.Entry(settings, textvariable=self.x_unit, width=12).grid(row=3, column=3, sticky="w")
        self.calibration_events = tk.Listbox(settings, selectmode="extended", exportselection=False, height=3, width=35)
        self.calibration_events.grid(row=2, column=4, rowspan=2, sticky="ew", padx=5)
        ttk.Button(settings, text="应用 Calibration 设置", command=self._set_calibration).grid(row=3, column=5, sticky="w")
        panes.add(settings, weight=2)

        footer = ttk.Frame(self); footer.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        self.status = tk.StringVar(); ttk.Label(footer, textvariable=self.status, foreground="#174a7e", justify="left").pack(side="left", fill="x", expand=True)
        self.feedback = tk.StringVar(); ttk.Label(footer, textvariable=self.feedback, foreground="#9a4d00", wraplength=560).pack(side="left", padx=6)
        self.run_button = ttk.Button(footer, text="开始正式 i-t Event 分析", command=on_run); self.run_button.pack(side="right")

    def render(self, state: ITWorkflowState, *, busy=False, workspace_token="default"):
        self._state = state
        self.metadata.delete(*self.metadata.get_children())
        for row in state.metadata_rows:
            self.metadata.insert("", "end", iid=row.record_key, values=("✓" if row.include else "—", row.file_name, row.sample_id, row.group, row.notes))
        self.events.delete(*self.events.get_children())
        for event in state.events:
            self.events.insert("", "end", iid=event.event_id, values=(event.event_id, event.name, f"{event.time_s:.9g}",
                               "" if event.value is None else f"{event.value:g}", event.unit or "", event.notes))
        self.tail.set(f"{state.tail_fraction:.6g}"); self.metric.set(state.analysis_metric)
        self.calibration_enabled.set(state.calibration_enabled); self.x_label.set(state.calibration_x_label); self.x_unit.set(state.calibration_x_unit)
        self.calibration_events.delete(0, "end")
        numeric = [event for event in state.events if event.value is not None]
        for index, event in enumerate(numeric):
            self.calibration_events.insert("end", f"{event.event_id} | {event.name} | {event.value:g} {event.unit or ''}")
            if event.event_id in state.calibration_event_ids:
                self.calibration_events.selection_set(index)
        self.status.set("    ".join(workflow_status_lines(state)))
        self.feedback.set(state.feedback.text)
        self.run_button.configure(state="disabled" if busy else "normal")

    def _edit_metadata(self, event):
        if self._state is None: return
        key = self.metadata.identify_row(event.y); column = self.metadata.identify_column(event.x)
        field = {"#1": "include", "#3": "sample_id", "#4": "group", "#5": "notes"}.get(column)
        if not key or not field: return
        row = next(row for row in self._state.metadata_rows if row.record_key == key)
        value = not row.include if field == "include" else simpledialog.askstring("编辑 i-t 样本信息", field, initialvalue=getattr(row, field), parent=self)
        if value is not None: self.on_change("metadata", key, field, value)

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
        values = self._event_values()
        if values is not None: self.on_change("add_event", *values)

    def _edit_event(self):
        if self._state is None or not self.events.selection(): return
        event = next(row for row in self._state.events if row.event_id == self.events.selection()[0])
        values = self._event_values(event)
        if values is not None: self.on_change("edit_event", event.event_id, *values)

    def _delete_events(self):
        if self.events.selection(): self.on_change("delete_events", tuple(self.events.selection()))

    def _set_response(self):
        try: fraction = float(self.tail.get())
        except ValueError:
            if self._state: self._state.set_feedback("warning", "响应设置未更新", ("尾段比例必须是数值。",))
            return
        self.on_change("response", fraction, self.metric.get())

    def _set_calibration(self):
        if self._state is None: return
        numeric = [event for event in self._state.events if event.value is not None]
        ids = tuple(numeric[index].event_id for index in self.calibration_events.curselection())
        self.on_change("calibration", self.calibration_enabled.get(), ids, self.x_label.get(), self.x_unit.get())


class ITResultsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=6); self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.status = tk.StringVar(value="尚未运行分析"); ttk.Label(self, textvariable=self.status).grid(row=0, column=0, sticky="w")
        self.notebook = ttk.Notebook(self); self.notebook.grid(row=1, column=0, sticky="nsew")
        definitions = {
            "Event Response": (("sample_id", "Sample ID"), ("group", "Group"), ("event", "Event"), ("time_s", "Time/s"), ("baseline_mean", "Baseline mean"), ("response_mean", "Response mean"), ("signed_delta", "Signed ΔI"), ("magnitude", "Magnitude"), ("response_sd", "Response SD"), ("window_start", "Window start"), ("window_end", "Window end"), ("status", "Status")),
            "Event Summary": (("group", "Group"), ("event", "Event"), ("n", "n"), ("mean", "Mean"), ("sd", "SD"), ("sem", "SEM"), ("cv_percent", "CV%")),
            "Calibration": (("sample_id", "Sample ID"), ("metric", "Metric"), ("x_label", "x label"), ("x_unit", "x unit"), ("slope", "Slope"), ("intercept", "Intercept"), ("r_squared", "R²"), ("events", "Events"), ("method", "Method")),
        }
        self.tables = {}
        for title, columns in definitions.items():
            frame = ttk.Frame(self.notebook); frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
            tree = ttk.Treeview(frame, columns=tuple(key for key, _ in columns), show="headings")
            for key, label in columns: tree.heading(key, text=label); tree.column(key, width=105, stretch=True)
            tree.grid(row=0, column=0, sticky="nsew"); ttk.Scrollbar(frame, orient="horizontal", command=tree.xview).grid(row=1, column=0, sticky="ew")
            self.notebook.add(frame, text=title); self.tables[title] = tree
        warnings_frame = ttk.Frame(self.notebook); warnings_frame.columnconfigure(0, weight=1); warnings_frame.rowconfigure(0, weight=1)
        self.warnings = tk.Text(warnings_frame, wrap="word"); self.warnings.grid(row=0, column=0, sticky="nsew")
        self.notebook.add(warnings_frame, text="Warnings / QC")

    def render(self, state: ITWorkflowState):
        self.status.set(result_summary_text(state.analysis_result) if state.analysis_result else state.result_status)
        getters = (("Event Response", response_display_rows), ("Event Summary", summary_display_rows), ("Calibration", calibration_display_rows))
        for title, getter in getters:
            tree = self.tables[title]; tree.delete(*tree.get_children())
            if state.analysis_result:
                for index, row in enumerate(getter(state.analysis_result)): tree.insert("", "end", iid=str(index), values=tuple(row.values()))
        self.warnings.delete("1.0", "end")
        if state.analysis_result:
            lines = ["原始 i-t 不平滑；Unavailable rows 保留；Calibration 仅使用用户显式选择的 Events。"]
            lines.extend(warning for item in state.analysis_result.files for warning in item.warnings)
            if state.result_stale: lines.insert(0, "设置已修改：当前结果已过期，禁止导出。")
            self.warnings.insert("1.0", "\n".join(lines))


class ITResultPlotPanel(ttk.Frame):
    def __init__(self, master, *, on_export: Callable, on_open_folder: Callable):
        super().__init__(master, padding=6); self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.state = None; self.figure = None; self.canvas = None; self.series = (); self.annotation = None
        toolbar = ttk.Frame(self); toolbar.grid(row=0, column=0, sticky="ew")
        self.plot_type = tk.StringVar(value="Raw + Events")
        combo = ttk.Combobox(toolbar, textvariable=self.plot_type, state="readonly", values=("Raw + Events", "Event Response", "Calibration"), width=20)
        combo.pack(side="left"); combo.bind("<<ComboboxSelected>>", lambda _e: self._changed())
        ttk.Button(toolbar, text="导出当前完整分析结果", command=on_export).pack(side="right")
        ttk.Button(toolbar, text="打开结果文件夹", command=on_open_folder).pack(side="right", padx=5)
        self.host = ttk.Frame(self); self.host.grid(row=1, column=0, sticky="nsew")
        self.export_status = tk.StringVar(); ttk.Label(self, textvariable=self.export_status).grid(row=2, column=0, sticky="w")

    def render(self, state: ITWorkflowState | None):
        self.state = state
        if self.canvas: self.canvas.get_tk_widget().destroy(); self.canvas = None
        if self.figure: plt.close(self.figure); self.figure = None
        self.series = (); self.annotation = None
        self.export_status.set(f"最近导出：{state.last_export_directory}" if state and state.last_export_directory else "尚未导出")
        if state is None or state.analysis_result is None:
            ttk.Label(self.host, text="完成正式 i-t Event 分析后可查看结果图。", padding=12).pack(); return
        kind = state.selected_result_plot; self.plot_type.set(kind)
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


__all__ = ["ITResultPlotPanel", "ITResultsPanel", "ITSettingsPanel", "nearest_it_response_point"]
