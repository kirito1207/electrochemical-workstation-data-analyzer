"""Compact scrollable curve list; visibility affects preview only."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..cursor import CursorReadingSet, InspectionCursorState
from ..layout import DATA_PAGE_RIGHT_PREFERRED_PX, compact_filename
from ..state import PreviewCollection


class CurveList(ttk.LabelFrame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_visibility_changed: Callable[[str, bool], None],
        on_clear_cursor: Callable[[], None],
        on_cursor_submitted: Callable[[str], None],
        on_cursor_step: Callable[[int], None],
    ):
        super().__init__(master, text="曲线列表（仅控制预览）")
        self._callback = on_visibility_changed
        self._clear_cursor = on_clear_cursor
        self._submit_cursor = on_cursor_submitted
        self._step_cursor = on_cursor_step
        self._variables: dict[str, tk.BooleanVar] = {}

        heading = ttk.Frame(self)
        heading.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(heading, text="游标：").pack(side="left")
        self.cursor_input = tk.StringVar()
        self.cursor_entry = ttk.Entry(heading, textvariable=self.cursor_input, width=11)
        self.cursor_entry.pack(side="left")
        self.cursor_entry.bind("<Return>", self._cursor_entered)
        self.cursor_entry.bind("<KP_Enter>", self._cursor_entered)
        self.cursor_entry.bind("<Left>", lambda event: self._cursor_key(event, -1))
        self.cursor_entry.bind("<Right>", lambda event: self._cursor_key(event, 1))
        self.cursor_unit = tk.StringVar(value="")
        ttk.Label(heading, textvariable=self.cursor_unit).pack(side="left", padx=(3, 5))
        self.cursor_status = tk.StringVar(value="")
        ttk.Label(heading, textvariable=self.cursor_status, foreground="#a34a00").pack(
            side="left"
        )
        ttk.Label(heading, text="Current / µA").pack(side="right", padx=(8, 2))
        ttk.Button(heading, text="清除游标", command=self._clear_cursor).pack(
            side="right", padx=(4, 8)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(
            body,
            width=DATA_PAGE_RIGHT_PREFERRED_PX,
            height=190,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)

    def set_collection(
        self,
        collection: PreviewCollection | None,
        readings: CursorReadingSet | None = None,
        cursor_state: InspectionCursorState | None = None,
    ) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._variables.clear()
        experiment_type = collection.experiment_type if collection is not None else ""
        self.cursor_unit.set("V" if experiment_type == "LSV" else "s" if experiment_type == "i-t" else "")
        self.cursor_input.set(cursor_state.input_text if cursor_state is not None else "")
        self.cursor_status.set(cursor_state.validation_message if cursor_state is not None else "")
        readings_by_key = readings.by_record_key() if readings is not None else {}
        if collection is None or not collection.curves:
            ttk.Label(self.inner, text="暂无曲线", padding=5).grid(sticky="w")
            return
        for row, curve in enumerate(collection.curves):
            variable = tk.BooleanVar(value=curve.visible)
            self._variables[curve.record_key] = variable
            tk.Label(self.inner, text="■", fg=curve.color, font=("Segoe UI Symbol", 11)).grid(
                row=row, column=0, padx=(4, 1), sticky="w"
            )
            ttk.Checkbutton(
                self.inner,
                text=compact_filename(curve.file_name),
                variable=variable,
                command=lambda key=curve.record_key, value=variable: self._callback(key, value.get()),
            ).grid(row=row, column=1, sticky="w")
            reading = readings_by_key.get(curve.record_key)
            if reading is None:
                value = "—"
            elif reading.available:
                value = f"{reading.current_uA:.3f}"
            else:
                value = "超出范围"
            ttk.Label(self.inner, text=value, anchor="e", width=13).grid(
                row=row, column=2, padx=(8, 4), sticky="e"
            )
        self.inner.columnconfigure(1, weight=1)

    def _cursor_entered(self, _event: tk.Event) -> str:
        self._submit_cursor(self.cursor_input.get())
        return "break"

    def _cursor_key(self, _event: tk.Event, direction: int) -> str:
        self._step_cursor(direction)
        return "break"

    def _sync_scrollregion(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)


__all__ = ["CurveList"]
