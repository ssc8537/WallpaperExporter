from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from PIL import ImageGrab

from .core import WallpaperCandidate, WallpaperService


SW_HIDE = 0
SW_SHOW = 5
VK_LWIN = 0x5B
VK_D = 0x44
KEYEVENTF_KEYUP = 0x0002


def enable_per_monitor_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass


def capture_rendered_desktop(service: WallpaperService) -> WallpaperCandidate | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    hidden = _visible_shell_windows(user32)
    _show_desktop(user32)
    try:
        time.sleep(0.45)
        for hwnd in hidden:
            user32.ShowWindow(hwnd, SW_HIDE)
        time.sleep(0.25)
        image = ImageGrab.grab(all_screens=False).convert("RGB")
        path = service.store.data_dir / "current_rendered_desktop.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path, "PNG", compress_level=1)
        return service.inspect_image(path, "Wallpaper Engine 桌面渲染帧", is_current=True)
    except OSError:
        return None
    finally:
        for hwnd in hidden:
            user32.ShowWindow(hwnd, SW_SHOW)
        time.sleep(0.15)
        _show_desktop(user32)


def _show_desktop(user32) -> None:
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(VK_D, 0, 0, 0)
    user32.keybd_event(VK_D, 0, KEYEVENTF_KEYUP, 0)
    user32.keybd_event(VK_LWIN, 0, KEYEVENTF_KEYUP, 0)


def _visible_shell_windows(user32) -> list[int]:
    handles: list[int] = []
    for class_name in ("Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
        hwnd = user32.FindWindowW(class_name, None)
        if hwnd and user32.IsWindowVisible(hwnd):
            handles.append(hwnd)

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def callback(hwnd, _lparam):
        def_view = user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
        if def_view:
            list_view = user32.FindWindowExW(def_view, None, "SysListView32", None)
            target = list_view or def_view
            if target and user32.IsWindowVisible(target):
                handles.append(target)
        return True

    user32.EnumWindows(callback, 0)
    return list(dict.fromkeys(handles))
