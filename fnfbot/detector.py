"""Детектор ноты: сравнение текущего кадра области с эталонным.

Оценка — процент пикселей, которые изменились сильнее порога.
Это устойчивее, чем «средняя яркость»: фон/анимация почти не мешают,
а появившаяся нота даёт резкий скачок.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .config import ArrowConfig


def diff_score(gray: np.ndarray, baseline: np.ndarray, pixel_threshold: int) -> float:
    """0..100 — доля пикселей, изменившихся сильнее порога."""
    if gray.size == 0 or baseline is None:
        return 0.0
    diff = np.abs(gray.astype(np.int16) - baseline)
    changed = int(np.count_nonzero(diff > int(pixel_threshold)))
    return changed * 100.0 / float(diff.size)


class ArrowDetector:
    def __init__(self, arrow: ArrowConfig):
        self.arrow = arrow
        self._baseline: Optional[np.ndarray] = None
        self.reload_baseline()

    # --- эталон ---
    def reload_baseline(self) -> None:
        base = self.arrow.get_baseline()
        self._baseline = None if base is None else base.astype(np.int16)

    @property
    def has_baseline(self) -> bool:
        return self._baseline is not None

    @property
    def baseline_shape(self):
        return None if self._baseline is None else self._baseline.shape

    def _fit(self, shape) -> Optional[np.ndarray]:
        """Подгоняет эталон под размер кадра (если область изменили)."""
        if self._baseline is None:
            return None
        h, w = int(shape[0]), int(shape[1])
        bh, bw = self._baseline.shape
        if h == bh and w == bw:
            return self._baseline
        if h < 1 or w < 1:
            return None
        ys = (np.arange(h) * bh) // h
        xs = (np.arange(w) * bw) // w
        return self._baseline[np.ix_(ys, xs)]

    def score(self, gray: np.ndarray) -> float:
        """0..100 — доля изменившихся пикселей области."""
        base = self._fit(gray.shape)
        if base is None:
            return 0.0
        return diff_score(gray, base, int(self.arrow.pixel_threshold))

    def matches(self, gray: np.ndarray) -> bool:
        return self.score(gray) >= float(self.arrow.area_threshold)


class ColorDetector:
    """Детектор по цвету: сравнивает RGB, а не яркость.

    Нужен для карт, где ноты переливаются. Такая нота может совпасть
    с фоном по яркости, но по каналам R/G/B отличается сильно.
    Порог «цвет» — максимальная разница по каналу (0..255).
    """

    def __init__(self, arrow: ArrowConfig):
        self.arrow = arrow
        self._baseline: Optional[np.ndarray] = None
        self.reload_baseline()

    def reload_baseline(self) -> None:
        base = self.arrow.get_baseline_rgb()
        self._baseline = None if base is None else base.astype(np.int16)

    @property
    def has_baseline(self) -> bool:
        return self._baseline is not None

    @property
    def baseline_shape(self):
        return None if self._baseline is None else self._baseline.shape[:2]

    def _fit(self, shape) -> Optional[np.ndarray]:
        if self._baseline is None:
            return None
        h, w = int(shape[0]), int(shape[1])
        bh, bw = self._baseline.shape[:2]
        if h == bh and w == bw:
            return self._baseline
        if h < 1 or w < 1:
            return None
        ys = (np.arange(h) * bh) // h
        xs = (np.arange(w) * bw) // w
        return self._baseline[np.ix_(ys, xs)]

    def score(self, rgb: np.ndarray) -> float:
        """0..100 — доля пикселей, у которых цвет отличается от эталона."""
        if rgb is None or rgb.ndim != 3 or not self.has_baseline:
            return 0.0
        base = self._fit(rgb.shape)
        if base is None:
            return 0.0
        diff = np.abs(rgb.astype(np.int16) - base)
        channel = diff.max(axis=2)
        changed = int(np.count_nonzero(channel > int(self.arrow.color_threshold)))
        total = int(channel.size)
        if total <= 0:
            return 0.0
        return changed * 100.0 / float(total)

    def matches(self, rgb: np.ndarray) -> bool:
        return self.score(rgb) >= float(self.arrow.area_threshold)
