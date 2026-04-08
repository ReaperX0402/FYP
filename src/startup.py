from __future__ import annotations

from pathlib import Path
from src.config import Config


def ensure_directories() -> None:
    required_dirs = [
        Config.DATA_ROOT,
        Config.INCOMING_DIR,
        Config.ARCHIVE_DIR,
        Config.EXPORT_DIR,
        Config.AI_REVIEW_DIR,
    ]

    for directory in required_dirs:
        Path(directory).mkdir(parents=True, exist_ok=True)