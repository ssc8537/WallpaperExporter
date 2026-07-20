from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PySide6.QtGui import QColor, QImage

from wallpaper_exporter.core import ConfigStore, WallpaperService
from wallpaper_exporter.video_tools import format_time, save_qimage
from wallpaper_exporter.workshop import WorkshopProject


class VideoToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = WallpaperService(ConfigStore(self.root / "Data"))
        self.service.update_config(export_dir=str(self.root / "Export"))
        self.project = WorkshopProject(
            workshop_id="123456",
            title="原始：壁纸/名称",
            project_type="video",
            project_dir=str(self.root),
            project_json=str(self.root / "project.json"),
            content_path=str(self.root / "video.mp4"),
            preview_path="",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_format_time_is_filename_safe(self) -> None:
        self.assertEqual(format_time(6983), "00-06.983")
        self.assertNotIn(":", format_time(6983))

    def test_saves_lossless_png_with_original_title_and_history_identity(self) -> None:
        image = QImage(320, 180, QImage.Format.Format_RGB32)
        image.fill(QColor("#F4AFC2"))

        target = save_qimage(
            image,
            self.service.export_dir,
            f"{self.project.safe_title}_候选B_00-06.983",
            "PNG",
            self.service,
            self.project,
            self.project.content_path,
            "测试帧",
        )

        self.assertEqual(target.suffix, ".png")
        self.assertTrue(target.name.startswith("原始：壁纸_名称_候选B"))
        with Image.open(target) as exported:
            self.assertEqual(exported.size, (320, 180))
            self.assertEqual(exported.format, "PNG")
        record = self.service.history[-1]
        self.assertEqual(record.original_title, self.project.title)
        self.assertEqual(record.workshop_id, "123456")

    def test_high_quality_jpg_is_available(self) -> None:
        image = QImage(64, 64, QImage.Format.Format_RGB32)
        image.fill(QColor("#A9DDF2"))

        target = save_qimage(
            image,
            self.service.export_dir,
            self.project.safe_title,
            "JPEG",
            self.service,
            self.project,
            self.project.content_path,
            "测试 JPG",
        )

        self.assertEqual(target.suffix, ".jpg")
        with Image.open(target) as exported:
            self.assertEqual(exported.format, "JPEG")


if __name__ == "__main__":
    unittest.main()
