"""In-memory raw-data preview; never writes into results/."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import numpy as np

from ..state import PreviewCollection


MAX_PREVIEW_POINTS = 5000


def downsample_for_display(x, y, *, max_points: int = MAX_PREVIEW_POINTS):
    """Return display-only samples while preserving the full parser arrays."""

    if len(x) <= max_points:
        return x, y
    indices = np.linspace(0, len(x) - 1, max_points, dtype=np.int64)
    return x[indices], y[indices]


class PlotPreview(ttk.LabelFrame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        on_cursor_clicked: Callable[[float], None] | None = None,
        on_cursor_step: Callable[[int], None] | None = None,
    ):
        super().__init__(master, text="原始曲线预览")
        self._on_cursor_clicked = on_cursor_clicked
        self._on_cursor_step = on_cursor_step
        self.figure = Figure(figsize=(6.4, 4.0), dpi=100, constrained_layout=True)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.configure(takefocus=True)
        canvas_widget.pack(fill="both", expand=True)
        canvas_widget.bind("<Left>", lambda event: self._handle_key(event, -1))
        canvas_widget.bind("<Right>", lambda event: self._handle_key(event, 1))
        self.canvas.mpl_connect("button_press_event", self._handle_click)
        self.clear("请选择一个解析成功的文件")

    def _handle_click(self, event) -> None:
        if (
            self._on_cursor_clicked is not None
            and event.button == 1
            and event.inaxes is self.axis
            and event.xdata is not None
        ):
            self.canvas.get_tk_widget().focus_set()
            self._on_cursor_clicked(float(event.xdata))

    def _handle_key(self, _event: tk.Event, direction: int) -> str:
        if self._on_cursor_step is not None:
            self._on_cursor_step(direction)
        return "break"

    def clear(self, message: str = "暂无预览") -> None:
        self.axis.clear()
        self.axis.text(0.5, 0.5, message, ha="center", va="center", transform=self.axis.transAxes)
        self.axis.set_axis_off()
        self.canvas.draw_idle()

    def show_collection(
        self,
        collection: PreviewCollection,
        *,
        cursor_x: float | None = None,
    ) -> None:
        self.axis.clear()
        self.axis.set_axis_on()
        visible = collection.visible_curves
        if not visible:
            self.clear("当前页面没有可见曲线")
            return
        for curve in visible:
            x, current_uA = downsample_for_display(curve.data.x, curve.data.current_uA)
            self.axis.plot(
                x,
                current_uA,
                color=curve.color,
                linewidth=2.4 if curve.selected else 1.0,
                alpha=1.0 if curve.selected else 0.72,
                zorder=3 if curve.selected else 1,
            )
        exemplar = visible[0].data
        self.axis.set_xlabel(exemplar.x_label)
        self.axis.set_ylabel(exemplar.y_label)
        self.axis.set_title(
            f"{collection.experiment_type} 原始曲线预览（可见 {len(visible)}/{len(collection.curves)}）"
        )
        if cursor_x is not None:
            self.axis.axvline(
                cursor_x,
                color="#333333",
                linewidth=1.2,
                linestyle="--",
                alpha=0.85,
                zorder=5,
            )
        self.axis.grid(True, alpha=0.22)
        self.canvas.draw_idle()


__all__ = ["MAX_PREVIEW_POINTS", "PlotPreview", "downsample_for_display"]
