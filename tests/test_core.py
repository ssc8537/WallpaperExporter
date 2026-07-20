from __future__ import annotations

import tempfile
import unittest
import os
import time
from pathlib import Path

from PIL import Image

from wallpaper_exporter.core import ConfigStore, WallpaperService


class WallpaperServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.themes = self.root / "Themes"
        self.export = self.root / "Export"
        self.data = self.root / "Data"
        self.themes.mkdir()
        self.service = WallpaperService(ConfigStore(self.data))
        self.service.update_config(themes_dir=str(self.themes), export_dir=str(self.export))

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def make_image(path: Path, size=(2560, 1440), image_format="JPEG", color=(245, 175, 196)) -> None:
        Image.new("RGB", size, color).save(path, format=image_format, quality=96)

    def test_current_wallpaper_reads_real_format_and_resolution(self) -> None:
        path = self.themes / "WallpaperEngineLockOverride.jpg"
        self.make_image(path, (3840, 2160), "JPEG")

        candidate = self.service.current_wallpaper()

        self.assertIsNotNone(candidate)
        self.assertEqual((candidate.width, candidate.height), (3840, 2160))
        self.assertEqual(candidate.image_format, "JPEG")
        self.assertEqual(candidate.extension, ".jpg")
        self.assertIn("4K+", candidate.resolution)

    def test_current_wallpaper_prefers_newer_desktop_override(self) -> None:
        lock = self.themes / "WallpaperEngineLockOverride.jpg"
        override = self.themes / "WallpaperEngineOverride.jpg"
        self.make_image(lock, (2560, 1440), "JPEG")
        time.sleep(0.02)
        self.make_image(override, (3840, 2160), "JPEG", color=(100, 160, 220))
        now = time.time()
        os.utime(lock, (now - 10, now - 10))
        os.utime(override, (now, now))

        candidate = self.service.current_wallpaper()

        self.assertEqual(Path(candidate.path).name, "WallpaperEngineOverride.jpg")
        self.assertEqual((candidate.width, candidate.height), (3840, 2160))

    def test_transcoded_wallpaper_without_extension_is_detected(self) -> None:
        path = self.themes / "TranscodedWallpaper"
        self.make_image(path, (1920, 1080), "PNG")

        candidates = self.service.scan_theme_images()

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].image_format, "PNG")
        self.assertEqual(candidates[0].extension, ".png")

    def test_export_preserves_source_bytes_format_and_resolution(self) -> None:
        path = self.themes / "WallpaperEngineLockOverride.jpg"
        self.make_image(path, (2560, 1440), "JPEG")
        source_bytes = path.read_bytes()
        candidate = self.service.current_wallpaper()

        record = self.service.export_candidate(candidate)

        target = Path(record.target_path)
        self.assertEqual(record.status, "success")
        self.assertEqual(target.suffix.lower(), ".jpg")
        self.assertEqual(target.read_bytes(), source_bytes)
        with Image.open(target) as image:
            self.assertEqual(image.size, (2560, 1440))
            self.assertEqual(image.format, "JPEG")

    def test_duplicate_is_skipped_only_within_same_destination(self) -> None:
        path = self.themes / "WallpaperEngineLockOverride.jpg"
        self.make_image(path)
        candidate = self.service.current_wallpaper()

        first = self.service.export_candidate(candidate, self.export)
        duplicate = self.service.export_candidate(candidate, self.export)
        other = self.service.export_candidate(candidate, self.root / "Other")

        self.assertEqual(first.status, "success")
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(other.status, "success")
        self.assertNotEqual(first.target_path, other.target_path)

    def test_invalid_or_unsupported_files_are_ignored(self) -> None:
        (self.themes / "WallpaperEngineOverride.jpg").write_text("not an image", encoding="utf-8")
        (self.themes / "WallpaperEngineBackupWallpaper.jpg").write_bytes(b"\x00\x01")

        self.assertEqual(self.service.scan_theme_images(), [])

    def test_exact_duplicates_are_represented_once(self) -> None:
        first = self.themes / "WallpaperEngineLockOverride.jpg"
        second = self.themes / "WallpaperEngineOverride.jpg"
        self.make_image(first, (2560, 1440), "PNG")
        second.write_bytes(first.read_bytes())

        candidates = self.service.scan_theme_images()
        best = self.service.best_per_exact_image(candidates)

        self.assertEqual(len(candidates), 2)
        self.assertEqual(len(best), 1)
        self.assertTrue(best[0].is_current)

    def test_missing_export_file_does_not_block_recovery(self) -> None:
        path = self.themes / "WallpaperEngineLockOverride.jpg"
        self.make_image(path)
        candidate = self.service.current_wallpaper()
        first = self.service.export_candidate(candidate)
        Path(first.target_path).unlink()

        recovered = self.service.export_candidate(candidate)

        self.assertEqual(recovered.status, "success")
        self.assertTrue(Path(recovered.target_path).is_file())

    def test_existing_identical_file_prevents_duplicate_after_history_clear(self) -> None:
        path = self.themes / "WallpaperEngineLockOverride.jpg"
        self.make_image(path)
        candidate = self.service.current_wallpaper()
        first = self.service.export_candidate(candidate)
        self.service.clear_history_records()

        duplicate = self.service.export_candidate(candidate)

        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(duplicate.target_path, first.target_path)
        self.assertEqual(len(list(self.export.glob("*.jpg"))), 1)


if __name__ == "__main__":
    unittest.main()
