"""Тёмная тема в стиле Windows 11 (ttk + tk), без эмодзи."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import glass

BG = glass.KEY          # фон окна: прозрачный ключ, за ним — акрил Windows
BG_ALT = glass.KEY      # панели тоже стеклянные
BG_FIELD = "#1a1a1a"    # поля ввода — непрозрачные
BG_LOG = "#080808"      # журнал
FG = "#ffffff"          # основной текст
FG_DIM = "#9a9a9a"      # второстепенный текст
BORDER = "#2e2e2e"
ACCENT = "#c8c8c8"      # монохромный акцент (без синего)
ACCENT_HOVER = "#e6e6e6"
ACCENT_PRESSED = "#8a8a8a"
BTN = "#3a3a3a"         # серая кнопка
BTN_HOVER = "#4a4a4a"
BTN_PRESSED = "#2a2a2a"
OK = "#ffffff"
WARN = "#a8a8a8"


def apply(root: tk.Misc) -> ttk.Style:
    """Применяет тёмную тему ко всему окну."""
    root.configure(bg=BG)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.option_add("*Font", "{Segoe UI} 9")

    style.configure(
        ".",
        background=BG,
        foreground=FG,
        fieldbackground=BG_FIELD,
        bordercolor=BORDER,
        lightcolor=BG_ALT,
        darkcolor=BG,
        troughcolor=BG_FIELD,
        focuscolor=ACCENT,
        selectbackground=ACCENT,
        selectforeground="#ffffff",
        font=("Segoe UI", 9),
    )

    style.configure("TFrame", background=BG)
    style.configure("TLabel", background=BG, foreground=FG)
    style.configure("Dim.TLabel", background=BG, foreground=FG_DIM)
    style.configure("Ok.TLabel", background=BG, foreground=OK)
    style.configure("Warn.TLabel", background=BG, foreground=WARN)

    style.configure(
        "TLabelframe",
        background=BG,
        bordercolor=BORDER,
        lightcolor=BG,
        darkcolor=BG,
        relief="solid",
        borderwidth=1,
    )
    style.configure("TLabelframe.Label", background=BG, foreground=FG_DIM)

    style.configure(
        "TButton",
        background=BTN,
        foreground=FG,
        bordercolor=BORDER,
        lightcolor=BTN,
        darkcolor=BTN,
        focusthickness=1,
        relief="flat",
        padding=(10, 5),
    )
    style.map(
        "TButton",
        background=[("pressed", BTN_PRESSED), ("active", BTN_HOVER), ("disabled", "#1e1e1e")],
        foreground=[("disabled", "#6b6b6b")],
        bordercolor=[("focus", ACCENT), ("active", "#555555")],
    )

    style.configure(
        "Accent.TButton",
        background=ACCENT,
        foreground="#000000",
        bordercolor=ACCENT,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        padding=(12, 5),
    )
    style.map(
        "Accent.TButton",
        background=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
        bordercolor=[("pressed", ACCENT_PRESSED), ("active", ACCENT_HOVER)],
        foreground=[("disabled", "#4a4a4a")],
    )

    style.configure(
        "TEntry",
        fieldbackground=BG_FIELD,
        foreground=FG,
        insertcolor=FG,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(6, 4),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", ACCENT)],
        fieldbackground=[("readonly", BG_ALT)],
    )

    style.configure(
        "TSpinbox",
        fieldbackground=BG_FIELD,
        foreground=FG,
        arrowcolor=FG,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=(4, 3),
    )
    style.map("TSpinbox", bordercolor=[("focus", ACCENT)])

    style.configure("TCheckbutton", background=BG, foreground=FG)
    style.map("TCheckbutton", background=[("active", BG)])
    style.configure("TRadiobutton", background=BG, foreground=FG)
    style.map("TRadiobutton", background=[("active", BG)])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 4, 0, 0))
    style.configure(
        "TNotebook.Tab",
        background=BG_ALT,
        foreground=FG_DIM,
        padding=(14, 6),
        borderwidth=1,
        bordercolor=BORDER,
        lightcolor=BG_ALT,
        darkcolor=BG_ALT,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", BG_FIELD)],
        foreground=[("selected", FG)],
        bordercolor=[("selected", ACCENT)],
    )

    style.configure(
        "Horizontal.TProgressbar",
        background=ACCENT,
        troughcolor="#262626",
        bordercolor=BORDER,
        lightcolor=ACCENT,
        darkcolor=ACCENT,
        thickness=10,
    )

    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background="#3d3d3d",
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=FG_DIM,
            lightcolor="#3d3d3d",
            darkcolor="#3d3d3d",
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", "#4d4d4d"), ("pressed", ACCENT)],
        )

    style.configure("TSeparator", background=BORDER)
    style.configure("Status.TLabel", background=BG, foreground=OK)

    style_scale(style)

    return style


def style_text(widget: tk.Text) -> None:
    widget.configure(
        bg=BG_LOG,
        fg="#d6d6d6",
        insertbackground=FG,
        selectbackground=ACCENT,
        selectforeground="#ffffff",
        highlightthickness=1,
        highlightbackground=BORDER,
        highlightcolor=BORDER,
        relief="flat",
        bd=0,
    )


def style_scale(style: ttk.Style) -> None:
    """Монохромный ползунок: светлый бегунок на почти чёрном жёлобе."""
    style.configure(
        "Mono.Horizontal.TScale",
        background="#c8c8c8",
        troughcolor="#101010",
        bordercolor=BORDER,
        lightcolor="#f0f0f0",
        darkcolor="#8a8a8a",
        sliderthickness=9,
    )
    style.map(
        "Mono.Horizontal.TScale",
        background=[("pressed", "#ffffff"), ("active", "#f0f0f0")],
    )


class _OptionBase(tk.Frame):
    """Тёмный чекбокс/радиокнопка: индикатор рисуем сами, без белых квадратов ttk."""

    def __init__(self, master, text: str, variable, command=None, bg: str = BG):
        super().__init__(master, bg=bg)
        self.var = variable
        self.command = command
        self._bg = bg
        self._fg = FG

        self._canvas = tk.Canvas(
            self, width=16, height=16, bg=bg, highlightthickness=0, bd=0, cursor="hand2"
        )
        self._canvas.pack(side="left", pady=(1, 0))
        self._label = tk.Label(
            self, text=text, bg=bg, fg=FG, cursor="hand2", anchor="w", justify="left"
        )
        self._label.pack(side="left", padx=(6, 0))

        for widget in (self._canvas, self._label):
            widget.bind("<Button-1>", self.invoke)
            widget.bind("<Enter>", lambda _e: self._label.configure(fg="#ffffff"))
            widget.bind("<Leave>", lambda _e: self._label.configure(fg=FG))

        try:
            variable.trace_add("write", lambda *_: self.refresh())
        except Exception:
            variable.trace("w", lambda *_: self.refresh())
        self.refresh()

    def invoke(self, _event=None):
        raise NotImplementedError

    def refresh(self) -> None:
        self._canvas.delete("all")
        self._paint()

    def _paint(self) -> None:
        raise NotImplementedError

    def _paint_check_box(self, on: bool) -> None:
        self._canvas.create_rectangle(
            1, 1, 15, 15,
            outline=ACCENT if on else "#6a6a6a",
            fill=ACCENT if on else BG_FIELD,
            width=1,
        )
        if on:
            self._canvas.create_line(
                3.5, 8.5, 6.5, 11.5, 12.5, 4.5,
                fill="#ffffff", width=2, capstyle="round", joinstyle="round",
            )


class DarkCheck(_OptionBase):
    def invoke(self, _event=None) -> str:
        self.var.set(not bool(self.var.get()))
        if self.command:
            self.command()
        return "break"

    def _paint(self) -> None:
        self._paint_check_box(bool(self.var.get()))


class DarkRadio(_OptionBase):
    def __init__(self, master, text, variable, value, command=None, bg: str = BG):
        self._value = value
        super().__init__(master, text, variable, command=command, bg=bg)

    def invoke(self, _event=None) -> str:
        self.var.set(self._value)
        if self.command:
            self.command()
        return "break"

    def _paint(self) -> None:
        on = self.var.get() == self._value
        self._canvas.create_oval(
            1, 1, 15, 15,
            outline=ACCENT if on else "#6a6a6a",
            fill=BG_FIELD,
            width=1,
        )
        if on:
            self._canvas.create_oval(5, 5, 11, 11, outline=ACCENT, fill=ACCENT)


def build_status_bar(root: tk.Misc):
    """Строка состояния как в Windows: серый фон, вдавленная рамка, две панели."""
    bar = tk.Frame(root, bg="SystemButtonFace", bd=1, relief="sunken")
    left = tk.Label(
        bar,
        bg="SystemButtonFace",
        fg="SystemWindowText",
        anchor="w",
        padx=8,
        pady=2,
    )
    left.pack(side="left", fill="x", expand=True)
    right = tk.Label(
        bar,
        bg="SystemButtonFace",
        fg="SystemWindowText",
        anchor="center",
        padx=10,
        pady=2,
        width=18,
        bd=1,
        relief="sunken",
    )
    right.pack(side="right", padx=(4, 2), pady=2)
    return bar, left, right

