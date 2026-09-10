"""Scrollable file table backed by ttk.Treeview."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..formatting import primary_parameter_text
from ..state import FileRecord


class FileTable(ttk.Frame):
    def __init__(self, master: tk.Misc, *, on_select: Callable[[FileRecord | None], None]):
        super().__init__(master)
        self._records: dict[str, FileRecord] = {}
        self._on_select = on_select
        columns = ("status", "name", "experiment", "points", "parameters")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="extended")
        headings = {
            "status": "状态",
            "name": "文件名",
            "experiment": "实验类型",
            "points": "数据点数",
            "parameters": "主要参数",
        }
        widths = {"status": 90, "name": 300, "experiment": 100, "points": 90, "parameters": 360}
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(column, width=widths[column], minwidth=70, stretch=column in {"name", "parameters"})
        y_scroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._selection_changed)
        self.tree.bind("<Control-a>", self._select_all)

    def set_records(self, records: tuple[FileRecord, ...]) -> None:
        self.tree.delete(*self.tree.get_children())
        self._records = {record.key: record for record in records}
        for record in records:
            points = record.data.n_points if record.data is not None else "—"
            self.tree.insert(
                "",
                "end",
                iid=record.key,
                values=(
                    record.status.value,
                    record.path.name,
                    record.experiment_type,
                    points,
                    primary_parameter_text(record.data),
                ),
            )

    def selected_records(self) -> tuple[FileRecord, ...]:
        return tuple(self._records[item] for item in self.tree.selection() if item in self._records)

    def _selection_changed(self, _event: tk.Event) -> None:
        selected = self.selected_records()
        self._on_select(selected[0] if len(selected) == 1 else None)

    def _select_all(self, _event: tk.Event) -> str:
        self.tree.selection_set(self.tree.get_children())
        return "break"
