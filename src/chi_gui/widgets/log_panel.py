"""Compact user-visible activity log."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, ttk


class LogPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc):
        super().__init__(master, text="消息与日志")
        self.text = scrolledtext.ScrolledText(self, height=7, wrap="word", state="disabled")
        self.text.pack(fill="both", expand=True, padx=6, pady=6)

    def append(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.text.configure(state="normal")
        self.text.insert("end", f"[{stamp}] {message}\n")
        self.text.see("end")
        self.text.configure(state="disabled")
