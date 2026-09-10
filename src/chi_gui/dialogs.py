"""User-facing dialogs with concise Chinese summaries and optional diagnostics."""

from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk

from .state import FileRecord


def show_record_details(parent: tk.Misc, record: FileRecord) -> None:
    window = tk.Toplevel(parent)
    window.title(f"文件详细信息 — {record.path.name}")
    window.geometry("760x520")
    window.minsize(560, 360)
    window.transient(parent)

    summary = record.error_message or "解析成功"
    ttk.Label(window, text=summary, wraplength=720, justify="left").pack(
        fill="x", padx=12, pady=(12, 6)
    )
    text = tk.Text(window, wrap="word", font=("Consolas", 9))
    text.pack(fill="both", expand=True, padx=12, pady=6)
    payload = {
        "file": str(record.path),
        "status": record.status.value,
        "experiment_type": record.experiment_type,
        "error_type": record.error_type,
        "error_message": record.error_message,
        "warnings": record.warning_messages,
        "diagnostic": record.diagnostic,
    }
    text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    text.configure(state="disabled")
    ttk.Button(window, text="关闭", command=window.destroy).pack(pady=(4, 12))


def confirm_close_while_busy(parent: tk.Misc) -> bool:
    return messagebox.askyesno(
        "后台任务仍在运行",
        "解析任务尚未结束。是否请求取消，并在当前文件处理完成后关闭？",
        parent=parent,
    )
