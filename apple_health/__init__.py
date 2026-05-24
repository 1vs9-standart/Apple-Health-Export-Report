"""Анализ экспорта Apple Health: парсинг, стресс-модель, дашборд."""

__version__ = "0.1.0"

from apple_health.paths import DEFAULT_DATA_DIR, DEFAULT_OUTPUT_DIR, DEFAULT_REPORT_PATH, PROJECT_ROOT

__all__ = [
    "__version__",
    "PROJECT_ROOT",
    "DEFAULT_DATA_DIR",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_REPORT_PATH",
]
