from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from image_dataset_checker.cli import main
from image_dataset_checker.scanner import CSV_COLUMNS, scan_directory, write_csv


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def make_image(
        self,
        relative_path: str,
        *,
        size: tuple[int, int] = (800, 600),
        image_format: str = "PNG",
        color: tuple[int, int, int] = (20, 40, 60),
    ) -> Path:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size=size, color=color).save(path, format=image_format)
        return path

    def test_empty_directory_has_no_records(self) -> None:
        self.assertEqual(scan_directory(self.root).records, ())

    def test_reads_format_and_dimensions(self) -> None:
        self.make_image("photo.png", size=(800, 600))
        record = scan_directory(self.root).records[0]
        self.assertEqual(record.path, "photo.png")
        self.assertEqual(record.image_format, "PNG")
        self.assertEqual((record.width, record.height), (800, 600))
        self.assertEqual(record.status, "ok")

    def test_supported_jpeg_is_scanned(self) -> None:
        self.make_image("photo.jpg", image_format="JPEG")
        record = scan_directory(self.root).records[0]
        self.assertEqual(record.image_format, "JPEG")

    def test_unsupported_files_are_ignored(self) -> None:
        (self.root / "notes.txt").write_text("not an image", encoding="utf-8")
        self.make_image("photo.png")
        self.assertEqual(scan_directory(self.root).total_count, 1)

    def test_scan_is_recursive_by_default(self) -> None:
        self.make_image("nested/photo.png")
        self.assertEqual(scan_directory(self.root).records[0].path, "nested/photo.png")

    def test_non_recursive_scan_skips_nested_files(self) -> None:
        self.make_image("nested/photo.png")
        self.assertEqual(scan_directory(self.root, recursive=False).records, ())

    def test_corrupt_image_is_marked(self) -> None:
        (self.root / "broken.png").write_bytes(b"not a PNG")
        record = scan_directory(self.root).records[0]
        self.assertEqual(record.status, "corrupt")
        self.assertIsNone(record.width)

    def test_truncated_jpeg_is_marked_corrupt(self) -> None:
        image = self.make_image("truncated.jpg", image_format="JPEG")
        image.write_bytes(image.read_bytes()[:-100])
        record = scan_directory(self.root).records[0]
        self.assertEqual(record.status, "corrupt")

    def test_image_below_minimum_width_is_marked(self) -> None:
        self.make_image("small.png", size=(639, 480))
        record = scan_directory(self.root, min_width=640, min_height=480).records[0]
        self.assertEqual(record.status, "too_small")

    def test_image_at_minimum_dimensions_passes(self) -> None:
        self.make_image("minimum.png", size=(640, 480))
        record = scan_directory(self.root, min_width=640, min_height=480).records[0]
        self.assertEqual(record.status, "ok")

    def test_later_exact_copy_is_marked_duplicate(self) -> None:
        source = self.make_image("a.png")
        shutil.copyfile(source, self.root / "b.png")
        records = scan_directory(self.root).records
        self.assertEqual(records[0].status, "ok")
        self.assertEqual(records[1].status, "duplicate")

    def test_duplicate_points_to_first_relative_path(self) -> None:
        source = self.make_image("a-original.png")
        duplicate = self.root / "copies" / "copy.png"
        duplicate.parent.mkdir()
        shutil.copyfile(source, duplicate)
        record = next(record for record in scan_directory(self.root).records if record.path == "copies/copy.png")
        self.assertEqual(record.duplicate_of, "a-original.png")

    def test_small_duplicate_has_combined_status(self) -> None:
        source = self.make_image("a.png", size=(100, 100))
        shutil.copyfile(source, self.root / "b.png")
        records = scan_directory(self.root, min_width=640).records
        self.assertEqual(records[1].status, "duplicate_too_small")

    def test_csv_contains_expected_columns_and_rows(self) -> None:
        self.make_image("photo.png")
        result = scan_directory(self.root)
        report = write_csv(result, self.root / "reports" / "report.csv")
        with report.open(encoding="utf-8-sig", newline="") as report_file:
            rows = list(csv.DictReader(report_file))
        self.assertEqual(tuple(rows[0]), CSV_COLUMNS)
        self.assertEqual(rows[0]["path"], "photo.png")

    def test_cli_creates_report(self) -> None:
        self.make_image("photo.png")
        report = self.root / "out.csv"
        exit_code = main([str(self.root), "--output", str(report), "--min-width", "640"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(report.exists())

    def test_report_does_not_overwrite_existing_file_by_default(self) -> None:
        report = self.root / "existing.csv"
        report.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            write_csv(scan_directory(self.root), report)
        self.assertEqual(report.read_text(encoding="utf-8"), "keep me")

    def test_report_cannot_overwrite_image_even_with_overwrite(self) -> None:
        image = self.make_image("photo.png")
        original = image.read_bytes()
        with self.assertRaises(ValueError):
            write_csv(scan_directory(self.root), image, overwrite=True)
        self.assertEqual(image.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

