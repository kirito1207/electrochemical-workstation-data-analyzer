"""Compact scrollable curve list; visibility affects preview only."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..cursor import CursorReadingSet
from ..state import PreviewCollection


class CurveList(ttk.LabelFrame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_visibility_changed: Callable[[str, bool], None],
        on_clear_cursor: Callable[[], None],
    ):
        super().__init__(master, text="曲线列表（仅控制预览）")
        self._callback = on_visibility_changed
        self._clear_cursor = on_clear_cursor
        self._variables: dict[str, tk.BooleanVar] = {}

        heading = ttk.Frame(self)
        heading.pack(fill="x", padx=6, pady=(4, 0))
        self.cursor_text = tk.StringVar(value="游标：—")
        ttk.Label(heading, textvariable=self.cursor_text).pack(side="left")
        ttk.Label(heading, text="Current / µA").pack(side="right", padx=(8, 2))
        ttk.Button(heading, text="清除游标", command=self._clear_cursor).pack(
            side="right", padx=(4, 8)
        )

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, height=190, highlightthickness=0)
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
    ) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._variables.clear()
        if readings is None:
            self.cursor_text.set("游标：—")
            readings_by_key = {}
        else:
            unit = "V" if readings.experiment_type == "LSV" else "s"
            precision = 3 if readings.experiment_type == "LSV" else 1
            self.cursor_text.set(f"游标：{readings.requested_x:.{precision}f} {unit}")
            readings_by_key = readings.by_record_key()
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
                text=curve.file_name,
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

    def _sync_scrollregion(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)


__all__ = ["CurveList"]
