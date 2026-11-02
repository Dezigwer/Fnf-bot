"""Вспомогательные функции для скриншотов игры."""

from __future__ import annotations

import os
import time
from typing import Optional, Tuple

import numpy as np

from . import APP_DIR

SHOTS_DIR = os.path.join(APP_DIR, "shots")


def screen_size() -> Tuple[int, int]:
    """Размер основного экрана в физических пикселях."""
    import ctypes

    user32 = ctypes.windll.user32
    return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))


def grab_screen():
    """Снимок основного экрана как PIL.Image (RGB)."""
    from PIL import Image

    import mss

    sw, sh = screen_size()
    with mss.mss() as sct:
        shot = sct.grab({"left": 0, "top": 0, "width": sw, "height": sh})
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def load_image(path: str):
    from PIL import Image

    img = Image.open(path)
    img.load()
    return img.convert("RGB")


def save_screenshot(img, prefix: str = "shot") -> str:
    os.makedirs(SHOTS_DIR, exist_ok=True)
    path = os.path.join(SHOTS_DIR, f"{prefix}_{time.strftime('%Y%m%d_%H%M%S')}.png")
    img.save(path)
    return path


def region_gray(img, rect: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """Вырезает область скриншота и отдаёт grayscale-массив (эталонный кадр)."""
    x, y, w, h = (int(v) for v in rect)
    if w < 1 or h < 1:
        return None
    iw, ih = img.size
    x = max(0, min(iw - 1, x))
    y = max(0, min(ih - 1, y))
    w = max(1, min(w, iw - x))
    h = max(1, min(h, ih - y))
    crop = img.crop((x, y, x + w, y + h)).convert("L")
    return np.asarray(crop, dtype=np.uint8)


def region_rgb(img, rect: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    """То же самое, но в RGB: эталон для режима «цвет»."""
    x, y, w, h = (int(v) for v in rect)
    if w < 1 or h < 1:
        return None
    iw, ih = img.size
    x = max(0, min(iw - 1, x))
    y = max(0, min(ih - 1, y))
    w = max(1, min(w, iw - x))
    h = max(1, min(h, ih - y))
    crop = img.crop((x, y, x + w, y + h)).convert("RGB")
    return np.asarray(crop, dtype=np.uint8)
