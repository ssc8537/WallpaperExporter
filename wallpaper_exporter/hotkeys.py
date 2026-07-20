from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal


WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000


class GlobalHotkeyManager(QObject, QAbstractNativeEventFilter):
    activated = Signal(str)

    def __init__(self, app, parent=None) -> None:
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self.app = app
        self._ids: dict[int, str] = {}
        self._next_id = 0xA510
        app.installNativeEventFilter(self)

    @property
    def available(self) -> bool:
        return sys.platform == "win32"

    def register(self, action: str, sequence: str) -> bool:
        self.unregister(action)
        parsed = self._parse(sequence)
        if not self.available or parsed is None:
            return False
        modifiers, virtual_key = parsed
        hotkey_id = self._next_id
        self._next_id += 1
        if not ctypes.windll.user32.RegisterHotKey(None, hotkey_id, modifiers | MOD_NOREPEAT, virtual_key):
            return False
        self._ids[hotkey_id] = action
        return True

    def unregister(self, action: str) -> None:
        for hotkey_id, name in list(self._ids.items()):
            if name == action:
                if self.available:
                    ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
                self._ids.pop(hotkey_id, None)

    def clear(self) -> None:
        for action in set(self._ids.values()):
            self.unregister(action)

    def nativeEventFilter(self, event_type, message):
        if self.available and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                action = self._ids.get(int(msg.wParam))
                if action:
                    self.activated.emit(action)
                    return True, 0
        return False, 0

    @staticmethod
    def _parse(sequence: str) -> tuple[int, int] | None:
        pieces = [piece.strip() for piece in sequence.replace("Meta", "Win").split("+") if piece.strip()]
        if not pieces:
            return None
        modifiers = 0
        for piece in pieces[:-1]:
            modifiers |= {
                "ctrl": MOD_CONTROL,
                "control": MOD_CONTROL,
                "alt": MOD_ALT,
                "shift": MOD_SHIFT,
                "win": MOD_WIN,
            }.get(piece.casefold(), 0)
        key = pieces[-1]
        names = {
            "Left": 0x25, "Up": 0x26, "Right": 0x27, "Down": 0x28,
            "Esc": 0x1B, "Escape": 0x1B, "Space": 0x20,
            "Home": 0x24, "End": 0x23, "PageUp": 0x21, "PageDown": 0x22,
        }
        virtual_key = names.get(key)
        if virtual_key is None and len(key) == 1:
            virtual_key = ord(key.upper())
        if virtual_key is None and key.upper().startswith("F") and key[1:].isdigit():
            number = int(key[1:])
            if 1 <= number <= 24:
                virtual_key = 0x6F + number
        if virtual_key is None:
            return None
        return modifiers, virtual_key

    def close(self) -> None:
        self.clear()
        self.app.removeNativeEventFilter(self)

