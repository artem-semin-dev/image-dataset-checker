"""Utilities for checking image datasets before annotation or model training."""

from .scanner import ScanResult, scan_directory

__all__ = ["ScanResult", "scan_directory"]
__version__ = "0.1.0"
