"""Compact Stage 5.2 Generic LSV workflow widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk
from time import monotonic
from typing import Callable

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from chi_gui.lsv_workflow import (
    ComparisonDraft,
    ComparisonEditorDraft,
    LSVWorkflowState,
    comparison_display_rows,
    descriptive_display_rows,
    mad_result_status,
    outlier_display_rows,
    result_summary_text,
    sign_qc_display_rows,
    sign_qc_result_status,
    workflow_status_lines,
)
from chi_gui.metadata_selection import MetadataSelectionModel
from plotting.lsv_mean import build_mean_lsv_figure
from plotting.lsv_raw import build_raw_lsv_figure
from plotting.repeatability import build_repeatability_figure
from plotting.selected_potential import build_selected_potential_figure


PLOT_LABELS = {
    "Raw curves": "原始曲线",
    "Mean ± SD": "均值 ± SD",
    "Mean overlay": "组均值叠加",
    "Selected magnitude": "指定电位 |I|",
    "Selected signed": "指定电位 Signed I",
    "Repeatability CV%": "重复性 CV%",
}
PLOT_KEYS = {label: key for key, label in PLOT_LABELS.items()}


class LSVSettingsPanel(ttk.Frame):
    """Editable user metadata, analysis settings and declared comparisons."""

    def __init__(self, master, *, on_change: Callable, on_confirm: Callable,
                 on_run: Callable, on_use_cursor: Callable):
        super().__init__(master, padding=6)
        self.on_change = on_change
        self.on_confirm = on_confirm
        self.on_run = on_run
        self.on_use_cursor = on_use_cursor
        self._state: LSVWorkflowState | None = None
        self._workspace_token: str | None = None
        self._editor_draft = ComparisonEditorDraft()
        self._selection_model = MetadataSelectionModel()
        self._suppress_edit_until = 0.0
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=3)
        self.rowconfigure(3, weight=2)

        ttk.Label(self, text="样本信息（自动识别仅为建议；正式分析前必须确认）").grid(row=0, column=0, sticky="w")
        columns = ("include", "file", "sample", "group", "electrode", "notes")
        self.metadata = ttk.Treeview(self, columns=columns, show="headings", selectmode="extended", height=9)
        headings = (("include", "纳入"), ("file", "文件"), ("sample", "Sample ID"),
                    ("group", "Group"), ("electrode", "电极类型"), ("notes", "备注"))
        for key, label in headings:
            self.metadata.heading(key, text=label)
        self.metadata.column("include", width=48, stretch=False, anchor="center")
        self.metadata.column("file", width=260)
        self.metadata.column("sample", width=95)
        self.metadata.column("group", width=100)
        self.metadata.column("electrode", width=90)
        self.metadata.column("notes", width=180)
        self.metadata.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.metadata.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.metadata.configure(yscrollcommand=scroll.set)
        self.metadata.bind("<Double-1>", self._edit_metadata)
        self.metadata.bind("<ButtonPress-1>", self._drag_begin, add="+")
        self.metadata.bind("<B1-Motion>", self._drag_motion, add="+")
        self.metadata.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.metadata.bind("<Control-a>", self._select_all)
        self.metadata.bind("<Control-A>", self._select_all)

        batch = ttk.Frame(self)
        batch.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        ttk.Label(batch, text="批量设置选中行：").pack(side="left")
        ttk.Button(batch, text="全选", command=self.select_all_rows).pack(side="left", padx=(0, 4))
        ttk.Button(batch, text="取消选择", command=self.clear_selection).pack(side="left", padx=(0, 6))
        self.batch_group = ttk.Entry(batch, width=12)
        self.batch_group.pack(side="left", padx=3)
        ttk.Button(batch, text="设置 Group", command=lambda: self._batch("group", self.batch_group.get())).pack(side="left")
        self.batch_electrode = ttk.Combobox(batch, values=("Material", "Bare"), width=10, state="readonly")
        self.batch_electrode.set("Material")
        self.batch_electrode.pack(side="left", padx=(10, 3))
        ttk.Button(batch, text="设置电极类型", command=lambda: self._batch("electrode_type", self.batch_electrode.get())).pack(side="left")

        lower = ttk.Panedwindow(self, orient="horizontal")
        lower.grid(row=3, column=0, columnspan=2, sticky="nsew")
        settings = ttk.LabelFrame(lower, text="分析设置", padding=6)
        lower.add(settings, weight=1)
        self.target = tk.StringVar(value="0.000")
        self.metric = tk.StringVar(value="magnitude")
        ttk.Label(settings, text="分析电位 / V").grid(row=0, column=0, sticky="w")
        target_entry = ttk.Entry(settings, textvariable=self.target, width=12)
        target_entry.grid(row=0, column=1, sticky="w", padx=5)
        target_entry.bind("<Return>", lambda _event: self._set_target())
        ttk.Button(settings, text="应用", command=self._set_target).grid(row=0, column=2)
        ttk.Button(settings, text="使用当前游标电位", command=self.on_use_cursor).grid(row=1, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Radiobutton(settings, text="绝对电流幅值 magnitude", value="magnitude", variable=self.metric,
                        command=self._set_metric).grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Radiobutton(settings, text="有符号电流 signed", value="signed", variable=self.metric,
                        command=self._set_metric).grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Label(settings, text="MAD 仅标记、不删除；Bootstrap ≥ 5000；默认全部纳入",
                  foreground="#555555", wraplength=300).grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(settings, text="Group 表示实验条件；Material / Bare 由电极类型单独指定。\n同一实验条件的 Bare 和 Material 可以使用同一个 Group。",
                  foreground="#555555", wraplength=320).grid(row=5, column=0, columnspan=3, sticky="w", pady=(5, 0))

        comparisons = ttk.LabelFrame(lower, text="用户定义比较", padding=6)
        lower.add(comparisons, weight=2)
        self.comparison_tree = ttk.Treeview(comparisons, columns=("left", "right", "role", "family", "name"), show="headings", height=5)
        for key, label, width in (("left", "左组", 70), ("right", "右组", 70), ("role", "角色", 90),
                                  ("family", "Holm Family", 100), ("name", "名称", 120)):
            self.comparison_tree.heading(key, text=label)
            self.comparison_tree.column(key, width=width)
        self.comparison_tree.grid(row=0, column=0, columnspan=6, sticky="nsew")
        comparisons.columnconfigure(5, weight=1)
        self.left = ttk.Combobox(comparisons, width=10, state="readonly")
        self.right = ttk.Combobox(comparisons, width=10, state="readonly")
        self.role = ttk.Combobox(comparisons, values=("Primary", "Exploratory"), width=11, state="readonly")
        self.role.set("Primary")
        self.family = ttk.Entry(comparisons, width=11)
        self.family.insert(0, "primary")
        self.comparison_name = ttk.Entry(comparisons, width=14)
        for index, widget in enumerate((self.left, self.right, self.role, self.family, self.comparison_name)):
            widget.grid(row=1, column=index, padx=(0, 3), pady=(4, 0), sticky="w")
        ttk.Button(comparisons, text="添加", command=self._add_comparison).grid(row=1, column=5, sticky="w")
        ttk.Button(comparisons, text="删除选中", command=self._delete_comparison).grid(row=2, column=5, sticky="w", pady=3)
        self.comparison_help = tk.StringVar()
        ttk.Label(comparisons, textvariable=self.comparison_help, foreground="#555555", wraplength=520).grid(
            row=2, column=0, columnspan=5, sticky="w", pady=3
        )

        footer = ttk.Frame(self)
        footer.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        feedback = ttk.Frame(footer)
        feedback.pack(side="left", fill="both", expand=True)
        self.workflow_status = tk.StringVar(value="① 样本信息：未确认")
        ttk.Label(feedback, textvariable=self.workflow_status, foreground="#174a7e", justify="left").pack(anchor="w")
        self.feedback = tk.StringVar(value="⚠ 样本信息尚未确认")
        self.feedback_label = ttk.Label(feedback, textvariable=self.feedback, foreground="#9a4d00",
                                        justify="left", wraplength=720)
        self.feedback_label.pack(anchor="w", pady=(3, 0))
        self.confirm_button = ttk.Button(footer, text="确认样本信息", command=self.on_confirm)
        self.confirm_button.pack(side="right", padx=4)
        self.run_button = ttk.Button(footer, text="开始正式分析", command=self.on_run)
        self.run_button.pack(side="right")

    def render(self, state: LSVWorkflowState, *, busy: bool = False,
               workspace_token: str = "default") -> None:
        self._state = state
        same_workspace = workspace_token == self._workspace_token
        selected = self.metadata.selection() if same_workspace else ()
        self._workspace_token = workspace_token
        self.target.set(f"{state.target_potential_V:.6g}")
        self.metric.set(state.analysis_metric)
        self.metadata.delete(*self.metadata.get_children())
        for row in state.metadata_rows:
            incomplete = row.include and (
                not row.sample_id.strip() or not row.group.strip()
                or row.electrode_type not in {"Material", "Bare"}
            )
            display = lambda value: value if value else ("未设置" if row.include else "—")
            self.metadata.insert("", "end", iid=row.record_key, tags=(("incomplete",) if incomplete else ()),
                                 values=("✓" if row.include else "—", row.file_name,
                                         display(row.sample_id), display(row.group),
                                         display(row.electrode_type), row.notes))
        self.metadata.tag_configure("incomplete", background="#fff6dc", foreground="#765a00")
        current_keys = tuple(row.record_key for row in state.metadata_rows)
        self._selection_model.reset(current_keys, selected)
        if selected:
            self.metadata.selection_set(self._selection_model.selection())
        groups = state.comparison_groups
        self.left.configure(values=groups)
        self.right.configure(values=groups)
        self._editor_draft.left_group = self.left.get()
        self._editor_draft.right_group = self.right.get()
        self._editor_draft.role = self.role.get() or "Primary"
        self._editor_draft.holm_family = self.family.get()
        self._editor_draft.name = self.comparison_name.get()
        self._editor_draft.synchronize(workspace_token, groups)
        self._apply_editor_draft()
        self.comparison_tree.delete(*self.comparison_tree.get_children())
        for index, item in enumerate(state.comparisons):
            self.comparison_tree.insert("", "end", iid=str(index), values=(item.left_group, item.right_group,
                                        item.role, item.holm_family, item.name))
        self.workflow_status.set("    ".join(workflow_status_lines(state)))
        self.feedback.set(state.feedback.text or "⚠ 样本信息尚未确认")
        self.feedback_label.configure(
            foreground="#177245" if state.feedback.level == "success" else "#174a7e"
            if state.feedback.level in {"info", "busy"} else "#9a4d00"
        )
        self.comparison_help.set(
            "当前仅 1 个 Material Group，可进行组内描述统计；≥2 个 Group 时可添加组间比较。"
            if len(groups) == 1 else
            "Primary：预先计划的主要比较；同一 Holm Family 的 Primary Welch p 进行 Holm 校正。"
        )
        button_state = "disabled" if busy else "normal"
        self.confirm_button.configure(state=button_state)
        self.run_button.configure(state=button_state)

    def _edit_metadata(self, event) -> None:
        if self._state is None or monotonic() < self._suppress_edit_until:
            return
        item = self.metadata.identify_row(event.y)
        column = self.metadata.identify_column(event.x)
        mapping = {"#1": "include", "#3": "sample_id", "#4": "group", "#5": "electrode_type", "#6": "notes"}
        field = mapping.get(column)
        if not item or not field:
            return
        row = next(row for row in self._state.metadata_rows if row.record_key == item)
        if field == "include":
            value = not row.include
        elif field == "electrode_type":
            value = "Bare" if row.electrode_type == "Material" else "Material"
        else:
            value = simpledialog.askstring("编辑样本信息", field, initialvalue=getattr(row, field), parent=self)
            if value is None:
                return
        self.on_change("metadata", item, field, value)

    def _batch(self, field: str, value: str) -> None:
        keys = self.metadata.selection()
        if keys:
            self.on_change("batch", tuple(keys), field, value)

    def _set_target(self) -> None:
        try:
            value = float(self.target.get())
        except ValueError:
            self.status.set("分析电位必须是数值")
            return
        self.on_change("target", value)

    def _set_metric(self) -> None:
        self.on_change("metric", self.metric.get())

    def _add_comparison(self) -> None:
        draft = ComparisonDraft(self.left.get(), self.right.get(), self.role.get(), self.family.get(), self.comparison_name.get())
        self.on_change("add_comparison", draft)
        self._editor_draft.clear_after_commit()
        self._apply_editor_draft()

    def _delete_comparison(self) -> None:
        indices = tuple(int(item) for item in self.comparison_tree.selection())
        if indices:
            self.on_change("delete_comparisons", indices)

    def _apply_editor_draft(self) -> None:
        self.left.set(self._editor_draft.left_group)
        self.right.set(self._editor_draft.right_group)
        self.role.set(self._editor_draft.role)
        self.family.delete(0, "end"); self.family.insert(0, self._editor_draft.holm_family)
        self.comparison_name.delete(0, "end"); self.comparison_name.insert(0, self._editor_draft.name)

    def _drag_begin(self, event) -> None:
        key = self.metadata.identify_row(event.y)
        self._selection_model.begin_drag(key, event.y, self.metadata.selection())

    def _drag_motion(self, event) -> str | None:
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

    def _drag_end(self, _event) -> None:
        if self._selection_model.finish_drag():
            self._suppress_edit_until = monotonic() + 0.45

    def _select_all(self, _event=None) -> str:
        self.select_all_rows()
        return "break"

    def select_all_rows(self) -> None:
        self.metadata.selection_set(self._selection_model.select_all())
        self.metadata.focus_set()

    def clear_selection(self) -> None:
        self._selection_model.clear()
        self.metadata.selection_remove(self.metadata.selection())


class LSVResultsPanel(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, padding=6)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.status = tk.StringVar(value="尚未运行分析")
        ttk.Label(self, textvariable=self.status).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self.tables = {}
        definitions = {
            "描述统计": (("group", "组别"), ("n", "n"), ("mean", "均值"), ("median", "中位数"),
                     ("sd", "SD"), ("sem", "SEM"), ("cv_percent", "CV%"),
                     ("minimum", "最小值"), ("q1", "Q1"), ("q3", "Q3"), ("maximum", "最大值")),
            "组间比较": (("comparison", "比较"), ("role", "类型"), ("welch_p", "Welch p"),
                     ("holm_p", "Holm校正 p"), ("mann_whitney_p", "Mann–Whitney p"),
                     ("mean_difference", "均值差"), ("mean_difference_ci", "均值差95% CI"),
                     ("hedges_g", "Hedges' g"), ("hedges_g_ci", "Hedges' g 95% CI")),
            "方向 QC": (("group", "组别"), ("negative", "负电流"), ("positive", "正电流"),
                    ("near_zero", "近零"), ("consistent", "方向一致"), ("warning", "提示")),
            "MAD 标记": (("sample_id", "Sample ID"), ("group", "组别"), ("current", "Current / µA"),
                     ("mad_score", "MAD score"), ("status", "状态")),
        }
        self.table_status = {}
        for title, definitions_for_table in definitions.items():
            columns = tuple(key for key, _label in definitions_for_table)
            frame = ttk.Frame(self.notebook)
            frame.columnconfigure(0, weight=1); frame.rowconfigure(1, weight=1)
            table_status = tk.StringVar()
            ttk.Label(frame, textvariable=table_status, foreground="#355f7c").grid(
                row=0, column=0, columnspan=2, sticky="w", pady=(3, 4)
            )
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for column, label in definitions_for_table:
                tree.heading(column, text=label)
                tree.column(column, width=105, stretch=True)
            tree.grid(row=1, column=0, sticky="nsew")
            ttk.Scrollbar(frame, orient="vertical", command=tree.yview).grid(row=1, column=1, sticky="ns")
            ttk.Scrollbar(frame, orient="horizontal", command=tree.xview).grid(row=2, column=0, sticky="ew")
            self.notebook.add(frame, text=title)
            self.tables[title] = tree
            self.table_status[title] = table_status
        self.warning_text = tk.Text(self, height=4, wrap="word")
        self.warning_text.grid(row=2, column=0, sticky="ew", pady=(5, 0))

    def render(self, state: LSVWorkflowState) -> None:
        self.status.set(result_summary_text(state.analysis_result) if state.analysis_result else state.result_status)
        result = state.analysis_result
        mappings = (("描述统计", descriptive_display_rows), ("组间比较", comparison_display_rows),
                    ("方向 QC", sign_qc_display_rows), ("MAD 标记", outlier_display_rows))
        for title, getter in mappings:
            tree = self.tables[title]
            tree.delete(*tree.get_children())
            if result is not None:
                for index, row in enumerate(getter(result)):
                    tree.insert("", "end", iid=str(index), values=tuple(row.values()))
        self.warning_text.delete("1.0", "end")
        if result is not None:
            self.table_status["MAD 标记"].set(mad_result_status(result))
            self.table_status["方向 QC"].set(sign_qc_result_status(result))
            self.table_status["描述统计"].set(f"正式指标：{result.settings.analysis_metric}；单位：µA")
            self.table_status["组间比较"].set("仅显示用户预先定义的 comparisons。")
            lines = ["默认全部纳入；MAD 仅标记，不自动删除。"]
            lines.extend(result.warnings or ("无 current sign warning。",))
            if state.result_stale:
                lines.insert(0, "设置已修改：下表为过期结果，重新分析前禁止导出。")
            self.warning_text.insert("1.0", "\n".join(lines))
        else:
            for status in self.table_status.values():
                status.set("尚未运行分析")


class LSVResultPlotPanel(ttk.Frame):
    def __init__(self, master, *, on_export: Callable, on_open_folder: Callable):
        super().__init__(master, padding=6)
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.figure = None; self.canvas = None; self.state = None
        self._hover_series = ()
        self._hover_annotation = None
        self._hover_connection = None
        toolbar = ttk.Frame(self); toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.plot_type = tk.StringVar(value=PLOT_LABELS["Selected magnitude"])
        self.group = tk.StringVar(value="ALL")
        combo = ttk.Combobox(toolbar, textvariable=self.plot_type, state="readonly", width=23,
                             values=tuple(PLOT_LABELS.values()))
        combo.pack(side="left"); combo.bind("<<ComboboxSelected>>", self._plot_changed)
        self.group_combo = ttk.Combobox(toolbar, textvariable=self.group, state="readonly", width=14)
        self.group_combo.pack(side="left", padx=5); self.group_combo.bind("<<ComboboxSelected>>", self._group_changed)
        ttk.Button(toolbar, text="导出当前完整分析结果", command=on_export).pack(side="right")
        ttk.Button(toolbar, text="打开结果文件夹", command=on_open_folder).pack(side="right", padx=5)
        self.host = ttk.Frame(self); self.host.grid(row=1, column=0, sticky="nsew")
        self.export_status = tk.StringVar(value="尚未导出当前 Workspace 的结果")
        ttk.Label(self, textvariable=self.export_status, foreground="#555555", wraplength=900).grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )

    def render(self, state: LSVWorkflowState | None) -> None:
        self.state = state
        self.export_status.set(
            f"最近导出：{state.last_export_directory}"
            if state is not None and state.last_export_directory
            else "尚未导出当前 Workspace 的结果"
        )
        if self.canvas is not None:
            self.canvas.get_tk_widget().destroy(); self.canvas = None
        if self.figure is not None:
            plt.close(self.figure); self.figure = None
        for child in self.host.winfo_children():
            child.destroy()
        if state is None or state.analysis_result is None:
            ttk.Label(self.host, text="完成正式分析后可查看结果图。", padding=12).pack()
            return
        result = state.analysis_result
        groups = result.groups
        if state.selected_result_plot:
            self.plot_type.set(PLOT_LABELS.get(state.selected_result_plot, PLOT_LABELS["Selected magnitude"]))
        self.group_combo.configure(values=groups)
        desired_group = state.selected_plot_group
        if desired_group not in groups:
            desired_group = groups[0]
        self.group.set(desired_group)
        kind = PLOT_KEYS.get(self.plot_type.get(), "Selected magnitude")
        self._hover_series = ()
        self._hover_annotation = None
        if kind == "Raw curves": self.figure = build_raw_lsv_figure(result, self.group.get())
        elif kind == "Mean ± SD": self.figure = build_mean_lsv_figure(result, self.group.get())
        elif kind == "Mean overlay": self.figure = build_mean_lsv_figure(result)
        elif kind == "Selected signed":
            self.figure, self._hover_series = build_selected_potential_figure(
                result, "signed", include_hover_metadata=True
            )
        elif kind == "Repeatability CV%": self.figure = build_repeatability_figure(result)
        else:
            self.figure, self._hover_series = build_selected_potential_figure(
                result, "magnitude", include_hover_metadata=True
            )
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.host)
        if self._hover_series:
            axis = self.figure.axes[0]
            self._hover_annotation = axis.annotate(
                "", xy=(0, 0), xytext=(9, 9), textcoords="offset points",
                bbox={"boxstyle": "round,pad=0.25", "fc": "white", "alpha": 0.92},
                arrowprops={"arrowstyle": "->", "color": "#666666"},
            )
            self._hover_annotation.set_visible(False)
            self._hover_connection = self.canvas.mpl_connect("motion_notify_event", self._hover_motion)
        self.canvas.draw_idle(); self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _plot_changed(self, _event=None) -> None:
        if self.state is not None:
            self.state.selected_result_plot = PLOT_KEYS.get(self.plot_type.get(), "Selected magnitude")
        self.render(self.state)

    def _group_changed(self, _event=None) -> None:
        if self.state is not None:
            self.state.selected_plot_group = self.group.get()
        self.render(self.state)

    def _hover_motion(self, event) -> None:
        annotation = self._hover_annotation
        if annotation is None or self.canvas is None:
            return
        found = None
        if event.inaxes is self.figure.axes[0]:
            for series in self._hover_series:
                contains, details = series.artist.contains(event)
                indices = details.get("ind", ()) if contains else ()
                if indices:
                    found = series.points[int(indices[0])]
                    break
        if found is None:
            if annotation.get_visible():
                annotation.set_visible(False)
                self.canvas.draw_idle()
            return
        annotation.xy = (found.x, found.current_uA)
        annotation.set_text(f"{found.sample_id}\n{found.current_uA:.4g} µA")
        annotation.set_visible(True)
        self.canvas.draw_idle()


__all__ = ["LSVResultPlotPanel", "LSVResultsPanel", "LSVSettingsPanel"]
