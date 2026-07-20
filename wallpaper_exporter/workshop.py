from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".avi"}
INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_title(title: str, fallback: str = "Wallpaper") -> str:
    cleaned = INVALID_FILENAME.sub("_", title).strip().rstrip(". ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if cleaned.upper() in reserved:
        cleaned = f"_{cleaned}"
    return cleaned[:140].rstrip(". ") or fallback


def _steam_library_paths() -> list[Path]:
    roots = [Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")]
    result: list[Path] = []
    for steam in roots:
        if steam.is_dir() and steam not in result:
            result.append(steam)
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for raw in re.findall(r'"path"\s+"([^"]+)"', text):
            library = Path(raw.replace("\\\\", "\\"))
            if library.is_dir() and library not in result:
                result.append(library)
    return result


def discover_workshop_dir(configured: str = "") -> Path | None:
    if configured:
        path = Path(configured)
        if path.is_dir():
            return path
    for library in _steam_library_paths():
        candidate = library / "steamapps" / "workshop" / "content" / "431960"
        if candidate.is_dir():
            return candidate
    return None


def discover_engine_dir(configured: str = "") -> Path | None:
    if configured:
        path = Path(configured)
        if (path / "wallpaper64.exe").is_file() or (path / "wallpaper32.exe").is_file():
            return path
    for library in _steam_library_paths():
        candidate = library / "steamapps" / "common" / "wallpaper_engine"
        if (candidate / "wallpaper64.exe").is_file() or (candidate / "wallpaper32.exe").is_file():
            return candidate
    return None


@dataclass(frozen=True)
class WorkshopProject:
    workshop_id: str
    title: str
    project_type: str
    project_dir: str
    project_json: str
    content_path: str
    preview_path: str

    @property
    def safe_title(self) -> str:
        return sanitize_title(self.title, f"Wallpaper_{self.workshop_id}")

    @property
    def is_video(self) -> bool:
        return self.project_type == "video" and Path(self.content_path).is_file()

    @property
    def is_composited(self) -> bool:
        return self.project_type in {"scene", "web"}

    @property
    def is_direct_image(self) -> bool:
        return Path(self.content_path).suffix.lower() in IMAGE_SUFFIXES and Path(self.content_path).is_file()

    @property
    def searchable_name(self) -> str:
        return f"{self.title} {self.workshop_id} {self.project_type}".casefold()


def project_export_stem(destination: Path, project: WorkshopProject, extension: str, suffix: str = "") -> str:
    base = f"{project.safe_title}{suffix}"
    if (destination / f"{base}{extension}").exists():
        return f"{base}_{project.workshop_id}"
    return base


class WorkshopScanner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def scan(self) -> list[WorkshopProject]:
        projects: list[WorkshopProject] = []
        if not self.root.is_dir():
            return projects
        for directory in sorted((item for item in self.root.iterdir() if item.is_dir()), key=lambda item: item.name):
            projects.append(self._scan_one(directory))
        return projects

    def _scan_one(self, directory: Path) -> WorkshopProject:
        project_json = directory / "project.json"
        data = self._read_project_json(project_json)
        workshop_id = directory.name
        title = str(data.get("title") or f"Wallpaper_{workshop_id}")
        kind = str(data.get("type") or "").strip().lower()
        declared_file = str(data.get("file") or "")
        content = directory / declared_file if declared_file else Path()

        if kind == "scene":
            packed = directory / "scene.pkg"
            if packed.is_file():
                content = packed
        elif kind == "web" and not content.is_file():
            content = directory / "index.html"
        elif kind == "video" and not content.is_file():
            content = self._first_with_suffix(directory, VIDEO_SUFFIXES) or content

        if not kind:
            video = self._first_with_suffix(directory, VIDEO_SUFFIXES)
            image = self._first_with_suffix(directory, IMAGE_SUFFIXES, exclude_preview=True)
            if video:
                kind, content = "video", video
            elif (directory / "scene.pkg").is_file():
                kind, content = "scene", directory / "scene.pkg"
            elif (directory / "index.html").is_file():
                kind, content = "web", directory / "index.html"
            elif image:
                kind, content = "image", image
            else:
                kind = "unknown"

        preview = self._preview_path(directory, data)
        return WorkshopProject(
            workshop_id=workshop_id,
            title=title,
            project_type=kind,
            project_dir=str(directory),
            project_json=str(project_json) if project_json.is_file() else "",
            content_path=str(content) if content and str(content) != "." else "",
            preview_path=str(preview) if preview else "",
        )
    @staticmethod
    def _read_project_json(path: Path) -> dict:
        if not path.is_file():
            return {}
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                value = json.loads(path.read_text(encoding=encoding))
                return value if isinstance(value, dict) else {}
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
        return {}

    @staticmethod
    def _first_with_suffix(directory: Path, suffixes: set[str], exclude_preview: bool = False) -> Path | None:
        try:
            for item in directory.iterdir():
                if not item.is_file() or item.suffix.lower() not in suffixes:
                    continue
                if exclude_preview and item.stem.casefold().startswith("preview"):
                    continue
                return item
        except OSError:
            return None
        return None

    @staticmethod
    def _preview_path(directory: Path, data: dict) -> Path | None:
        declared = str(data.get("preview") or "")
        if declared and (directory / declared).is_file():
            return directory / declared
        for name in ("preview.jpg", "preview.png", "preview.gif"):
            path = directory / name
            if path.is_file():
                return path
        return None


def scan_project_from_source(source: str) -> WorkshopProject | None:
    path = Path(source)
    directory = path.parent
    if not directory.is_dir():
        normalized = source.replace("\\", "/")
        match = re.search(r"/431960/(\d+)/", normalized)
        if not match:
            return None
        workshop_id = match.group(1)
        suffix = path.suffix.lower()
        project_type = "video" if suffix in VIDEO_SUFFIXES else "scene" if suffix == ".pkg" else "unknown"
        return WorkshopProject(
            workshop_id=workshop_id,
            title=f"Workshop 项目 {workshop_id}（本地文件已不存在）",
            project_type=project_type,
            project_dir=str(directory),
            project_json="",
            content_path=source,
            preview_path="",
        )
    return WorkshopScanner(directory.parent)._scan_one(directory)


class WallpaperEngineController:
    def __init__(self, engine_dir: Path) -> None:
        self.engine_dir = engine_dir
        self.exe = engine_dir / "wallpaper64.exe"
        if not self.exe.is_file():
            self.exe = engine_dir / "wallpaper32.exe"
        self.config_path = engine_dir / "config.json"

    @property
    def available(self) -> bool:
        return self.exe.is_file()

    def current_wallpaper_file(self, monitor: str = "Monitor0") -> str:
        if not self.config_path.is_file():
            return ""
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
            selected = data["s"]["general"]["wallpaperconfig"]["selectedwallpapers"]
            item = selected.get(monitor) or next(iter(selected.values()))
            return str(item.get("file") or "")
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, StopIteration):
            return ""

    def apply_project(self, project: WorkshopProject, monitor: int = 0) -> None:
        source = project.project_json if project.project_json else project.content_path
        self.open_file(source, monitor)

    def next_wallpaper(self, monitor: int = 0) -> None:
        if not self.available:
            raise OSError("未找到 Wallpaper Engine 主程序。")
        self._run_async(["-control", "nextWallpaper", "-monitor", str(monitor)])

    def previous_wallpaper_file(self, monitor: str = "Monitor0") -> str:
        """Return the newest recent wallpaper that differs from the current one."""
        if not self.config_path.is_file():
            return ""
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
            general = data["s"]["general"]
            current = self.current_wallpaper_file(monitor).casefold()
            recent = general.get("wallpaperconfigrecent", [])
        except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError):
            return ""

        def paths(value):
            if isinstance(value, str):
                match = re.search(r"file=([^;}]*)", value)
                if match:
                    value = match.group(1).strip()
                if value and ("431960" in value or Path(value).suffix):
                    yield value
            elif isinstance(value, list):
                for child in value:
                    yield from paths(child)
            elif isinstance(value, dict):
                preferred = value.get("file")
                if isinstance(preferred, str):
                    yield preferred
                for key, child in value.items():
                    if key != "file":
                        yield from paths(child)

        for candidate in paths(recent):
            if candidate.casefold() != current and Path(candidate).exists():
                return candidate
        return ""

    def open_file(self, source: str, monitor: int = 0) -> None:
        if not self.available or not source:
            raise OSError("未找到 Wallpaper Engine 主程序或壁纸源文件。")
        path = Path(source)
        project_json = path.parent / "project.json"
        control_source = str(project_json) if project_json.is_file() else source
        if not Path(control_source).is_file():
            raise OSError("壁纸本地文件不存在，可能已经取消订阅；为避免空桌面，已停止切换。")
        self._run(["-control", "openWallpaper", "-file", control_source, "-monitor", str(monitor)])

    def play_in_window(self, project: WorkshopProject, width: int = 1280, height: int = 720) -> str:
        source = project.project_json if project.project_json else project.content_path
        if not self.available or not source:
            raise OSError("未找到 Wallpaper Engine 主程序或壁纸源文件。")
        window_name = f"SakuraSea-{project.workshop_id}"
        self._run_async([
            "-control", "openWallpaper", "-file", source,
            "-playInWindow", window_name, "-width", str(width), "-height", str(height),
        ])
        return window_name

    def bring_window_front(self, window_name: str) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.FindWindowW(None, window_name)
            if not hwnd:
                return False
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            return True
        except (AttributeError, OSError):
            return False

    def close_window(self, window_name: str) -> None:
        if not self.available or not window_name:
            return
        self._run_async(["-control", "closeWallpaper", "-location", window_name])

    def _run(self, arguments: Iterable[str]) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run(
            [str(self.exe), *arguments],
            check=False,
            timeout=15,
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            raise OSError(f"Wallpaper Engine 命令执行失败，退出代码 {completed.returncode}。")

    def _run_async(self, arguments: Iterable[str]) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            subprocess.Popen(
                [str(self.exe), *arguments],
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise OSError(f"Wallpaper Engine 命令启动失败：{exc}") from exc
