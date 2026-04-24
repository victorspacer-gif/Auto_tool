"""Entry point for the refactored SystemMonitor application."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def _show_startup_splash() -> tk.Tk:
    splash = tk.Tk()
    splash.title("Starting SystemMonitor")
    splash.configure(bg="#10161f")
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)

    width = 420
    height = 150
    screen_w = splash.winfo_screenwidth()
    screen_h = splash.winfo_screenheight()
    pos_x = (screen_w - width) // 2
    pos_y = (screen_h - height) // 2
    splash.geometry(f"{width}x{height}+{pos_x}+{pos_y}")

    frame = tk.Frame(splash, bg="#10161f", padx=24, pady=22)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text="SystemMonitor",
        font=("Segoe UI Semibold", 18),
        fg="#f4f7fb",
        bg="#10161f",
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        frame,
        text="Loading interface and automation services...",
        font=("Segoe UI", 10),
        fg="#99a8bb",
        bg="#10161f",
        anchor="w",
    ).pack(fill="x", pady=(8, 16))

    progress = ttk.Progressbar(frame, mode="indeterminate", length=360)
    progress.pack(fill="x")
    progress.start(12)

    splash.update_idletasks()
    splash.update()
    return splash


def main() -> None:
    splash = _show_startup_splash()
    try:
        from systool.app import run

        splash.update_idletasks()
        splash.update()
    finally:
        splash.destroy()
    run()


if __name__ == "__main__":
    main()
