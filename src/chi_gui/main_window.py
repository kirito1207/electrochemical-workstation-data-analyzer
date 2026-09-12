"""Responsive Chinese ttk main window for LSV and Generic i-t workflows."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .background import BackgroundRunner, WorkerEvent
from .controller import GUIController, discover_bin_files
from .cursor import (
    CursorReadingSet,
    build_cursor_readings,
    format_cursor_input,
    parse_cursor_input,
    step_cursor_on_axis,
)
from .dialogs import confirm_close_while_busy, show_record_details
from .formatting import parameter_rows
from .layout import (
    DATA_PAGE_LEFT_MIN_PX,
    DATA_PAGE_RIGHT_MIN_PX,
    DataPageLayoutState,
    PARAMETER_VALUE_WRAP_PX,
)
from .lsv_export import export_lsv_result, open_output_directory
from .matplotlib_config import configure_gui_matplotlib_fonts
from .it_export import export_it_result
from .it_workflow import (ITAnalysisCompleted, execute_it_analysis)
from .lsv_workflow import (
    GUIWorkflowValidationError,
    LSVAnalysisCompleted,
    StaleAnalysisResultError,
    execute_lsv_analysis,
)
from .pages import IT_STAGE_MESSAGE, LSV_STAGE_MESSAGE, WELCOME_MESSAGE, unsupported_message
from .state import AppState, FileRecord, PreviewDisplayState
from .widgets import (CurveList, FileTable, ITResultPlotPanel, ITResultsPanel,
                      ITSettingsPanel, LogPanel, LSVResultPlotPanel, LSVResultsPanel,
                      LSVSettingsPanel, PlotPreview, WorkspaceTabs)
from .workspaces import WorkspaceManager, WorkspaceSession


WINDOW_TITLE = "电化学工作站数据分析工具"


class MainWindow:
    def __init__(self, root: tk.Tk):
        # MainWindow is also instantiated directly by tests and embedders, so
        # configure fonts before PlotPreview creates its first Figure.
        configure_gui_matplotlib_fonts()
        self.root = root
        self.controller = GUIController()
        self.workspace_manager = WorkspaceManager()
        self.runner = BackgroundRunner()
        self.current_record: FileRecord | None = None
        self._running_workspace_id: str | None = None
        self._closing = False
        self._data_layout = DataPageLayoutState()
        self._data_layout_job: str | None = None
        self._data_layout_verify_job: str | None = None

        root.title(WINDOW_TITLE)
        root.geometry("1280x820")
        root.minsize(920, 620)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_style()
        self._build_layout()
        self._refresh_workspace_tabs()
        self.log_panel.set_messages(self.workspace.log_messages)
        self._set_route("all")
        self.root.after(100, self._poll_worker)

    @property
    def workspace(self) -> WorkspaceSession:
        return self.workspace_manager.active

    @property
    def state(self) -> AppState:
        return self.workspace.state

    @property
    def preview_display(self) -> PreviewDisplayState:
        return self.workspace.preview_display

    @property
    def selected_by_route(self) -> dict[str, str | None]:
        return self.workspace.selected_by_route

    @property
    def current_route(self) -> str:
        return self.workspace.current_route

    @current_route.setter
    def current_route(self, route: str) -> None:
        self.workspace.current_route = route

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Nav.TButton", anchor="w", padding=(12, 9))

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, padding=8)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        navigation = ttk.Frame(shell, padding=(4, 8), width=175)
        navigation.grid(row=0, column=0, sticky="nsw", padx=(0, 8))
        navigation.grid_propagate(False)
        ttk.Label(navigation, text="功能导航", style="Title.TLabel").pack(fill="x", pady=(0, 12))
        nav_items = (
            ("主页", "all"),
            ("LSV 分析", "LSV"),
            ("i-t 分析", "i-t"),
            ("CV（尚未支持）", "CV"),
            ("CA（尚未支持）", "CA"),
        )
        for label, route in nav_items:
            ttk.Button(
                navigation,
                text=label,
                style="Nav.TButton",
                command=lambda selected=route: self._set_route(selected),
            ).pack(fill="x", pady=2)

        workspace = ttk.Frame(shell)
        workspace.grid(row=0, column=1, sticky="nsew")
        workspace.columnconfigure(0, weight=1)
        workspace.rowconfigure(3, weight=1)

        self.workspace_tabs = WorkspaceTabs(
            workspace,
            on_select=self._switch_workspace,
            on_new=self._new_workspace,
            on_close=self._close_workspace,
            on_rename=self._rename_workspace,
        )
        self.workspace_tabs.grid(row=0, column=0, sticky="ew", pady=(0, 5))

        header = ttk.Frame(workspace)
        header.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text=WINDOW_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(header, mode="determinate", length=210)
        self.progress.grid(row=0, column=1, sticky="e", padx=(12, 0))

        toolbar = ttk.Frame(workspace)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(0, 6))
        self.action_buttons = []
        for text, command in (
            ("选择文件", self._choose_files),
            ("选择文件夹", self._choose_folder),
            ("移除选中", self._remove_selected),
            ("清空", self._clear),
            ("详细信息", self._show_details),
        ):
            button = ttk.Button(toolbar, text=text, command=command)
            button.pack(side="left", padx=(0, 6))
            self.action_buttons.append(button)

        self.page_message = tk.StringVar()
        ttk.Label(toolbar, textvariable=self.page_message, wraplength=540, justify="left").pack(
            side="left", fill="x", expand=True, padx=(8, 0)
        )

        self.workflow_tabs = ttk.Notebook(workspace)
        self.workflow_tabs.grid(row=3, column=0, sticky="nsew")
        self.workflow_tabs.bind("<<NotebookTabChanged>>", self._workflow_tab_changed)
        self.data_tab = ttk.Frame(self.workflow_tabs)
        self.data_tab.columnconfigure(0, weight=1)
        self.data_tab.rowconfigure(0, weight=3)
        self.data_tab.rowconfigure(1, weight=2)
        self.settings_tab = ttk.Frame(self.workflow_tabs)
        self.results_tab = ttk.Frame(self.workflow_tabs)
        self.figures_tab = ttk.Frame(self.workflow_tabs)
        for frame, label in ((self.data_tab, "数据与曲线"), (self.settings_tab, "分析设置"),
                             (self.results_tab, "统计结果"), (self.figures_tab, "结果图表")):
            self.workflow_tabs.add(frame, text=label)

        # Wide result widgets stay inside their own allocated page and cannot
        # change the data page's requested width or sash allocation.
        for frame in (self.settings_tab, self.results_tab, self.figures_tab):
            frame.grid_propagate(False)

        table_frame = ttk.LabelFrame(self.data_tab, text="文件列表")
        table_frame.grid(row=0, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.file_table = FileTable(table_frame, on_select=self._record_selected)
        self.file_table.grid(row=0, column=0, sticky="nsew")

        self.data_panes = tk.PanedWindow(
            self.data_tab,
            orient="horizontal",
            sashwidth=6,
            showhandle=False,
            borderwidth=0,
            relief="flat",
        )
        self.data_panes.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.plot_preview = PlotPreview(
            self.data_panes,
            on_cursor_clicked=self._cursor_clicked,
            on_cursor_step=self._cursor_step,
        )
        self.data_panes.add(
            self.plot_preview,
            minsize=DATA_PAGE_LEFT_MIN_PX,
            stretch="always",
        )

        info = ttk.Frame(self.data_panes, width=360)
        self.data_panes.add(
            info,
            minsize=DATA_PAGE_RIGHT_MIN_PX,
            stretch="always",
        )
        info.columnconfigure(0, weight=1)
        info.rowconfigure(0, weight=3)
        self.curve_list = CurveList(
            info,
            on_visibility_changed=self._visibility_changed,
            on_clear_cursor=self._clear_cursor,
            on_cursor_submitted=self._cursor_submitted,
            on_cursor_step=self._cursor_step,
        )
        self.curve_list.grid(row=0, column=0, sticky="nsew")
        self.parameter_box = ttk.LabelFrame(info, text="实验参数")
        self.parameter_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.log_panel = LogPanel(info)
        self.log_panel.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        self.data_panes.bind("<Configure>", self._data_panes_resized, add="+")
        self.data_panes.bind("<ButtonRelease-1>", self._remember_data_sash, add="+")
        self.data_tab.bind("<Map>", lambda _event: self._schedule_data_layout(force=True), add="+")

        for frame in (self.settings_tab, self.results_tab, self.figures_tab):
            frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)
        self.lsv_settings = LSVSettingsPanel(
            self.settings_tab, on_change=self._lsv_setting_changed,
            on_confirm=self._confirm_lsv_metadata, on_run=self._run_lsv_analysis,
            on_use_cursor=self._use_cursor_as_target,
        )
        self.lsv_settings.grid(row=0, column=0, sticky="nsew")
        self.lsv_results = LSVResultsPanel(self.results_tab)
        self.lsv_results.grid(row=0, column=0, sticky="nsew")
        self.lsv_figures = LSVResultPlotPanel(
            self.figures_tab, on_export=self._export_lsv_analysis,
            on_open_folder=self._open_lsv_output,
        )
        self.lsv_figures.grid(row=0, column=0, sticky="nsew")
        self.it_settings = ITSettingsPanel(
            self.settings_tab, on_change=self._it_setting_changed,
            on_confirm_metadata=self._confirm_it_metadata,
            on_confirm_timeline=self._confirm_it_timeline,
            on_add_cursor_event=self._add_it_event_from_cursor,
            on_run=self._run_it_analysis,
        )
        self.it_results = ITResultsPanel(self.results_tab)
        self.it_figures = ITResultPlotPanel(
            self.figures_tab, on_export=self._export_it_analysis,
            on_open_folder=self._open_it_output,
        )

        self.status_text = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_text, relief="sunken", anchor="w", padding=(8, 4)).pack(
            fill="x", side="bottom"
        )

    def _refresh_workspace_tabs(self) -> None:
        self.workspace_tabs.set_sessions(
            self.workspace_manager.sessions,
            self.workspace.workspace_id,
        )

    def _new_workspace(self) -> None:
        session = self.workspace_manager.create()
        self._refresh_workspace_tabs()
        self.log_panel.set_messages(session.log_messages)
        self.current_record = None
        self._set_route(session.current_route)

    def _switch_workspace(self, workspace_id: str) -> None:
        if workspace_id == self.workspace.workspace_id:
            return
        session = self.workspace_manager.switch(workspace_id)
        self._refresh_workspace_tabs()
        self.log_panel.set_messages(session.log_messages)
        self.current_record = None
        self._set_route(session.current_route)

    def _rename_workspace(self, workspace_id: str) -> None:
        session = self.workspace_manager.get(workspace_id)
        if session is None:
            return
        name = simpledialog.askstring(
            "重命名工作区",
            "请输入新的工作区名称：",
            initialvalue=session.name,
            parent=self.root,
        )
        if name is None:
            return
        try:
            self.workspace_manager.rename(workspace_id, name)
        except ValueError as error:
            messagebox.showwarning("名称无效", str(error), parent=self.root)
            return
        self._refresh_workspace_tabs()

    def _close_workspace(self, workspace_id: str) -> None:
        session = self.workspace_manager.get(workspace_id)
        if session is None:
            return
        if workspace_id == self._running_workspace_id and self.runner.busy:
            messagebox.showinfo(
                "无法关闭工作区",
                "该工作区正在解析文件，请等待任务完成后再关闭。",
                parent=self.root,
            )
            return
        if session.state.records and not messagebox.askyesno(
            "关闭工作区",
            "该工作区包含已加载数据，确定关闭？\n原始文件不会被删除。",
            parent=self.root,
        ):
            return
        self.workspace_manager.close(workspace_id)
        self._refresh_workspace_tabs()
        self.log_panel.set_messages(self.workspace.log_messages)
        self.current_record = None
        self._set_route(self.workspace.current_route)

    def _log(self, message: str, *, session: WorkspaceSession | None = None) -> None:
        target = session or self.workspace
        line = LogPanel.format_message(message)
        target.log_messages.append(line)
        if target.workspace_id == self.workspace.workspace_id:
            self.log_panel.append_line(line)

    def _set_route(self, route: str) -> None:
        self.current_route = route
        if route == "all":
            self.page_message.set(WELCOME_MESSAGE)
            records = self.state.records
        elif route == "LSV":
            self.page_message.set(LSV_STAGE_MESSAGE)
            records = self.state.for_route("LSV")
        elif route == "i-t":
            self.page_message.set(IT_STAGE_MESSAGE)
            records = self.state.for_route("i-t")
        else:
            self.page_message.set(unsupported_message(route))
            records = tuple(
                item for item in self.state.for_route("unsupported")
                if item.experiment_type.upper() == route
            )
        self.file_table.set_records(records)
        for tab in (1, 2, 3):
            self.workflow_tabs.tab(tab, state="normal" if route in {"LSV", "i-t"} else "disabled")
        if route not in {"LSV", "i-t"}:
            self.workflow_tabs.select(0)
        if route in {"LSV", "i-t"}:
            self._render_technique_preview(route)
        else:
            selected_key = self.selected_by_route.get(route)
            selected = next((item for item in records if item.key == selected_key), None)
            self.current_record = selected
            self._render_parameters(selected)
            self.file_table.select_record(selected.key if selected is not None else None)
            self.curve_list.set_collection(None)
            self.plot_preview.clear(
                "请选择 LSV 或 i-t 页面查看曲线" if route == "all" else unsupported_message(route)
            )
        self._update_status()
        self._show_workflow_panels(route)
        self._refresh_active_workflow()

    def _show_workflow_panels(self, route: str) -> None:
        lsv = (self.lsv_settings, self.lsv_results, self.lsv_figures)
        it = (self.it_settings, self.it_results, self.it_figures)
        for widget in (*lsv, *it):
            widget.grid_remove()
        selected = lsv if route == "LSV" else it if route == "i-t" else ()
        for widget in selected:
            widget.grid(row=0, column=0, sticky="nsew")

    def _refresh_active_workflow(self) -> None:
        if self.current_route == "i-t":
            self._refresh_it_workflow()
        else:
            self._refresh_lsv_workflow()

    def _refresh_lsv_workflow(self) -> None:
        workflow = self.workspace.lsv_workflow
        self.lsv_settings.render(
            workflow,
            busy=self.runner.busy,
            workspace_token=self.workspace.workspace_id,
        )
        self.lsv_results.render(workflow)
        if self.current_route == "LSV" and self.workflow_tabs.select() == str(self.figures_tab):
            self.lsv_figures.render(workflow)

    def _refresh_it_workflow(self) -> None:
        workflow = self.workspace.it_workflow
        self.it_settings.render(workflow, busy=self.runner.busy,
                                workspace_token=self.workspace.workspace_id)
        self.it_results.render(workflow)
        if self.current_route == "i-t" and self.workflow_tabs.select() == str(self.figures_tab):
            self.it_figures.render(workflow)

    def _workflow_tab_changed(self, _event=None) -> None:
        selected = self.workflow_tabs.select()
        if selected == str(self.data_tab):
            self._schedule_data_layout(force=True)
        if self.current_route == "LSV" and selected == str(self.figures_tab):
            self.lsv_figures.render(self.workspace.lsv_workflow)
        if self.current_route == "i-t" and selected == str(self.figures_tab):
            self.it_figures.render(self.workspace.it_workflow)

    def _data_panes_resized(self, event=None) -> None:
        width = int(getattr(event, "width", 0) or self.data_panes.winfo_width())
        if width != self._data_layout.last_width:
            self._schedule_data_layout()

    def _schedule_data_layout(self, *, force: bool = False) -> None:
        if force:
            self._data_layout.last_width = 0
        if self._data_layout_job is None:
            self._data_layout_job = self.root.after_idle(self._apply_data_layout)

    def _apply_data_layout(self) -> None:
        self._data_layout_job = None
        width = self.data_panes.winfo_width()
        if width <= 1 or width == self._data_layout.last_width:
            return
        self.data_panes.sash_place(0, self._data_layout.sash_position(width), 1)
        self._data_layout.last_width = width
        if self._data_layout_verify_job is None:
            self._data_layout_verify_job = self.root.after_idle(self._verify_data_layout)

    def _verify_data_layout(self) -> None:
        """Correct one late Tk requested-geometry pass after mapping a tab."""

        self._data_layout_verify_job = None
        width = self.data_panes.winfo_width()
        if width <= 1:
            return
        desired = self._data_layout.sash_position(width)
        try:
            actual, _sash_y = self.data_panes.sash_coord(0)
        except tk.TclError:
            return
        if abs(actual - desired) > 2:
            self.data_panes.sash_place(0, desired, 1)
        self._data_layout.last_width = width

    def _remember_data_sash(self, _event=None) -> None:
        if self._data_layout_verify_job is not None:
            self.root.after_cancel(self._data_layout_verify_job)
            self._data_layout_verify_job = None
        try:
            sash_x, _sash_y = self.data_panes.sash_coord(0)
        except tk.TclError:
            return
        self._data_layout.remember(self.data_panes.winfo_width(), sash_x)

    def _render_technique_preview(self, experiment_type: str) -> None:
        collection = self.controller.build_preview_collection(
            self.state.records,
            experiment_type=experiment_type,
            display_state=self.preview_display,
            selected_key=self.selected_by_route.get(experiment_type),
        )
        self.selected_by_route[experiment_type] = collection.selected_key
        readings = self._cursor_readings(collection, experiment_type)
        cursor = self.workspace.cursor_by_route[experiment_type]
        self.curve_list.set_collection(collection, readings, cursor)
        if collection.curves:
            self.plot_preview.show_collection(
                collection,
                cursor_x=cursor.requested_x if cursor.visible else None,
            )
            selected = next(
                record for record in self.state.records if record.key == collection.selected_key
            )
            self.current_record = selected
            self._render_parameters(selected)
            self.file_table.select_record(selected.key)
        else:
            self.current_record = None
            self._render_parameters(None)
            self.plot_preview.clear(f"当前没有已成功解析的 {experiment_type} 文件")

    def _cursor_readings(
        self,
        collection,
        experiment_type: str,
    ) -> CursorReadingSet | None:
        cursor = self.workspace.cursor_by_route[experiment_type]
        if not cursor.visible or cursor.requested_x is None:
            return None
        return build_cursor_readings(self.state.records, collection, cursor.requested_x)

    def _cursor_clicked(self, requested_x: float) -> None:
        if self.current_route not in {"LSV", "i-t"}:
            return
        self._apply_cursor_value(
            requested_x,
            input_text=format_cursor_input(self.current_route, requested_x),
        )

    def _cursor_submitted(self, text: str) -> None:
        if self.current_route not in {"LSV", "i-t"}:
            return
        value = parse_cursor_input(text)
        if value is None:
            cursor = self.workspace.cursor_by_route[self.current_route]
            cursor.invalidate(text, "请输入有限数值")
            self._render_technique_preview(self.current_route)
            return
        self._apply_cursor_value(value, input_text=text.strip())

    def _apply_cursor_value(self, requested_x: float, *, input_text: str) -> bool:
        collection = self.controller.build_preview_collection(
            self.state.records,
            experiment_type=self.current_route,
            display_state=self.preview_display,
            selected_key=self.selected_by_route[self.current_route],
        )
        candidate = build_cursor_readings(self.state.records, collection, requested_x)
        if not any(reading.available for reading in candidate.readings):
            self.workspace.cursor_by_route[self.current_route].invalidate(
                input_text,
                "超出范围",
            )
            self._render_technique_preview(self.current_route)
            return False
        self.workspace.cursor_by_route[self.current_route].set(
            requested_x,
            input_text=input_text,
        )
        self._render_technique_preview(self.current_route)
        return True

    def _cursor_step(self, direction: int) -> None:
        if self.current_route not in {"LSV", "i-t"}:
            return
        collection = self.controller.build_preview_collection(
            self.state.records,
            experiment_type=self.current_route,
            display_state=self.preview_display,
            selected_key=self.selected_by_route[self.current_route],
        )
        visible = collection.visible_curves
        if not visible:
            cursor = self.workspace.cursor_by_route[self.current_route]
            cursor.invalidate(cursor.input_text, "无可见曲线")
            self._render_technique_preview(self.current_route)
            return
        reference = next((curve for curve in visible if curve.selected), visible[0])
        cursor = self.workspace.cursor_by_route[self.current_route]
        current = cursor.requested_x
        if current is None:
            current = parse_cursor_input(cursor.input_text)
        target = step_cursor_on_axis(reference.data.x, current, direction)
        if cursor.visible and cursor.requested_x == target:
            return
        self._apply_cursor_value(
            target,
            input_text=format_cursor_input(self.current_route, target),
        )

    def _clear_cursor(self) -> None:
        if self.current_route not in {"LSV", "i-t"}:
            return
        self.workspace.cursor_by_route[self.current_route].clear()
        self._render_technique_preview(self.current_route)

    def _choose_files(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title="选择 CHI760E 二进制文件",
            filetypes=(("CHI 二进制文件", "*.bin"), ("所有文件", "*.*")),
        )
        if selected:
            self._start_import(selected)

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(parent=self.root, title="选择包含 .bin 文件的文件夹")
        if selected:
            self._start_import((selected,))

    def _start_import(self, selections: tuple[str, ...] | tuple[str | Path, ...]) -> None:
        discovered = discover_bin_files(selections)
        new_paths = tuple(path for path in discovered if not self.state.contains(path))
        duplicates = len(discovered) - len(new_paths)
        if duplicates:
            self._log(f"已忽略 {duplicates} 个重复路径。")
        if not new_paths:
            self._log("没有发现新的 .bin 文件。")
            return
        workspace_id = self.workspace.workspace_id
        self._running_workspace_id = workspace_id
        self._set_busy(True)
        self.progress.configure(maximum=len(new_paths), value=0)
        self._log(f"发现 {len(new_paths)} 个新文件，开始逐文件解析。")

        def task(cancel_event, emit):
            records = self.controller.parse_many(
                new_paths,
                progress=lambda index, total, path: emit(
                    (workspace_id, index, total, str(path))
                ),
                should_cancel=cancel_event.is_set,
            )
            return workspace_id, records

        self.runner.submit(task)

    def _poll_worker(self) -> None:
        for event in self.runner.drain():
            self._handle_worker_event(event)
        if self._closing and not self.runner.busy:
            self.root.destroy()
            return
        self.root.after(100, self._poll_worker)

    def _handle_worker_event(self, event: WorkerEvent) -> None:
        if event.kind == "progress":
            workspace_id, index, total, path = event.payload
            session = self.workspace_manager.get(workspace_id)
            workspace_name = session.name if session is not None else "已关闭工作区"
            self.progress.configure(maximum=total, value=index)
            self.status_text.set(
                f"{workspace_name} 正在解析 {index}/{total}：{Path(path).name}"
            )
        elif event.kind == "result":
            if isinstance(event.payload, LSVAnalysisCompleted):
                completed = event.payload
                session = self.workspace_manager.get(completed.workspace_id)
                if session is None:
                    return
                session.lsv_workflow.accept_result(completed.request, completed.result)
                self._log("LSV 正式分析完成；默认全部样本纳入，MAD 仅作标记。", session=session)
                for warning in completed.result.warnings:
                    self._log(f"方向一致性警告：{warning}", session=session)
                if session.workspace_id == self.workspace.workspace_id:
                    self._refresh_lsv_workflow()
                    self.workflow_tabs.select(self.results_tab)
                return
            if isinstance(event.payload, ITAnalysisCompleted):
                completed = event.payload
                session = self.workspace_manager.get(completed.workspace_id)
                if session is None:
                    return
                session.it_workflow.accept_result(completed.request, completed.result)
                self._log("Generic i-t Event 正式分析完成；Timeline 与 Calibration 均来自用户显式设置。", session=session)
                if session.workspace_id == self.workspace.workspace_id:
                    self._refresh_it_workflow()
                    self.workflow_tabs.select(self.results_tab)
                return
            workspace_id, supplied_records = event.payload
            records = tuple(supplied_records)
            session = self.workspace_manager.get(workspace_id)
            if session is None:
                return
            session.state.add_records(records)
            session.lsv_workflow.sync_records(session.state.records)
            session.it_workflow.sync_records(session.state.records)
            successful_routes = tuple(
                dict.fromkeys(record.route for record in records if record.parse_success)
            )
            if session.current_route == "all" and successful_routes:
                session.current_route = "LSV" if "LSV" in successful_routes else successful_routes[0]
            summary = session.state.summary()
            self._log(
                f"导入完成：共 {summary.total} 个文件；解析成功 {summary.parsed}，"
                f"失败 {summary.failed}，不支持 {summary.unsupported}；"
                f"LSV {summary.lsv}，i-t {summary.it}。",
                session=session,
            )
            for record in records:
                if record.error_message:
                    self._log(f"{record.path.name}：{record.error_message}", session=session)
                for warning in record.warning_messages:
                    self._log(f"{record.path.name} 警告：{warning}", session=session)
            if session.workspace_id == self.workspace.workspace_id:
                self._set_route(session.current_route)
        elif event.kind == "error":
            session = self.workspace_manager.get(self._running_workspace_id or "")
            if session is not None and session.lsv_workflow.analysis_running:
                session.lsv_workflow.analysis_running = False
                session.lsv_workflow.set_feedback(
                    "warning", "正式分析失败", (f"{type(event.payload).__name__}：{event.payload}",)
                )
            if session is not None and session.it_workflow.analysis_running:
                session.it_workflow.analysis_running = False
                session.it_workflow.set_feedback(
                    "warning", "i-t 正式分析失败", (f"{type(event.payload).__name__}：{event.payload}",)
                )
            self._log(
                f"后台任务异常：{type(event.payload).__name__}：{event.payload}",
                session=session,
            )
        elif event.kind == "finished":
            self._running_workspace_id = None
            self._set_busy(False)
            self._update_status()
            self._refresh_active_workflow()

    def _record_selected(self, record: FileRecord | None) -> None:
        selected_key = record.key if record is not None else None
        current_key = self.selected_by_route.get(self.current_route)
        current_record_key = self.current_record.key if self.current_record is not None else None
        if selected_key == current_key and selected_key == current_record_key:
            return

        self.current_record = record
        self.selected_by_route[self.current_route] = selected_key
        if self.current_route in {"LSV", "i-t"}:
            self._render_technique_preview(self.current_route)
        else:
            self._render_parameters(record)

    def _visibility_changed(self, record_key: str, visible: bool) -> None:
        self.preview_display.set_visible(record_key, visible)
        if self.current_route in {"LSV", "i-t"}:
            self._render_technique_preview(self.current_route)

    def _render_parameters(self, record: FileRecord | None) -> None:
        for child in self.parameter_box.winfo_children():
            child.destroy()
        if record is None:
            ttk.Label(self.parameter_box, text="请选择单个文件查看参数。", padding=8).grid(sticky="w")
            return
        rows = [("完整路径", str(record.path)), ("状态", record.status.value)]
        rows.extend(parameter_rows(record.data))
        if record.error_type:
            rows.extend((("错误类型", record.error_type), ("错误信息", record.error_message or "")))
        for index, (name, value) in enumerate(rows):
            ttk.Label(self.parameter_box, text=f"{name}：", padding=(5, 1)).grid(row=index, column=0, sticky="nw")
            ttk.Label(
                self.parameter_box,
                text=value,
                wraplength=PARAMETER_VALUE_WRAP_PX,
                padding=(2, 1),
            ).grid(row=index, column=1, sticky="nw")
        self.parameter_box.columnconfigure(1, weight=1)

    def _remove_selected(self) -> None:
        selected = self.file_table.selected_records()
        if not selected:
            return
        count = self.state.remove([record.path for record in selected])
        self.workspace.lsv_workflow.sync_records(self.state.records)
        self.workspace.it_workflow.sync_records(self.state.records)
        self._log(f"已从当前工作区移除 {count} 个文件；源文件未被修改。")
        self._set_route(self.current_route)

    def _clear(self) -> None:
        if not self.state.records:
            return
        if messagebox.askyesno("清空文件列表", "清空当前文件列表？不会删除磁盘上的源文件。", parent=self.root):
            self.workspace.clear_data()
            self._log("当前工作区文件列表已清空；其他工作区和源文件未被修改。")
            self._set_route(self.current_route)

    def _lsv_setting_changed(self, action: str, *values) -> None:
        workflow = self.workspace.lsv_workflow
        try:
            if action == "metadata": workflow.update_metadata(*values)
            elif action == "batch": workflow.batch_update(*values)
            elif action == "target": workflow.set_target_potential(values[0])
            elif action == "metric": workflow.set_metric(values[0])
            elif action == "add_comparison": workflow.add_comparison(values[0])
            elif action == "delete_comparisons":
                removed = set(values[0]); workflow.replace_comparisons(item for i, item in enumerate(workflow.comparisons) if i not in removed)
        except ValueError as error:
            workflow.set_feedback("warning", "设置未更新", (str(error),))
            self._log(f"设置未更新：{error}")
        self._refresh_lsv_workflow()

    def _confirm_lsv_metadata(self) -> None:
        try:
            manifest = self.workspace.lsv_workflow.confirm_metadata()
        except GUIWorkflowValidationError as error:
            self.workspace.lsv_workflow.set_feedback("warning", "样本信息无法确认", error.errors)
            self._log(f"样本信息无法确认：{error}")
        else:
            self.workspace.lsv_workflow.set_feedback(
                "success", f"样本信息已确认：{len(manifest.entries)} 个文件"
            )
            self._log(f"已由用户确认 {len(manifest.entries)} 个 LSV 样本的 metadata。")
        self._refresh_lsv_workflow()

    def _use_cursor_as_target(self) -> None:
        cursor = self.workspace.cursor_by_route["LSV"]
        if not cursor.visible or cursor.requested_x is None:
            self._log("当前没有有效的 LSV inspection cursor；分析电位未改变。")
            return
        self.workspace.lsv_workflow.set_target_potential(cursor.requested_x)
        self._log(f"已显式复制游标电位为分析电位：{cursor.requested_x:.6g} V；尚未运行分析。")
        self._refresh_lsv_workflow()

    def _run_lsv_analysis(self) -> None:
        try:
            request = self.workspace.lsv_workflow.build_request(self.state.records)
        except GUIWorkflowValidationError as error:
            self.workspace.lsv_workflow.set_feedback("warning", "无法开始正式分析", error.errors)
            self._log("无法开始正式分析：" + "；".join(error.errors))
            self._refresh_lsv_workflow()
            return
        workspace_id = self.workspace.workspace_id
        self._running_workspace_id = workspace_id
        self._set_busy(True)
        self.workspace.lsv_workflow.analysis_running = True
        self.workspace.lsv_workflow.set_feedback("busy", "正在分析…")
        self._log("开始后台运行 Generic LSV 正式分析。")
        def task(cancel_event, emit):
            if cancel_event.is_set():
                raise RuntimeError("分析已取消")
            return LSVAnalysisCompleted(workspace_id, request, execute_lsv_analysis(request))
        self.runner.submit(task)
        self._refresh_lsv_workflow()

    def _export_lsv_analysis(self) -> None:
        try:
            result = self.workspace.lsv_workflow.require_exportable_result()
        except StaleAnalysisResultError as error:
            self._log(f"无法导出：{error}")
            return
        selected = filedialog.askdirectory(parent=self.root, title="选择结果保存位置")
        if not selected:
            return
        try:
            run = export_lsv_result(result, selected)
        except Exception as error:
            self._log(f"导出失败：{type(error).__name__}：{error}")
            return
        self.workspace.lsv_workflow.last_export_directory = str(run.output_directory)
        self._log(f"已导出 {len(run.generated_files)} 个文件：{run.output_directory}")
        self._refresh_lsv_workflow()

    def _open_lsv_output(self) -> None:
        directory = self.workspace.lsv_workflow.last_export_directory
        if directory:
            try:
                open_output_directory(directory)
            except Exception as error:
                self._log(f"无法打开结果文件夹：{type(error).__name__}：{error}")
        else:
            self._log("当前 Workspace 尚无已导出的结果目录。")

    def _it_setting_changed(self, action: str, *values) -> None:
        workflow = self.workspace.it_workflow
        try:
            if action == "metadata": workflow.update_metadata(*values)
            elif action == "add_event":
                time_s, name, value, unit, notes = values
                workflow.add_event(time_s=time_s, name=name, value=value, unit=unit, notes=notes)
            elif action == "edit_event":
                event_id, time_s, name, value, unit, notes = values
                workflow.edit_event(event_id, time_s=time_s, name=name, value=value, unit=unit, notes=notes)
            elif action == "delete_events": workflow.delete_events(values[0])
            elif action == "timeline_context": workflow.select_timeline_context(values[0])
            elif action == "create_override": workflow.create_sample_override(values[0])
            elif action == "restore_default": workflow.restore_default_timeline(values[0])
            elif action == "inherited_timeline_blocked": workflow.set_feedback(
                "warning", "当前样本正在使用默认 Timeline",
                ("请先创建样本专用 Timeline，或切换到默认 Timeline 编辑。",),
            )
            elif action == "response":
                workflow.set_tail_fraction(values[0]); workflow.set_metric(values[1])
            elif action == "calibration": workflow.set_calibration(*values)
        except Exception as error:
            workflow.set_feedback("warning", "i-t 设置未更新", (str(error),))
            self._log(f"i-t 设置未更新：{error}")
        self._refresh_it_workflow()

    def _confirm_it_metadata(self) -> None:
        try:
            self.workspace.it_workflow.confirm_metadata()
        except GUIWorkflowValidationError as error:
            self.workspace.it_workflow.set_feedback("warning", "样本信息无法确认", error.errors)
        self._refresh_it_workflow()

    def _confirm_it_timeline(self) -> None:
        try:
            self.workspace.it_workflow.confirm_timeline(self.state.records)
        except GUIWorkflowValidationError as error:
            self.workspace.it_workflow.set_feedback("warning", "Event Timeline 无法确认", error.errors)
        self._refresh_it_workflow()

    def _add_it_event_from_cursor(self) -> None:
        cursor = self.workspace.cursor_by_route["i-t"]
        if not cursor.visible or cursor.requested_x is None:
            self.workspace.it_workflow.set_feedback("warning", "无法从游标添加 Event", ("当前没有有效的 i-t inspection cursor。",))
            self._refresh_it_workflow(); return
        collection = self.controller.build_preview_collection(
            self.state.records, experiment_type="i-t", display_state=self.preview_display,
            selected_key=self.selected_by_route.get("i-t"),
        )
        readings = build_cursor_readings(self.state.records, collection, cursor.requested_x)
        target_key = self.workspace.it_workflow.current_timeline_record_key or collection.selected_key
        preferred = next((row for row in readings.readings if row.record_key == target_key and row.available), None)
        preferred = preferred or next((row for row in readings.readings if row.available), None)
        actual_time = preferred.actual_sampled_x if preferred is not None else None
        if actual_time is None:
            self.workspace.it_workflow.set_feedback("warning", "无法从游标添加 Event", ("当前游标没有可用的真实采样时间。",))
        else:
            try:
                event = self.workspace.it_workflow.add_event(time_s=actual_time, name=f"Event {len(self.workspace.it_workflow.events) + 1}")
            except ValueError as error:
                self.workspace.it_workflow.set_feedback("warning", "Event 草稿未添加", (str(error),))
            else:
                self.workspace.it_workflow.set_feedback("info", f"已从真实采样时间 {event.time_s:.9g} s 添加 Event 草稿；请编辑并确认 Timeline")
        self._refresh_it_workflow()

    def _run_it_analysis(self) -> None:
        try:
            request = self.workspace.it_workflow.build_request(self.state.records)
        except GUIWorkflowValidationError as error:
            self.workspace.it_workflow.set_feedback("warning", "无法开始正式 i-t 分析", error.errors)
            self._refresh_it_workflow(); return
        workspace_id = self.workspace.workspace_id
        self._running_workspace_id = workspace_id; self._set_busy(True)
        self.workspace.it_workflow.analysis_running = True
        self.workspace.it_workflow.set_feedback("busy", "正在运行 Generic i-t Event 分析…")
        def task(cancel_event, emit):
            if cancel_event.is_set(): raise RuntimeError("分析已取消")
            return ITAnalysisCompleted(workspace_id, request, execute_it_analysis(request))
        self.runner.submit(task); self._refresh_it_workflow()

    def _export_it_analysis(self) -> None:
        try: result = self.workspace.it_workflow.require_exportable_result()
        except StaleAnalysisResultError as error:
            self._log(f"无法导出 i-t 结果：{error}"); return
        selected = filedialog.askdirectory(parent=self.root, title="选择 i-t 结果保存位置")
        if not selected: return
        try: run = export_it_result(result, selected)
        except Exception as error:
            self._log(f"i-t 导出失败：{type(error).__name__}：{error}"); return
        self.workspace.it_workflow.last_export_directory = str(run.output_directory)
        self._log(f"已导出 {len(run.generated_files)} 个 i-t 结果文件：{run.output_directory}")
        self._refresh_it_workflow()

    def _open_it_output(self) -> None:
        directory = self.workspace.it_workflow.last_export_directory
        if not directory:
            self._log("当前 Workspace 尚无已导出的 i-t 结果目录。"); return
        try: open_output_directory(directory)
        except Exception as error: self._log(f"无法打开结果文件夹：{type(error).__name__}：{error}")

    def _show_details(self) -> None:
        if self.current_record is None:
            messagebox.showinfo("详细信息", "请先选择一个文件。", parent=self.root)
            return
        show_record_details(self.root, self.current_record)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)

    def _update_status(self) -> None:
        summary = self.state.summary()
        self.status_text.set(
            f"{self.workspace.name}｜共 {summary.total} 个文件｜成功 {summary.parsed}｜失败 {summary.failed}｜"
            f"不支持 {summary.unsupported}｜LSV {summary.lsv}｜i-t {summary.it}"
        )

    def _on_close(self) -> None:
        if self.runner.busy:
            if not confirm_close_while_busy(self.root):
                return
            self._closing = True
            self.runner.request_cancel()
            self.status_text.set("正在等待当前文件解析完成后关闭……")
            return
        self.root.destroy()


__all__ = ["MainWindow", "WINDOW_TITLE"]
