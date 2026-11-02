"""Ликвид-гласс для окна Tk на Windows 11.

Tk не умеет полупрозрачные виджеты, поэтому используется связка:
1. DWM-акрил (SetWindowCompositionAttribute) размывает то, что за окном;
2. цвет-ключ `-transparentcolor` делает пиксели цвета KEY полностью прозрачными.

В итоге фон окна — размытое стекло с тёмным оттенком, а текст, поля и кнопки
рисуются обычными непрозрачными цветами и остаются чёткими.

Если Windows старее или efecto недоступен, всё тихо откатывается к обычному
тёмному фону — приложение продолжает работать.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
from typing import Optional

KEY = "#010101"  # цвет-ключ: всё, что им залито, становится прозрачным

ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2

# AABBGGRR: альфа 0x99, цвет почти чёрный — стекло тёмное, текст читается
DEFAULT_TINT = 0x99101010


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _CompositionData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _hwnd(root) -> int:
    hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
    return int(hwnd or root.winfo_id())


def _apply_accent(hwnd: int, tint: int) -> bool:
    try:
        policy = _AccentPolicy(ACCENT_ENABLE_ACRYLICBLURBEHIND, 2, tint, 0)
        data = _CompositionData(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            ctypes.sizeof(policy),
        )
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wt.HWND, ctypes.POINTER(_CompositionData)]
        fn.restype = ctypes.c_int
        if fn(hwnd, ctypes.byref(data)):
            return True
    except Exception:
        pass

    # Запасной вариант для старых сборок Windows 10.
    try:
        policy = _AccentPolicy(ACCENT_ENABLE_BLURBEHIND, 2, tint, 0)
        data = _CompositionData(
            WCA_ACCENT_POLICY,
            ctypes.cast(ctypes.pointer(policy), ctypes.c_void_p),
            ctypes.sizeof(policy),
        )
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wt.HWND, ctypes.POINTER(_CompositionData)]
        fn.restype = ctypes.c_int
        return bool(fn(hwnd, ctypes.byref(data)))
    except Exception:
        return False


def _round_corners(hwnd: int) -> None:
    try:
        value = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wt.HWND(hwnd),
            DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def enable(root, tint: int = DEFAULT_TINT, transparent_key: Optional[str] = KEY) -> bool:
    """Включает стекло. Возвращает True, если прозрачность удалась."""
    try:
        root.update_idletasks()
    except Exception:
        pass

    hwnd = _hwnd(root)
    _round_corners(hwnd)

    transparent = False
    if transparent_key:
        try:
            root.wm_attributes("-transparentcolor", transparent_key)
            transparent = True
        except Exception:
            transparent = False

    if transparent:
        _apply_accent(hwnd, tint)
    return transparent
