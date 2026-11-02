"""Отправка нажатий клавиш через SendInput (scan codes).

Scan-коды, а не виртуальные клавиши: так нажатия корректно видят игры,
которые читают DirectInput/Raw Input (в том числе Roblox).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Dict, Optional, Set, Tuple

_user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC = 0


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


# --- имена клавиш -> виртуальные коды ---
NAMED_VK: Dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "printscreen": 0x2C,
    "insert": 0x2D,
    "delete": 0x2E,
    "numlock": 0x90,
    "scrolllock": 0x91,
    "semicolon": 0xBA,
    "equals": 0xBB,
    "comma": 0xBC,
    "minus": 0xBD,
    "period": 0xBE,
    "slash": 0xBF,
    "grave": 0xC0,
    "bracketleft": 0xDB,
    "backslash": 0xDC,
    "bracketright": 0xDD,
    "quote": 0xDE,
}
for _i in range(1, 25):
    NAMED_VK[f"f{_i}"] = 0x6F + _i

# клавиши, которым нужен флаг EXTENDEDKEY
EXTENDED_VK: Set[int] = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,
    0x2C, 0x2D, 0x2E, 0x90, 0x6F, 0x5B, 0x5C, 0x5D, 0xA3, 0xA5,
}

_cache: Dict[str, Optional[Tuple[int, bool]]] = {}


def key_to_vk(key: str) -> Optional[int]:
    """'a' / 'space' / 'left' / 'f8' -> виртуальный код клавиши."""
    if not key:
        return None
    name = key.strip().lower()
    vk = NAMED_VK.get(name)
    if vk is not None:
        return vk
    if len(name) == 1:
        return _char_to_vk(name)
    return None


def resolve_key(key: str) -> Optional[Tuple[int, bool]]:
    """'a' / 'space' / 'left' -> (scan code, extended)."""
    if not key:
        return None
    name = key.strip().lower()
    if name in _cache:
        return _cache[name]

    vk = key_to_vk(name)
    result: Optional[Tuple[int, bool]] = None
    if vk:
        scan = _user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)
        if scan:
            result = (int(scan), vk in EXTENDED_VK)
    _cache[name] = result
    return result


def _char_to_vk(ch: str) -> Optional[int]:
    """Буквы/цифры — напрямую; остальное — через раскладку."""
    if "a" <= ch <= "z":
        return ord(ch.upper())
    if "0" <= ch <= "9":
        return ord(ch)
    try:
        res = _user32.VkKeyScanW(ctypes.c_wchar(ch))
    except Exception:
        return None
    if res == -1:
        return None
    vk = res & 0xFF
    return vk if vk else None


class KeySender:
    """Нажатия клавиш. Держит список зажатых клавиш, чтобы всё отпустить при стопе."""

    def __init__(self):
        self._held: Set[str] = set()
        self._sent = 0

    @staticmethod
    def _send(scan: int, extended: bool, keyup: bool) -> bool:
        flags = KEYEVENTF_SCANCODE
        if extended:
            flags |= KEYEVENTF_EXTENDEDKEY
        if keyup:
            flags |= KEYEVENTF_KEYUP
        inp = INPUT(
            type=INPUT_KEYBOARD,
            u=_INPUTUNION(
                ki=KEYBDINPUT(wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None)
            ),
        )
        sent = _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
        return sent == 1

    def key_down(self, key: str) -> bool:
        resolved = resolve_key(key)
        if resolved is None:
            return False
        scan, extended = resolved
        ok = self._send(scan, extended, keyup=False)
        if ok:
            self._held.add(key.strip().lower())
            self._sent += 1
        return ok

    def key_down_many(self, keys: list) -> int:
        """Нажимает несколько клавиш одним вызовом SendInput — без зазора.

        Двойные ноты (аккорды) должны попадать в один кадр игры; отдельные
        вызовы SendInput теоретически могут разъехаться по времени.
        """
        events = []
        pressed = []
        for key in keys:
            resolved = resolve_key(key)
            if resolved is None:
                continue
            scan, extended = resolved
            flags = KEYEVENTF_SCANCODE
            if extended:
                flags |= KEYEVENTF_EXTENDEDKEY
            events.append(
                INPUT(
                    type=INPUT_KEYBOARD,
                    u=_INPUTUNION(
                        ki=KEYBDINPUT(
                            wVk=0, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=None
                        )
                    ),
                )
            )
            pressed.append(key.strip().lower())

        if not events:
            return 0

        array = (INPUT * len(events))(*events)
        sent = _user32.SendInput(len(events), array, ctypes.sizeof(INPUT))
        if sent:
            self._held.update(pressed[:sent])
            self._sent += sent
        return int(sent)

    def key_up(self, key: str) -> bool:
        resolved = resolve_key(key)
        if resolved is None:
            return False
        scan, extended = resolved
        ok = self._send(scan, extended, keyup=True)
        self._held.discard(key.strip().lower())
        return ok

    def tap(self, key: str, hold_ms: int = 30) -> bool:
        if not self.key_down(key):
            return False
        time.sleep(max(1, hold_ms) / 1000.0)
        self.key_up(key)
        return True

    def release_all(self) -> None:
        for key in list(self._held):
            self.key_up(key)
        self._held.clear()

    @property
    def sent_count(self) -> int:
        return self._sent
