from __future__ import annotations

import unittest

from wallpaper_exporter.hotkeys import MOD_ALT, MOD_CONTROL, GlobalHotkeyManager


class GlobalHotkeyTests(unittest.TestCase):
    def test_parses_default_save_and_arrow_shortcuts(self) -> None:
        modifiers, key = GlobalHotkeyManager._parse("Ctrl+Alt+S")
        self.assertEqual(modifiers, MOD_CONTROL | MOD_ALT)
        self.assertEqual(key, ord("S"))

        modifiers, key = GlobalHotkeyManager._parse("Ctrl+Alt+Right")
        self.assertEqual(modifiers, MOD_CONTROL | MOD_ALT)
        self.assertEqual(key, 0x27)

    def test_parses_escape_for_temporary_preview_close(self) -> None:
        self.assertEqual(GlobalHotkeyManager._parse("Esc"), (0, 0x1B))


if __name__ == "__main__":
    unittest.main()
