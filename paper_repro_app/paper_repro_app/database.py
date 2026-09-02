from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List


class TaskStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    paper_url TEXT,
                    repo_url TEXT,
                    host TEXT,
                    user TEXT,
                    ssh_key_path TEXT,
                    remote_workdir TEXT,
                    local_data_dir TEXT,
                    environment_mode TEXT DEFAULT 'conda',
                    status TEXT DEFAULT 'queued',
                    current_step TEXT DEFAULT 'queued',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    log TEXT DEFAULT ''
                )
                """
            )

    def create_task(self, **kwargs: Any) -> Dict[str, Any]:
        task_id = kwargs.get("id") or f"task-{uuid.uuid4().hex[:8]}"
        status = kwargs.get("status", "queued")
        current_step = kwargs.get("current_step", "queued")
        log = kwargs.get("log", "")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, paper_url, repo_url, host, user, ssh_key_path, remote_workdir,
                    local_data_dir, environment_mode, status, current_step, log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    kwargs.get("paper_url"),
                    kwargs.get("repo_url"),
                    kwargs.get("host"),
                    kwargs.get("user"),
                    kwargs.get("ssh_key_path"),
                    kwargs.get("remote_workdir"),
                    kwargs.get("local_data_dir"),
                    kwargs.get("environment_mode", "conda"),
                    status,
                    current_step,
                    log,
                ),
            )
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return dict(row) if row else {}

    def list_tasks(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def update_task_status(self, task_id: str, status: str, log: str | None = None, current_step: str | None = None) -> None:
        with self._connect() as conn:
            updates = ["status = ?", "updated_at = CURRENT_TIMESTAMP"]
            params: List[Any] = [status]
            if log is not None:
                updates.append("log = ?")
                params.append(log)
            if current_step is not None:
                updates.append("current_step = ?")
                params.append(current_step)
            params.append(task_id)
            conn.execute(
                f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?",
                tuple(params),
            )

    def append_task_log(self, task_id: str, entry: str) -> None:
        with self._connect() as conn:
            row = conn.execute("SELECT log FROM tasks WHERE id = ?", (task_id,)).fetchone()
            current_log = row["log"] if row else ""
            chunk = f"{entry}\n" if entry and not entry.endswith("\n") else entry
            merged = (current_log + chunk).strip("\n") + "\n"
            conn.execute(
                "UPDATE tasks SET log = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (merged, task_id),
            )
