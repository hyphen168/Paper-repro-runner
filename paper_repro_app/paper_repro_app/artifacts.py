from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class ArtifactCollector:
    """Write task output and logs into a local artifact directory owned by the user."""

    def __init__(self, base_dir: str | Path | None = None):
        self.base_dir = Path(base_dir or Path.home() / "paper_repro_artifacts")
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def collect(self, task_id: str, payload: Dict[str, Any]) -> Path:
        artifact_dir = self.base_dir / task_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        meta_path = artifact_dir / "task.json"
        meta_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        logs = payload.get("logs")
        if isinstance(logs, str):
            (artifact_dir / "remote.log").write_text(logs, encoding="utf-8")

        if not (artifact_dir / "status.txt").exists():
            (artifact_dir / "status.txt").write_text(payload.get("status", "unknown"), encoding="utf-8")

        return artifact_dir
