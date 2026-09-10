"""In-memory raw-data preview; never writes into results/."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from ..state import PreviewData


class PlotPreview(ttk.LabelFrame):
    def __init__(self, master: tk.Misc):
        super().__init__(master, text="原始曲线预览")
        self.figure = Figure(figsize=(6.4, 4.0), dpi=100, constrained_layout=True)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.clear("请选择一个解析成功的文件")

    def clear(self, message: str = "暂无预览") -> None:
        self.axis.clear()
        self.axis.text(0.5, 0.5, message, ha="center", va="center", transform=self.axis.transAxes)
        self.axis.set_axis_off()
        self.canvas.draw_idle()

    def show_preview(self, preview: PreviewData) -> None:
        self.axis.clear()
        self.axis.set_axis_on()
        self.axis.plot(preview.x, preview.current_uA, color="#1769aa", linewidth=1.1)
        self.axis.set_xlabel(preview.x_label)
        self.axis.set_ylabel(preview.y_label)
        self.axis.set_title(f"{preview.experiment_type} — {preview.source_file.name}")
        self.axis.grid(True, alpha=0.22)
        self.canvas.draw_idle()
