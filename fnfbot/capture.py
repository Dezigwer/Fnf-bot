"""Захват экрана и вырезание областей нот.

Основной бэкенд — mss (очень быстрый), запасной — PIL.ImageGrab.
Возвращаем сразу grayscale numpy-массивы: так детектор работает за микросекунды.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np

Rect = Tuple[int, int, int, int]
# (красный, зелёный, синий) веса для перевода в grayscale
_LUMA_R, _LUMA_G, _LUMA_B = 77, 150, 29


class ScreenCapture:
    """Захват прямоугольной области экрана в оттенки серого."""

    def __init__(self, backend: str = "auto"):
        self.backend = ""
        self._mss = None
        self._pil = None
        self._lock_owner = None

        if backend in ("auto", "mss"):
            try:
                import mss  # noqa: F401

                self._mss = mss.mss()
                self.backend = "mss"
            except Exception:
                self._mss = None

        if self.backend == "" and backend in ("auto", "pil"):
            try:
                from PIL import ImageGrab

                self._pil = ImageGrab
                self.backend = "pil"
            except Exception:
                self._pil = None

        if not self.backend:
            raise RuntimeError(
                "Не удалось инициализировать захват экрана. "
                "Установите зависимости: pip install -r requirements.txt"
            )

    def grab_gray(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """Снимок области -> массив uint8 (h, w) в оттенках серого."""
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w <= 0 or h <= 0:
            return None

        if self._mss is not None:
            try:
                shot = self._mss.grab({"left": x, "top": y, "width": w, "height": h})
            except Exception:
                return None
            if shot.width <= 0 or shot.height <= 0:
                return None
            buf = np.frombuffer(shot.bgra, dtype=np.uint8)
            arr = buf.reshape(shot.height, shot.width, 4).astype(np.uint16)
            gray = (
                arr[..., 2] * _LUMA_R + arr[..., 1] * _LUMA_G + arr[..., 0] * _LUMA_B
            ) >> 8
            return gray.astype(np.uint8)

        if self._pil is not None:
            try:
                img = self._pil.grab((x, y, x + w, y + h), all_screens=True)
            except Exception:
                try:
                    img = self._pil.grab((x, y, x + w, y + h))
                except Exception:
                    return None
            return np.asarray(img.convert("L"), dtype=np.uint8)

        return None

    def grab_rgb(self, x: int, y: int, w: int, h: int) -> Optional[np.ndarray]:
        """Снимок области -> массив uint8 (h, w, 3) в RGB (для цветового режима)."""
        x, y, w, h = int(x), int(y), int(w), int(h)
        if w <= 0 or h <= 0:
            return None

        if self._mss is not None:
            try:
                shot = self._mss.grab({"left": x, "top": y, "width": w, "height": h})
            except Exception:
                return None
            if shot.width <= 0 or shot.height <= 0:
                return None
            buf = np.frombuffer(shot.bgra, dtype=np.uint8)
            arr = buf.reshape(shot.height, shot.width, 4)
            return np.ascontiguousarray(arr[..., 2::-1])

        if self._pil is not None:
            try:
                img = self._pil.grab((x, y, x + w, y + h), all_screens=True)
            except Exception:
                try:
                    img = self._pil.grab((x, y, x + w, y + h))
                except Exception:
                    return None
            return np.asarray(img.convert("RGB"), dtype=np.uint8)

        return None

    def close(self) -> None:
        if self._mss is not None:
            try:
                self._mss.close()
            except Exception:
                pass
            self._mss = None


class RegionGrabber:
    """Делает снимки сразу нескольких областей, по возможности одним захватом."""

    def __init__(self, regions: Dict[str, Rect], color: bool = False):
        self.regions: Dict[str, Rect] = {}
        self.color = bool(color)
        for name, rect in regions.items():
            x, y, w, h = (int(v) for v in rect)
            if w >= 2 and h >= 2:
                self.regions[name] = (x, y, w, h)

        self.capture = ScreenCapture()
        self.union: Optional[Rect] = None
        self._single_shot = False
        if self.regions:
            self.union = self._union_rect(self.regions.values())
            area_union = self.union[2] * self.union[3]
            area_sum = sum(w * h for _, _, w, h in self.regions.values())
            # Один общий захват выгоден, пока объединение не сильно больше суммы областей
            self._single_shot = area_union <= max(area_sum * 3, area_sum + 200_000)

    @staticmethod
    def _union_rect(rects) -> Rect:
        xs, ys, xe, ye = [], [], [], []
        for x, y, w, h in rects:
            xs.append(x)
            ys.append(y)
            xe.append(x + w)
            ye.append(y + h)
        x0, y0 = min(xs), min(ys)
        return x0, y0, max(xe) - x0, max(ye) - y0

    def describe(self) -> str:
        mode = "одним снимком" if self._single_shot else "по областям"
        kind = "цвет" if self.color else "серый"
        return f"{self.capture.backend}, {kind}, областей: {len(self.regions)}, {mode}"

    def grab(self) -> Dict[str, np.ndarray]:
        out: Dict[str, np.ndarray] = {}
        if not self.regions:
            return out

        grab_one = self.capture.grab_rgb if self.color else self.capture.grab_gray

        if self._single_shot and self.union is not None:
            ux, uy, uw, uh = self.union
            frame = grab_one(ux, uy, uw, uh)
            if frame is not None and frame.shape[0] == uh and frame.shape[1] == uw:
                for name, (x, y, w, h) in self.regions.items():
                    out[name] = frame[y - uy:y - uy + h, x - ux:x - ux + w]
                return out
            # не получилось общим снимком — падаем на поштучный режим
            self._single_shot = False

        for name, (x, y, w, h) in self.regions.items():
            frame = grab_one(x, y, w, h)
            if frame is not None:
                out[name] = frame
        return out

    def close(self) -> None:
        self.capture.close()
