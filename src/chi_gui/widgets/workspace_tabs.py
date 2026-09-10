"""Compact browser-style workspace tab strip for a single MainWindow."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from ..workspaces import WorkspaceSession


class WorkspaceTabs(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_select: Callable[[str], None],
        on_new: Callable[[], None],
        on_close: Callable[[str], None],
        on_rename: Callable[[str], None],
    ):
        super().__init__(master)
        self._on_select = on_select
        self._on_new = on_new
        self._on_close = on_close
        self._on_rename = on_rename
        self.canvas = tk.Canvas(self, height=38, highlightthickness=0)
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        scrollbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(xscrollcommand=scrollbar.set)
        self.canvas.pack(fill="x", expand=True)
        scrollbar.pack(fill="x")
        self.inner.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._fit_inner)

    def set_sessions(
        self, sessions: tuple[WorkspaceSession, ...], active_id: str
    ) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        for session in sessions:
            tab = ttk.Frame(self.inner, padding=(2, 1))
            tab.pack(side="left")
            prefix = "● " if session.workspace_id == active_id else ""
            label = ttk.Button(
                tab,
                text=f"{prefix}{session.name}",
                command=lambda item=session.workspace_id: self._on_select(item),
                padding=(10, 5),
            )
            label.pack(side="left")
            label.bind(
                "<Double-Button-1>",
                lambda _event, item=session.workspace_id: self._on_rename(item),
            )
            ttk.Button(
                tab,
                text="×",
                width=3,
                command=lambda item=session.workspace_id: self._on_close(item),
            ).pack(side="left", padx=(1, 4))
        ttk.Button(self.inner, text="+", width=4, command=self._on_new).pack(
            side="left", padx=(2, 0)
        )

    def _update_scroll_region(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _fit_inner(self, event: tk.Event) -> None:
        requested = self.inner.winfo_reqwidth()
        self.canvas.itemconfigure(self.window_id, width=max(event.width, requested))


__all__ = ["WorkspaceTabs"]
