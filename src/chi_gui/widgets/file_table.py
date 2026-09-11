"""Scrollable file table backed by ttk.Treeview."""

from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Callable

from ..formatting import primary_parameter_text
from ..state import FileRecord


@dataclass(slots=True)
class SelectionCallbackGate:
    """Suppress duplicate or synthetic Treeview selection notifications.

    Tk may deliver ``<<TreeviewSelect>>`` synchronously or after the method
    performing a programmatic selection has returned. Recording the final
    selection token handles both cases without relying on ``after()`` timing.
    """

    last_token: tuple[str, ...] = ()
    suppression_depth: int = 0

    def begin_programmatic_update(self) -> None:
        self.suppression_depth += 1

    def end_programmatic_update(self, token: tuple[str, ...]) -> None:
        self.last_token = token
        self.suppression_depth = max(0, self.suppression_depth - 1)

    def should_notify(self, token: tuple[str, ...]) -> bool:
        if self.suppression_depth or token == self.last_token:
            return False
        self.last_token = token
        return True


class FileTable(ttk.Frame):
    def __init__(self, master: tk.Misc, *, on_select: Callable[[FileRecord | None], None]):
        super().__init__(master)
        self._records: dict[str, FileRecord] = {}
        self._on_select = on_select
        self._selection_gate = SelectionCallbackGate()
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
        self._selection_gate.begin_programmatic_update()
        try:
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
        finally:
            self._selection_gate.end_programmatic_update(tuple(self.tree.selection()))

    def selected_records(self) -> tuple[FileRecord, ...]:
        return tuple(self._records[item] for item in self.tree.selection() if item in self._records)

    def select_record(self, key: str | None) -> bool:
        """Synchronize selection without notifying the user-action callback.

        Returns ``True`` only when the Treeview selection actually changed.
        """

        desired = (key,) if key is not None and key in self._records else ()
        current = tuple(self.tree.selection())
        if current == desired:
            self._selection_gate.last_token = desired
            return False

        self._selection_gate.begin_programmatic_update()
        try:
            if desired:
                self.tree.selection_set(desired[0])
                self.tree.focus(desired[0])
                self.tree.see(desired[0])
            else:
                self.tree.selection_remove(current)
        finally:
            self._selection_gate.end_programmatic_update(tuple(self.tree.selection()))
        return True

    def _selection_changed(self, _event: tk.Event) -> None:
        token = tuple(self.tree.selection())
        if not self._selection_gate.should_notify(token):
            return
        selected = self.selected_records()
        self._on_select(selected[0] if len(selected) == 1 else None)

    def _select_all(self, _event: tk.Event) -> str:
        self.tree.selection_set(self.tree.get_children())
        return "break"
