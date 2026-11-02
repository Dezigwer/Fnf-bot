"""Главное окно: компактная разметка нот, запуск бота и настройки."""

from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

from . import APP_DIR, RESOURCE_DIR, __version__, glass, theme
from .config import DIRECTIONS, DIR_LABELS, BotConfig
from .engine import Engine
from .hotkeys import HotkeyManager, parse_hotkey
from .overlay import pick_region, show_regions
from .screenshot import load_image, screen_size
from .shot_editor import ShotEditor, is_modifier, key_name_from_event


class MainApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title(f"FNF Pixel Player Bot {__version__}")
        root.geometry("1040x740")
        root.minsize(900, 640)

        self.cfg = BotConfig.load()
        self.engine: Optional[Engine] = None
        self.ui: Dict[str, dict] = {}
        self._bars: Dict[str, ttk.Progressbar] = {}
        self._base_labels: Dict[str, ttk.Label] = {}
        self._region_labels: Dict[str, ttk.Label] = {}
        self.editor: Optional[ShotEditor] = None
        self._loading = False
        self._save_job = None
        self._closing = False
        self._auto_running = False
        self._auto_result = None
        self._events: "queue.Queue[str]" = queue.Queue()

        self.status_var = tk.StringVar(value="Готов. Укажите ноты на скриншоте и нажмите «Старт».")
        self.mode_var = tk.StringVar(value="остановлен")

        self._style()
        self._build()
        self._glass = glass.enable(self.root)
        self._refresh_ui()
        self._start_hotkeys()
        self._tick()
        self._startup_checks()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------- оформление ----------
    def _style(self) -> None:
        theme.apply(self.root)
        ttk.Style(self.root).configure("Accent.TButton", font=("Segoe UI", 10, "bold"))

    # ---------- построение ----------
    def _build(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 10, 12, 4))
        header.pack(fill="x")

        self.btn_start = ttk.Button(
            header,
            text=f"Старт ({self.cfg.hotkey_start})",
            style="Accent.TButton",
            command=self.start,
        )
        self.btn_start.pack(side="left")
        self.btn_stop = ttk.Button(
            header, text=f"Стоп ({self.cfg.hotkey_stop})", command=self.stop, state="disabled"
        )
        self.btn_stop.pack(side="left", padx=(6, 0))
        self.btn_monitor = ttk.Button(header, text="Монитор", command=self.monitor)
        self.btn_monitor.pack(side="left", padx=(6, 0))

        ttk.Separator(header, orient="vertical").pack(side="left", fill="y", padx=10)

        ttk.Button(header, text="Скриншот игры…", command=self.open_shot_editor).pack(side="left")
        ttk.Button(header, text="Области", command=self.show_areas).pack(side="left", padx=(6, 0))
        ttk.Button(header, text="Сверить", command=self.verify_alignment).pack(
            side="left", padx=(6, 0)
        )

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=12)

        notes_tab = ttk.Frame(self.nb, padding=(12, 10))
        self.nb.add(notes_tab, text="Ноты")
        self._build_notes_tab(notes_tab)

        settings_tab = ttk.Frame(self.nb)
        self.nb.add(settings_tab, text="Настройки")
        self._build_settings_tab(settings_tab)

        log_frame = ttk.LabelFrame(self.root, text="Журнал", padding=6)
        log_frame.pack(fill="x", padx=12, pady=(8, 10))
        self.log_text = tk.Text(
            log_frame, height=4, wrap="none", state="disabled", font=("Consolas", 9)
        )
        theme.style_text(self.log_text)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        bar, self.status_label, self.mode_label = theme.build_status_bar(self.root)
        bar.pack(side="bottom", fill="x")
        self.status_label.configure(textvariable=self.status_var)
        self.mode_label.configure(textvariable=self.mode_var)

    # ---------- вкладка «Ноты» ----------
    def _build_notes_tab(self, tab: ttk.Frame) -> None:
        ttk.Label(
            tab,
            text=(
                "Обведите внутреннюю часть приёмника (не яркий контур). "
                "Высота области — 24–30 px: так быстрая нота не проскочит между кадрами."
            ),
            style="Dim.TLabel",
            wraplength=920,
            justify="left",
        ).pack(anchor="w", pady=(0, 4))

        for index, d in enumerate(DIRECTIONS):
            if index:
                ttk.Separator(tab).pack(fill="x", pady=2)
            self._build_note_row(tab, d)

        tip = ttk.Frame(tab)
        tip.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Separator(tip).pack(fill="x")
        head = ttk.Frame(tip)
        head.pack(fill="x", pady=(9, 0))
        ttk.Label(
            head, text="Если бот пропускает ноты", font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        ttk.Button(
            head, text="Рекомендуемые тайминги", command=self.apply_recommended
        ).pack(side="right")
        ttk.Label(
            tip,
            text=(
                "• Область — 24–30 px в высоту по линии нажатия. Если пропускает, "
                "расширяйте вниз: верхнюю границу не двигайте, она задаёт момент нажатия.\n"
                "• «Держать» 25–35 мс, кулдаун 40–80 мс. Проверка: «Монитор» → "
                "сыграйте фрагмент → смотрите «пропуск» и «слабо».\n"
                "• Слайды: галочка «слайды» держит клавишу, пока нота в приёмнике. "
                "Отпускает рано — увеличьте «Отпускать, тишина мс»."
            ),
            style="Dim.TLabel",
            justify="left",
            wraplength=940,
        ).pack(anchor="w", pady=(6, 0))

    def _build_note_row(self, parent: ttk.Frame, d: str) -> None:
        arrow = self.cfg.arrows[d]
        vars_ = {
            "enabled": tk.BooleanVar(value=arrow.enabled),
            "key": tk.StringVar(value=arrow.key),
            "hold": tk.IntVar(value=arrow.hold_ms),
            "cd": tk.IntVar(value=arrow.cooldown_ms),
            "pix": tk.IntVar(value=arrow.pixel_threshold),
            "color": tk.IntVar(value=arrow.color_threshold),
            "area": tk.DoubleVar(value=arrow.area_threshold),
            "release": tk.DoubleVar(value=arrow.release_ratio),
            "slide": tk.BooleanVar(value=arrow.slide),
            "grace": tk.IntVar(value=arrow.hold_grace_ms),
            "hmax": tk.IntVar(value=arrow.hold_max_ms),
            "region": tk.StringVar(),
            "base": tk.StringVar(),
            "score": tk.StringVar(value="0.0 %"),
            "peak": tk.StringVar(value="пик 0.0 %"),
            "stats": tk.StringVar(value="нажатий 0"),
        }
        self.ui[d] = vars_

        row = ttk.Frame(parent)
        row.pack(fill="x", pady=7)

        line1 = ttk.Frame(row)
        line1.pack(fill="x")
        theme.DarkCheck(
            line1,
            text=DIR_LABELS[d],
            variable=vars_["enabled"],
            command=lambda d=d: self._toggle_note(d),
        ).pack(side="left")
        ttk.Label(line1, text="клавиша", style="Dim.TLabel").pack(side="left", padx=(16, 4))
        entry = ttk.Entry(line1, textvariable=vars_["key"], width=8, justify="center")
        entry.pack(side="left")
        entry.bind("<KeyPress>", lambda e, d=d: self._on_key(e, d))
        entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, "end"))
        ttk.Button(line1, text="Область…", command=lambda d=d: self._pick_region(d)).pack(
            side="left", padx=(10, 0)
        )
        ttk.Button(line1, text="Калибровать", command=lambda d=d: self.calibrate([d])).pack(
            side="left", padx=(4, 0)
        )
        theme.DarkCheck(
            line1,
            text="слайды",
            variable=vars_["slide"],
            command=lambda d=d: self._toggle_note(d),
        ).pack(side="left", padx=(10, 0))

        base_label = ttk.Label(line1, textvariable=vars_["base"], style="Ok.TLabel")
        base_label.pack(side="right")
        self._base_labels[d] = base_label
        region_label = ttk.Label(line1, textvariable=vars_["region"], style="Dim.TLabel")
        region_label.pack(side="right", padx=(0, 12))
        self._region_labels[d] = region_label

        line2 = ttk.Frame(row)
        line2.pack(fill="x", pady=(5, 0))
        bar = ttk.Progressbar(line2, maximum=100.0, value=0.0)
        bar.pack(side="left", fill="x", expand=True)
        self._bars[d] = bar
        ttk.Label(line2, textvariable=vars_["stats"], style="Dim.TLabel").pack(side="right")
        ttk.Label(line2, textvariable=vars_["peak"], style="Dim.TLabel", width=12, anchor="e").pack(
            side="right", padx=(0, 8)
        )
        ttk.Label(
            line2, textvariable=vars_["score"], font=("Consolas", 10, "bold"), width=7, anchor="e"
        ).pack(side="right", padx=(10, 0))

    # ---------- вкладка «Настройки» ----------
    def _build_settings_tab(self, tab: ttk.Frame) -> None:
        canvas = tk.Canvas(tab, bg=theme.BG, highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        inner = ttk.Frame(canvas, padding=(12, 10))
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(window, width=e.width)
        )

        inner.columnconfigure(0, weight=1, uniform="settings")
        inner.columnconfigure(1, weight=1, uniform="settings")
        left = ttk.Frame(inner)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        right = ttk.Frame(inner)
        right.grid(row=0, column=1, sticky="nsew")

        # --- срабатывание ---
        mode = ttk.LabelFrame(left, text="Срабатывание", padding=10)
        mode.pack(fill="x")
        self.mode_trigger = tk.StringVar(value=self.cfg.trigger_mode)
        theme.DarkRadio(
            mode,
            text="По фронту — одно нажатие на ноту (рекомендуется)",
            variable=self.mode_trigger,
            value="edge",
            command=self._apply_general,
        ).pack(anchor="w")
        theme.DarkRadio(
            mode,
            text="По кулдауну — повторять, пока нота держится",
            variable=self.mode_trigger,
            value="cooldown",
            command=self._apply_general,
        ).pack(anchor="w", pady=(4, 0))

        # --- распознавание ---
        detect = ttk.LabelFrame(left, text="Распознавание нот", padding=10)
        detect.pack(fill="x", pady=(10, 0))
        self.mode_detect = tk.StringVar(value=self.cfg.detect_mode)
        theme.DarkRadio(
            detect,
            text="Пиксели — как сейчас (яркость + эталон)",
            variable=self.mode_detect,
            value="pixel",
            command=self._apply_general,
        ).pack(anchor="w")
        theme.DarkRadio(
            detect,
            text="Цвет — для переливающихся нот",
            variable=self.mode_detect,
            value="color",
            command=self._apply_general,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            detect,
            text=(
                "Цвет сравнивает каналы RGB: радужная нота ловится при любом "
                "оттенке. Нужен цветовой эталон — «Калибровать» на паузе."
            ),
            style="Dim.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # --- тайминги ---
        timing = ttk.LabelFrame(left, text="Тайминги", padding=10)
        timing.pack(fill="x", pady=(10, 0))
        timing.columnconfigure(1, weight=1)
        ttk.Label(timing, text="Задержка старта, сек:").grid(row=0, column=0, sticky="w")
        self.countdown_var = tk.DoubleVar(value=self.cfg.countdown_sec)
        countdown = ttk.Spinbox(
            timing,
            from_=0,
            to=10,
            increment=0.5,
            width=8,
            textvariable=self.countdown_var,
            command=self._apply_general,
        )
        countdown.grid(row=0, column=1, sticky="w", padx=8)
        countdown.bind("<FocusOut>", lambda _e: self._apply_general())
        countdown.bind("<Return>", lambda _e: self._apply_general())
        ttk.Label(timing, text="время переключиться в игру", style="Dim.TLabel").grid(
            row=0, column=2, sticky="w"
        )

        ttk.Label(timing, text="Пауза между кадрами, мс:").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.loop_delay_var = tk.IntVar(value=self.cfg.loop_delay_ms)
        loop_delay = ttk.Spinbox(
            timing,
            from_=0,
            to=100,
            increment=1,
            width=8,
            textvariable=self.loop_delay_var,
            command=self._apply_general,
        )
        loop_delay.grid(row=1, column=1, sticky="w", padx=8, pady=(6, 0))
        loop_delay.bind("<FocusOut>", lambda _e: self._apply_general())
        loop_delay.bind("<Return>", lambda _e: self._apply_general())
        ttk.Label(timing, text="0 — максимальная частота опроса", style="Dim.TLabel").grid(
            row=1, column=2, sticky="w"
        )

        # --- диагностика ---
        diag = ttk.LabelFrame(left, text="Диагностика", padding=10)
        diag.pack(fill="x", pady=(10, 0))
        self.btn_auto = ttk.Button(
            diag, text="Автопорог по паузе", command=self.auto_threshold
        )
        self.btn_auto.pack(fill="x")
        buttons = ttk.Frame(diag)
        buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="Проверить настройки", command=self.check_settings).pack(
            side="left"
        )
        ttk.Button(buttons, text="Рекомендуемые тайминги", command=self.apply_recommended).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(
            diag,
            text="Автопорог: игра на паузе, нот на приёмниках нет.",
            style="Dim.TLabel",
            wraplength=380,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # --- тонкая настройка ноты ---
        tune = ttk.LabelFrame(right, text="Нота: чувствительность", padding=10)
        tune.pack(fill="x")
        self._tune_note = tk.StringVar(value="left")
        tune_row = ttk.Frame(tune)
        tune_row.pack(fill="x")
        for d in DIRECTIONS:
            theme.DarkRadio(
                tune_row,
                text=DIR_LABELS[d],
                variable=self._tune_note,
                value=d,
                command=self._sync_tune_widgets,
            ).pack(side="left", padx=(0, 10))

        body = ttk.Frame(tune)
        body.pack(fill="x", pady=(8, 0))
        self.tune_thumb = tk.Label(body, bg=theme.BG_FIELD, width=56, height=56, fg=theme.FG_DIM)
        self.tune_thumb.pack(side="left", padx=(0, 10))

        grid = ttk.Frame(body)
        grid.pack(side="left", fill="x", expand=True)
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="Держать, мс:").grid(row=0, column=0, sticky="w")
        self.tune_hold = ttk.Spinbox(grid, from_=1, to=300, increment=5, width=8)
        self.tune_hold.grid(row=0, column=1, sticky="w", padx=8, pady=2)
        self.tune_hold.bind("<FocusOut>", lambda _e: self._apply_tune())
        self.tune_hold.bind("<Return>", lambda _e: self._apply_tune())

        ttk.Label(grid, text="Кулдаун, мс:").grid(row=1, column=0, sticky="w")
        self.tune_cd = ttk.Spinbox(grid, from_=0, to=1000, increment=10, width=8)
        self.tune_cd.grid(row=1, column=1, sticky="w", padx=8, pady=2)
        self.tune_cd.bind("<FocusOut>", lambda _e: self._apply_tune())
        self.tune_cd.bind("<Return>", lambda _e: self._apply_tune())

        ttk.Label(grid, text="Порог пикселя:").grid(row=2, column=0, sticky="w", pady=(4, 0))
        pix_row = ttk.Frame(grid)
        pix_row.grid(row=2, column=1, sticky="ew", padx=8, pady=(4, 0))
        pix_row.columnconfigure(0, weight=1)
        self._pix_var = tk.DoubleVar(value=1.0)
        self.tune_pix = ttk.Scale(
            pix_row,
            from_=1,
            to=120,
            orient="horizontal",
            variable=self._pix_var,
            style="Mono.Horizontal.TScale",
            command=self._on_pix_scale,
        )
        self.tune_pix.grid(row=0, column=0, sticky="ew")
        self.pix_value = ttk.Label(pix_row, width=4, anchor="e", style="Dim.TLabel")
        self.pix_value.grid(row=0, column=1, sticky="e", padx=(6, 0))

        ttk.Label(grid, text="Мин. площадь, %:").grid(row=3, column=0, sticky="w", pady=(4, 0))
        area_row = ttk.Frame(grid)
        area_row.grid(row=3, column=1, sticky="ew", padx=8, pady=(4, 0))
        area_row.columnconfigure(0, weight=1)
        self.tune_area = ttk.Scale(
            area_row,
            from_=0.2,
            to=50.0,
            orient="horizontal",
            variable=self.ui["left"]["area"],
            style="Mono.Horizontal.TScale",
            command=self._on_area_scale,
        )
        self.tune_area.grid(row=0, column=0, sticky="ew")
        self.area_value = ttk.Label(area_row, width=4, anchor="e", style="Dim.TLabel")
        self.area_value.grid(row=0, column=1, sticky="e", padx=(6, 0))

        ttk.Label(grid, text="Отпускать, тишина мс:").grid(row=4, column=0, sticky="w")
        self.tune_grace = ttk.Spinbox(grid, from_=20, to=600, increment=10, width=8)
        self.tune_grace.grid(row=4, column=1, sticky="w", padx=8, pady=2)
        self.tune_grace.bind("<FocusOut>", lambda _e: self._apply_tune())
        self.tune_grace.bind("<Return>", lambda _e: self._apply_tune())

        ttk.Label(grid, text="Макс. удержание, мс:").grid(row=5, column=0, sticky="w")
        self.tune_hmax = ttk.Spinbox(grid, from_=200, to=30000, increment=500, width=8)
        self.tune_hmax.grid(row=5, column=1, sticky="w", padx=8, pady=2)
        self.tune_hmax.bind("<FocusOut>", lambda _e: self._apply_tune())
        self.tune_hmax.bind("<Return>", lambda _e: self._apply_tune())

        ttk.Label(grid, text="Порог цвета (0–255):").grid(row=6, column=0, sticky="w", pady=(4, 0))
        self.tune_color = ttk.Spinbox(grid, from_=5, to=254, increment=5, width=8)
        self.tune_color.grid(row=6, column=1, sticky="w", padx=8, pady=(4, 0))
        self.tune_color.bind("<FocusOut>", lambda _e: self._apply_tune())
        self.tune_color.bind("<Return>", lambda _e: self._apply_tune())

        ttk.Button(grid, text="Проверить нажатие", command=self._test_tune_key).grid(
            row=7, column=1, sticky="w", padx=8, pady=(6, 0)
        )

        # --- горячие клавиши ---
        hot = ttk.LabelFrame(right, text="Горячие клавиши", padding=10)
        hot.pack(fill="x", pady=(10, 0))
        self.hot_start = tk.StringVar(value=self.cfg.hotkey_start)
        self.hot_stop = tk.StringVar(value=self.cfg.hotkey_stop)
        self.hot_cal = tk.StringVar(value=self.cfg.hotkey_calibrate)
        hot_row = ttk.Frame(hot)
        hot_row.pack(fill="x")
        for label, var in (
            ("Старт", self.hot_start),
            ("Стоп", self.hot_stop),
            ("Калибровка", self.hot_cal),
        ):
            ttk.Label(hot_row, text=label + ":").pack(side="left")
            ttk.Entry(hot_row, textvariable=var, width=9).pack(side="left", padx=(5, 12))
        ttk.Button(hot, text="Применить", command=self._rebind_hotkeys).pack(
            anchor="w", pady=(8, 0)
        )
        ttk.Label(
            hot,
            text="Формат: F8, ctrl+shift+s. Работают, даже когда окно не в фокусе.",
            style="Dim.TLabel",
            wraplength=400,
            justify="left",
        ).pack(anchor="w", pady=(6, 0))

        # --- прочее ---
        other = ttk.LabelFrame(right, text="Прочее", padding=10)
        other.pack(fill="x", pady=(10, 0))
        other_row = ttk.Frame(other)
        other_row.pack(fill="x")
        ttk.Button(other_row, text="Открыть папку", command=self._open_folder).pack(side="left")
        ttk.Button(
            other_row, text="Сбросить эталоны", command=self._clear_baselines
        ).pack(side="left", padx=(6, 0))
        ttk.Button(other_row, text="Сбросить статистику", command=self._reset_stats).pack(
            side="left", padx=(6, 0)
        )
        ttk.Label(
            other,
            text=(
                "Если игра запущена от администратора, запустите бота тоже от администратора — "
                "иначе Windows не пропустит нажатия."
            ),
            wraplength=400,
            justify="left",
            style="Dim.TLabel",
        ).pack(anchor="w", pady=(8, 0))

    # ---------- синхронизация ----------
    def _refresh_ui(self) -> None:
        self._loading = True
        try:
            for d in DIRECTIONS:
                arrow = self.cfg.arrows[d]
                v = self.ui[d]
                v["enabled"].set(arrow.enabled)
                v["key"].set(arrow.key)
                v["hold"].set(arrow.hold_ms)
                v["cd"].set(arrow.cooldown_ms)
                v["pix"].set(arrow.pixel_threshold)
                v["color"].set(arrow.color_threshold)
                v["area"].set(arrow.area_threshold)
                v["release"].set(arrow.release_ratio)
                v["slide"].set(arrow.slide)
                v["grace"].set(arrow.hold_grace_ms)
                v["hmax"].set(arrow.hold_max_ms)
                self._update_labels(d)
            self.mode_trigger.set(self.cfg.trigger_mode)
            self.mode_detect.set(self.cfg.detect_mode)
            self.countdown_var.set(self.cfg.countdown_sec)
            self.loop_delay_var.set(self.cfg.loop_delay_ms)
            self.hot_start.set(self.cfg.hotkey_start)
            self.hot_stop.set(self.cfg.hotkey_stop)
            self.hot_cal.set(self.cfg.hotkey_calibrate)
            self._sync_tune_widgets()
        finally:
            self._loading = False

    def _update_labels(self, d: str) -> None:
        arrow = self.cfg.arrows[d]
        v = self.ui[d]
        x, y, w, h = arrow.rect()

        if not arrow.has_region():
            v["region"].set("область не выбрана")
            self._region_labels[d].configure(style="Dim.TLabel")
        elif w < 24 or h < 24:
            v["region"].set(f"{x}, {y} · {w}×{h} — тонко")
            self._region_labels[d].configure(style="Warn.TLabel")
        else:
            v["region"].set(f"{x}, {y} · {w}×{h}")
            self._region_labels[d].configure(style="Dim.TLabel")

        base = arrow.get_baseline()
        if base is None:
            v["base"].set("эталон: нет")
            self._base_labels[d].configure(style="Warn.TLabel")
        else:
            if arrow.baseline_source == "shot":
                text = "эталон: скриншот"
            elif arrow.baseline_source == "screen":
                text = "эталон: с экрана"
            else:
                text = "эталон: есть"
            flat = False
            dark_flat = False
            try:
                flat = float(base.std()) < 2.5
                dark_flat = flat and float(base.mean()) < 8.0
            except Exception:
                pass
            if dark_flat:
                text += " · чёрный фон"
            elif flat:
                text += " · пусто?"
            v["base"].set(text)
            self._base_labels[d].configure(
                style="Warn.TLabel" if flat and not dark_flat else "Ok.TLabel"
            )
        self._update_tune_thumb()

    def _update_tune_thumb(self) -> None:
        try:
            d = self._tune_note.get()
        except Exception:
            return
        if not hasattr(self, "tune_thumb"):
            return
        base = self.cfg.arrows[d].get_baseline()
        if base is None:
            self.tune_thumb.configure(image="", text="нет\nэталона", width=56, height=56)
            self.tune_thumb.image = None
            return
        try:
            from PIL import Image, ImageTk

            img = Image.fromarray(base).convert("RGB")
            img = img.resize((56, 56), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self.tune_thumb.configure(image=photo, text="", width=56, height=56)
            self.tune_thumb.image = photo
        except Exception:
            pass

    def _sync_tune_widgets(self) -> None:
        """Привязывает ползунки настроек к выбранной ноте."""
        try:
            d = self._tune_note.get()
        except Exception:
            return
        if not hasattr(self, "tune_hold"):
            return
        v = self.ui[d]
        self.tune_hold.configure(textvariable=v["hold"])
        self.tune_cd.configure(textvariable=v["cd"])
        self.tune_grace.configure(textvariable=v["grace"])
        self.tune_hmax.configure(textvariable=v["hmax"])
        self.tune_color.configure(textvariable=v["color"])
        pix = int(v["pix"].get())
        self._pix_var.set(float(pix))
        self.pix_value.configure(text=str(pix))
        self.tune_area.configure(variable=v["area"])
        self.area_value.configure(text=f"{float(v['area'].get()):.1f}")
        self._update_tune_thumb()

    def _apply(self, d: str) -> None:
        if self._loading:
            return
        arrow = self.cfg.arrows[d]
        v = self.ui[d]
        arrow.enabled = bool(v["enabled"].get())
        arrow.key = str(v["key"].get()).strip()[:32]
        try:
            arrow.hold_ms = max(1, min(500, int(float(v["hold"].get()))))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.cooldown_ms = max(0, min(2000, int(float(v["cd"].get()))))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.pixel_threshold = max(1, min(254, int(float(v["pix"].get()))))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.color_threshold = max(1, min(254, int(float(v["color"].get()))))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.area_threshold = max(0.1, min(100.0, float(v["area"].get())))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.release_ratio = max(0.1, min(0.95, float(v["release"].get())))
        except (tk.TclError, ValueError):
            pass
        arrow.slide = bool(v["slide"].get())
        try:
            arrow.hold_grace_ms = max(20, min(600, int(float(v["grace"].get()))))
        except (tk.TclError, ValueError):
            pass
        try:
            arrow.hold_max_ms = max(200, min(30000, int(float(v["hmax"].get()))))
        except (tk.TclError, ValueError):
            pass
        self._update_labels(d)
        self._schedule_save()

    def _apply_tune(self) -> None:
        if self._loading:
            return
        self._apply(self._tune_note.get())

    def _on_pix_scale(self, value) -> None:
        try:
            number = int(round(float(value)))
        except (TypeError, ValueError):
            return
        number = max(1, min(254, number))
        self.pix_value.configure(text=str(number))
        if self._loading:
            return
        self.ui[self._tune_note.get()]["pix"].set(number)
        self._apply_tune()

    def _on_area_scale(self, value) -> None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return
        self.area_value.configure(text=f"{number:.1f}")
        if self._loading:
            return
        self._apply_tune()

    def _toggle_note(self, d: str) -> None:
        self._tune_note.set(d)
        self._sync_tune_widgets()
        self._apply(d)

    def _apply_general(self) -> None:
        if self._loading:
            return
        self.cfg.trigger_mode = "cooldown" if self.mode_trigger.get() == "cooldown" else "edge"
        self.cfg.detect_mode = "color" if self.mode_detect.get() == "color" else "pixel"
        try:
            self.cfg.countdown_sec = max(0.0, min(10.0, float(self.countdown_var.get())))
        except (tk.TclError, ValueError):
            pass
        try:
            self.cfg.loop_delay_ms = max(0, min(200, int(float(self.loop_delay_var.get()))))
        except (tk.TclError, ValueError):
            pass
        self._schedule_save()

    def _schedule_save(self) -> None:
        if self._closing:
            return
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_job = self.root.after(700, self._save_now)

    def _save_now(self) -> None:
        self._save_job = None
        try:
            self.cfg.save()
        except Exception as exc:
            self._log(f"Не удалось сохранить настройки: {exc}")

    # ---------- проверки настроек ----------
    def _config_issues(self) -> List[str]:
        issues: List[str] = []
        sw, sh = screen_size()
        for d in DIRECTIONS:
            a = self.cfg.arrows[d]
            label = DIR_LABELS[d]
            if not a.enabled:
                continue
            if not a.has_region():
                issues.append(f"{label}: область не выбрана.")
                continue
            x, y, w, h = a.rect()
            if w < 24 or h < 24:
                issues.append(
                    f"{label}: область {w}×{h} — тонкая. Нота может проскочить между кадрами; "
                    "расширьте её вниз до 24–30 px, верхнюю границу оставьте на месте."
                )
            if x < 0 or y < 0 or x + w > sw or y + h > sh:
                issues.append(f"{label}: область выходит за экран ({sw}×{sh}).")
            if a.hold_ms < 15:
                issues.append(
                    f"{label}: «держать» {a.hold_ms} мс — игра может не увидеть нажатие. "
                    "Поставьте 25–35 мс."
                )
            if a.cooldown_ms > 120:
                issues.append(
                    f"{label}: кулдаун {a.cooldown_ms} мс — частые ноты будут пропускаться. "
                    "Поставьте 40–80 мс."
                )
            if not a.has_baseline():
                issues.append(f"{label}: нет эталона — нота не будет срабатывать.")
            else:
                base = a.get_baseline()
                try:
                    # Полностью чёрный эталон — это нормально для чёрного приёмника
                    # (Roblox-FNF): нота появляется поверх чёрного фона. Тревожно
                    # только однотонное, но не чёрное пятно — там ноты обычно нет.
                    if (
                        base is not None
                        and float(base.std()) < 2.5
                        and float(base.mean()) > 8.0
                    ):
                        issues.append(
                            f"{label}: эталон однотонный и не чёрный — похоже, область "
                            "стоит в пустом месте, а не на приёмнике."
                        )
                except Exception:
                    pass
            if not a.key:
                issues.append(f"{label}: не назначена клавиша.")
        if self.cfg.loop_delay_ms > 25:
            issues.append(
                f"Пауза между кадрами {self.cfg.loop_delay_ms} мс снижает частоту опроса. "
                "Поставьте 0."
            )
        return issues

    def _startup_checks(self) -> None:
        issues = self._config_issues()
        for text in issues:
            self._log("Проверка: " + text)
        if issues:
            self.status_var.set(
                f"Замечания по настройкам: {len(issues)}. "
                "Вкладка «Настройки» → «Проверить настройки»."
            )

    def check_settings(self) -> None:
        issues = self._config_issues()
        for text in issues:
            self._log("Проверка: " + text)
        if not issues:
            messagebox.showinfo(
                "Проверка настроек",
                "Всё выглядит хорошо.\n\n"
                "Если ноты всё равно пропускаются: нажмите «Монитор», сыграйте фрагмент "
                "и посмотрите на «пропуск» и «слабо» у каждой ноты.",
            )
            return

        text = "Найдено:\n\n" + "\n".join("• " + item for item in issues)
        text += (
            "\n\nТайминги (держать / кулдаун) можно исправить одной кнопкой. "
            "Тонкие области и пустой эталон нужно перерисовать вручную: "
            "«Скриншот игры…» → обвести центр приёмника."
        )
        if messagebox.askyesno("Проверка настроек", text + "\n\nИсправить тайминги сейчас?"):
            self.apply_recommended(silent=True)

    def apply_recommended(self, silent: bool = False) -> None:
        if not silent and not messagebox.askyesno(
            "Рекомендуемые тайминги",
            "Поставить для всех нот:\n\n"
            "• держать 30 мс (игра успевает увидеть нажатие);\n"
            "• кулдаун 60 мс (быстрые ноты не пропускаются);\n"
            "• пауза между кадрами 0.\n\n"
            "Порог чувствительности и области не меняются.",
        ):
            return
        for d in DIRECTIONS:
            a = self.cfg.arrows[d]
            if not a.enabled:
                continue
            a.hold_ms = 30
            a.cooldown_ms = 60
            a.release_ratio = 0.5
            a.slide = True
            a.hold_grace_ms = 80
            a.hold_max_ms = 8000
        self.cfg.loop_delay_ms = 0
        self._refresh_ui()
        self._save_now()
        self._log("Тайминги исправлены: держать 30 мс, кулдаун 60 мс, пауза 0")
        if not silent:
            messagebox.showinfo(
                "Готово",
                "Тайминги исправлены.\n\n"
                "Если области тоньше 30 px или эталон «пусто?» — перерисуйте их на скриншоте.",
            )

    # ---------- автопорог ----------
    def auto_threshold(self) -> None:
        dirs = [
            d
            for d in DIRECTIONS
            if self.cfg.arrows[d].enabled
            and self.cfg.arrows[d].has_region()
            and self.cfg.arrows[d].has_baseline()
        ]
        if not dirs:
            messagebox.showinfo(
                "Автопорог",
                "Нужны размеченные ноты с эталоном. Сначала разметьте скриншот.",
            )
            return
        if self._auto_running:
            return
        if not messagebox.askokcancel(
            "Автопорог",
            "Поставьте игру на паузу так, чтобы нот на приёмниках не было.\n\n"
            "Бот 1,5 секунды будет измерять шум в областях и поставит порог "
            "чуть выше шума. Нажмите ОК и не двигайте игру.",
        ):
            return
        if self.engine is not None and self.engine.is_alive():
            self.stop()
        self._auto_running = True
        self.btn_auto.configure(state="disabled", text="Измеряю шум…")
        self.status_var.set("Измеряю шум 1,5 секунды — игра должна стоять на паузе")
        thread = threading.Thread(target=self._sample_noise, args=(dirs,), daemon=True)
        thread.start()

    def _sample_noise(self, dirs) -> None:
        from .capture import RegionGrabber
        from .detector import ArrowDetector

        try:
            import numpy as np
        except Exception as exc:  # noqa: BLE001
            self._auto_result = {"error": str(exc)}
            self._events.put("auto_threshold")
            return

        result = {}
        try:
            regions = {d: self.cfg.arrows[d].rect() for d in dirs}
            grabber = RegionGrabber(regions)
            detectors = {d: ArrowDetector(self.cfg.arrows[d]) for d in dirs}
            values = {d: [] for d in dirs}
            end = time.perf_counter() + 1.5
            while time.perf_counter() < end:
                frames = grabber.grab()
                for d in dirs:
                    gray = frames.get(d)
                    if gray is not None:
                        values[d].append(detectors[d].score(gray))
                time.sleep(0.005)
            grabber.close()
            for d in dirs:
                arr = values[d]
                if not arr:
                    result[d] = None
                else:
                    noise = float(np.percentile(arr, 99))
                    result[d] = (noise, float(max(arr)))
        except Exception as exc:  # noqa: BLE001
            result = {"error": str(exc)}
        self._auto_result = result
        self._events.put("auto_threshold")

    def _finish_auto_threshold(self) -> None:
        self._auto_running = False
        try:
            self.btn_auto.configure(state="normal", text="Автопорог по паузе")
        except Exception:
            pass
        result = self._auto_result
        self._auto_result = None
        if not result:
            self.status_var.set("Автопорог не удался")
            return
        if "error" in result:
            self._log(f"Автопорог: {result['error']}")
            self.status_var.set("Автопорог не удался")
            return

        lines = []
        changed = False
        for d in DIRECTIONS:
            if d not in result:
                continue
            label = DIR_LABELS[d]
            value = result[d]
            if value is None:
                lines.append(f"{label}: не удалось снять область")
                continue
            noise, peak = value
            if noise > 12.0:
                lines.append(
                    f"{label}: шум {noise:.1f}% — похоже, в области нота или анимация. "
                    "Поставьте паузу и повторите."
                )
                continue
            threshold = max(2.0, min(30.0, round(noise * 2.5 + 1.0, 1)))
            self.cfg.arrows[d].area_threshold = threshold
            changed = True
            lines.append(f"{label}: шум {noise:.1f}% → порог {threshold:.1f}%")
        if changed:
            self._refresh_ui()
            self._save_now()
        self._log("Автопорог: " + "; ".join(lines))
        self.status_var.set("Автопорог готов")
        messagebox.showinfo(
            "Автопорог",
            "\n".join(lines)
            + "\n\nЕсли после этого бот не реагирует — область стоит не там, где проходит "
            "нота: обведите центр приёмника на скриншоте.",
        )

    # ---------- клавиши ----------
    def _on_key(self, event, d: str) -> str:
        if is_modifier(event):
            return "break"
        name = key_name_from_event(event)
        if not name or name == "??":
            return "break"
        self.ui[d]["key"].set(name)
        self._apply(d)
        return "break"

    def _test_key(self, d: str) -> None:
        key = self.cfg.arrows[d].key
        if not key:
            messagebox.showinfo("Клавиша не задана", "Сначала назначьте клавишу для этой ноты.")
            return
        from .keys import KeySender

        sender = KeySender()
        ok = sender.tap(key, 40)
        self._log(
            f"Проверка {DIR_LABELS[d]}: {'нажата' if ok else 'не удалось нажать'} "
            f"клавиша {key.upper()}"
        )

    def _test_tune_key(self) -> None:
        self._test_key(self._tune_note.get())

    # ---------- области ----------
    def _hide_windows(self):
        hidden = []
        for win in (self.root, self.editor):
            try:
                if win is not None and win.winfo_exists() and win.state() != "withdrawn":
                    win.withdraw()
                    hidden.append(win)
            except Exception:
                pass
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        return hidden

    def _show_windows(self, hidden) -> None:
        if self._closing:
            return
        for win in hidden:
            try:
                if win.winfo_exists():
                    win.deiconify()
                    win.lift()
            except Exception:
                pass

    def _pick_region(self, d: str) -> None:
        hidden = self._hide_windows()
        time.sleep(0.25)
        try:
            rect = pick_region(
                self.root,
                hint=(
                    f"Обведите {DIR_LABELS[d].lower()} ноту — внутреннюю часть приёмника. "
                    "Esc — отмена"
                ),
            )
        finally:
            self._show_windows(hidden)
        if rect is None:
            return
        self.cfg.arrows[d].set_rect(*rect)
        self.cfg.arrows[d].enabled = True
        self.ui[d]["enabled"].set(True)
        self._update_labels(d)
        self._schedule_save()

        if messagebox.askyesno(
            "Сделать эталон?",
            "Область сохранена.\n\n"
            "Сделать эталон («спокойное» состояние) с экрана прямо сейчас?\n\n"
            "Игра должна быть на паузе, нот на приёмниках нет.\n"
            "Можно отказаться и взять эталон со скриншота.",
            parent=self.root,
        ):
            self.calibrate([d])

    def show_areas(self) -> None:
        regions = {}
        labels = {}
        for d in DIRECTIONS:
            arrow = self.cfg.arrows[d]
            if arrow.enabled and arrow.has_region():
                regions[d] = arrow.rect()
                labels[d] = f"{DIR_LABELS[d]}: {(arrow.key or '—').upper()}"
        if not regions:
            messagebox.showinfo("Нет областей", "Сначала разметьте ноты на скриншоте или на экране.")
            return
        hidden = self._hide_windows()
        time.sleep(0.2)
        show_regions(
            self.root,
            regions,
            labels,
            title="Проверка: рамки должны совпасть с приёмниками в игре",
            duration=5.0,
        )
        self.root.after(5300, lambda: self._show_windows(hidden))

    # ---------- сверка эталона с экраном ----------
    def _alignment_scores(self, hide_window: bool = True):
        """Считает, насколько текущий экран отличается от эталона каждой ноты."""
        from .capture import RegionGrabber
        from .detector import ArrowDetector

        dirs = [
            d
            for d in DIRECTIONS
            if self.cfg.arrows[d].enabled
            and self.cfg.arrows[d].has_region()
            and self.cfg.arrows[d].has_baseline()
        ]
        if not dirs:
            return {}, {}

        hidden = self._hide_windows() if hide_window else []
        if hide_window:
            time.sleep(0.25)
        try:
            scores = {}
            try:
                grabber = RegionGrabber({d: self.cfg.arrows[d].rect() for d in dirs})
                frames = grabber.grab()
                grabber.close()
            except Exception as exc:
                self._log(f"Не удалось снять экран для сверки: {exc}")
                return {}, {}

            for d in dirs:
                gray = frames.get(d)
                if gray is None:
                    scores[d] = None
                else:
                    scores[d] = ArrowDetector(self.cfg.arrows[d]).score(gray)
            return dirs, scores
        finally:
            if hide_window:
                self._show_windows(hidden)

    def verify_alignment(self) -> None:
        dirs, scores = self._alignment_scores()
        if not dirs:
            messagebox.showinfo(
                "Нечего сверять",
                "Нужны размеченные ноты с эталоном: разметьте их на скриншоте "
                "или нажмите «Калибровать».",
            )
            return

        lines = []
        problems = []
        for d in dirs:
            score = scores[d]
            threshold = float(self.cfg.arrows[d].area_threshold)
            if score is None:
                lines.append(f"{DIR_LABELS[d]}: область вне экрана")
                problems.append(d)
                continue
            if score >= threshold:
                lines.append(
                    f"{DIR_LABELS[d]}: {score:.1f}% — НЕ совпадает "
                    "(или сейчас нота на приёмнике)"
                )
                problems.append(d)
            elif score >= threshold * 0.5:
                lines.append(f"{DIR_LABELS[d]}: {score:.1f}% — на границе, лучше перекалибровать")
            else:
                lines.append(f"{DIR_LABELS[d]}: {score:.1f}% — совпадает")

        for line in lines:
            self._log("Сверка: " + line)

        if problems:
            text = "\n".join(lines) + (
                "\n\nЕсли сейчас идёт песня — поставьте игру на паузу и проверьте снова.\n"
                "Если ноты нет на приёмнике — нажмите «Калибровать» (окно бота и игра "
                "должны быть в одном положении, что и при скриншоте)."
            )
        else:
            text = "\n".join(lines) + "\n\nВсё совпадает, можно запускать."
        messagebox.showinfo("Сверка эталона с экраном", text)

    # ---------- скриншот ----------
    def open_shot_editor(self) -> None:
        if self.editor is not None:
            try:
                if self.editor.winfo_exists():
                    self.editor.lift()
                    self.editor.focus_force()
                    return
            except Exception:
                pass
            self.editor = None

        self.editor = ShotEditor(self.root, self.cfg, on_apply=self._on_shot_applied)
        try:
            self.editor.bind("<Destroy>", self._on_editor_destroyed)
        except Exception:
            pass

        if self.cfg.screenshot:
            try:
                img = load_image(self.cfg.screenshot)
                self.editor.set_image(img, self.cfg.screenshot)
                self.editor.status.set(f"Открыт последний скриншот: {os.path.basename(self.cfg.screenshot)}")
            except Exception as exc:
                self._log(f"Не удалось открыть последний скриншот: {exc}")

    def _on_editor_destroyed(self, event) -> None:
        if event.widget is self.editor:
            self.editor = None

    def _on_shot_applied(self) -> None:
        if self.engine is not None and self.engine.is_alive():
            self.stop()
            self._log("Разметка изменена — бот остановлен")
        self._refresh_ui()
        self._save_now()
        self._log("Разметка со скриншота применена")

    # ---------- калибровка ----------
    def calibrate_all(self) -> None:
        self.calibrate([d for d in DIRECTIONS if self.cfg.arrows[d].enabled])

    def calibrate(self, dirs) -> None:
        dirs = [d for d in dirs if self.cfg.arrows[d].has_region()]
        if not dirs:
            messagebox.showinfo(
                "Некуда калибровать",
                "Сначала разметьте области нот на скриншоте или кнопкой «Область…».",
            )
            return
        if self.engine is not None and self.engine.is_alive():
            self.stop()
        self._calibrate_countdown(dirs, 3)

    def _calibrate_countdown(self, dirs, left: int) -> None:
        if self._closing:
            return
        if left > 0:
            names = ", ".join(DIR_LABELS[d] for d in dirs)
            self.status_var.set(
                f"Калибровка ({names}) через {left}… ноты не должны быть на приёмниках"
            )
            self.root.after(1000, self._calibrate_countdown, dirs, left - 1)
            return
        self._calibrate_now(dirs)

    def _calibrate_now(self, dirs) -> None:
        import numpy as np

        from .capture import RegionGrabber

        regions = {d: self.cfg.arrows[d].rect() for d in dirs}
        try:
            grabber = RegionGrabber(regions, color=True)
            frames = grabber.grab()
            grabber.close()
        except Exception as exc:
            self._log(f"Ошибка захвата при калибровке: {exc}")
            return

        done = []
        empty = []
        for d in dirs:
            rgb = frames.get(d)
            if rgb is None or rgb.size == 0:
                self._log(f"{DIR_LABELS[d]}: не удалось снять область")
                continue
            rgb = np.asarray(rgb, dtype=np.uint8)
            # серый эталон считаем из того же снимка — пригодится для режима «пиксели»
            gray = (
                rgb[..., 0].astype(np.uint16) * 77
                + rgb[..., 1].astype(np.uint16) * 150
                + rgb[..., 2].astype(np.uint16) * 29
            ) >> 8
            gray = gray.astype(np.uint8)
            self.cfg.arrows[d].set_baseline(gray, "screen")
            self.cfg.arrows[d].set_baseline_rgb(rgb, "screen")
            try:
                if float(gray.std()) < 2.5 and float(gray.mean()) > 8.0:
                    empty.append(DIR_LABELS[d])
            except Exception:
                pass
            done.append(DIR_LABELS[d])
            self._update_labels(d)
        if done:
            self._save_now()
            self._log("Эталон снят: " + ", ".join(done))
            self.status_var.set("Эталон обновлён: " + ", ".join(done))
            if empty:
                self._log(
                    "Внимание: почти однотонный эталон у " + ", ".join(empty)
                    + " — проверьте, что область стоит на приёмнике."
                )
        else:
            self.status_var.set("Калибровка не удалась — проверьте области")

    def _clear_baselines(self) -> None:
        if not messagebox.askyesno(
            "Сбросить эталоны",
            "Снять эталоны у всех нот? Их нужно будет откалибровать заново.",
        ):
            return
        for d in DIRECTIONS:
            self.cfg.arrows[d].clear_baseline()
            self._update_labels(d)
        self._save_now()
        self._log("Эталоны сброшены — калибруйте заново")

    # ---------- запуск ----------
    def start(self) -> None:
        self._launch(monitor=False)

    def monitor(self) -> None:
        self._launch(monitor=True)

    def _set_running(self, running: bool) -> None:
        try:
            self.btn_start.configure(state="disabled" if running else "normal")
            self.btn_stop.configure(state="normal" if running else "disabled")
            self.btn_monitor.configure(state="disabled" if running else "normal")
        except Exception:
            pass

    def _launch(self, monitor: bool) -> None:
        if self.engine is not None and self.engine.is_alive():
            self._log("Бот уже запущен")
            return
        if self.editor is not None:
            try:
                if self.editor.winfo_exists() and self.editor.state() != "withdrawn":
                    if not messagebox.askyesno(
                        "Редактор открыт",
                        "Окно редактора скриншота может закрывать игру и мешать захвату.\n\n"
                        "Закрыть редактор и запустить бота?",
                    ):
                        return
                    self.editor._close()
            except Exception:
                pass
        self._save_now()

        ready = [
            d
            for d in DIRECTIONS
            if self.cfg.arrows[d].enabled and self.cfg.arrows[d].has_region()
        ]
        if not ready:
            messagebox.showinfo(
                "Нет разметки",
                "Не размечено ни одной ноты.\n\n"
                "Откройте «Скриншот игры…», обведите ноты, назначьте клавиши "
                "и нажмите «Применить разметку».",
            )
            return

        if not monitor:
            missing_key = [DIR_LABELS[d] for d in ready if not self.cfg.arrows[d].key]
            if missing_key:
                messagebox.showwarning(
                    "Нет клавиш", "Не назначены клавиши для: " + ", ".join(missing_key)
                )
                return
            missing_base = [DIR_LABELS[d] for d in ready if not self.cfg.arrows[d].has_baseline()]
            if missing_base:
                if not messagebox.askyesno(
                    "Нет эталона",
                    "Для нот " + ", ".join(missing_base) + " не снят эталон.\n\n"
                    "Они не будут срабатывать. Продолжить?",
                ):
                    return

            # эталон мог быть снят со скриншота в другом положении окна — проверяем
            checked, scores = self._alignment_scores()
            suspicious = [
                DIR_LABELS[d]
                for d in checked
                if scores.get(d) is not None
                and scores[d] >= float(self.cfg.arrows[d].area_threshold)
            ]
            if suspicious:
                self._log("Сверка при старте: не совпадает — " + ", ".join(suspicious))
                if not messagebox.askyesno(
                    "Эталон не совпадает с экраном",
                    "Области отличаются от эталона: " + ", ".join(suspicious) + ".\n\n"
                    "Бот может нажимать без остановки. Если игра на паузе и нот на приёмниках "
                    "нет — нажмите «Калибровать».\n\n"
                    "Запустить всё равно?",
                ):
                    return

        self.engine = Engine(
            self.cfg,
            send_keys=not monitor,
            countdown=not monitor,
            verbose=True,
        )
        self.engine.reset_peaks()
        self.engine.start()
        self._set_running(True)
        self.mode_var.set("МОНИТОРИНГ" if monitor else "РАБОТАЕТ")
        self.status_var.set(
            "Мониторинг: бот только показывает изменение пикселей, клавиши не нажимает"
            if monitor
            else "Бот запущен — переключитесь в игру"
        )
        self._log("Мониторинг запущен" if monitor else "Бот запущен")

    def stop(self) -> None:
        if self.engine is not None:
            self.engine.stop()
            self.engine.join(timeout=2.0)
            for line in self.engine.drain_log():
                self._log(line)
            self.engine = None
        self.mode_var.set("остановлен")
        self._set_running(False)
        for d in DIRECTIONS:
            self.ui[d]["score"].set("0.0 %")
            self._bars[d]["value"] = 0.0
        self.status_var.set("Остановлен")

    def _reset_stats(self) -> None:
        if self.engine is not None:
            self.engine.reset_peaks()
        for d in DIRECTIONS:
            self.ui[d]["peak"].set("пик 0.0 %")
            self.ui[d]["stats"].set("нажатий 0")
        self._log("Статистика сброшена")

    # ---------- горячие клавиши ----------
    def _start_hotkeys(self) -> None:
        self.hotkeys = HotkeyManager(
            {
                "start": self.cfg.hotkey_start,
                "stop": self.cfg.hotkey_stop,
                "calibrate": self.cfg.hotkey_calibrate,
            },
            on_hotkey=self._events.put,
            on_error=lambda text: self._events.put("error:" + text),
        )
        self.hotkeys.start()

    def _rebind_hotkeys(self) -> None:
        combos = {
            "start": self.hot_start.get().strip(),
            "stop": self.hot_stop.get().strip(),
            "calibrate": self.hot_cal.get().strip(),
        }
        for name, combo in combos.items():
            if parse_hotkey(combo) is None:
                messagebox.showerror("Неверный формат", f"Не могу разобрать «{combo}»")
                return
        self.cfg.hotkey_start = combos["start"]
        self.cfg.hotkey_stop = combos["stop"]
        self.cfg.hotkey_calibrate = combos["calibrate"]
        self._save_now()
        self.hotkeys.rebind(combos)
        self.btn_start.configure(text=f"Старт ({combos['start']})")
        self.btn_stop.configure(text=f"Стоп ({combos['stop']})")
        self._log("Горячие клавиши обновлены")

    # ---------- цикл обновления ----------
    def _tick(self) -> None:
        if self._closing:
            return
        self._drain_events()
        self._update_live()
        self.root.after(60, self._tick)

    def _drain_events(self) -> None:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if event.startswith("error:"):
                self._log(event[6:])
            elif event == "auto_threshold":
                self._finish_auto_threshold()
            elif event == "start":
                if self.engine is None or not self.engine.is_alive():
                    self._launch(monitor=False)
            elif event == "stop":
                self.stop()
            elif event == "calibrate":
                self.calibrate_all()

    def _update_live(self) -> None:
        if self.engine is None:
            return
        states, status, fps, error = self.engine.snapshot()
        for line in self.engine.drain_log():
            self._log(line)
        if error:
            self._log(f"Остановлено: {error}")
            self.engine = None
            self.mode_var.set("остановлен")
            self._set_running(False)
            self.status_var.set("Остановлен из-за ошибки")
            return
        if not self.engine.is_alive():
            self.engine = None
            self.mode_var.set("остановлен")
            self._set_running(False)
            self.status_var.set("Остановлен")
            return

        self.status_var.set(f"{status} · {fps:.0f} кадр/с")
        for d, state in states.items():
            score = float(state.get("score", 0.0))
            self._bars[d]["value"] = min(100.0, score)
            self.ui[d]["score"].set(f"{score:.1f} %")
            self.ui[d]["peak"].set(f"пик {state.get('peak', 0.0):.1f} %")
            hits = int(state.get("hits", 0))
            missed = int(state.get("missed", 0))
            near = int(state.get("near", 0))
            text = f"нажатий {hits}"
            if missed:
                text += f" · пропуск {missed}"
            if near:
                text += f" · слабо {near}"
            self.ui[d]["stats"].set(text)

    # ---------- журнал ----------
    def _log(self, text: str) -> None:
        if self._closing:
            return
        try:
            at_bottom = self.log_text.yview()[1] >= 0.999
            self.log_text.configure(state="normal")
            self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {text}\n")
            lines = int(self.log_text.index("end-1c").split(".")[0])
            if lines > 600:
                self.log_text.delete("1.0", "101.0")
            if at_bottom:
                self.log_text.see("end")
            self.log_text.configure(state="disabled")
        except tk.TclError:
            pass

    # ---------- прочее ----------
    def _open_folder(self) -> None:
        try:
            os.startfile(os.path.normpath(APP_DIR))  # type: ignore[attr-defined]
        except Exception as exc:
            self._log(f"Не удалось открыть папку: {exc}")

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._save_job is not None:
            try:
                self.root.after_cancel(self._save_job)
            except Exception:
                pass
        self._save_now()
        try:
            self.hotkeys.stop()
        except Exception:
            pass
        if self.engine is not None:
            self.engine.stop()
            self.engine.join(timeout=1.0)
        self.root.destroy()


def run() -> None:
    root = tk.Tk()
    icon = os.path.join(RESOURCE_DIR, "assets", "icon.ico")
    if os.path.exists(icon):
        try:
            root.iconbitmap(default=icon)
        except Exception:
            pass
    MainApp(root)

    def _front() -> None:
        # Показываем окно поверх остальных при запуске. Раньше здесь было
        # iconify()+deiconify(), и на части систем окно оставалось свёрнутым.
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
        except Exception:
            pass

    root.after(80, _front)
    root.mainloop()
