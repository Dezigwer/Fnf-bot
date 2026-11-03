"""Нативные штрихи Windows 11: тёмный заголовок и скруглённые углы окна.

Прозрачность здесь не включается нигде: окно остаётся полностью непрозрачным,
поэтому клик по фону не может «растворить» программу.
"""

from __future__ import annotations

import ctypes
import tkinter as tk

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2


def apply(root: tk.Misc) -> None:
    """Красит заголовок в тёмный и скругляет углы. Ошибки тихо игнорируются."""
    try:
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        dwm = ctypes.windll.dwmapi
        dark = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(
            hwnd,
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(dark),
            ctypes.sizeof(dark),
        )
        corner = ctypes.c_int(DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(
            hwnd,
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(corner),
            ctypes.sizeof(corner),
        )
    except Exception:
        pass
