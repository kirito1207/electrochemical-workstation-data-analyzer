"""Responsive Chinese ttk main window for Stage 5.1."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .background import BackgroundRunner, WorkerEvent
from .controller import GUIController, discover_bin_files
from .cursor import CursorReadingSet, build_cursor_readings
from .dialogs import confirm_close_while_busy, show_record_details
from .formatting import parameter_rows
from .pages import IT_STAGE_MESSAGE, LSV_STAGE_MESSAGE, WELCOME_MESSAGE, unsupported_message
from .state import AppState, FileRecord, PreviewDisplayState
from .widgets import CurveList, FileTable, LogPanel, PlotPreview, WorkspaceTabs
from .workspaces import WorkspaceManager, WorkspaceSession


WINDOW_TITLE = "CHI760E 电化学数据分析工具"


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.controller = GUIController()
        self.workspace_manager = WorkspaceManager()
        self.runner = BackgroundRunner()
        self.current_record: FileRecord | None = None
        self._running_workspace_id: str | None = None
        self._closing = False

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
        workspace.rowconfigure(3, weight=3)
        workspace.rowconfigure(4, weight=2)

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

        table_frame = ttk.LabelFrame(workspace, text="文件列表")
        table_frame.grid(row=3, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)
        self.file_table = FileTable(table_frame, on_select=self._record_selected)
        self.file_table.grid(row=0, column=0, sticky="nsew")

        lower = ttk.Panedwindow(workspace, orient="horizontal")
        lower.grid(row=4, column=0, sticky="nsew", pady=(6, 0))
        self.plot_preview = PlotPreview(lower, on_cursor_clicked=self._cursor_clicked)
        lower.add(self.plot_preview, weight=3)

        info = ttk.Frame(lower)
        lower.add(info, weight=2)
        info.columnconfigure(0, weight=1)
        info.rowconfigure(0, weight=3)
        self.curve_list = CurveList(
            info,
            on_visibility_changed=self._visibility_changed,
            on_clear_cursor=self._clear_cursor,
        )
        self.curve_list.grid(row=0, column=0, sticky="nsew")
        self.parameter_box = ttk.LabelFrame(info, text="实验参数")
        self.parameter_box.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.log_panel = LogPanel(info)
        self.log_panel.grid(row=2, column=0, sticky="nsew", pady=(6, 0))

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

    def _render_technique_preview(self, experiment_type: str) -> None:
        collection = self.controller.build_preview_collection(
            self.state.records,
            experiment_type=experiment_type,
            display_state=self.preview_display,
            selected_key=self.selected_by_route.get(experiment_type),
        )
        self.selected_by_route[experiment_type] = collection.selected_key
        readings = self._cursor_readings(collection, experiment_type)
        self.curve_list.set_collection(collection, readings)
        if collection.curves:
            cursor = self.workspace.cursor_by_route[experiment_type]
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
        collection = self.controller.build_preview_collection(
            self.state.records,
            experiment_type=self.current_route,
            display_state=self.preview_display,
            selected_key=self.selected_by_route[self.current_route],
        )
        candidate = build_cursor_readings(self.state.records, collection, requested_x)
        if not any(reading.available for reading in candidate.readings):
            self._log("游标位置超出当前可见曲线的记录范围，未进行外推。")
            return
        self.workspace.cursor_by_route[self.current_route].set(requested_x)
        self._render_technique_preview(self.current_route)

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
            workspace_id, supplied_records = event.payload
            records = tuple(supplied_records)
            session = self.workspace_manager.get(workspace_id)
            if session is None:
                return
            session.state.add_records(records)
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
            self._log(
                f"后台任务异常：{type(event.payload).__name__}：{event.payload}",
                session=session,
            )
        elif event.kind == "finished":
            self._running_workspace_id = None
            self._set_busy(False)
            self._update_status()

    def _record_selected(self, record: FileRecord | None) -> None:
        self.current_record = record
        self._render_parameters(record)
        self.selected_by_route[self.current_route] = record.key if record is not None else None
        if self.current_route in {"LSV", "i-t"}:
            self._render_technique_preview(self.current_route)

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
            ttk.Label(self.parameter_box, text=value, wraplength=390, padding=(2, 1)).grid(row=index, column=1, sticky="nw")
        self.parameter_box.columnconfigure(1, weight=1)

    def _remove_selected(self) -> None:
        selected = self.file_table.selected_records()
        if not selected:
            return
        count = self.state.remove([record.path for record in selected])
        self._log(f"已从当前工作区移除 {count} 个文件；源文件未被修改。")
        self._set_route(self.current_route)

    def _clear(self) -> None:
        if not self.state.records:
            return
        if messagebox.askyesno("清空文件列表", "清空当前文件列表？不会删除磁盘上的源文件。", parent=self.root):
            self.workspace.clear_data()
            self._log("当前工作区文件列表已清空；其他工作区和源文件未被修改。")
            self._set_route(self.current_route)

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
