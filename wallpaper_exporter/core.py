from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError


APP_NAME = "WallpaperExporter"
CURRENT_SNAPSHOT_NAME = "WallpaperEngineLockOverride.jpg"
THEME_NAMES = (
    CURRENT_SNAPSHOT_NAME,
    "WallpaperEngineOverride.jpg",
    "WallpaperEngineBackupWallpaper.jpg",
    "TranscodedWallpaper",
)


def default_themes_dir() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Themes"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Themes"


def default_export_dir() -> Path:
    pictures = Path.home() / "Pictures"
    return pictures / "Wallpaper Engine 导出"


def default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / "AppData" / "Local"
    return root / APP_NAME


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_size(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.2f} {unit}"
        value /= 1024
    return f"{byte_count} B"


def resolution_label(width: int, height: int) -> str:
    longest = max(width, height)
    if longest >= 3840:
        level = "4K+"
    elif longest >= 2560:
        level = "2K+"
    elif longest >= 1920:
        level = "1080p+"
    else:
        level = "低于 1080p"
    return f"{width} × {height}  ·  {level}"


@dataclass(frozen=True)
class WallpaperCandidate:
    path: str
    source_name: str
    width: int
    height: int
    image_format: str
    file_size: int
    modified_at: str
    content_hash: str
    discovered_at: str
    is_current: bool = False

    @property
    def pixel_count(self) -> int:
        return self.width * self.height

    @property
    def extension(self) -> str:
        return ".jpg" if self.image_format.upper() in {"JPEG", "JPG"} else f".{self.image_format.lower()}"

    @property
    def resolution(self) -> str:
        return resolution_label(self.width, self.height)

    @property
    def size_text(self) -> str:
        return display_size(self.file_size)


@dataclass(frozen=True)
class ExportRecord:
    source_path: str
    target_path: str
    content_hash: str
    width: int
    height: int
    image_format: str
    discovered_at: str
    exported_at: str
    status: str
    message: str = ""
    original_title: str = ""
    workshop_id: str = ""
    project_path: str = ""


class ConfigStore:
    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = data_dir or default_data_dir()
        self.config_path = self.data_dir / "config.json"
        self.history_path = self.data_dir / "history.json"

    def load_config(self) -> dict:
        default = {
            "export_dir": str(default_export_dir()),
            "themes_dir": str(default_themes_dir()),
            "monitor_enabled": False,
            "monitor_user_set": False,
            "monitor_seconds": 5,
            "workshop_dir": "",
            "wallpaper_engine_dir": "",
            "video_image_format": "PNG",
            "hotkey_save": "Ctrl+Alt+S",
            "hotkey_next": "Ctrl+Alt+Right",
            "hotkey_previous": "Ctrl+Alt+Left",
        }
        loaded = self._read_json(self.config_path, {})
        if isinstance(loaded, dict):
            default.update({k: v for k, v in loaded.items() if k in default})
        return default

    def save_config(self, config: dict) -> None:
        self._write_json(self.config_path, config)

    def load_history(self) -> list[ExportRecord]:
        raw = self._read_json(self.history_path, [])
        records: list[ExportRecord] = []
        if not isinstance(raw, list):
            return records
        for item in raw:
            try:
                records.append(ExportRecord(**item))
            except (TypeError, ValueError):
                continue
        return records

    def save_history(self, records: Iterable[ExportRecord]) -> None:
        self._write_json(self.history_path, [asdict(record) for record in records])

    def _read_json(self, path: Path, fallback):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return fallback

    def _write_json(self, path: Path, value) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)


