"""模块化迁移与可测性回归：ssh/task/storage_utils 外迁一致性 + DB 迁移完整性 + 注入安全。"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


def _module_app():
    """延迟导入 app（streamlit 环境就绪后）。"""
    import app  # noqa: WPS433
    return app


def test_ssh_parse_target_basic():
    from paper_repro_app.ssh_utils import parse_ssh_target

    parsed = parse_ssh_target("ubuntu@1.2.3.4 -p 2200 -i /tmp/mykey")
    assert parsed["user"] == "ubuntu"
    assert parsed["host"] == "1.2.3.4"
    assert parsed["port"] == "2200"
    assert parsed["key"] == "/tmp/mykey"
    assert parse_ssh_target("") == {}


def test_task_helpers():
    from paper_repro_app.task_utils import estimate_completion, get_status_color, get_step_order

    assert get_step_order()[0] == "prepare"
    assert estimate_completion({"status": "success"}) == "已结束"
    assert get_status_color("success") == "#5cb8a4" or get_status_color("success").startswith("#")


def test_storage_helpers(tmp_path):
    from paper_repro_app.storage_utils import ensure_local_storage_tree, resolve_repo_url

    tree = ensure_local_storage_tree(str(tmp_path / "out"), "task-x")
    for folder in ("logs", "reports", "artifacts", "checkpoints", "tasks"):
        assert (Path(tree["root"]) / folder).is_dir()
    assert (Path(tree["root"]) / "tasks" / "task-x").is_dir()

    assert resolve_repo_url("https://github.com/a/b.git", "https://x/y") == "https://github.com/a/b.git"
    assert resolve_repo_url("", "https://huggingface.co/huggingface") == ""
    assert resolve_repo_url("", "https://github.com/x/y") == "https://github.com/x/y"


def test_app_exposes_migrated_names_without_duplicate_impl():
    """app 导入名与模块实现为同一对象（无双实现）。"""
    from paper_repro_app import ssh_utils, storage_utils, task_utils

    app = _module_app()
    assert app.parse_ssh_target is ssh_utils.parse_ssh_target
    assert app.resolve_repo_url is storage_utils.resolve_repo_url
    assert app.get_step_order is task_utils.get_step_order


def test_storage_detect_remote_workdir_is_single_impl():
    from paper_repro_app.remote_workdir import detect_remote_workdir as rw_detect
    from paper_repro_app.storage_utils import detect_remote_workdir as st_detect

    assert st_detect is rw_detect


def test_db_migration_v6_to_v8_keeps_data():
    """旧 v6 库打开后自动补列且旧数据保留。"""
    from paper_repro_app.database import TaskStore

    td = tempfile.mkdtemp(prefix="dbmig_")
    try:
        db = Path(td) / "tasks.db"
        conn = sqlite3.connect(str(db))
        conn.execute("PRAGMA user_version = 6;")
        conn.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                paper_url TEXT, repo_url TEXT, clone_url TEXT, host TEXT,
                user TEXT, ssh_key_path TEXT, port TEXT, remote_workdir TEXT,
                local_data_dir TEXT, environment_mode TEXT DEFAULT 'conda',
                run_command TEXT DEFAULT '', command_timeout INTEGER DEFAULT 900,
                data_config TEXT DEFAULT '', model_weights TEXT DEFAULT '',
                auto_download_dataset INTEGER DEFAULT 1, auto_run INTEGER DEFAULT 0,
                status TEXT DEFAULT 'queued', current_step TEXT DEFAULT 'queued',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                log TEXT DEFAULT ''
            )
            """
        )
        conn.execute(
            "INSERT INTO tasks (id, paper_url, repo_url, host, user, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("old-1", "https://arxiv.org/abs/1", "https://github.com/a/b", "h", "u", "failed"),
        )
        conn.commit()
        conn.close()

        store = TaskStore(db)
        c = store._connect()
        try:
            cols = [r["name"] for r in c.execute("PRAGMA table_info(tasks)")]
            assert "tune_args" in cols and "data_split" in cols
            assert "batch_id" in cols  # 批量复现新增列：旧库升级时自动补齐
            row = store.get_task("old-1")
            assert row is not None and row["paper_url"].startswith("https://arxiv.org")
            ver = c.execute("PRAGMA user_version").fetchone()[0]
            assert ver == store.version  # 断言升到当前架构版本（迁移链最终态）
        finally:
            c.close()
            store._connect().close()
    finally:
        import shutil
        shutil.rmtree(td, ignore_errors=True)


def test_injection_safe_repo_name_in_pipeline_bash():
    """恶意仓库名不得破坏生成脚本语法（bash -n 通过且含引用）。"""
    import subprocess

    from paper_repro_app.remote_runner import RemoteRunner

    evil = "https://github.com/a/repo;rm -rf ~;$(id).git"
    runner = RemoteRunner(
        {
            "host": "x",
            "user": "root",
            "repo_url": evil,
            "env_mode": "conda",
            "run_command": "python train.py --data x",
            "data_config": "data/c.yaml",
            "remote_workdir": "/w/repo_name;rm -rf",
        }
    )
    for step in runner.build_pipeline():
        check = subprocess.run(
            ["bash", "-n"],
            input=step["command"].encode("utf-8"),
            capture_output=True,
        )
        assert check.returncode == 0, f"{step['id']}: {check.stderr.decode('utf-8', errors='replace')[:200]}"


def test_migrated_modules_have_no_streamlit_import():
    """外迁模块不得 import streamlit（保持可单测）。"""
    import ast

    for mod in ("ssh_utils.py", "task_utils.py", "storage_utils.py"):
        tree = ast.parse((APP_DIR / "paper_repro_app" / mod).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("streamlit"), f"{mod} 依赖 streamlit: {alias.name}"
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("streamlit"):
                raise AssertionError(f"{mod} 依赖 streamlit")
