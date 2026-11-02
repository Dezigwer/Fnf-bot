"""Полноэкранные оверлеи: выделение области мышью и показ размеченных зон."""

from __future__ import annotations

import tkinter as tk
from typing import Dict, Optional, Tuple

from .screenshot import screen_size

COLOR_SELECT = "#2bff88"
COLOR_DIM = "#000000"


def pick_region(
    parent: Optional[tk.Misc] = None,
    hint: str = "Выделите область ноты мышью. Esc — отмена",
    alpha: float = 0.4,
) -> Optional[Tuple[int, int, int, int]]:
    """Даёт пользователю обвести прямоугольник поверх экрана.

    Возвращает (x, y, w, h) в экранных пикселях или None при отмене.
    """
    sw, sh = screen_size()
    top = tk.Toplevel(parent) if parent is not None else tk.Tk()
    top.withdraw()
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", alpha)
    top.geometry(f"{sw}x{sh}+0+0")
    top.configure(bg=COLOR_DIM)

    canvas = tk.Canvas(
        top, bg=COLOR_DIM, highlightthickness=0, cursor="crosshair", bd=0
    )
    canvas.pack(fill="both", expand=True)

    result: Dict[str, Optional[Tuple[int, int, int, int]]] = {"rect": None}
    state = {"x0": 0, "y0": 0, "rect": None, "label": None}

    canvas.create_text(
        sw // 2,
        34,
        text=hint,
        fill="#ffffff",
        font=("Segoe UI", 16, "bold"),
        width=sw - 80,
        justify="center",
    )
    canvas.create_text(
        sw // 2,
        sh - 28,
        text="ЛКМ — обвести · Esc / ПКМ — отмена",
        fill="#c9ffd8",
        font=("Segoe UI", 11),
    )

    def on_press(event):
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline=COLOR_SELECT, width=2
        )
        state["label"] = canvas.create_text(
            event.x + 8,
            max(12, event.y - 14),
            text="",
            fill=COLOR_SELECT,
            font=("Consolas", 11, "bold"),
            anchor="w",
        )

    def on_motion(event):
        if state["rect"] is None:
            return
        canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)
        w = abs(event.x - state["x0"])
        h = abs(event.y - state["y0"])
        canvas.coords(state["label"], min(event.x, state["x0"]) + 6, max(14, event.y - 12))
        canvas.itemconfigure(state["label"], text=f"{w}×{h}")

    def on_release(event):
        w = abs(event.x - state["x0"])
        h = abs(event.y - state["y0"])
        if w >= 3 and h >= 3:
            x = min(event.x, state["x0"])
            y = min(event.y, state["y0"])
            result["rect"] = (int(x), int(y), int(w), int(h))
        close()

    def close(_event=None):
        try:
            top.grab_release()
        except Exception:
            pass
        top.destroy()

    def cancel(_event=None):
        result["rect"] = None
        close()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_motion)
    canvas.bind("<ButtonRelease-1>", on_release)
    canvas.bind("<ButtonPress-3>", cancel)
    top.bind("<Escape>", cancel)
    top.bind("<ButtonPress-3>", cancel)

    top.deiconify()
    top.lift()
    top.attributes("-topmost", True)
    top.focus_force()
    try:
        top.grab_set()
    except Exception:
        pass
    top.wait_window(top)
    return result["rect"]


def show_regions(
    parent: Optional[tk.Misc],
    regions: Dict[str, Tuple[int, int, int, int]],
    labels: Optional[Dict[str, str]] = None,
    title: str = "Проверка областей: рамки должны совпасть со стрелками в игре",
    duration: float = 5.0,
    alpha: float = 0.3,
) -> None:
    """Показывает рамки поверх экрана, чтобы проверить привязку координат."""
    labels = labels or {}
    sw, sh = screen_size()
    top = tk.Toplevel(parent) if parent is not None else tk.Tk()
    top.overrideredirect(True)
    top.attributes("-topmost", True)
    top.attributes("-alpha", alpha)
    top.geometry(f"{sw}x{sh}+0+0")

    canvas = tk.Canvas(top, bg="#000000", highlightthickness=0, bd=0)
    canvas.pack(fill="both", expand=True)

    canvas.create_text(
        sw // 2,
        30,
        text=title,
        fill="#ffffff",
        font=("Segoe UI", 14, "bold"),
        width=sw - 80,
        justify="center",
    )

    colors = {"left": "#4fd1ff", "down": "#ffe066", "up": "#ff8fab", "right": "#8affc1"}
    for name, rect in regions.items():
        x, y, w, h = rect
        if w < 2 or h < 2:
            continue
        color = colors.get(name, "#ffffff")
        canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=2)
        text = labels.get(name, name)
        canvas.create_text(
            x,
            max(12, y - 10),
            text=text,
            fill=color,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )

    canvas.create_text(
        sw // 2,
        sh - 26,
        text="Esc — закрыть (закроется само)",
        fill="#dddddd",
        font=("Segoe UI", 10),
    )

    def close(_event=None):
        try:
            top.destroy()
        except Exception:
            pass

    top.bind("<Escape>", close)
    canvas.bind("<Button-1>", close)
    top.focus_force()
    if duration > 0:
        top.after(int(duration * 1000), close)
