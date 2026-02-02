"""
Centralized logging configuration for the backend application.
"""
import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler

from .config import settings

# Create logs directory (stable regardless of current working directory)
# This avoids accidentally creating "backend/backend/logs" when running with cwd="backend".
BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
LOGS_DIR = BACKEND_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

_LOGGING_CONFIGURED = False


def _configure_root_logging() -> None:
    """Configure root logger once so all module loggers print consistently."""
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, settings.LOG_LEVEL, logging.INFO))

    # Avoid double-adding handlers (e.g. on reload).
    def _has_stream_stdout_handler() -> bool:
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stdout:
                return True
        return False

    def _has_file_handler(filename: str) -> bool:
        for h in root.handlers:
            if isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "").endswith(filename):
                return True
        return False

    detailed_formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    simple_formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console handler: show important logs in terminal (INFO+).
    if not _has_stream_stdout_handler():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(simple_formatter)
        root.addHandler(console_handler)

    # File handler: keep full detail for debugging (DEBUG+).
    if not _has_file_handler("app.log"):
        file_handler = RotatingFileHandler(
            LOGS_DIR / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        root.addHandler(file_handler)

    # Error file handler: errors only.
    if not _has_file_handler("error.log"):
        error_file_handler = RotatingFileHandler(
            LOGS_DIR / "error.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        error_file_handler.setLevel(logging.ERROR)
        error_file_handler.setFormatter(detailed_formatter)
        root.addHandler(error_file_handler)

    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Create and configure a logger with both file and console handlers.
    
    Args:
        name: Name of the logger (typically __name__ of the module)
    
    Returns:
        Configured logger instance
    """
    _configure_root_logging()
    # Child loggers propagate to root handlers by default.
    return logging.getLogger(name)
