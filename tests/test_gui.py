from __future__ import annotations

import os
import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

from wallpaper_exporter.app import MainWindow
from wallpaper_exporter.core import ConfigStore, WallpaperService
from wallpaper_exporter.workshop_ui import thumbnail_pixmap
from wallpaper_exporter.workshop import WorkshopProject
from PySide6.QtCore import QSize


class GuiSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.themes = self.root / "Themes"
        self.themes.mkdir()
        self.workshop = self.root / "Workshop"
        self.workshop.mkdir()
        project_dir = self.workshop / "123456"
        project_dir.mkdir()
        (project_dir / "project.json").write_text(
            json.dumps({"title": "原始壁纸名称", "type": "scene", "file": "scene.json"}, ensure_ascii=False),
            encoding="utf-8",
        )
        (project_dir / "scene.pkg").write_bytes(b"PKGV0001")
        Image.new("RGB", (400, 400), (120, 160, 220)).save(project_dir / "preview.jpg")
        self.engine = self.root / "engine"
        self.engine.mkdir()
        (self.engine / "wallpaper64.exe").write_bytes(b"")
        engine_config = {
            "s": {"general": {"wallpaperconfig": {"selectedwallpapers": {
                "Monitor0": {"file": str(project_dir / "scene.pkg")}
            }}}}
        }
        (self.engine / "config.json").write_text(json.dumps(engine_config), encoding="utf-8")
        Image.new("RGB", (2560, 1440), (169, 221, 242)).save(
            self.themes / "WallpaperEngineLockOverride.jpg", format="JPEG", quality=95
        )
        self.service = WallpaperService(ConfigStore(self.root / "Data"))
        self.service.update_config(
            themes_dir=str(self.themes),
            export_dir=str(self.root / "Export"),
            workshop_dir=str(self.workshop),
            wallpaper_engine_dir=str(self.engine),
            monitor_enabled=False,
            monitor_user_set=True,
        )

    def tearDown(self) -> None:
        window = getattr(self, "window", None)
        if window is not None:
            window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_main_window_renders_current_wallpaper_and_pages(self) -> None:
        self.window = MainWindow(self.service)
        self.window.show()
        self.window.refresh_all()
        self.app.processEvents()

        self.assertIsNotNone(self.window.current_candidate)
        self.assertEqual(self.window.current_candidate.width, 2560)
        self.assertEqual(len(self.window.batch_page.candidates), 1)
        self.assertEqual(self.window.stack.count(), 6)
        self.assertEqual(self.window.size().width(), 900)
        self.assertEqual(self.window.size().height(), 585)
        self.assertGreaterEqual(self.window.minimumWidth(), 820)

    def test_workshop_grid_is_responsive_and_preview_is_not_cropped(self) -> None:
        self.window = MainWindow(self.service)
        self.window.show()
        self.window.refresh_all()
        self.window.nav.setCurrentRow(1)
        self.app.processEvents()
        compact_columns = self.window.workshop_page._layout_metrics()[0]
        preview_path = self.window.workshop_projects[0].preview_path
        pixmap = thumbnail_pixmap(preview_path, QSize(200, 100))

        self.window.resize(1400, 800)
        self.app.processEvents()
        wide_columns = self.window.workshop_page._layout_metrics()[0]
        self.window.workshop_page.change_zoom(2)
        large_columns = self.window.workshop_page._layout_metrics()[0]

        self.assertGreaterEqual(compact_columns, 6)
        self.assertGreater(wide_columns, compact_columns)
        self.assertLess(large_columns, wide_columns)
        self.assertEqual((pixmap.width(), pixmap.height()), (100, 100))

        many = [
            WorkshopProject(str(index), f"项目 {index}", "unknown", "", "", "", "")
            for index in range(60)
        ]
        self.window.resize(900, 585)
        self.window.workshop_page.change_zoom(-2)
        self.window.workshop_page.set_projects(many)
        self.app.processEvents()
        bar = self.window.workshop_page.scroll.verticalScrollBar()
        self.assertGreater(bar.maximum(), 0)
        self.window.workshop_page._auto_load_at_bottom(int(bar.maximum() * 0.69))
        self.assertEqual(self.window.workshop_page.visible_count, 48)
        self.window.workshop_page._auto_load_at_bottom(int(bar.maximum() * 0.70) + 1)
        self.assertEqual(self.window.workshop_page.visible_count, 60)

    def test_current_snapshot_uses_wallpaper_original_title(self) -> None:
        self.window = MainWindow(self.service)
        self.window.refresh_all()

        record = self.window._export_current_named(self.window.current_candidate)

        self.assertEqual(record.original_title, "原始壁纸名称")
        self.assertEqual(record.workshop_id, "123456")
        self.assertEqual(Path(record.target_path).name, "原始壁纸名称.jpg")

        with patch("wallpaper_exporter.app.QMessageBox.information") as information:
            self.window._show_export_result(record)
        information.assert_not_called()
        self.assertIn("保存成功", self.window.status.text())


if __name__ == "__main__":
    unittest.main()
