"""Compact Stage 5.2 Generic LSV workflow widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import simpledialog, ttk
from typing import Callable

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt

from chi_gui.lsv_workflow import (
    ComparisonDraft,
    LSVWorkflowState,
    comparison_display_rows,
    descriptive_display_rows,
    outlier_display_rows,
    sign_qc_display_rows,
)
from plotting.lsv_mean import build_mean_lsv_figure
from plotting.lsv_raw import build_raw_lsv_figure
from plotting.repeatability import build_repeatability_figure
from plotting.selected_potential import build_selected_potential_figure


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

        batch = ttk.Frame(self)
        batch.grid(row=2, column=0, sticky="ew", pady=(4, 8))
        ttk.Label(batch, text="批量设置选中行：").pack(side="left")
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

        footer = ttk.Frame(self)
        footer.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(7, 0))
        self.status = tk.StringVar(value="尚未确认样本信息")
        ttk.Label(footer, textvariable=self.status, foreground="#174a7e").pack(side="left", fill="x", expand=True)
        self.confirm_button = ttk.Button(footer, text="确认样本信息", command=self.on_confirm)
        self.confirm_button.pack(side="right", padx=4)
        self.run_button = ttk.Button(footer, text="开始正式分析", command=self.on_run)
        self.run_button.pack(side="right")

    def render(self, state: LSVWorkflowState, *, busy: bool = False) -> None:
        self._state = state
        self.target.set(f"{state.target_potential_V:.6g}")
        self.metric.set(state.analysis_metric)
        self.metadata.delete(*self.metadata.get_children())
        for row in state.metadata_rows:
            self.metadata.insert("", "end", iid=row.record_key, values=("✓" if row.include else "—", row.file_name,
                                 row.sample_id, row.group, row.electrode_type, row.notes))
        groups = state.groups
        self.left.configure(values=groups)
        self.right.configure(values=groups)
        self.comparison_tree.delete(*self.comparison_tree.get_children())
        for index, item in enumerate(state.comparisons):
            self.comparison_tree.insert("", "end", iid=str(index), values=(item.left_group, item.right_group,
                                        item.role, item.holm_family, item.name))
        self.status.set(f"{state.manifest_status}｜{state.result_status}")
        button_state = "disabled" if busy else "normal"
        self.confirm_button.configure(state=button_state)
        self.run_button.configure(state=button_state)

    def _edit_metadata(self, event) -> None:
        if self._state is None:
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

    def _delete_comparison(self) -> None:
        indices = tuple(int(item) for item in self.comparison_tree.selection())
        if indices:
            self.on_change("delete_comparisons", indices)


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
            "描述统计": ("group", "n", "mean", "median", "sd", "sem", "cv_percent", "minimum", "q1", "q3", "maximum"),
            "组间比较": ("comparison", "role", "welch_p", "holm_p", "mann_whitney_p", "mean_difference", "mean_difference_ci", "hedges_g", "hedges_g_ci"),
            "方向 QC": ("group", "negative", "positive", "near_zero", "consistent", "warning"),
            "MAD 标记": ("sample_id", "group", "current", "mad_score", "status"),
        }
        for title, columns in definitions.items():
            frame = ttk.Frame(self.notebook)
            frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
            tree = ttk.Treeview(frame, columns=columns, show="headings")
            for column in columns:
                tree.heading(column, text=column)
                tree.column(column, width=105, stretch=True)
            tree.grid(row=0, column=0, sticky="nsew")
            ttk.Scrollbar(frame, orient="vertical", command=tree.yview).grid(row=0, column=1, sticky="ns")
            ttk.Scrollbar(frame, orient="horizontal", command=tree.xview).grid(row=1, column=0, sticky="ew")
            self.notebook.add(frame, text=title)
            self.tables[title] = tree
        self.warning_text = tk.Text(self, height=4, wrap="word")
        self.warning_text.grid(row=2, column=0, sticky="ew", pady=(5, 0))

    def render(self, state: LSVWorkflowState) -> None:
        self.status.set(state.result_status)
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
            lines = ["默认全部纳入；MAD 仅标记，不自动删除。"]
            lines.extend(result.warnings or ("无 current sign warning。",))
            if state.result_stale:
                lines.insert(0, "设置已修改：下表为过期结果，重新分析前禁止导出。")
            self.warning_text.insert("1.0", "\n".join(lines))


class LSVResultPlotPanel(ttk.Frame):
    def __init__(self, master, *, on_export: Callable, on_open_folder: Callable):
        super().__init__(master, padding=6)
        self.columnconfigure(0, weight=1); self.rowconfigure(1, weight=1)
        self.figure = None; self.canvas = None; self.state = None
        toolbar = ttk.Frame(self); toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.plot_type = tk.StringVar(value="Selected magnitude")
        self.group = tk.StringVar(value="ALL")
        combo = ttk.Combobox(toolbar, textvariable=self.plot_type, state="readonly", width=23,
                             values=("Raw curves", "Mean ± SD", "Mean overlay", "Selected magnitude", "Selected signed", "Repeatability CV%"))
        combo.pack(side="left"); combo.bind("<<ComboboxSelected>>", self._plot_changed)
        self.group_combo = ttk.Combobox(toolbar, textvariable=self.group, state="readonly", width=14)
        self.group_combo.pack(side="left", padx=5); self.group_combo.bind("<<ComboboxSelected>>", self._group_changed)
        ttk.Button(toolbar, text="导出当前完整分析结果", command=on_export).pack(side="right")
        ttk.Button(toolbar, text="打开结果文件夹", command=on_open_folder).pack(side="right", padx=5)
        self.host = ttk.Frame(self); self.host.grid(row=1, column=0, sticky="nsew")

    def render(self, state: LSVWorkflowState | None) -> None:
        self.state = state
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
            self.plot_type.set(state.selected_result_plot)
        self.group_combo.configure(values=groups)
        desired_group = state.selected_plot_group
        if desired_group not in groups:
            desired_group = groups[0]
        self.group.set(desired_group)
        kind = self.plot_type.get()
        if kind == "Raw curves": self.figure = build_raw_lsv_figure(result, self.group.get())
        elif kind == "Mean ± SD": self.figure = build_mean_lsv_figure(result, self.group.get())
        elif kind == "Mean overlay": self.figure = build_mean_lsv_figure(result)
        elif kind == "Selected signed": self.figure = build_selected_potential_figure(result, "signed")
        elif kind == "Repeatability CV%": self.figure = build_repeatability_figure(result)
        else: self.figure = build_selected_potential_figure(result, "magnitude")
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.host)
        self.canvas.draw_idle(); self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def _plot_changed(self, _event=None) -> None:
        if self.state is not None:
            self.state.selected_result_plot = self.plot_type.get()
        self.render(self.state)

    def _group_changed(self, _event=None) -> None:
        if self.state is not None:
            self.state.selected_plot_group = self.group.get()
        self.render(self.state)


__all__ = ["LSVResultPlotPanel", "LSVResultsPanel", "LSVSettingsPanel"]
