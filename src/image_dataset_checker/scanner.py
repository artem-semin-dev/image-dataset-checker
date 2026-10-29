"""Scanning and CSV reporting for image datasets."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from PIL import Image, UnidentifiedImageError

SUPPORTED_EXTENSIONS = frozenset({".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"})
CSV_COLUMNS = (
    "path",
    "status",
    "format",
    "width",
    "height",
    "size_bytes",
    "sha256",
    "duplicate_of",
    "details",
)


@dataclass(frozen=True)
class ImageRecord:
    """One inspected file in a dataset."""

    path: str
    status: str
    image_format: str | None
    width: int | None
    height: int | None
    size_bytes: int
    sha256: str | None
    duplicate_of: str | None
    details: str

    def as_csv_row(self) -> dict[str, str | int | None]:
        return {
            "path": self.path,
            "status": self.status,
            "format": self.image_format,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "duplicate_of": self.duplicate_of,
            "details": self.details,
        }


@dataclass(frozen=True)
class ScanResult:
    """The records from one dataset scan."""

    root: Path
    records: tuple[ImageRecord, ...]

    @property
    def total_count(self) -> int:
        return len(self.records)

    @property
    def corrupt_count(self) -> int:
        return sum(record.status == "corrupt" for record in self.records)

    @property
    def duplicate_count(self) -> int:
        return sum(record.status.startswith("duplicate") for record in self.records)

    @property
    def too_small_count(self) -> int:
        return sum("too_small" in record.status for record in self.records)

    @property
    def ok_count(self) -> int:
        return sum(record.status == "ok" for record in self.records)


def scan_directory(
    directory: str | Path,
    *,
    min_width: int = 0,
    min_height: int = 0,
    recursive: bool = True,
) -> ScanResult:
    """Inspect supported image files in *directory*.

    Exact binary duplicates are compared only among valid images.  The first
    occurrence keeps its normal status; later occurrences are marked as
    duplicates and point to that first relative path.
    """

    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Directory does not exist or is not a directory: {root}")
    if min_width < 0 or min_height < 0:
        raise ValueError("Minimum dimensions cannot be negative.")

    seen_hashes: dict[str, str] = {}
    records: list[ImageRecord] = []

    for file_path in _candidate_files(root, recursive=recursive):
        record = _inspect_file(file_path, root, min_width=min_width, min_height=min_height)
        if record.status != "corrupt" and record.sha256 is not None:
            duplicate_of = seen_hashes.get(record.sha256)
            if duplicate_of is None:
                seen_hashes[record.sha256] = record.path
            else:
                record = _mark_duplicate(record, duplicate_of)
        records.append(record)

    return ScanResult(root=root, records=tuple(records))


def write_csv(result: ScanResult, output_path: str | Path, *, overwrite: bool = False) -> Path:
    """Write *result* to CSV and return the resolved output path."""

    output = Path(output_path).expanduser().resolve()
    if output.suffix.lower() != ".csv":
        raise ValueError("Report path must have a .csv extension.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w" if overwrite else "x", encoding="utf-8-sig", newline="") as report_file:
        writer = csv.DictWriter(report_file, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(record.as_csv_row() for record in result.records)
    return output


def _candidate_files(root: Path, *, recursive: bool) -> Iterable[Path]:
    iterator = root.rglob("*") if recursive else root.glob("*")
    candidates = (
        path
        for path in iterator
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix().casefold())


def _inspect_file(file_path: Path, root: Path, *, min_width: int, min_height: int) -> ImageRecord:
    relative_path = file_path.relative_to(root).as_posix()
    size_bytes = file_path.stat().st_size
    content_hash = _sha256(file_path)

    try:
        # verify() checks the file structure, while load() also decodes pixels.
        # Both are needed: some truncated JPEG files pass verify() alone.
        with Image.open(file_path) as image:
            image.verify()
        with Image.open(file_path) as image:
            image_format = image.format
            width, height = image.size
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError) as error:
        return ImageRecord(
            path=relative_path,
            status="corrupt",
            image_format=None,
            width=None,
            height=None,
            size_bytes=size_bytes,
            sha256=content_hash,
            duplicate_of=None,
            details=f"Cannot read image: {error.__class__.__name__}",
        )

    is_too_small = width < min_width or height < min_height
    status = "too_small" if is_too_small else "ok"
    details = (
        f"Below minimum size {min_width}x{min_height}."
        if is_too_small
        else "Image passed all configured checks."
    )
    return ImageRecord(
        path=relative_path,
        status=status,
        image_format=image_format,
        width=width,
        height=height,
        size_bytes=size_bytes,
        sha256=content_hash,
        duplicate_of=None,
        details=details,
    )


def _mark_duplicate(record: ImageRecord, duplicate_of: str) -> ImageRecord:
    status = "duplicate_too_small" if record.status == "too_small" else "duplicate"
    details = f"Exact duplicate of {duplicate_of}. {record.details}"
    return ImageRecord(
        path=record.path,
        status=status,
        image_format=record.image_format,
        width=record.width,
        height=record.height,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        duplicate_of=duplicate_of,
        details=details,
    )


def _sha256(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

