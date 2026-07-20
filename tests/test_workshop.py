from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from wallpaper_exporter.workshop import (
    WallpaperEngineController,
    WorkshopScanner,
    project_export_stem,
    sanitize_title,
    scan_project_from_source,
)


class WorkshopScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_project(self, workshop_id: str, data: dict) -> Path:
        directory = self.root / workshop_id
        directory.mkdir()
        (directory / "project.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return directory

    def test_scans_video_with_original_title_and_preview(self) -> None:
        directory = self.make_project("123", {"title": "角色：夏日/海边", "type": "video", "file": "动画.mp4", "preview": "preview.jpg"})
        (directory / "动画.mp4").write_bytes(b"video")
        Image.new("RGB", (320, 180)).save(directory / "preview.jpg")

        project = WorkshopScanner(self.root).scan()[0]

        self.assertEqual(project.title, "角色：夏日/海边")
        self.assertEqual(project.safe_title, "角色：夏日_海边")
        self.assertTrue(project.is_video)
        self.assertTrue(project.preview_path.endswith("preview.jpg"))

    def test_scene_uses_packed_content_and_project_json_for_control(self) -> None:
        directory = self.make_project("456", {"title": "场景壁纸", "type": "scene", "file": "scene.json"})
        (directory / "scene.pkg").write_bytes(b"PKGV0001")

        project = WorkshopScanner(self.root).scan()[0]

        self.assertEqual(project.project_type, "scene")
        self.assertTrue(project.content_path.endswith("scene.pkg"))
        self.assertTrue(project.project_json.endswith("project.json"))
        self.assertTrue(project.is_composited)

    def test_missing_type_is_inferred_from_video(self) -> None:
        directory = self.make_project("789", {"title": "旧项目"})
        (directory / "source.mp4").write_bytes(b"video")

        project = WorkshopScanner(self.root).scan()[0]

        self.assertEqual(project.project_type, "video")
        self.assertEqual(Path(project.content_path).name, "source.mp4")

    def test_invalid_windows_names_are_sanitized(self) -> None:
        self.assertEqual(sanitize_title('A<B>:C/D\\E|F?G*.'), "A_B__C_D_E_F_G_")
        self.assertEqual(sanitize_title("CON"), "_CON")

    def test_reads_current_wallpaper_from_engine_config(self) -> None:
        engine = self.root / "engine"
        engine.mkdir()
        (engine / "wallpaper64.exe").write_bytes(b"")
        value = "C:/Steam/steamapps/workshop/content/431960/123/scene.pkg"
        config = {"s": {"general": {"wallpaperconfig": {"selectedwallpapers": {"Monitor0": {"file": value}}}}}}
        (engine / "config.json").write_text(json.dumps(config), encoding="utf-8")

        controller = WallpaperEngineController(engine)

        self.assertEqual(controller.current_wallpaper_file(), value)

    def test_duplicate_original_title_adds_workshop_id(self) -> None:
        directory = self.make_project("123", {"title": "同名壁纸", "type": "video", "file": "a.mp4"})
        (directory / "a.mp4").write_bytes(b"video")
        project = WorkshopScanner(self.root).scan()[0]
        export = self.root / "export"
        export.mkdir()
        (export / "同名壁纸.png").write_bytes(b"existing")

        self.assertEqual(project_export_stem(export, project, ".png"), "同名壁纸_123")

    def test_scene_control_uses_project_json_and_monitor(self) -> None:
        directory = self.make_project("456", {"title": "场景", "type": "scene", "file": "scene.json"})
        (directory / "scene.pkg").write_bytes(b"PKGV0001")
        project = WorkshopScanner(self.root).scan()[0]
        engine = self.root / "engine"
        engine.mkdir()
        (engine / "wallpaper64.exe").write_bytes(b"")
        controller = WallpaperEngineController(engine)
        captured = []
        controller._run = lambda arguments: captured.append(list(arguments))
        controller._run_async = lambda arguments: captured.append(list(arguments))

        controller.apply_project(project, monitor=0)

        self.assertEqual(captured[0][:3], ["-control", "openWallpaper", "-file"])
        self.assertEqual(captured[0][3], project.project_json)
        self.assertEqual(captured[0][-2:], ["-monitor", "0"])

        window_name = controller.play_in_window(project)
        controller.close_window(window_name)
        self.assertNotIn("-activate", captured[1])
        self.assertEqual(captured[2], ["-control", "closeWallpaper", "-location", "SakuraSea-456"])

    def test_previous_wallpaper_uses_recent_entry_different_from_current(self) -> None:
        engine = self.root / "engine"
        engine.mkdir()
        (engine / "wallpaper64.exe").write_bytes(b"")
        current = self.root / "current" / "project.json"
        previous = self.root / "previous" / "project.json"
        current.parent.mkdir()
        previous.parent.mkdir()
        current.write_text("{}", encoding="utf-8")
        previous.write_text("{}", encoding="utf-8")
        data = {"s": {"general": {
            "wallpaperconfig": {"selectedwallpapers": {"Monitor0": {"file": str(current)}}},
            "wallpaperconfigrecent": [{"file": str(current)}, {"file": str(previous)}],
        }}}
        (engine / "config.json").write_text(json.dumps(data), encoding="utf-8")

        controller = WallpaperEngineController(engine)

        self.assertEqual(controller.previous_wallpaper_file(), str(previous))

    def test_open_scene_source_normalizes_to_project_json(self) -> None:
        directory = self.make_project("901", {"title": "Scene", "type": "scene", "file": "scene.json"})
        scene = directory / "scene.pkg"
        scene.write_bytes(b"PKGV0001")
        engine = self.root / "engine"
        engine.mkdir()
        (engine / "wallpaper64.exe").write_bytes(b"")
        controller = WallpaperEngineController(engine)
        captured = []
        controller._run = lambda arguments: captured.append(list(arguments))

        controller.open_file(str(scene))

        self.assertEqual(captured[0][3], str(directory / "project.json"))

    def test_scans_local_project_folder_without_numeric_workshop_id(self) -> None:
        directory = self.make_project("My Local Wallpaper", {"title": "本地壁纸", "type": "video", "file": "wall.mp4"})
        video = directory / "wall.mp4"
        video.write_bytes(b"video")

        project = scan_project_from_source(str(video))

        self.assertIsNotNone(project)
        self.assertEqual(project.title, "本地壁纸")

    def test_missing_workshop_source_keeps_id_for_management(self) -> None:
        source = self.root / "431960" / "778899" / "missing.mp4"

        project = scan_project_from_source(str(source))

        self.assertIsNotNone(project)
        self.assertEqual(project.workshop_id, "778899")
        self.assertIn("本地文件已不存在", project.title)

    def test_open_missing_source_stops_before_wallpaper_command(self) -> None:
        engine = self.root / "engine"
        engine.mkdir()
        (engine / "wallpaper64.exe").write_bytes(b"")
        controller = WallpaperEngineController(engine)
        called = []
        controller._run = lambda arguments: called.append(arguments)

        with self.assertRaises(OSError):
            controller.open_file(str(self.root / "missing" / "scene.pkg"))

        self.assertEqual(called, [])


if __name__ == "__main__":
    unittest.main()
