"""Настройки бота: области нот, клавиши, пороги чувствительности.

Всё хранится в config.json рядом с main.py, эталонный кадр каждой ноты
(«базовая картинка») сохраняется в base64, чтобы не перекалибровывать каждый запуск.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from . import APP_DIR

DIRECTIONS: Tuple[str, ...] = ("left", "down", "up", "right")
DIR_LABELS = {"left": "Лево", "down": "Вниз", "up": "Вверх", "right": "Право"}
DEFAULT_KEYS = {"left": "a", "down": "s", "up": "w", "right": "d"}

# Стандартные цвета нот FNF: их можно поменять под свою игру.
DEFAULT_NOTE_COLORS = {
    "left": "#c24b99",   # фиолетовая
    "down": "#00ffff",   # голубая
    "up": "#12fa05",     # зелёная
    "right": "#f9393f",  # красная
}

CONFIG_PATH = os.path.join(APP_DIR, "config.json")


def parse_color(text) -> Optional[Tuple[int, int, int]]:
    """'#rrggbb' / 'rrggbb' / '#rgb' -> (r, g, b). None, если это не цвет."""
    if not isinstance(text, str):
        return None
    value = text.strip().lstrip("#").strip()
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    if len(value) != 6:
        return None
    try:
        return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return None


def normalize_color(text, fallback: str = "#ffffff") -> str:
    """Приводит цвет к виду '#rrggbb' или возвращает fallback."""
    rgb = parse_color(text)
    if rgb is None:
        rgb = parse_color(fallback) or (255, 255, 255)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _as_int(value, default: int, low: int, high: int) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


def _as_float(value, default: float, low: float, high: float) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, value))


@dataclass
class ArrowConfig:
    """Одна стрелка (нота): где искать, чем нажимать, насколько чувствительно."""

    enabled: bool = True
    region: list = field(default_factory=lambda: [0, 0, 0, 0])  # x, y, w, h (экранные пиксели)
    key: str = ""
    hold_ms: int = 30           # сколько держать клавишу (1 мс игра часто не успевает увидеть)
    cooldown_ms: int = 60       # минимальный интервал между нажатиями
    pixel_threshold: int = 28   # насколько пиксель должен измениться (0..255)
    color_threshold: int = 60   # цвет: насколько пиксель может отличаться от цвета ноты
    area_threshold: float = 6.0  # какой % пикселей области должен «попасть в цвет»
    release_ratio: float = 0.5  # во сколько раз должно упасть изменение для перевзвода
    slide: bool = True          # держать клавишу, пока через приёмник идёт слайдер
    hold_grace_ms: int = 120    # сколько полоса над приёмником должна молчать, чтобы отпустить
    hold_max_ms: int = 8000     # страховка от залипания клавиши
    note_color: str = ""        # точный цвет ноты («#rrggbb»), нужен режиму «цвет»
    baseline: str = ""          # base64 от grayscale-эталона
    baseline_size: list = field(default_factory=lambda: [0, 0])  # [высота, ширина]
    baseline_rgb: str = ""      # base64 от цветного эталона (RGB)
    baseline_source: str = ""   # "shot" — со скриншота, "screen" — с экрана

    # --- область ---
    def rect(self) -> Tuple[int, int, int, int]:
        r = list(self.region) + [0, 0, 0, 0]
        return int(r[0]), int(r[1]), int(r[2]), int(r[3])

    def set_rect(self, x: int, y: int, w: int, h: int) -> None:
        self.region = [int(x), int(y), int(w), int(h)]

    def has_region(self) -> bool:
        _, _, w, h = self.rect()
        return w >= 3 and h >= 3

    # --- эталонный кадр ---
    def set_baseline(self, gray, source: str = "") -> None:
        import numpy as np

        arr = np.asarray(gray, dtype=np.uint8)
        self.baseline = base64.b64encode(arr.tobytes()).decode("ascii")
        self.baseline_size = [int(arr.shape[0]), int(arr.shape[1])]
        self.baseline_source = source

    def get_baseline(self):
        import numpy as np

        if not self.baseline:
            return None
        try:
            raw = base64.b64decode(self.baseline)
        except (ValueError, TypeError):
            return None
        h, w = int(self.baseline_size[0]), int(self.baseline_size[1])
        if h <= 0 or w <= 0 or len(raw) != h * w:
            return None
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w)

    def has_baseline(self) -> bool:
        return self.get_baseline() is not None

    # --- цветной эталон (для режима «цвет») ---
    def set_baseline_rgb(self, rgb, source: str = "") -> None:
        import numpy as np

        arr = np.asarray(rgb, dtype=np.uint8)
        if arr.ndim != 3 or arr.shape[2] < 3:
            return
        arr = np.ascontiguousarray(arr[..., :3])
        self.baseline_rgb = base64.b64encode(arr.tobytes()).decode("ascii")
        self.baseline_size = [int(arr.shape[0]), int(arr.shape[1])]
        self.baseline_source = source

    def get_baseline_rgb(self):
        import numpy as np

        if not self.baseline_rgb:
            return None
        try:
            raw = base64.b64decode(self.baseline_rgb)
        except (ValueError, TypeError):
            return None
        h, w = int(self.baseline_size[0]), int(self.baseline_size[1])
        if h <= 0 or w <= 0 or len(raw) != h * w * 3:
            return None
        return np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3)

    def has_baseline_rgb(self) -> bool:
        return self.get_baseline_rgb() is not None

    # --- цвет ноты (режим «цвет») ---
    def note_rgb(self) -> Optional[Tuple[int, int, int]]:
        return parse_color(self.note_color)

    def clear_baseline(self) -> None:
        self.baseline = ""
        self.baseline_rgb = ""
        self.baseline_size = [0, 0]
        self.baseline_source = ""

    # --- сериализация ---
    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "region": self.region,
            "key": self.key,
            "hold_ms": self.hold_ms,
            "cooldown_ms": self.cooldown_ms,
            "pixel_threshold": self.pixel_threshold,
            "color_threshold": self.color_threshold,
            "area_threshold": self.area_threshold,
            "release_ratio": self.release_ratio,
            "slide": self.slide,
            "hold_grace_ms": self.hold_grace_ms,
            "hold_max_ms": self.hold_max_ms,
            "note_color": self.note_color,
            "baseline": self.baseline,
            "baseline_rgb": self.baseline_rgb,
            "baseline_size": self.baseline_size,
            "baseline_source": self.baseline_source,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArrowConfig":
        data = data or {}
        cfg = cls()
        cfg.enabled = bool(data.get("enabled", True))
        region = list(data.get("region") or [0, 0, 0, 0])
        region = (region + [0, 0, 0, 0])[:4]
        cfg.region = [_as_int(v, 0, -100000, 100000) for v in region]
        cfg.key = str(data.get("key") or "")[:32]
        cfg.hold_ms = _as_int(data.get("hold_ms"), 30, 1, 500)
        cfg.cooldown_ms = _as_int(data.get("cooldown_ms"), 60, 0, 2000)
        cfg.pixel_threshold = _as_int(data.get("pixel_threshold"), 28, 1, 254)
        cfg.color_threshold = _as_int(data.get("color_threshold"), 60, 1, 255)
        cfg.area_threshold = _as_float(data.get("area_threshold"), 6.0, 0.1, 100.0)
        cfg.release_ratio = _as_float(data.get("release_ratio"), 0.5, 0.1, 0.95)
        cfg.slide = bool(data.get("slide", True))
        cfg.hold_grace_ms = _as_int(data.get("hold_grace_ms"), 120, 20, 600)
        cfg.hold_max_ms = _as_int(data.get("hold_max_ms"), 8000, 200, 30000)
        color = str(data.get("note_color") or "").strip()
        cfg.note_color = normalize_color(color) if parse_color(color) else ""
        cfg.baseline = str(data.get("baseline") or "")
        cfg.baseline_rgb = str(data.get("baseline_rgb") or "")
        size = list(data.get("baseline_size") or [0, 0])
        size = (size + [0, 0])[:2]
        cfg.baseline_size = [_as_int(v, 0, 0, 10000) for v in size]
        cfg.baseline_source = str(data.get("baseline_source") or "")[:16]
        return cfg


@dataclass
class BotConfig:
    arrows: Dict[str, ArrowConfig] = field(
        default_factory=lambda: {
            d: ArrowConfig(key=DEFAULT_KEYS[d], note_color=DEFAULT_NOTE_COLORS[d])
            for d in DIRECTIONS
        }
    )
    trigger_mode: str = "edge"   # "edge" — по фронту изменения, "cooldown" — по кулдауну
    detect_mode: str = "pixel"   # "pixel" — сравнение яркости, "color" — сравнение цвета
    countdown_sec: float = 2.0   # задержка перед стартом, чтобы успеть переключиться в игру
    loop_delay_ms: int = 0       # принудительная пауза между кадрами
    hotkey_start: str = "F8"
    hotkey_stop: str = "F9"
    hotkey_calibrate: str = "F7"
    screenshot: str = ""  # последний скриншот игры, с которого брали разметку
    screenshot_map: list = field(default_factory=lambda: [0, 0, 0, 0])  # куда скриншот лёг на экран

    def map_rect(self):
        """Привязка скриншота к экрану (x, y, w, h) или None."""
        r = list(self.screenshot_map) + [0, 0, 0, 0]
        x, y, w, h = (int(v) for v in r[:4])
        if w > 3 and h > 3:
            return x, y, w, h
        return None

    def set_map_rect(self, rect) -> None:
        if not rect:
            self.screenshot_map = [0, 0, 0, 0]
            return
        x, y, w, h = (int(v) for v in rect)
        self.screenshot_map = [x, y, w, h]

    def enabled_arrows(self):
        return [self.arrows[d] for d in DIRECTIONS if self.arrows[d].enabled]

    def to_dict(self) -> dict:
        return {
            "arrows": {d: self.arrows[d].to_dict() for d in DIRECTIONS},
            "trigger_mode": self.trigger_mode,
            "detect_mode": self.detect_mode,
            "countdown_sec": self.countdown_sec,
            "loop_delay_ms": self.loop_delay_ms,
            "hotkey_start": self.hotkey_start,
            "hotkey_stop": self.hotkey_stop,
            "hotkey_calibrate": self.hotkey_calibrate,
            "screenshot": self.screenshot,
            "screenshot_map": self.screenshot_map,
        }

    def save(self, path: str = CONFIG_PATH) -> None:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    @classmethod
    def load(cls, path: str = CONFIG_PATH) -> "BotConfig":
        cfg = cls()
        if not os.path.exists(path):
            return cfg
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return cfg
        if not isinstance(data, dict):
            return cfg

        arrows = data.get("arrows")
        if isinstance(arrows, dict):
            for d in DIRECTIONS:
                item = arrows.get(d)
                if isinstance(item, dict):
                    arrow = ArrowConfig.from_dict(item)
                    # Старые конфиги не знали о цветах нот: подставляем стандартный
                    # цвет и более мягкий допуск.
                    if not arrow.note_color:
                        arrow.note_color = DEFAULT_NOTE_COLORS[d]
                        if _as_int(item.get("color_threshold"), 40, 1, 255) == 40:
                            arrow.color_threshold = 60
                    cfg.arrows[d] = arrow
        mode = str(data.get("trigger_mode") or "edge")
        cfg.trigger_mode = mode if mode in ("edge", "cooldown") else "edge"
        detect = str(data.get("detect_mode") or "pixel")
        cfg.detect_mode = detect if detect in ("pixel", "color") else "pixel"
        cfg.countdown_sec = _as_float(data.get("countdown_sec"), 2.0, 0.0, 10.0)
        cfg.loop_delay_ms = _as_int(data.get("loop_delay_ms"), 0, 0, 200)
        for attr, default in (
            ("hotkey_start", "F8"),
            ("hotkey_stop", "F9"),
            ("hotkey_calibrate", "F7"),
        ):
            value = str(data.get(attr) or default)[:32]
            setattr(cfg, attr, value)
        cfg.screenshot = str(data.get("screenshot") or "")[:260]
        mapping = list(data.get("screenshot_map") or [0, 0, 0, 0])
        mapping = (mapping + [0, 0, 0, 0])[:4]
        cfg.screenshot_map = [_as_int(v, 0, -100000, 100000) for v in mapping]
        return cfg
