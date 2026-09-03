from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from paper_repro_app.paths import DB_PATH, DEFAULT_DATA_DIR


DEFAULT_CONFIG: Dict[str, Any] = {
    "db_path": str(DB_PATH),
    "app_title": "Paper Repro Runner",
    "default_remote_workdir": "/workspace/paper-repro",
    "default_data_dir": str(DEFAULT_DATA_DIR),
}


def load_config(config_path: str | Path) -> Dict[str, Any]:
    config_file = Path(config_path)
    if not config_file.exists():
        return DEFAULT_CONFIG
    with config_file.open("r", encoding="utf-8") as stream:
        loaded = yaml.safe_load(stream) or {}
    merged = DEFAULT_CONFIG.copy()
    merged.update(loaded)
    return merged
