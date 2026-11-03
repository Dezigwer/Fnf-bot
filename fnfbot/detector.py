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
    """Детектор по точному цвету ноты.

    У каждого направления свой цвет (левая нота фиолетовая, нижняя голубая
    и т. д.). Бот считает, какая доля пикселей области близка к этому цвету:
    фон приёмника в него не попадает, а пришедшая нота даёт резкий скачок.
    Эталон не нужен — цвет задаётся в настройках.
    """

    def __init__(self, arrow: ArrowConfig):
        self.arrow = arrow
        self._target: Optional[np.ndarray] = None
        self._chroma: Optional[np.ndarray] = None
        self._brightness = 0.0
        self.reload_baseline()

    def reload_baseline(self) -> None:
        rgb = self.arrow.note_rgb()
        if rgb is None:
            self._target = None
            self._chroma = None
            self._brightness = 0.0
            return
        self._target = np.array(rgb, dtype=np.int32)
        # «Оттенок» как доля каждого канала: не зависит от яркости.
        total = float(sum(rgb)) or 1.0
        self._chroma = np.array([c / total for c in rgb], dtype=np.float32)
        self._brightness = float(max(rgb))

    @property
    def has_baseline(self) -> bool:
        # Имя оставлено для движка: детектор готов, если задан цвет ноты.
        return self._target is not None

    @property
    def baseline_shape(self):
        return None

    @property
    def target(self) -> Optional[np.ndarray]:
        return None if self._target is None else self._target.copy()

    def score(self, rgb: np.ndarray) -> float:
        """0..100 — доля пикселей, попавших в допуск вокруг цвета ноты."""
        if rgb is None or rgb.ndim != 3 or self._target is None:
            return 0.0
        # int32 обязателен: 255² не влезает в int16 и переполняет квадрат.
        diff = rgb[..., :3].astype(np.int32) - self._target.astype(np.int32)
        # евклидово расстояние в RGB: допускает лёгкую тень и подсветку.
        # Сравниваем квадраты — так быстрее и без корня/NaN.
        limit = float(self.arrow.color_threshold)
        squared = np.sum(diff * diff, axis=2)
        hit = int(np.count_nonzero(squared <= limit * limit))
        total = int(squared.size)
        if total <= 0:
            return 0.0
        return hit * 100.0 / float(total)

    def shade_score(self, rgb: np.ndarray) -> float:
        """0..100 — доля пикселей «того же оттенка», но любой яркости.

        Хвост слайдера часто темнее головы: он полупрозрачный или лежит в тени.
        Точный RGB тогда не совпадает, а оттенок сохраняется — затемнение
        умножает все каналы на одно число, и их соотношение не меняется.
        Слишком тёмные пиксели (фон) отсекаются порогом яркости, иначе тёмная
        дорожка того же цвета держала бы клавишу вечно.
        """
        if rgb is None or rgb.ndim != 3 or self._chroma is None:
            return 0.0
        px = rgb[..., :3].astype(np.float32)
        bright = px.max(axis=2)
        total = px.sum(axis=2) + 1e-6
        norm = px / total[..., None]
        dist = np.sqrt(np.sum((norm - self._chroma) ** 2, axis=2)) * 255.0
        floor_bright = max(16.0, self._brightness * 0.35)
        hit = int(np.count_nonzero((dist <= 22.0) & (bright >= floor_bright)))
        size = int(bright.size)
        if size <= 0:
            return 0.0
        return hit * 100.0 / float(size)

    def matches(self, rgb: np.ndarray) -> bool:
        return self.score(rgb) >= float(self.arrow.area_threshold)
