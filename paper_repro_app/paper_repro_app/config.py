from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml


DEFAULT_CONFIG: Dict[str, Any] = {
    "db_path": str(Path(__file__).resolve().parents[1] / "data" / "tasks.db"),
    "app_title": "Paper Repro Runner",
    "default_remote_workdir": "/workspace/paper-repro",
    "default_data_dir": "~/data",
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
