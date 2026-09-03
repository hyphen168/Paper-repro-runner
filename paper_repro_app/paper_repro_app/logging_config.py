from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = Path(__file__).resolve().parents[1] / "logs"
DEFAULT_LOG_FILE = DEFAULT_LOG_DIR / "app.log"


def setup_logger(
    name: str = "paper_repro_app",
    log_file: str | Path | None = None,
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 5,
) -> logging.Logger:
    """Configures and returns a thread-safe, structured rotating logger."""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if already initialized
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    target_file = Path(log_file) if log_file else DEFAULT_LOG_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        target_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "paper_repro_app") -> logging.Logger:
    """Returns the application logger instance."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logger(name)
    return logger
