"""Самопроверка без игры: детектор, конфиг, клавиши, хоткеи, логика срабатываний.

Запуск:  python selftest.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

import numpy as np

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors="replace")
    except Exception:
        pass

import fnfbot.engine as engine_mod
from fnfbot.config import (
    DEFAULT_NOTE_COLORS,
    DIRECTIONS,
    ArrowConfig,
    BotConfig,
    normalize_color,
    parse_color,
)
from fnfbot.detector import ArrowDetector, ColorDetector
from fnfbot.holds import HoldController
from fnfbot.hotkeys import parse_hotkey
from fnfbot.keys import key_to_vk, resolve_key
from fnfbot.shot_editor import is_modifier, key_name_from_event

FAILED = []
PASSED = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  ok   {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL {name} {extra}")


def test_detector() -> None:
    print("[детектор]")
    arrow = ArrowConfig(pixel_threshold=30, area_threshold=3.0)
    base = np.full((40, 40), 60, dtype=np.uint8)
    arrow.set_baseline(base, "screen")
    det = ArrowDetector(arrow)

    check("эталон читается из конфига", det.has_baseline)
    check("пустой кадр даёт 0%", det.score(base) == 0.0, f"{det.score(base)}")

    frame = base.copy()
    frame[10:20, 10:20] = 255
    score = det.score(frame)
    check("нота 10×10 в области 40×40 ≈ 6.25%", abs(score - 6.25) < 0.2, f"{score}")

    arrow.area_threshold = 5.0
    check("срабатывание при 6.25% и пороге 5%", det.matches(frame))
    arrow.area_threshold = 10.0
    check("нет срабатывания при пороге 10%", not det.matches(frame))

    arrow.pixel_threshold = 250
    check("высокий порог пикселя игнорирует изменение", det.score(frame) == 0.0)

    small = np.full((20, 20), 60, dtype=np.uint8)
    arrow.pixel_threshold = 30
    check("эталон подстраивается под новый размер", det.score(small) == 0.0)


def test_config_roundtrip() -> None:
    print("[конфиг]")
    cfg = BotConfig()
    cfg.arrows["left"].set_rect(100, 200, 60, 60)
    cfg.arrows["left"].key = "left"
    cfg.arrows["left"].set_baseline(np.full((60, 60), 42, dtype=np.uint8), "shot")
    cfg.arrows["up"].area_threshold = 12.5
    cfg.trigger_mode = "cooldown"
    cfg.screenshot = "C:/shots/game.png"
    cfg.set_map_rect((10, 20, 800, 600))

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        cfg.save(path)
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        check("JSON валиден и содержит 4 ноты", len(raw["arrows"]) == 4)
        loaded = BotConfig.load(path)

    check("координаты области сохранились", loaded.arrows["left"].rect() == (100, 200, 60, 60))
    check("клавиша сохранилась", loaded.arrows["left"].key == "left")
    check("источник эталона сохранился", loaded.arrows["left"].baseline_source == "shot")
    check(
        "эталон восстановлен",
        loaded.arrows["left"].get_baseline() is not None
        and int(loaded.arrows["left"].get_baseline()[0, 0]) == 42,
    )
    check("порог площади сохранился", abs(loaded.arrows["up"].area_threshold - 12.5) < 1e-6)
    check("режим сохранился", loaded.trigger_mode == "cooldown")
    check("путь скриншота сохранился", loaded.screenshot == "C:/shots/game.png")
    check("привязка скриншота сохранилась", loaded.map_rect() == (10, 20, 800, 600))
    check("битый путь не ломает загрузку", BotConfig.load(os.path.join("нет", "такого.json")).arrows)

    # --- цвета нот ---
    check("цвет разбирается", parse_color("#12FA05") == (18, 250, 5))
    check("короткий цвет разбирается", parse_color("f0f") == (255, 0, 255))
    check("цвет с решёткой и пробелами", parse_color("  #00FFFF ") == (0, 255, 255))
    check("мусор вместо цвета", parse_color("нет") is None)
    check("цвет нормализуется", normalize_color("ABC") == "#aabbcc")
    check(
        "у каждой ноты свой стандартный цвет",
        len({DEFAULT_NOTE_COLORS[d] for d in DIRECTIONS}) == 4,
    )
    cfg.arrows["left"].note_color = "#123456"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        cfg.save(path)
        reloaded = BotConfig.load(path)
    check("цвет ноты сохранился", reloaded.arrows["left"].note_color == "#123456")

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "old.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"arrows": {"left": {"key": "a", "color_threshold": 40}}}, fh)
        old = BotConfig.load(path)
    check(
        "старый конфиг получает стандартный цвет",
        old.arrows["left"].note_color == DEFAULT_NOTE_COLORS["left"],
    )
    check("старый конфиг получает новый допуск", old.arrows["left"].color_threshold == 60)


def test_keys() -> None:
    print("[клавиши]")
    check("'a' -> scan code", resolve_key("a") is not None)
    check("'space' распознаётся", key_to_vk("space") == 0x20)
    check("'f8' распознаётся", key_to_vk("f8") == 0x77)
    left = resolve_key("left")
    check("стрелка помечена как extended", left is not None and left[1] is True, str(left))
    check("мусор не распознаётся", resolve_key("нет-такой-клавиши") is None)
    check("хоткей ctrl+shift+s", parse_hotkey("ctrl+shift+s") == (0x0002 | 0x0004, ord("S")))
    check("хоткей F8", parse_hotkey("F8") == (0, 0x77))
    check("кривой хоткей отклонён", parse_hotkey("ctrl+нет") is None)


class FakeEvent:
    def __init__(self, keycode: int, keysym: str):
        self.keycode = keycode
        self.keysym = keysym


def test_layout_independent_keys() -> None:
    print("[независимость от раскладки]")
    check(
        "русская раскладка: физическая A -> a",
        key_name_from_event(FakeEvent(65, "Cyrillic_ef")) == "a",
    )
    check(
        "русская раскладка: физическая D -> d",
        key_name_from_event(FakeEvent(68, "Cyrillic_ve")) == "d",
    )
    check("F8 по физическому коду", key_name_from_event(FakeEvent(119, "F8")) == "f8")
    check("стрелка по физическому коду", key_name_from_event(FakeEvent(37, "Left")) == "left")
    check("цифра по физическому коду", key_name_from_event(FakeEvent(53, "5")) == "5")
    check("Shift — модификатор", is_modifier(FakeEvent(16, "Shift_L")))
    check("Ctrl — модификатор", is_modifier(FakeEvent(17, "Control_L")))
    check("A — не модификатор", not is_modifier(FakeEvent(65, "a")))


class FakeGrabber:
    """Отдаёт заранее заданную последовательность кадров вместо экрана.

    Кадр — строка ("idle"/"note"/"weak") для всех областей сразу или словарь
    {имя области: вид}, чтобы зона приёмника и полоса удержания жили отдельно.
    """

    script = []
    index = 0

    def __init__(self, regions, color: bool = False):
        self.regions = regions
        self.color = bool(color)
        self.idle = np.full((30, 30), 60, dtype=np.uint8)
        self.idle_rgb = np.dstack([np.full((30, 30), 60, dtype=np.uint8)] * 3)
        FakeGrabber.index = 0

    def describe(self) -> str:
        return "fake"

    def _image(self, kind: str):
        if self.color:
            image = self.idle_rgb.copy()
            # (0, 102, 0) по яркости почти равно серому 60 — пиксельный режим
            # такую ноту не заметит, а цветной заметит по каналам R/B.
            if kind in ("note", "rainbow"):
                image[5:15, 5:15] = (0, 102, 0)
            elif kind == "tail":
                image[2:28, 8:22] = (0, 102, 0)
            elif kind == "thintail":
                image[12:17, 12:17] = (0, 102, 0)
            elif kind == "darktail":
                # полупрозрачный хвост: тот же оттенок, но темнее
                image[2:28, 10:20] = (0, 46, 0)
            elif kind == "weak":
                image[5:11, 5:11] = (0, 102, 0)
            return image
        if kind == "note":
            image = self.idle.copy()
            image[5:15, 5:15] = 250
            return image
        if kind == "tail":
            image = self.idle.copy()
            image[2:28, 8:22] = 250
            return image
        if kind == "thintail":
            image = self.idle.copy()
            image[12:17, 12:17] = 250
            return image
        if kind == "weak":
            image = self.idle.copy()
            image[5:11, 5:11] = 250
            return image
        if kind == "rainbow":
            image = self.idle.copy()
            image[5:15, 5:15] = 59
            return image
        return self.idle

    def grab(self):
        i = FakeGrabber.index
        FakeGrabber.index += 1
        pattern = FakeGrabber.script
        frame = pattern[min(i, len(pattern) - 1)] if pattern else "idle"
        time.sleep(0.003)
        if isinstance(frame, dict):
            return {
                name: self._image(frame.get(name, "idle"))
                for name in self.regions
            }
        image = self._image(frame)
        return {d: image for d in self.regions}

    def close(self) -> None:
        pass


class FakeSender:
    presses = []
    events = []

    def __init__(self):
        FakeSender.presses = []
        FakeSender.events = []

    def key_down(self, key):
        FakeSender.presses.append(key)
        FakeSender.events.append(("down", key, time.perf_counter()))
        return True

    def key_down_many(self, keys):
        for key in list(keys):
            FakeSender.presses.append(key)
            FakeSender.events.append(("down", key, time.perf_counter()))
        return len(keys)

    def key_up(self, key):
        FakeSender.events.append(("up", key, time.perf_counter()))
        return True

    def release_all(self):
        pass


def test_engine_logic() -> None:
    print("[логика срабатываний]")
    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 0, 30, 30)
        cfg.arrows[d].enabled = d == "left"
        cfg.arrows[d].key = "a"
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].release_ratio = 0.6
        cfg.arrows[d].cooldown_ms = 0
        cfg.arrows[d].hold_ms = 5
        cfg.arrows[d].slide = False  # слайды проверяются отдельно
        cfg.arrows[d].set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    cfg.trigger_mode = "edge"
    cfg.countdown_sec = 0

    FakeGrabber.script = ["idle", "note", "note", "note", "idle", "idle", "note", "idle", "idle"]
    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng.start()
    time.sleep(0.35)
    eng.stop()
    eng.join(timeout=2)
    states, status, _fps, error = eng.snapshot()
    check("бот не упал", error is None, str(error))
    check("две ноты -> два нажатия (режим «по фронту»)", len(FakeSender.presses) == 2,
          f"{len(FakeSender.presses)}")
    check("клавиша правильная", all(k == "a" for k in FakeSender.presses))
    check("счётчик срабатываний", states["left"]["hits"] == 2, str(states["left"]))

    # режим «по кулдауну» при долго висящей ноте должен нажимать несколько раз
    FakeGrabber.script = ["idle"] + ["note"] * 60
    cfg.trigger_mode = "cooldown"
    cfg.arrows["left"].cooldown_ms = 40
    eng2 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng2.start()
    time.sleep(0.4)
    eng2.stop()
    eng2.join(timeout=2)
    check("режим «по кулдауну» жмёт повторно", len(FakeSender.presses) >= 3, f"{len(FakeSender.presses)}")

    # мониторинг не должен нажимать клавиши
    FakeSender.presses = []
    cfg.trigger_mode = "edge"
    eng3 = engine_mod.Engine(cfg, send_keys=False, countdown=False, verbose=False)
    eng3.start()
    time.sleep(0.25)
    eng3.stop()
    eng3.join(timeout=2)
    check("мониторинг не нажимает клавиши", len(FakeSender.presses) == 0)

    # Шум в области выше threshold*release_ratio, но ниже порога, не должен
    # «залипать»: иначе бот пропускает все следующие ноты.
    cfg.trigger_mode = "edge"
    cfg.arrows["left"].cooldown_ms = 0
    FakeGrabber.script = ["idle", "note", "weak", "note", "weak", "note", "idle"]
    eng4 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng4.start()
    time.sleep(0.35)
    eng4.stop()
    eng4.join(timeout=2)
    check(
        "шум выше release_ratio не блокирует следующие ноты",
        len(FakeSender.presses) == 3,
        f"{len(FakeSender.presses)}",
    )

    # Счётчик пропусков: нота пришла во время кулдауна.
    cfg.arrows["left"].cooldown_ms = 300
    FakeGrabber.script = ["idle", "note", "weak", "note", "idle"]
    eng5 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng5.start()
    time.sleep(0.3)
    eng5.stop()
    eng5.join(timeout=2)
    states5, _status, _fps, error5 = eng5.snapshot()
    check("пропуск из-за кулдауна посчитан", states5["left"]["missed"] >= 1, str(states5["left"]))
    check("после пропуска бот не упал", error5 is None, str(error5))

    # «Слабое» изменение (ниже порога, но выше половины) считается как near.
    cfg.arrows["left"].cooldown_ms = 0
    FakeGrabber.script = ["idle", "weak", "weak", "idle"]
    eng6 = engine_mod.Engine(cfg, send_keys=False, countdown=False, verbose=False)
    eng6.start()
    time.sleep(0.25)
    eng6.stop()
    eng6.join(timeout=2)
    states6, _status, _fps, _error = eng6.snapshot()
    check("слабое изменение посчитано", states6["left"]["near"] >= 1, str(states6["left"]))


def test_slides() -> None:
    print("[слайды]")
    # --- чистая логика удержания ---
    # Короткая нота: сигнал был, пропал — отпускаем, не дожидаясь grace.
    tap = HoldController(enabled=True, tap_ms=30, grace_ms=60, max_ms=500)
    tap.on_press(0.0, True)
    check("тап: пока нота видна — держим", not tap.update(0.010, True))
    check("тап: нота пропала — пауза", not tap.update(0.030, False))
    check("тап: отпускает по таймеру", tap.update(0.042, False))

    # Слайд: сигнал держится дольше tail_confirm — отпускаем только по тишине.
    hold = HoldController(enabled=True, tap_ms=30, grace_ms=60, max_ms=500)
    hold.on_press(0.0, True)
    check("слайд: сигнал держит клавишу", not hold.update(0.4, True))
    check("слайд: тишина короче grace не отпускает", not hold.update(0.45, False))
    check("слайд: тишина дольше grace отпускает", hold.update(0.52, False))

    # Мигание в первые кадры не должно превращать слайд в тап.
    flick = HoldController(enabled=True, tap_ms=30, grace_ms=60, max_ms=500)
    flick.on_press(0.0, True)
    check("слайд: одиночный сбой кадра не отпускает", not flick.update(0.02, False))
    check("слайд: сигнал вернулся — держим", not flick.update(0.03, True))
    check("слайд: хвост идёт — держим", not flick.update(0.30, True))

    cap = HoldController(enabled=True, tap_ms=30, grace_ms=60, max_ms=200)
    cap.on_press(0.0, True)
    check(
        "слайд: страховка max_ms срабатывает",
        not cap.update(0.15, True) and cap.update(0.21, True),
    )

    off = HoldController(enabled=False, tap_ms=20, grace_ms=60, max_ms=500)
    off.on_press(0.0, True)
    check(
        "слайды выключены — обычный тап",
        not off.update(0.010, True) and off.update(0.021, True),
    )

    # --- движок: слайд держится, пока нота в приёмнике ---
    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 40, 30, 30)
        cfg.arrows[d].enabled = d == "left"
        cfg.arrows[d].key = "a"
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].cooldown_ms = 0
        cfg.arrows[d].hold_ms = 25
        cfg.arrows[d].hold_grace_ms = 60
        cfg.arrows[d].hold_max_ms = 3000
        cfg.arrows[d].slide = True
        cfg.arrows[d].set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    cfg.countdown_sec = 0

    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    FakeGrabber.script = ["idle"] * 6 + ["note"] * 90 + ["idle"] * 40
    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng.start()
    time.sleep(0.65)
    eng.stop()
    eng.join(timeout=2)
    downs = [e for e in FakeSender.events if e[0] == "down"]
    ups = [e for e in FakeSender.events if e[0] == "up"]
    check("слайд: одно нажатие", len(downs) == 1, str(FakeSender.events))
    check("слайд: клавиша отпущена", len(ups) >= 1, str(FakeSender.events))
    held = (ups[0][2] - downs[0][2]) if downs and ups else 0.0
    check("слайд: клавиша удерживалась долго", held > 0.15, f"{held*1000:.0f} мс")

    # --- движок: короткая нота при включённых слайдах отпускается быстро ---
    FakeSender.events = []
    FakeGrabber.script = ["idle"] * 6 + ["note"] * 2 + ["idle"] * 30
    eng2 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng2.start()
    time.sleep(0.3)
    eng2.stop()
    eng2.join(timeout=2)
    downs = [e for e in FakeSender.events if e[0] == "down"]
    ups = [e for e in FakeSender.events if e[0] == "up"]
    check("короткая нота: одно нажатие", len(downs) == 1, str(FakeSender.events))
    held = (ups[0][2] - downs[0][2]) if downs and ups else 0.0
    check("короткая нота: отпущена быстро", 0 < held < 0.2, f"{held*1000:.0f} мс")

    # --- главное: непрерывные ноты не зажимают клавишу навсегда ---
    cfg.arrows["left"].hold_max_ms = 300
    FakeSender.events = []
    FakeGrabber.script = ["idle"] * 6 + ["note"] * 400
    eng3 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng3.start()
    time.sleep(0.9)
    eng3.stop()
    eng3.join(timeout=2)
    downs = [e for e in FakeSender.events if e[0] == "down"]
    ups = [e for e in FakeSender.events if e[0] == "up"]
    check("не залипает: клавиша отпущена", len(ups) >= 1, str(FakeSender.events))
    down_time = sum(
        (ups[i][2] - downs[i][2]) for i in range(min(len(downs), len(ups)))
    )
    check(
        "не залипает: не держим дольше max",
        down_time < 1.2,
        f"{down_time*1000:.0f} мс нажатий за 0.9 с",
    )
    check(
        "слайды: движок не упал",
        eng.error is None and eng2.error is None and eng3.error is None,
        str(eng.error or eng2.error or eng3.error),
    )


def test_chords() -> None:
    print("[двойные ноты]")
    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 40, 30, 30)
        cfg.arrows[d].enabled = d in ("left", "right")
        cfg.arrows[d].key = {"left": "a", "right": "d"}.get(d, "")
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].cooldown_ms = 60
        cfg.arrows[d].hold_ms = 25
        cfg.arrows[d].slide = True
        cfg.arrows[d].set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    cfg.countdown_sec = 0

    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    FakeGrabber.script = ["idle"] * 6 + ["note"] * 4 + ["idle"] * 20
    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=True)
    eng.start()
    time.sleep(0.35)
    eng.stop()
    eng.join(timeout=2)

    downs = [e for e in FakeSender.events if e[0] == "down"]
    check("двойная нота: нажаты обе клавиши", len(downs) >= 2, str(FakeSender.events))
    for key in ("a", "d"):
        hits = [e for e in downs if e[1] == key]
        check(f"двойная нота: клавиша {key} нажата", len(hits) >= 1, str(FakeSender.events))
    if len(downs) >= 2:
        gap = abs(downs[0][2] - downs[1][2])
        check(
            "двойная нота: клавиши в одном кадре",
            gap < 0.01,
            f"зазор {gap*1000:.1f} мс",
        )
    ups = [e for e in FakeSender.events if e[0] == "up"]
    check("двойная нота: обе клавиши отпущены", len(ups) >= 2, str(FakeSender.events))
    check("двойная нота: движок не упал", eng.error is None, str(eng.error))


def test_slide_hold() -> None:
    """Слайд держится, даже если хвост тоньше головы и не добирает мин. площадь."""
    print("[слайды]")

    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 0, 30, 30)
        cfg.arrows[d].enabled = d == "left"
        cfg.arrows[d].key = "a"
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].cooldown_ms = 0
        cfg.arrows[d].hold_ms = 20
        cfg.arrows[d].hold_grace_ms = 60
        cfg.arrows[d].hold_max_ms = 3000
        cfg.arrows[d].slide = True
        cfg.arrows[d].set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    cfg.trigger_mode = "edge"
    cfg.countdown_sec = 0

    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    FakeGrabber.script = ["idle", "note"] + ["thintail"] * 40 + ["idle"] * 40
    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng.start()
    time.sleep(0.45)
    eng.stop()
    eng.join(timeout=2)

    downs = [t for kind, _k, t in FakeSender.events if kind == "down"]
    ups = [t for kind, _k, t in FakeSender.events if kind == "up"]
    check("слайд: нажатие одно", len(downs) == 1, str(FakeSender.events))
    check("слайд: клавиша отпущена", len(ups) >= 1, str(FakeSender.events))
    held = (ups[0] - downs[0]) if downs and ups else 0.0
    check("слайд держится, а не тапается", held >= 0.12, f"{held * 1000:.0f} мс")


def test_color_slide_hold() -> None:
    """Цветной режим: слайд держится, даже если хвост темнее головы ноты."""
    print("[слайды в режиме «цвет нот»]")

    idle = np.dstack([np.full((30, 30), 60, dtype=np.uint8)] * 3)
    note = idle.copy()
    note[5:15, 5:15] = (0, 102, 0)
    dark_tail = idle.copy()
    dark_tail[2:28, 10:20] = (0, 46, 0)

    arrow = ArrowConfig(note_color="#006600", color_threshold=40, area_threshold=5.0)
    det = ColorDetector(arrow)
    check(
        "тёмный хвост: точный цвет не совпадает",
        det.score(dark_tail) < 1.0,
        f"{det.score(dark_tail):.1f}%",
    )
    check(
        "тёмный хвост виден по оттенку",
        det.shade_score(dark_tail) > 5.0,
        f"{det.shade_score(dark_tail):.1f}%",
    )
    check("пустой приёмник: оттенка нет", det.shade_score(idle) == 0.0)
    grey = idle.copy()
    grey[5:15, 5:15] = (60, 60, 60)
    check("серый фон не считается оттенком ноты", det.shade_score(grey) == 0.0)

    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 0, 30, 30)
        cfg.arrows[d].enabled = d == "left"
        cfg.arrows[d].key = "a"
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].color_threshold = 40
        cfg.arrows[d].note_color = "#006600"
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].cooldown_ms = 0
        cfg.arrows[d].hold_ms = 20
        cfg.arrows[d].hold_grace_ms = 60
        cfg.arrows[d].hold_max_ms = 3000
        cfg.arrows[d].slide = True
    cfg.trigger_mode = "edge"
    cfg.detect_mode = "color"
    cfg.countdown_sec = 0

    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    FakeGrabber.script = ["idle", "note"] + ["darktail"] * 40 + ["idle"] * 40
    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng.start()
    time.sleep(0.45)
    eng.stop()
    eng.join(timeout=2)

    downs = [t for kind, _k, t in FakeSender.events if kind == "down"]
    ups = [t for kind, _k, t in FakeSender.events if kind == "up"]
    check("цветной слайд: нажатие одно", len(downs) == 1, str(FakeSender.events))
    check("цветной слайд: клавиша отпущена", len(ups) >= 1, str(FakeSender.events))
    held = (ups[0] - downs[0]) if downs and ups else 0.0
    check(
        "цветной слайд держится, а не тапается",
        held >= 0.12,
        f"{held * 1000:.0f} мс",
    )


def test_color_mode() -> None:
    """Цветной режим: у каждой ноты свой точный цвет, эталон не нужен."""
    print("[распознавание по цвету ноты]")

    idle = np.dstack([np.full((30, 30), 60, dtype=np.uint8)] * 3)

    def frame_with(color, box=(5, 15, 5, 15)):
        image = idle.copy()
        y0, y1, x0, x1 = box
        image[y0:y1, x0:x1] = color
        return image

    frame_rgb = frame_with((0, 102, 0))

    # та же нота в оттенках серого — как её увидит пиксельный режим
    gray = (
        frame_rgb[..., 0].astype(np.uint16) * 77
        + frame_rgb[..., 1].astype(np.uint16) * 150
        + frame_rgb[..., 2].astype(np.uint16) * 29
    ) >> 8
    gray = gray.astype(np.uint8)
    gray_arrow = ArrowConfig(pixel_threshold=25, area_threshold=5.0)
    gray_arrow.set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    pixel = ArrowDetector(gray_arrow)

    arrow = ArrowConfig(note_color="#006600", color_threshold=40, area_threshold=5.0)
    color = ColorDetector(arrow)
    strict = ColorDetector(
        ArrowConfig(note_color="#006600", color_threshold=10, area_threshold=5.0)
    )
    wrong = ColorDetector(
        ArrowConfig(note_color="#c24b99", color_threshold=40, area_threshold=5.0)
    )

    check("цвет: детектор готов без эталона", color.has_baseline)
    check("цвет: пустой приёмник 0%", color.score(idle) == 0.0, f"{color.score(idle)}")
    check(
        "пиксельный режим не видит ноту той же яркости",
        pixel.score(gray) < 1.0,
        f"{pixel.score(gray)}",
    )
    check(
        "цветной режим видит ноту нужного цвета",
        color.score(frame_rgb) > 5.0,
        f"{color.score(frame_rgb)}",
    )
    check("цвет: срабатывание по площади", color.matches(frame_rgb))
    check(
        "цвет: тень ноты попадает в допуск",
        color.score(frame_with((0, 88, 0))) > 5.0,
        f"{color.score(frame_with((0, 88, 0)))}",
    )
    check(
        "цвет: строгий допуск отсекает тень",
        strict.score(frame_with((0, 88, 0))) == 0.0,
    )
    check("цвет: чужой цвет не ловится", wrong.score(frame_rgb) == 0.0)
    check("цвет: без цвета ноты 0%", ColorDetector(ArrowConfig()).score(frame_rgb) == 0.0)

    # --- двигатель целиком ---
    cfg = BotConfig()
    for d in DIRECTIONS:
        cfg.arrows[d].set_rect(0, 0, 30, 30)
        cfg.arrows[d].enabled = d == "left"
        cfg.arrows[d].key = "a"
        cfg.arrows[d].pixel_threshold = 25
        cfg.arrows[d].color_threshold = 40
        cfg.arrows[d].note_color = "#006600"
        cfg.arrows[d].area_threshold = 5.0
        cfg.arrows[d].cooldown_ms = 0
        cfg.arrows[d].hold_ms = 5
        cfg.arrows[d].slide = False
        cfg.arrows[d].set_baseline(np.full((30, 30), 60, dtype=np.uint8), "screen")
    cfg.trigger_mode = "edge"
    cfg.countdown_sec = 0

    engine_mod.RegionGrabber = FakeGrabber
    sender = FakeSender()
    engine_mod.KeySender = lambda: sender

    FakeGrabber.script = ["idle", "rainbow", "idle", "rainbow", "idle"]
    cfg.detect_mode = "pixel"
    eng = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng.start()
    time.sleep(0.3)
    eng.stop()
    eng.join(timeout=2)
    check(
        "режим «пиксели» пропускает ноту той же яркости",
        len(FakeSender.presses) == 0,
        str(FakeSender.presses),
    )
    check("режим «пиксели» не падает", eng.error is None, str(eng.error))

    FakeGrabber.script = ["idle", "rainbow", "idle", "rainbow", "idle"]
    cfg.detect_mode = "color"
    eng2 = engine_mod.Engine(cfg, send_keys=True, countdown=False, verbose=False)
    eng2.start()
    time.sleep(0.3)
    eng2.stop()
    eng2.join(timeout=2)
    states, _status, _fps, error = eng2.snapshot()
    check(
        "режим «цвет нот» ловит ноту по цвету",
        len(FakeSender.presses) == 2,
        str(FakeSender.presses),
    )
    check(
        "режим «цвет нот»: счётчик срабатываний",
        states["left"]["hits"] == 2,
        str(states["left"]),
    )
    check("режим «цвет нот» не падает", error is None, str(error))


def main() -> int:
    print("Fnf-bot — самопроверка\n")
    test_detector()
    test_config_roundtrip()
    test_keys()
    test_layout_independent_keys()
    test_engine_logic()
    test_slides()
    test_slide_hold()
    test_color_slide_hold()
    test_chords()
    test_color_mode()
    print()
    if FAILED:
        print(f"Провалено: {len(FAILED)} из {PASSED + len(FAILED)}")
        for name in FAILED:
            print("  -", name)
        return 1
    print(f"Всё хорошо: {PASSED} проверок пройдено")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
