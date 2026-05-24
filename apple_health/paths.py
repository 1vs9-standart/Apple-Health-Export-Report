"""Пути проекта по умолчанию."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_REPORT_PATH = DEFAULT_OUTPUT_DIR / "health_report.html"
