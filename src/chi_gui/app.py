"""Application bootstrap kept separate for import-safe headless tests."""

from __future__ import annotations

import tkinter as tk

from .main_window import MainWindow


def create_application() -> tuple[tk.Tk, MainWindow]:
    root = tk.Tk()
    window = MainWindow(root)
    return root, window


def main() -> None:
    try:
        root, _window = create_application()
    except tk.TclError as error:
        raise SystemExit(
            "无法启动图形界面：当前环境没有可用桌面显示。"
            "请在 Windows 或带图形桌面的环境运行 python -m chi_gui。"
        ) from error
    root.mainloop()


__all__ = ["create_application", "main"]
