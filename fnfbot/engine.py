"""Движок бота: быстрый цикл «захват → сравнение с эталоном → нажатие»."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from typing import Dict, List, Optional, Tuple

import numpy as np

from .capture import RegionGrabber
from .config import DIRECTIONS, DIR_LABELS, BotConfig
from .detector import ArrowDetector, ColorDetector
from .holds import HoldController
from .keys import KeySender, resolve_key


class Engine(threading.Thread):
    def __init__(
        self,
        config: BotConfig,
        send_keys: bool = True,
        countdown: bool = True,
        verbose: bool = True,
    ):
        super().__init__(daemon=True, name="fnfbot-engine")
        self.bot_config = config
        self.send_keys = send_keys
        self.countdown = countdown
        self.verbose = verbose

        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._logs: deque = deque(maxlen=400)
        self._log_times: deque = deque(maxlen=40)
        self._miss_times: deque = deque(maxlen=40)

        self._states = {
            d: {"score": 0.0, "peak": 0.0, "hits": 0, "missed": 0, "near": 0}
            for d in DIRECTIONS
        }
        self.status = "остановлен"
        self.error: Optional[str] = None
        self.fps = 0.0

        self._sender: Optional[KeySender] = None
        self._pending: List[Tuple[float, str]] = []
        self._next_ok = {d: 0.0 for d in DIRECTIONS}
        self._latched = {d: False for d in DIRECTIONS}
        self._held_key = {d: False for d in DIRECTIONS}
        self._above = {d: False for d in DIRECTIONS}
        self._near_active = {d: False for d in DIRECTIONS}
        self._near_peak = {d: 0.0 for d in DIRECTIONS}
        self._active_dirs: List[str] = []

    # ---------- внешнее API ----------
    def stop(self) -> None:
        self._stop_event.set()

    def reset_peaks(self) -> None:
        with self._state_lock:
            for st in self._states.values():
                st["peak"] = 0.0
                st["hits"] = 0
                st["missed"] = 0
                st["near"] = 0

    def snapshot(self):
        with self._state_lock:
            states = {d: dict(v) for d, v in self._states.items()}
        return states, self.status, self.fps, self.error

    def drain_log(self) -> List[str]:
        with self._log_lock:
            items = list(self._logs)
            self._logs.clear()
        return items

    def log(self, text: str) -> None:
        with self._log_lock:
            self._logs.append(text)

    # ---------- поток ----------
    def run(self) -> None:
        try:
            self._loop()
        except Exception as exc:  # не роняем приложение из-за потока
            self.error = f"{type(exc).__name__}: {exc}"
            self.log(f"Ошибка: {self.error}")
        finally:
            try:
                if self._sender is not None:
                    self._sender.release_all()
            except Exception:
                pass
            self._pending.clear()
            self.status = "остановлен"

    def _loop(self) -> None:
        cfg = self.bot_config
        dirs = [
            d
            for d in DIRECTIONS
            if cfg.arrows[d].enabled and cfg.arrows[d].has_region()
        ]
        if not dirs:
            self.error = "Нет ни одной размеченной ноты"
            self.log("Сначала укажите области нот на скриншоте или на экране")
            return

        self._active_dirs = dirs
        self._sender = KeySender() if self.send_keys else None

        holds: Dict[str, HoldController] = {}
        regions: Dict[str, Tuple[int, int, int, int]] = {}
        slide_lanes: List[str] = []
        for d in dirs:
            arrow = cfg.arrows[d]
            regions[d] = arrow.rect()
            holds[d] = HoldController(
                enabled=arrow.slide,
                tap_ms=arrow.hold_ms,
                grace_ms=arrow.hold_grace_ms,
                max_ms=arrow.hold_max_ms,
            )
            if arrow.slide:
                slide_lanes.append(d)

        grabber = RegionGrabber(regions, color=cfg.detect_mode == "color")
        self.log(f"Захват экрана: {grabber.describe()}")
        if slide_lanes:
            self.log(
                "Слайды: держим клавишу, пока нота/хвост виден в приёмнике"
            )
        if cfg.detect_mode == "color":
            self.log("Режим распознавания: по цвету (для переливающихся нот)")

        color_mode = cfg.detect_mode == "color"
        detectors: Dict[str, object] = {}
        for d in dirs:
            det = ColorDetector(cfg.arrows[d]) if color_mode else ArrowDetector(cfg.arrows[d])
            detectors[d] = det
            if not det.has_baseline:
                if color_mode:
                    self.log(
                        f"{DIR_LABELS[d]}: нет цветового эталона — нажмите «Калибровать» "
                        "на паузе или подождите: бот снимет его сам, когда приёмник пуст"
                    )
                else:
                    self.log(
                        f"{DIR_LABELS[d]}: нет эталона — нажмите «Калибровать» "
                        "или примените скриншот"
                    )
        bad_keys = [DIR_LABELS[d] for d in dirs if not cfg.arrows[d].key]
        if bad_keys:
            self.log("Не назначены клавиши: " + ", ".join(bad_keys))

        unknown_keys = [
            f"{DIR_LABELS[d]} ({cfg.arrows[d].key})"
            for d in dirs
            if cfg.arrows[d].key and resolve_key(cfg.arrows[d].key) is None
        ]
        if unknown_keys:
            self.log("Не удалось распознать клавиши: " + ", ".join(unknown_keys))

        if self.countdown and cfg.countdown_sec > 0:
            total = int(math.ceil(cfg.countdown_sec))
            for i in range(total, 0, -1):
                self.status = f"старт через {i}…"
                if self._stop_event.wait(1.0):
                    return

        self.status = "мониторинг" if not self.send_keys else "работает"
        if self.send_keys:
            self.log("Бот запущен. F9 / кнопка «Стоп» — выключить")

        last_canvas_shape: Dict[str, Tuple[int, int]] = {}
        prev_frames: Dict[str, np.ndarray] = {}
        quiet_frames: Dict[str, int] = {}
        try:
            while not self._stop_event.is_set():
                frame_start = time.perf_counter()
                frames = grabber.grab()
                now = time.perf_counter()

                self._flush_releases(now)

                # Нажатия собираем за кадр и отправляем пачкой: двойные ноты
                # должны попасть в игру одновременно, без зазора между клавишами.
                frame_press: List[Tuple[str, str, float, bool]] = []

                for d in dirs:
                    frame = frames.get(d)
                    arrow = cfg.arrows[d]
                    det = detectors[d]
                    hold = holds[d]
                    state = self._states[d]
                    if frame is None or frame.size == 0:
                        state["score"] = 0.0
                        continue
                    shape = (int(frame.shape[0]), int(frame.shape[1]))
                    if last_canvas_shape.get(d) != shape:
                        last_canvas_shape[d] = shape
                        if det.baseline_shape is not None and det.baseline_shape != shape:
                            self.log(
                                f"{DIR_LABELS[d]}: размер области изменился — "
                                "эталон подстроен автоматически"
                            )

                    # Цветовой режим без эталона: снимаем сами, как только
                    # картинка в приёмнике перестала меняться (нот нет).
                    if color_mode and not det.has_baseline:
                        prev = prev_frames.get(d)
                        if prev is not None and prev.shape == frame.shape:
                            moving = np.abs(
                                frame.astype(np.int16) - prev.astype(np.int16)
                            ).max(axis=2)
                            quiet_now = int(np.count_nonzero(moving > 12)) * 100.0 / max(
                                1, moving.size
                            ) < 1.0
                        else:
                            quiet_now = False
                        prev_frames[d] = frame
                        quiet_frames[d] = quiet_frames.get(d, 0) + 1 if quiet_now else 0
                        if quiet_frames[d] >= 8:
                            arrow.set_baseline_rgb(frame, "screen")
                            det.reload_baseline()
                            quiet_frames[d] = 0
                            self.log(
                                f"{DIR_LABELS[d]}: цветовой эталон снят с экрана"
                            )

                    score = det.score(frame)
                    threshold = max(0.1, float(arrow.area_threshold))
                    state["score"] = score
                    if score > state["peak"]:
                        state["peak"] = score

                    above = score >= threshold
                    was_above = self._above[d]

                    # Удержание: сигнал берём из самого приёмника — пока там видна
                    # нота или хвост слайдера, клавиша нажата.
                    if hold.active and hold.update(now, above):
                        forced = hold.held_for(now) >= arrow.hold_max_ms / 1000.0 - 0.02
                        if self._sender is not None and arrow.key:
                            self._sender.key_up(arrow.key)
                        self._held_key[d] = False
                        if forced:
                            self.log(
                                f"{DIR_LABELS[d]}: слайд держался слишком долго — "
                                "клавиша отпущена принудительно"
                            )
                        hold.reset()

                    # Диагностика «почти сработало»: помогает понять, что порог завышен
                    # или область стоит мимо ноты.
                    if above:
                        self._near_active[d] = False
                    else:
                        half = threshold * 0.5
                        if not self._near_active[d] and score >= half:
                            self._near_active[d] = True
                            self._near_peak[d] = score
                        elif self._near_active[d]:
                            if score > self._near_peak[d]:
                                self._near_peak[d] = score
                            if score < threshold * 0.35:
                                if self._near_peak[d] >= half:
                                    state["near"] += 1
                                self._near_active[d] = False

                    ready = now >= self._next_ok[d]
                    if cfg.trigger_mode == "edge":
                        ready = ready and not self._latched[d]

                    if above and ready:
                        self._latched[d] = True
                        state["hits"] += 1
                        # Кулдаун отсчитываем всегда, даже если клавиша не назначена.
                        self._next_ok[d] = now + arrow.cooldown_ms / 1000.0
                        if self._sender is not None and arrow.key:
                            frame_press.append((d, arrow.key, score, hold.enabled))
                    elif above and not ready and not was_above:
                        # Новая нота пришла, пока бот «остывал» после прошлой.
                        state["missed"] += 1
                        self._log_miss(d, score)

                    # Перевзвод. Раньше ждали падения ниже threshold*release_ratio,
                    # и если шум в области был выше этой границы, бот залипал
                    # и пропускал все следующие ноты. Теперь достаточно любого
                    # кадра ниже порога после кулдауна.
                    if not above and now >= self._next_ok[d]:
                        self._latched[d] = False
                    self._above[d] = above

                if frame_press:
                    self._fire(frame_press, now, holds, cfg)

                elapsed = time.perf_counter() - frame_start
                inst_fps = 1.0 / elapsed if elapsed > 0 else 0.0
                self.fps = inst_fps if self.fps <= 0 else self.fps * 0.9 + inst_fps * 0.1

                delay = cfg.loop_delay_ms / 1000.0
                if elapsed < delay:
                    time.sleep(delay - elapsed)
        finally:
            grabber.close()
            if self._sender is not None:
                self._sender.release_all()

    # ---------- клавиши ----------
    def _fire(self, presses, now: float, holds, cfg) -> None:
        """Отправляет нажатия кадра одной пачкой (аккорды — без зазора)."""
        sender = self._sender
        if sender is None:
            return

        keys = []
        for d, key, _score, slide in presses:
            # Клавиша могла остаться зажатой от прошлой ноты: игра игнорирует
            # key_down по уже нажатой клавише, поэтому сначала отпускаем.
            if slide and self._held_key.get(d):
                sender.key_up(key)
                self._held_key[d] = False
            keys.append(key)

        sender.key_down_many(keys)

        for d, key, score, slide in presses:
            if slide:
                holds[d].on_press(now, True)
                self._held_key[d] = True
            else:
                self._pending.append(
                    (now + max(1, int(cfg.arrows[d].hold_ms)) / 1000.0, key)
                )
            self._log_press(d, key, score)

        if len(presses) > 1:
            names = " + ".join(DIR_LABELS[d] for d, _k, _s, _sl in presses)
            self.log(f"Двойное нажатие: {names}")

    def _press(self, key: str, hold_ms: int) -> None:
        if self._sender is None:
            return
        if self._sender.key_down(key):
            self._pending.append(
                (time.perf_counter() + max(1, int(hold_ms)) / 1000.0, key)
            )

    def _flush_releases(self, now: float) -> None:
        if not self._pending or self._sender is None:
            return
        keep: List[Tuple[float, str]] = []
        for when, key in self._pending:
            if when <= now:
                self._sender.key_up(key)
            else:
                keep.append((when, key))
        self._pending = keep

    def _log_press(self, direction: str, key: str, score: float) -> None:
        if not self.verbose:
            return
        now = time.perf_counter()
        while self._log_times and now - self._log_times[0] > 1.0:
            self._log_times.popleft()
        if len(self._log_times) >= 10:
            return
        self._log_times.append(now)
        self.log(f"{DIR_LABELS[direction]} → {key.upper()}  ({score:.0f}%)")

    def _log_miss(self, direction: str, score: float) -> None:
        if not self.verbose:
            return
        now = time.perf_counter()
        while self._miss_times and now - self._miss_times[0] > 1.0:
            self._miss_times.popleft()
        if len(self._miss_times) >= 5:
            return
        self._miss_times.append(now)
        self.log(
            f"Пропуск: {DIR_LABELS[direction]} {score:.0f}% — не успел после прошлого нажатия. "
            "Уменьшите кулдаун (40–60 мс)."
        )
