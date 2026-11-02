"""Редактор скриншота игры: размечаем, ГДЕ нота и КАКОЙ клавишей бить.

Пользователь прикладывает скриншот, обводит на нём области нот, назначает клавиши.
Скриншот же служит эталоном «спокойного» состояния — калибровка не нужна.
"""

from __future__ import annotations

import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, Optional

from .config import DIRECTIONS, DIR_LABELS, BotConfig
from . import theme
from .overlay import pick_region, show_regions
from .screenshot import (
    grab_screen,
    load_image,
    region_gray,
    region_rgb,
    save_screenshot,
    screen_size,
)

COLORS = {"left": "#4fd1ff", "down": "#ffe066", "up": "#ff8fab", "right": "#8affc1"}
ZOOM_STEPS = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0)

# Виртуальные коды Windows -> имена клавиш. Нужны, чтобы клавиша ловилась
# по физической кнопке, даже если включена русская раскладка.
_VK_NAMES = {
    0x08: "backspace",
    0x09: "tab",
    0x0D: "enter",
    0x1B: "esc",
    0x20: "space",
    0x21: "pageup",
    0x22: "pagedown",
    0x23: "end",
    0x24: "home",
    0x25: "left",
    0x26: "up",
    0x27: "right",
    0x28: "down",
    0x2D: "insert",
    0x2E: "delete",
    0x6A: "multiply",
    0x6B: "add",
    0x6D: "subtract",
    0x6E: "decimal",
    0x6F: "divide",
    0xBA: "semicolon",
    0xBB: "equals",
    0xBC: "comma",
    0xBD: "minus",
    0xBE: "period",
    0xBF: "slash",
    0xC0: "grave",
    0xDB: "bracketleft",
    0xDC: "backslash",
    0xDD: "bracketright",
    0xDE: "quote",
}
_MODIFIER_VK = {0x10, 0x11, 0x12, 0x14, 0x5B, 0x5C, 0x5D, 0x90, 0x91}


def normalize_keysym(keysym: str) -> str:
    name = (keysym or "").lower()
    aliases = {"prior": "pageup", "next": "pagedown", "return": "enter", "control_l": "ctrl"}
    return aliases.get(name, name)


def key_name_from_event(event) -> str:
    """Имя клавиши по физическому коду, а не по символу раскладки.

    На русской раскладке event.keysym для клавиши A будет «Cyrillic_ef»,
    а event.keycode останется 65 — именно это и нужно боту (scan code).
    """
    vk = int(getattr(event, "keycode", 0) or 0)
    if 65 <= vk <= 90:  # A..Z
        return chr(vk).lower()
    if 48 <= vk <= 57:  # 0..9
        return chr(vk)
    if 0x70 <= vk <= 0x87:  # F1..F24
        return f"f{vk - 0x6F}"
    if 0x60 <= vk <= 0x69:  # Num 0..9
        return f"num{vk - 0x60}"
    if vk in _VK_NAMES:
        return _VK_NAMES[vk]
    return normalize_keysym(event.keysym)


def is_modifier(event) -> bool:
    vk = int(getattr(event, "keycode", 0) or 0)
    if vk in _MODIFIER_VK:
        return True
    return normalize_keysym(event.keysym) in (
        "shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r",
        "caps_lock", "win_l", "win_r", "super_l", "super_r", "meta_l", "meta_r",
    )


