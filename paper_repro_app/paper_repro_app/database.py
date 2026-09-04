from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List


class SQLiteOpenHelper:
    """Python implementation of the SQLiteOpenHelper pattern for managing SQLite DB lifecycle, schemas, and migrations."""

    def __init__(self, db_path: str | Path, version: int = 2):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.version = version
        self._bootstrap()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _bootstrap(self) -> None:
        with self.get_connection() as conn:
            cursor = conn.execute("PRAGMA user_version;")
            row = cursor.fetchone()
            current_version = row[0] if row else 0
            if current_version == 0:
                self.onCreate(conn)
                conn.execute(f"PRAGMA user_version = {self.version};")
            else:
                self.onUpgrade(conn, current_version, self.version)
                if current_version < self.version:
                    conn.execute(f"PRAGMA user_version = {self.version};")

    def onCreate(self, conn: sqlite3.Connection) -> None:
        pass

    def onUpgrade(self, conn: sqlite3.Connection, old_version: int, new_version: int) -> None:
        pass


class TaskStore(SQLiteOpenHelper):
    def __init__(self, db_path: str | Path):
        super().__init__(db_path, version=9)

    def _connect(self) -> sqlite3.Connection:
        return self.get_connection()

    def onCreate(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                paper_url TEXT,
                repo_url TEXT,
                clone_url TEXT,
                host TEXT,
                user TEXT,
                ssh_key_path TEXT,
                port TEXT,
                remote_workdir TEXT,
                local_data_dir TEXT,
                environment_mode TEXT DEFAULT 'conda',
                run_command TEXT DEFAULT '',
                command_timeout INTEGER DEFAULT 900,
                data_config TEXT DEFAULT '',
                model_weights TEXT DEFAULT '',
                auto_download_dataset INTEGER DEFAULT 1,
                auto_run INTEGER DEFAULT 0,
                tune_args TEXT DEFAULT '',
                data_split TEXT DEFAULT '',
                status TEXT DEFAULT 'queued',
                current_step TEXT DEFAULT 'queued',
                batch_id TEXT DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                log TEXT DEFAULT ''
            )
            """
        )

    def onUpgrade(self, conn: sqlite3.Connection, old_version: int, new_version: int) -> None:
        self.onCreate(conn)
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(tasks)").fetchall()
        }
        for col, col_type in [
            ("port", "TEXT"),
            ("clone_url", "TEXT"),
            ("current_step", "TEXT DEFAULT 'queued'"),
            ("run_command", "TEXT DEFAULT ''"),
            ("command_timeout", "INTEGER DEFAULT 900"),
            ("data_config", "TEXT DEFAULT ''"),
            ("model_weights", "TEXT DEFAULT ''"),
            ("auto_download_dataset", "INTEGER DEFAULT 1"),
            ("auto_run", "INTEGER DEFAULT 0"),
            ("tune_args", "TEXT DEFAULT ''"),
            ("data_split", "TEXT DEFAULT ''"),
            ("batch_id", "TEXT DEFAULT ''"),
        ]:
            if col not in columns:
                conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {col_type}")

    def create_task(self, **kwargs: Any) -> Dict[str, Any]:
        task_id = kwargs.get("id") or f"task-{uuid.uuid4().hex[:8]}"
        status = kwargs.get("status", "queued")
        current_step = kwargs.get("current_step", "queued")
        log = kwargs.get("log", "")

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    id, paper_url, repo_url, clone_url, host, user, ssh_key_path, port, remote_workdir,
                    local_data_dir, environment_mode, run_command, command_timeout, data_config, model_weights,
                    auto_download_dataset, auto_run, tune_args, data_split, status, current_step, batch_id, log
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    kwargs.get("paper_url"),
                    kwargs.get("repo_url"),
                    kwargs.get("clone_url") or kwargs.get("repo_url"),
                    kwargs.get("host"),
                    kwargs.get("user"),
                    kwargs.get("ssh_key_path"),
                    kwargs.get("port") or kwargs.get("ssh_port") or "22",
                    kwargs.get("remote_workdir"),
                    kwargs.get("local_data_dir"),
                    kwargs.get("environment_mode", "conda"),
                    kwargs.get("run_command", ""),
                    kwargs.get("command_timeout", 900),
                    kwargs.get("data_config", ""),
                    kwargs.get("model_weights", ""),
                    int(bool(kwargs.get("auto_download_dataset", True))),
                    int(bool(kwargs.get("auto_run", False))),
                    kwargs.get("tune_args", ""),
                    kwargs.get("data_split", ""),
                    status,
                    current_step,
                    kwargs.get("batch_id", ""),
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

    # ============ 批量任务队列 ============
    def get_oldest_queued(self) -> Dict[str, Any]:
        """取最早一个排队中的任务（供批量串行调度器取件）。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
            ).fetchone()
            return dict(row) if row else {}

    def list_tasks_by_batch(self, batch_id: str) -> List[Dict[str, Any]]:
        """某批次全部任务（按创建时间升序）。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE batch_id = ? ORDER BY created_at ASC",
                (batch_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_batches(self, limit: int = 20) -> List[Dict[str, Any]]:
        """批次汇总：batch_id / 任务总数 / 各状态计数 / 最近更新时间。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT batch_id,
                       COUNT(*) AS total,
                       SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END) AS queued,
                       SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running,
                       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                       SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) AS cancelled,
                       MAX(updated_at) AS updated_at
                FROM tasks WHERE batch_id <> ''
                GROUP BY batch_id ORDER BY updated_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]
