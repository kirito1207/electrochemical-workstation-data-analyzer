"""Compact user-visible activity log."""

from __future__ import annotations

from datetime import datetime
import tkinter as tk
from tkinter import scrolledtext, ttk


class LogPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc):
        super().__init__(master, text="消息与日志")
        self._expanded = False
        heading = ttk.Frame(self)
        heading.pack(fill="x", padx=6, pady=4)
        self.summary = tk.StringVar(value="暂无消息")
        ttk.Label(heading, textvariable=self.summary).pack(side="left", fill="x", expand=True)
        self.toggle_button = ttk.Button(heading, text="日志 ▼", command=self._toggle)
        self.toggle_button.pack(side="right")
        self.body = ttk.Frame(self)
        self.text = scrolledtext.ScrolledText(self.body, height=5, wrap="word", state="disabled")
        self.text.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="both", expand=True)
            self.toggle_button.configure(text="日志 ▲")
        else:
            self.body.pack_forget()
            self.toggle_button.configure(text="日志 ▼")

    @staticmethod
    def format_message(message: str) -> str:
        stamp = datetime.now().strftime("%H:%M:%S")
        return f"[{stamp}] {message}"

    def append(self, message: str) -> str:
        line = self.format_message(message)
        self.append_line(line)
        return line

    def append_line(self, line: str) -> None:
        self.summary.set(line)
        self.text.configure(state="normal")
        self.text.insert("end", f"{line}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def set_messages(self, messages: list[str]) -> None:
        self.summary.set(messages[-1] if messages else "暂无消息")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if messages:
            self.text.insert("1.0", "\n".join(messages) + "\n")
            self.text.see("end")
        self.text.configure(state="disabled")
