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

    @staticmethod
    def format_message(message: str) -> str:
        stamp = datetime.now().strftime("%H:%M:%S")
        return f"[{stamp}] {message}"

    def append(self, message: str) -> str:
        line = self.format_message(message)
        self.append_line(line)
        return line

    def append_line(self, line: str) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", f"{line}\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def set_messages(self, messages: list[str]) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if messages:
            self.text.insert("1.0", "\n".join(messages) + "\n")
            self.text.see("end")
        self.text.configure(state="disabled")
