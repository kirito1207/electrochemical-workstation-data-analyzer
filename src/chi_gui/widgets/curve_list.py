"""Compact scrollable curve list; visibility affects preview only."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..state import PreviewCollection


class CurveList(ttk.LabelFrame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_visibility_changed: Callable[[str, bool], None],
    ):
        super().__init__(master, text="曲线列表（仅控制预览）")
        self._callback = on_visibility_changed
        self._variables: dict[str, tk.BooleanVar] = {}
        self.canvas = tk.Canvas(self, height=112, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True, padx=(5, 0), pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)
        self.inner.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)

    def set_collection(self, collection: PreviewCollection | None) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._variables.clear()
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

    def _sync_scrollregion(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)


__all__ = ["CurveList"]
