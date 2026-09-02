from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


class LocalConfigStore:
    """Persist lightweight local configuration without committing secrets to the repo."""

    def __init__(self, config_dir: str | Path | None = None):
        self.config_dir = Path(config_dir or Path.home() / ".paper_repro_app")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.config_dir / "cloud_config.json"

    def load(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self, values: Dict[str, Any]) -> Dict[str, Any]:
        merged = self.load()
        merged.update(values)
        with self.config_path.open("w", encoding="utf-8") as handle:
            json.dump(merged, handle, ensure_ascii=False, indent=2)
        try:
            os.chmod(self.config_path, 0o600)
        except OSError:
            pass
        return merged

    def clear(self) -> None:
        if self.config_path.exists():
            self.config_path.unlink()