class WallpaperService:
    def __init__(self, store: ConfigStore | None = None) -> None:
        self.store = store or ConfigStore()
        self.config = self.store.load_config()
        self.history = self.store.load_history()

    @property
    def themes_dir(self) -> Path:
        return Path(self.config["themes_dir"])

    @property
    def export_dir(self) -> Path:
        return Path(self.config["export_dir"])

    def update_config(self, **changes) -> None:
        self.config.update(changes)
        self.store.save_config(self.config)

    def inspect_image(self, path: Path, source_name: str, is_current: bool = False) -> WallpaperCandidate | None:
        if not path.is_file():
            return None
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
                image_format = (image.format or "").upper()
        except (OSError, ValueError, UnidentifiedImageError):
            return None
        if image_format not in {"JPEG", "PNG"} or width < 1 or height < 1:
            return None
        stat = path.stat()
        return WallpaperCandidate(
            path=str(path),
            source_name=source_name,
            width=width,
            height=height,
            image_format=image_format,
            file_size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            content_hash=sha256_file(path),
            discovered_at=iso_now(),
            is_current=is_current,
        )

    def current_wallpaper(self) -> WallpaperCandidate | None:
        primary_names = (CURRENT_SNAPSHOT_NAME, "WallpaperEngineOverride.jpg", "TranscodedWallpaper")
        candidates = []
        for name in primary_names:
            candidate = self.inspect_image(self.themes_dir / name, self._source_label(name), is_current=True)
            if candidate:
                candidates.append(candidate)
        return max(candidates, key=lambda item: item.modified_at, default=None)

    def scan_theme_images(self) -> list[WallpaperCandidate]:
        paths: list[tuple[Path, str, bool]] = []
        for name in THEME_NAMES:
            paths.append((self.themes_dir / name, self._source_label(name), name == CURRENT_SNAPSHOT_NAME))
        cached_dir = self.themes_dir / "CachedFiles"
        if cached_dir.is_dir():
            for path in cached_dir.iterdir():
                if path.is_file():
                    paths.append((path, "Windows 主题缓存", False))

        candidates: list[WallpaperCandidate] = []
        seen_paths: set[str] = set()
        for path, label, is_current in paths:
            normalized = str(path.resolve(strict=False)).casefold()
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            candidate = self.inspect_image(path, label, is_current)
            if candidate:
                candidates.append(candidate)
        return sorted(candidates, key=lambda item: (not item.is_current, -item.pixel_count, item.path.casefold()))

    def best_per_exact_image(self, candidates: Iterable[WallpaperCandidate]) -> list[WallpaperCandidate]:
        """Exact duplicates are represented once; visual guesses never discard a source."""
        best: dict[str, WallpaperCandidate] = {}
        for item in candidates:
            existing = best.get(item.content_hash)
            if existing is None or item.pixel_count > existing.pixel_count:
                best[item.content_hash] = item
        return sorted(best.values(), key=lambda item: (not item.is_current, -item.pixel_count, item.path.casefold()))

    def previous_export(self, content_hash: str, destination: Path | None = None) -> ExportRecord | None:
        destination_key = None
        if destination is not None:
            destination_key = str(destination.resolve(strict=False)).casefold()
        for record in reversed(self.history):
            if record.content_hash != content_hash or record.status != "success":
                continue
            target = Path(record.target_path)
            if destination_key is not None:
                parent_key = str(target.parent.resolve(strict=False)).casefold()
                if parent_key != destination_key:
                    continue
            if target.is_file():
                return record
        return None

    def has_exported_hash(self, content_hash: str, destination: Path | None = None) -> bool:
        if self.previous_export(content_hash, destination) is not None:
            return True
        return bool(destination and self.find_existing_file(content_hash, destination))

    def find_existing_file(
        self,
        content_hash: str,
        destination: Path,
        file_size: int | None = None,
        exclude: Path | None = None,
    ) -> Path | None:
        """Find matching content even when history was cleared or came from an older version."""
        if not destination.is_dir():
            return None
        try:
            entries = destination.iterdir()
        except OSError:
            return None
        for path in entries:
            try:
                if exclude is not None and path.resolve(strict=False) == exclude.resolve(strict=False):
                    continue
                if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                    continue
                if file_size is not None and path.stat().st_size != file_size:
                    continue
                if sha256_file(path) == content_hash:
                    return path
            except OSError:
                continue
        return None

    def export_candidate(
        self,
        candidate: WallpaperCandidate,
        destination: Path | None = None,
        preferred_stem: str | None = None,
        original_title: str = "",
        workshop_id: str = "",
        project_path: str = "",
    ) -> ExportRecord:
        destination = destination or self.export_dir
        destination.mkdir(parents=True, exist_ok=True)

        previous = self.previous_export(candidate.content_hash, destination)
        existing_file = None if previous else self.find_existing_file(candidate.content_hash, destination, candidate.file_size)
        if previous is not None or existing_file is not None:
            previous_target = previous.target_path if previous else str(existing_file)
            record = ExportRecord(
                source_path=candidate.path,
                target_path=previous_target,
                content_hash=candidate.content_hash,
                width=candidate.width,
                height=candidate.height,
                image_format=candidate.image_format,
                discovered_at=candidate.discovered_at,
                exported_at=iso_now(),
                status="duplicate",
                message="图片内容与历史导出完全相同，已跳过。",
                original_title=original_title,
                workshop_id=workshop_id,
                project_path=project_path,
            )
            self._append_history(record)
            return record

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        prefix = preferred_stem or ("当前壁纸" if candidate.is_current else "壁纸")
        target = self._unique_target(destination, prefix if preferred_stem else f"{prefix}_{timestamp}", candidate.extension)
        temp_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            shutil.copyfile(candidate.path, temp_path)
            exported = self.inspect_image(temp_path, "导出校验")
            if exported is None:
                raise OSError("复制后的文件不是有效的 JPG/PNG 图片")
            if exported.content_hash != candidate.content_hash:
                raise OSError("复制校验失败：目标内容与源文件不一致")
            os.replace(temp_path, target)
            record = ExportRecord(
                source_path=candidate.path,
                target_path=str(target),
                content_hash=candidate.content_hash,
                width=candidate.width,
                height=candidate.height,
                image_format=candidate.image_format,
                discovered_at=candidate.discovered_at,
                exported_at=iso_now(),
                status="success",
                message="已保留原格式与原始分辨率。",
                original_title=original_title,
                workshop_id=workshop_id,
                project_path=project_path,
            )
        except OSError as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            record = ExportRecord(
                source_path=candidate.path,
                target_path=str(target),
                content_hash=candidate.content_hash,
                width=candidate.width,
                height=candidate.height,
                image_format=candidate.image_format,
                discovered_at=candidate.discovered_at,
                exported_at=iso_now(),
                status="failed",
                message=str(exc),
                original_title=original_title,
                workshop_id=workshop_id,
                project_path=project_path,
            )
        self._append_history(record)
        return record

    def export_new_current(self) -> ExportRecord | None:
        candidate = self.current_wallpaper()
        if candidate is None or self.has_exported_hash(candidate.content_hash, self.export_dir):
            return None
        return self.export_candidate(candidate)

    def export_many(self, candidates: Iterable[WallpaperCandidate], destination: Path | None = None) -> list[ExportRecord]:
        return [self.export_candidate(item, destination) for item in self.best_per_exact_image(candidates)]

    def clear_history_records(self) -> None:
        self.history.clear()
        self.store.save_history(self.history)

    def register_external_export(
        self,
        source_path: str,
        target_path: Path,
        width: int,
        height: int,
        image_format: str,
        original_title: str = "",
        workshop_id: str = "",
        project_path: str = "",
        message: str = "由视频原始解码帧生成。",
    ) -> ExportRecord:
        content_hash = sha256_file(target_path)
        record = ExportRecord(
            source_path=source_path,
            target_path=str(target_path),
            content_hash=content_hash,
            width=width,
            height=height,
            image_format=image_format,
            discovered_at=iso_now(),
            exported_at=iso_now(),
            status="success",
            message=message,
            original_title=original_title,
            workshop_id=workshop_id,
            project_path=project_path,
        )
        self._append_history(record)
        return record

    def unique_target(self, destination: Path, stem: str, extension: str) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        return self._unique_target(destination, stem, extension)

    def _append_history(self, record: ExportRecord) -> None:
        self.history.append(record)
        self.store.save_history(self.history)

    @staticmethod
    def _unique_target(destination: Path, stem: str, extension: str) -> Path:
        candidate = destination / f"{stem}{extension}"
        number = 2
        while candidate.exists():
            candidate = destination / f"{stem}_{number}{extension}"
            number += 1
        return candidate

    @staticmethod
    def _source_label(name: str) -> str:
        labels = {
            CURRENT_SNAPSHOT_NAME: "当前 Wallpaper Engine 快照",
            "WallpaperEngineOverride.jpg": "Wallpaper Engine 桌面覆盖图",
            "WallpaperEngineBackupWallpaper.jpg": "Wallpaper Engine 备用桌面图",
            "TranscodedWallpaper": "Windows 转码桌面图",
        }
        return labels.get(name, name)
