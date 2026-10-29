"""Command-line interface for Image Dataset Checker."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .scanner import scan_directory, write_csv


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.directory.is_dir():
        parser.error(f"directory does not exist or is not a directory: {args.directory}")

    result = scan_directory(
        args.directory,
        min_width=args.min_width,
        min_height=args.min_height,
        recursive=not args.no_recursive,
    )
    output_path = args.output or args.directory / "image_dataset_report.csv"
    try:
        report_path = write_csv(result, output_path, overwrite=args.overwrite)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Cannot write report: {error}\n")

    print(f"Checked files: {result.total_count}")
    print(f"OK: {result.ok_count}")
    print(f"Corrupt: {result.corrupt_count}")
    print(f"Duplicates: {result.duplicate_count}")
    print(f"Below minimum size: {result.too_small_count}")
    print(f"CSV report: {report_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check image files in a dataset and save a CSV report.",
    )
    parser.add_argument("directory", type=Path, help="Dataset directory to scan")
    parser.add_argument("--output", "-o", type=Path, help="Path for the CSV report")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing CSV report")
    parser.add_argument("--min-width", type=_non_negative_int, default=0)
    parser.add_argument("--min-height", type=_non_negative_int, default=0)
    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Scan only the specified directory, without subdirectories",
    )
    return parser


def _non_negative_int(value: str) -> int:
    try:
        integer = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if integer < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return integer