class ShotEditor(tk.Toplevel):
    def __init__(self, master, config: BotConfig, on_apply: Optional[Callable[[], None]] = None):
        super().__init__(master)
        self.title("Скриншот игры — где нота и чем нажимать")
        self.geometry("1160x800")
        self.minsize(900, 640)

        self.bot_config = config
        self.on_apply = on_apply
        self.image = None
        self.image_path = ""
        self.tk_img = None
        self.scale = 1.0
        self.zoom_index = 0
        self.map_rect = config.map_rect()
        self._drag = None
        self._last_canvas = (0, 0)
        self._dirty = False
        self._boxes_loaded = False

        self.boxes: Dict[str, list] = {}
        self._offset = (0, 0)

        self.current = tk.StringVar(value="left")
        self.use_shot_baseline = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Шаг 1: загрузите скриншот игры или сделайте новый")

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.bind("<Escape>", lambda _e: self._close())
        self.after(120, self._render)

    # ---------- интерфейс ----------
    def _build(self) -> None:
        theme.apply(self)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(side="top", fill="x")
        ttk.Button(top, text="Открыть скриншот…", command=self.open_file).pack(side="left")
        ttk.Button(top, text="Сделать скриншот (3с)", command=self.grab_now).pack(
            side="left", padx=(8, 0)
        )
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=10)
        ttk.Button(top, text="−", width=3, command=lambda: self._zoom(-1)).pack(side="left")
        ttk.Button(top, text="+", width=3, command=lambda: self._zoom(1)).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="Привязать к экрану…", command=self.bind_to_screen).pack(
            side="left", padx=(12, 0)
        )
        ttk.Button(top, text="Показать на экране", command=self.preview_on_screen).pack(
            side="left", padx=(8, 0)
        )
        ttk.Button(
            top, text="Применить разметку", style="Accent.TButton", command=self.apply
        ).pack(side="right")

        body = ttk.Frame(self, padding=(10, 0))
        body.pack(side="top", fill="both", expand=True)

        canvas_wrap = ttk.Frame(body)
        canvas_wrap.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(canvas_wrap, bg=theme.BG_LOG, highlightthickness=0, bd=0)
        hbar = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        canvas_wrap.rowconfigure(0, weight=1)
        canvas_wrap.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<MouseWheel>", self._on_wheel)

        side = ttk.Frame(body, padding=(12, 0, 0, 0))
        side.pack(side="left", fill="y")
        side.configure(width=330)

        info = ttk.LabelFrame(side, text="Куда и чем нажимать", padding=10)
        info.pack(fill="x")

        ttk.Label(
            info,
            text="Обведите внутреннюю часть приёмника — там, где появляется нота, "
            "а не яркий контур. Затем назначьте клавишу.",
            wraplength=290,
            justify="left",
            style="Dim.TLabel",
        ).pack(anchor="w", pady=(0, 8))

        self._key_vars: Dict[str, tk.StringVar] = {}
        for d in DIRECTIONS:
            row = ttk.Frame(info)
            row.pack(fill="x", pady=3)
            theme.DarkRadio(
                row,
                text=DIR_LABELS[d],
                variable=self.current,
                value=d,
                command=self._render,
            ).pack(side="left")
            var = tk.StringVar(value=self.bot_config.arrows[d].key)
            self._key_vars[d] = var
            entry = ttk.Entry(row, textvariable=var, width=10, justify="center")
            entry.pack(side="right")
            entry.bind("<KeyPress>", lambda e, d=d: self._on_key(e, d))
            entry.bind("<FocusIn>", lambda e: e.widget.select_range(0, "end"))

        ttk.Button(info, text="Стереть рамку выбранной ноты", command=self._clear_current).pack(
            fill="x", pady=(10, 0)
        )
        theme.DarkCheck(
            info,
            text="Эталон брать из скриншота",
            variable=self.use_shot_baseline,
        ).pack(anchor="w", pady=(10, 0))
        ttk.Button(info, text="Закрыть", command=self._close).pack(fill="x", pady=(10, 0))

        tips = ttk.LabelFrame(side, text="Коротко", padding=10)
        tips.pack(fill="both", expand=True, pady=(10, 0))
        ttk.Label(
            tips,
            text=(
                "• Скриншот — в том же окне и разрешении, что и игра.\n\n"
                "• На скриншоте ноты не должно быть на приёмнике.\n\n"
                "• Область должна быть не меньше 30 px в высоту, иначе "
                "быстрая нота проскочит между кадрами.\n\n"
                "• Скриншот не на весь экран — «Привязать к экрану…»."
            ),
            wraplength=290,
            justify="left",
            style="Dim.TLabel",
        ).pack(anchor="w")

        bottom = ttk.Frame(self, padding=(10, 6))
        bottom.pack(side="bottom", fill="x")
        ttk.Label(bottom, textvariable=self.status, style="Ok.TLabel").pack(anchor="w")

    # ---------- загрузка изображения ----------
    def set_image(self, img, path: str = "") -> None:
        """Поставить картинку и (при первом открытии) подтянуть рамки из настроек."""
        self.image = img
        if path:
            self.image_path = path
        if not self._boxes_loaded:
            self.load_boxes_from_config()
        self._render()

    def load_boxes_from_config(self) -> None:
        """Рамки в config.json хранятся в экранных координатах — переводим в координаты картинки."""
        self.boxes = {}
        for d in DIRECTIONS:
            x, y, w, h = self.bot_config.arrows[d].rect()
            if w > 3 and h > 3:
                self.boxes[d] = self._screen_to_image((x, y, w, h))
        self._boxes_loaded = True

    def _screen_to_image(self, rect):
        x, y, w, h = (int(v) for v in rect)
        if self.map_rect and self.image is not None:
            mx, my, mw, mh = self.map_rect
            iw, ih = self.image.size
            if mw > 3 and mh > 3 and iw > 0 and ih > 0:
                return [
                    int(round((x - mx) * iw / mw)),
                    int(round((y - my) * ih / mh)),
                    max(1, int(round(w * iw / mw))),
                    max(1, int(round(h * ih / mh))),
                ]
        return [x, y, w, h]

    # ---------- рендер ----------
    def _on_canvas_configure(self, event) -> None:
        if (event.width, event.height) == self._last_canvas:
            return
        self._last_canvas = (event.width, event.height)
        self._render()

    def _on_wheel(self, event) -> None:
        self._zoom(1 if event.delta > 0 else -1)

    def _zoom(self, direction: int) -> None:
        self.zoom_index = max(0, min(len(ZOOM_STEPS) - 1, self.zoom_index + direction))
        self._render()

    def _render(self) -> None:
        c = self.canvas
        c.delete("all")
        if self.image is None:
            c.create_text(
                40,
                40,
                anchor="nw",
                text="Скриншот не загружен.\n\n"
                "«Открыть скриншот…» — выбрать готовый файл\n"
                "«Сделать скриншот сейчас» — снять экран через 3 секунды",
                fill="#7a8794",
                font=("Segoe UI", 13),
            )
            c.configure(scrollregion=(0, 0, 10, 10))
            return

        from PIL import Image, ImageTk

        iw, ih = self.image.size
        cw = max(c.winfo_width(), 240)
        ch = max(c.winfo_height(), 240)
        fit = min(cw / iw, ch / ih)
        self.scale = max(0.05, fit * ZOOM_STEPS[self.zoom_index])
        dw, dh = max(1, int(iw * self.scale)), max(1, int(ih * self.scale))

        resized = self.image.resize((dw, dh), Image.LANCZOS)
        self.tk_img = ImageTk.PhotoImage(resized)
        dx = max(0, (cw - dw) // 2)
        dy = max(0, (ch - dh) // 2)
        self._offset = (dx, dy)
        c.create_image(dx, dy, anchor="nw", image=self.tk_img)
        c.configure(scrollregion=(0, 0, max(dw + dx * 2, cw), max(dh + dy * 2, ch)))

        for d in DIRECTIONS:
            box = self.boxes.get(d)
            if not box:
                continue
            x, y, w, h = box
            x0, y0 = dx + x * self.scale, dy + y * self.scale
            x1, y1 = dx + (x + w) * self.scale, dy + (y + h) * self.scale
            active = d == self.current.get()
            color = COLORS[d]
            c.create_rectangle(
                x0, y0, x1, y1, outline=color, width=3 if active else 2,
                dash=() if active else (4, 3),
            )
            key = self._key_vars[d].get() or "—"
            c.create_text(
                x0 + 3,
                max(9, y0 - 9),
                anchor="w",
                text=f"{DIR_LABELS[d]}: {key.upper()}",
                fill="#08110c",
                font=("Segoe UI", 10, "bold"),
            )
            c.create_text(
                x0 + 2,
                max(8, y0 - 9),
                anchor="w",
                text=f"{DIR_LABELS[d]}: {key.upper()}",
                fill=color,
                font=("Segoe UI", 10, "bold"),
            )

        self._update_status()

    def _update_status(self) -> None:
        parts = []
        if self.image is not None:
            iw, ih = self.image.size
            sw, sh = screen_size()
            parts.append(f"Скриншот {iw}×{ih}, экран {sw}×{sh}")
            if self.map_rect:
                mx, my, mw, mh = self.map_rect
                parts.append(f"привязка к экрану: {mw}×{mh} в ({mx}, {my})")
            elif (iw, ih) != (sw, sh):
                parts.append("размеры не совпадают — нажмите «Привязать к экрану…»")
            parts.append(f"масштаб {self.scale:.2f}×")
        parts.append(f"выбрана нота: {DIR_LABELS[self.current.get()]}")
        self.status.set(" · ".join(parts))

    # ---------- мышь ----------
    def _canvas_to_image(self, cx: float, cy: float):
        dx, dy = self._offset
        x = (cx - dx) / self.scale
        y = (cy - dy) / self.scale
        iw, ih = self.image.size
        return max(0, min(iw - 1, x)), max(0, min(ih - 1, y))

    def _on_press(self, event) -> None:
        if self.image is None:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self._drag = [cx, cy, None]
        self._drag[2] = self.canvas.create_rectangle(
            cx, cy, cx, cy, outline=COLORS[self.current.get()], width=2
        )

    def _on_motion(self, event) -> None:
        if not self._drag:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        self.canvas.coords(self._drag[2], self._drag[0], self._drag[1], cx, cy)

    def _on_release(self, event) -> None:
        if not self._drag or self.image is None:
            return
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        x0, y0 = self._canvas_to_image(self._drag[0], self._drag[1])
        x1, y1 = self._canvas_to_image(cx, cy)
        self.canvas.delete(self._drag[2])
        self._drag = None

        x, y = int(min(x0, x1)), int(min(y0, y1))
        w, h = int(abs(x1 - x0)), int(abs(y1 - y0))
        if w < 4 or h < 4:
            self.status.set("Слишком маленькая рамка — обведите область ноты побольше")
            return
        self.boxes[self.current.get()] = [x, y, w, h]
        self._dirty = True
        self._render()

    def _clear_current(self) -> None:
        if self.current.get() in self.boxes:
            self._dirty = True
        self.boxes.pop(self.current.get(), None)
        self._render()

    def _on_key(self, event, direction: str) -> str:
        if is_modifier(event):
            return "break"
        name = key_name_from_event(event)
        if not name or name == "??":
            return "break"
        self._key_vars[direction].set(name)
        self.bot_config.arrows[direction].key = name
        self._dirty = True
        self._render()
        return "break"

    # ---------- скриншот ----------
    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Скриншот игры",
            filetypes=[
                ("Изображения", "*.png;*.jpg;*.jpeg;*.bmp;*.webp"),
                ("Все файлы", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self.image = load_image(path)
        except Exception as exc:
            messagebox.showerror("Не удалось открыть", f"{path}\n\n{exc}", parent=self)
            return
        self.image_path = path
        self.map_rect = None
        self.bot_config.screenshot = path
        self.bot_config.set_map_rect(None)
        self._dirty = True
        self.zoom_index = 0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        if not self._boxes_loaded:
            self.load_boxes_from_config()
        self._render()
        iw, ih = self.image.size
        sw, sh = screen_size()
        if (iw, ih) != (sw, sh):
            self.status.set(
                f"Скриншот {iw}×{ih}, экран {sw}×{sh}: нажмите «Привязать к экрану…», "
                "иначе координаты будут смещены"
            )

    def grab_now(self) -> None:
        self.withdraw()
        try:
            self.master.withdraw()
        except Exception:
            pass
        self.update_idletasks()
        time.sleep(0.25)
        img = self._countdown_grab(3)
        try:
            self.master.deiconify()
        except Exception:
            pass
        self.deiconify()
        self.lift()
        if img is None:
            return
        self.image = img
        try:
            self.image_path = save_screenshot(img, "game")
            self.bot_config.screenshot = self.image_path
        except Exception:
            self.image_path = ""
        self.map_rect = None
        self.bot_config.set_map_rect(None)
        self._dirty = True
        self.zoom_index = 0
        if not self._boxes_loaded:
            self.load_boxes_from_config()
        self._render()
        self.status.set("Скриншот снят. Обведите ноты и назначайте клавиши")

    def _countdown_grab(self, seconds: int):
        sw, sh = screen_size()
        toast = tk.Toplevel(self)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        label = tk.Label(
            toast,
            text="",
            font=("Segoe UI", 34, "bold"),
            bg="#101418",
            fg="#2bff88",
            padx=28,
            pady=16,
        )
        label.pack()
        result = {}

        def tick(n: int) -> None:
            if n <= 0:
                toast.destroy()
                time.sleep(0.12)
                try:
                    result["img"] = grab_screen()
                except Exception as exc:
                    messagebox.showerror("Скриншот", str(exc), parent=self)
                return
            label.config(text=f"Скриншот через {n}… переключитесь в игру")
            toast.update_idletasks()
            toast.geometry(f"+{sw // 2 - toast.winfo_width() // 2}+40")
            toast.after(1000, tick, n - 1)

        tick(seconds)
        try:
            self.wait_window(toast)
        except Exception:
            pass
        return result.get("img")

    def bind_to_screen(self) -> None:
        """Обвести игру на экране — так координаты скриншота лягут на реальный экран."""
        self.withdraw()
        try:
            self.master.withdraw()
        except Exception:
            pass
        self.update_idletasks()
        time.sleep(0.2)
        rect = pick_region(
            self,
            hint="Обведите на экране область, которая изображена на скриншоте (окно игры). Esc — отмена",
        )
        try:
            self.master.deiconify()
        except Exception:
            pass
        self.deiconify()
        self.lift()
        if rect is None:
            return
        self.map_rect = rect
        self.bot_config.set_map_rect(rect)
        self._dirty = True
        self._render()

    def preview_on_screen(self) -> None:
        boxes = {d: b for d, b in self.boxes.items() if b and b[2] > 3 and b[3] > 3}
        if not boxes:
            self.status.set("Сначала обведите хотя бы одну ноту")
            return
        mapped = {d: self._map_to_screen(b) for d, b in boxes.items()}
        labels = {
            d: f"{DIR_LABELS[d]}: {(self._key_vars[d].get() or '—').upper()}"
            for d in boxes
        }
        self.withdraw()
        try:
            self.master.withdraw()
        except Exception:
            pass
        self.update_idletasks()
        time.sleep(0.2)
        show_regions(
            self,
            mapped,
            labels,
            title="Проверка: рамки должны совпасть со стрелками в игре",
            duration=5.0,
        )
        self.after(5300, self._restore_after_preview)

    def _restore_after_preview(self) -> None:
        try:
            self.master.deiconify()
        except Exception:
            pass
        self.deiconify()
        self.lift()

    # ---------- применить ----------
    def _map_to_screen(self, box) -> tuple:
        x, y, w, h = (int(v) for v in box)
        if self.map_rect and self.image is not None:
            mx, my, mw, mh = self.map_rect
            iw, ih = self.image.size
            sx = mx + round(x * mw / iw)
            sy = my + round(y * mh / ih)
            sw = max(3, round(w * mw / iw))
            sh = max(3, round(h * mh / ih))
            return sx, sy, sw, sh
        return x, y, w, h

    def apply(self) -> None:
        if self.image is None:
            messagebox.showinfo("Нет скриншота", "Сначала загрузите скриншот игры.", parent=self)
            return
        applied = []
        empty_baseline = []
        no_key = []
        for d in DIRECTIONS:
            box = self.boxes.get(d)
            if not box or box[2] < 4 or box[3] < 4:
                continue
            cfg = self.bot_config.arrows[d]
            cfg.key = self._key_vars[d].get().strip() or cfg.key
            cfg.set_rect(*self._map_to_screen(box))
            cfg.enabled = True
            if self.use_shot_baseline.get():
                gray = region_gray(self.image, box)
                if gray is not None:
                    cfg.set_baseline(gray, "shot")
                    try:
                        if float(gray.std()) < 2.5 and float(gray.mean()) > 8.0:
                            empty_baseline.append(DIR_LABELS[d])
                    except Exception:
                        pass
                rgb = region_rgb(self.image, box)
                if rgb is not None:
                    cfg.set_baseline_rgb(rgb, "shot")
            if not cfg.key:
                no_key.append(DIR_LABELS[d])
            applied.append(DIR_LABELS[d])

        if not applied:
            messagebox.showinfo(
                "Пусто", "Обведите хотя бы одну ноту на скриншоте.", parent=self
            )
            return

        self._dirty = False
        if self.on_apply:
            self.on_apply()
        self.status.set("Применено: " + ", ".join(applied) + ". Можно запускать бота")

        extra = ""
        if empty_baseline:
            extra += (
                "\n\nВнимание: область " + ", ".join(empty_baseline) + " почти однотонная. "
                "Похоже, вы обвели пустое место, а не центр приёмника — нота может не попадать "
                "в рамку. Перерисуйте область по центру, где появляется нота."
            )
        if no_key:
            extra += "\n\nНе назначены клавиши: " + ", ".join(no_key) + "."
        messagebox.showinfo(
            "Готово",
            "Разметка применена: " + ", ".join(applied) + "." + extra +
            "\n\nПроверьте кнопкой «Показать на экране», что рамки стоят на приёмниках.",
            parent=self,
        )

    def _close(self) -> None:
        # Сохраняем только если что-то реально меняли: иначе закрытие редактора
        # каждый раз перезаписывало config.json без причины.
        if self._dirty and self.on_apply:
            self.on_apply()
        self.destroy()
