"""Глобальные горячие клавиши через RegisterHotKey (без внешних библиотек)."""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Dict, Optional, Tuple

from .keys import key_to_vk

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_MODS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "alt": MOD_ALT,
    "menu": MOD_ALT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}


def parse_hotkey(combo: str) -> Optional[Tuple[int, int]]:
    """'ctrl+shift+s' -> (modifiers, virtual key). None, если не разобрать."""
    if not combo:
        return None
    parts = [p.strip() for p in combo.split("+") if p.strip()]
    if not parts:
        return None
    mods = 0
    for part in parts[:-1]:
        mod = _MODS.get(part.lower())
        if mod is None:
            return None
        mods |= mod
    vk = key_to_vk(parts[-1])
    if not vk:
        return None
    return mods, vk


class HotkeyManager:
    """Регистрирует хоткеи в отдельном потоке и отдаёт события в callback."""

    def __init__(
        self,
        bindings: Dict[str, str],
        on_hotkey: Callable[[str], None],
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.bindings = dict(bindings)
        self.on_hotkey = on_hotkey
        self.on_error = on_error
        self._thread: Optional[threading.Thread] = None
        self._tid: Optional[int] = None
        self._running = threading.Event()
        self._ids: Dict[int, str] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="fnfbot-hotkeys", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._tid:
            _user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=1.0)
        self._thread = None

    def rebind(self, bindings: Dict[str, str]) -> None:
        self.stop()
        self.bindings = dict(bindings)
        self.start()

    # --- поток ---
    def _run(self) -> None:
        self._tid = int(_kernel32.GetCurrentThreadId())
        self._running.set()
        hotkey_id = 1
        for action, combo in self.bindings.items():
            parsed = parse_hotkey(combo)
            if parsed is None:
                self._error(f"Неверный формат горячей клавиши: «{combo}» ({action})")
                continue
            mods, vk = parsed
            if not _user32.RegisterHotKey(None, hotkey_id, mods, vk):
                self._error(
                    f"Клавиша {combo} занята другой программой — выберите другую"
                )
                continue
            self._ids[hotkey_id] = action
            hotkey_id += 1

        msg = wintypes.MSG()
        try:
            while True:
                ret = _user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if ret == 0 or ret == -1:
                    break
                if msg.message == WM_HOTKEY:
                    action = self._ids.get(int(msg.wParam))
                    if action:
                        try:
                            self.on_hotkey(action)
                        except Exception:
                            pass
        finally:
            for hid in list(self._ids):
                _user32.UnregisterHotKey(None, hid)
            self._ids.clear()

    def _error(self, text: str) -> None:
        if self.on_error:
            try:
                self.on_error(text)
            except Exception:
                pass
