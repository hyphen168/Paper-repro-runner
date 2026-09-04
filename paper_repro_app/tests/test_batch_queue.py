"""批量复现回归测试：队列串行调度、DB batch 迁移与批次聚合、取消整批。

不触网、不写真实用户目录：storage_utils.DB_PATH 与 RemoteRunner 全部注入替身。
"""
from __future__ import annotations

import sqlite3
import threading
import time

import pytest

import paper_repro_app.storage_utils as su
from paper_repro_app.database import TaskStore


class _FakeRunner:
    """替身 RemoteRunner：模拟一次耗时云端流水线，响应取消事件。"""

    EXECUTED: list = []  # 记录按序执行的任务 id

    def __init__(self, task):
        self.task = task

    def execute(self, on_step=None, cancel_event=None):
        _FakeRunner.EXECUTED.append(str(self.task.get("id")))
        if on_step:
            on_step("clone", "拉取代码", "fake clone start")
            on_step("collect", "收集指标", "fake collect done")
        for _ in range(60):
            if cancel_event is not None and cancel_event.is_set():
                return {"status": "cancelled", "message": "fake cancelled", "failed_step": "run"}
            time.sleep(0.01)
        return {"status": "success", "metrics": {}, "logs": "fake success", "message": "ok"}


@pytest.fixture()
def _isolated(tmp_path, monkeypatch):
    db_file = tmp_path / "tasks.db"
    monkeypatch.setattr(su, "DB_PATH", db_file)
    monkeypatch.setattr(su, "RemoteRunner", _FakeRunner)
    # 每个测试独立的调度状态字典：避免上一个测试残留的 drainer 线程/事件串扰
    _fresh_state: dict = {}
    monkeypatch.setattr(su, "_get_exec_state", lambda: _fresh_state)

    class _FakeAnalyzer:
        def analyze(self, **kwargs):
            return {"summary": "", "possible_innovations": [], "risks": [], "confidence": 0}

    class _FakeCollector:
        def collect(self, *a, **k):
            return None

    monkeypatch.setattr(su, "PaperInnovationAnalyzer", _FakeAnalyzer)
    monkeypatch.setattr(su, "ArtifactCollector", _FakeCollector)
    monkeypatch.setattr(
        su, "generate_repro_report",
        lambda task, analysis: {"report_path": str(tmp_path / "r.md"), "report_md": "# report"},
    )
    monkeypatch.setattr(su, "generate_project_summary", lambda *a, **k: "# summary")

    def _fake_tree(base_dir, task_id=None):
        base = tmp_path / "local"
        return {"root": str(base), "logs": str(base / "logs"), "reports": str(base / "reports"),
                "artifacts": str(base / "artifacts"), "checkpoints": str(base / "checkpoints"),
                "tasks": str(base / "tasks"), "task_dir": str(base / "tasks" / (task_id or "x"))}

    monkeypatch.setattr(su, "ensure_local_storage_tree", _fake_tree)
    _FakeRunner.EXECUTED = []
    return db_file


def _seed_batch(store: TaskStore, batch_id: str, n: int, prefix: str = "task") -> list:
    ids = []
    for i in range(n):
        t = store.create_task(
            id=f"{prefix}-{batch_id}-{i}",
            paper_url="https://arxiv.org/abs/9999.0000",
            repo_url=f"https://github.com/demo/repo{i}",
            host="example.com",
            user="root",
            ssh_key_path="~/.ssh/id_ed25519",
            port="22",
            remote_workdir="/workspace/x",
            local_data_dir="/tmp/x",
            environment_mode="conda",
            batch_id=batch_id,
            status="queued",
            current_step="queued",
        )
        ids.append(t["id"])
    return ids


def test_db_batch_columns_and_aggregation(tmp_path):
    store = TaskStore(tmp_path / "tasks.db")
    b1 = "batch-aaa"
    b2 = "batch-bbb"
    ids1 = _seed_batch(store, b1, 2)
    _seed_batch(store, b2, 1)
    assert store.get_task(ids1[0])["batch_id"] == b1
    rows = store.list_tasks_by_batch(b1)
    assert [r["id"] for r in rows] == ids1
    batches = {b["batch_id"]: b for b in store.list_batches()}
    assert batches[b1]["total"] == 2
    assert batches[b1]["queued"] == 2
    assert batches[b2]["total"] == 1
    # 队列取件：最早创建的 queued 任务
    assert store.get_oldest_queued()["id"] == ids1[0]


def test_db_migration_adds_batch_column(tmp_path):
    """旧库（v8 无 batch_id）打开后自动 ALTER，历史数据保留。"""
    db_file = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """CREATE TABLE tasks (
            id TEXT PRIMARY KEY, paper_url TEXT, repo_url TEXT, clone_url TEXT, host TEXT, user TEXT,
            ssh_key_path TEXT, port TEXT, remote_workdir TEXT, local_data_dir TEXT,
            environment_mode TEXT DEFAULT 'conda', run_command TEXT DEFAULT '', command_timeout INTEGER DEFAULT 900,
            data_config TEXT DEFAULT '', model_weights TEXT DEFAULT '', auto_download_dataset INTEGER DEFAULT 1,
            auto_run INTEGER DEFAULT 0, tune_args TEXT DEFAULT '', data_split TEXT DEFAULT '',
            status TEXT DEFAULT 'queued', current_step TEXT DEFAULT 'queued',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP, log TEXT DEFAULT '')"""
    )
    conn.execute("PRAGMA user_version = 8;")
    conn.execute(
        "INSERT INTO tasks (id, repo_url, host, user, status) VALUES ('legacy-1', 'https://github.com/a/b', 'h', 'u', 'success')"
    )
    conn.commit()
    conn.close()

    store = TaskStore(db_file)
    legacy = store.get_task("legacy-1")
    assert legacy["status"] == "success"
    assert "batch_id" in legacy and legacy["batch_id"] == ""
    # 新建任务可写 batch_id
    t = store.create_task(id="t-b", repo_url="https://github.com/a/b", host="h", user="u",
                          status="queued", current_step="queued", batch_id="batch-x")
    assert t["batch_id"] == "batch-x"


def test_drainer_runs_queued_tasks_in_order(_isolated, tmp_path):
    store = TaskStore(_isolated)
    batch = "batch-order"
    _seed_batch(store, batch, 3)
    su.ensure_batch_drainer()
    su.wake_batch_drainer()

    deadline = time.time() + 15
    while time.time() < deadline:
        statuses = [store.get_task(t)["status"] for t in _FakeRunner.EXECUTED]
        if len(_FakeRunner.EXECUTED) == 3 and all(s == "success" for s in statuses):
            break
        time.sleep(0.05)
    assert _FakeRunner.EXECUTED == [f"task-{batch}-0", f"task-{batch}-1", f"task-{batch}-2"], _FakeRunner.EXECUTED
    for tid in _FakeRunner.EXECUTED:
        assert store.get_task(tid)["status"] == "success"


def test_drainer_serializes_and_moves_to_next(_isolated):
    """严格串行：后一个任务必须在先一个进入终态后才被取件。"""
    store = TaskStore(_isolated)
    batch = "batch-serial"
    _seed_batch(store, batch, 2)
    su.ensure_batch_drainer()
    su.wake_batch_drainer()
    deadline = time.time() + 15
    saw_running = 0
    while time.time() < deadline:
        running_count = sum(1 for t in _FakeRunner.EXECUTED if store.get_task(t)["status"] == "running")
        saw_running = max(saw_running, running_count)
        if len(_FakeRunner.EXECUTED) == 2:
            break
        time.sleep(0.05)
    assert saw_running <= 1
    time.sleep(0.8)
    assert all(store.get_task(t)["status"] == "success" for t in _FakeRunner.EXECUTED)
    assert store.get_oldest_queued() == {}


def test_cancel_batch(_isolated):
    store = TaskStore(_isolated)
    batch = "batch-cancel"
    ids = _seed_batch(store, batch, 3)
    su.ensure_batch_drainer()
    su.wake_batch_drainer()
    time.sleep(0.3)  # 让第一个开始执行
    affected = su.cancel_batch(batch)
    assert affected >= 1
    deadline = time.time() + 10
    while time.time() < deadline:
        statuses = {t: store.get_task(t)["status"] for t in ids}
        if statuses.get(ids[0]) in ("cancelled", "failed") and all(
            statuses[t] in ("cancelled", "success") for t in ids if t != ids[0]
        ):
            break
        time.sleep(0.05)
    assert store.get_task(ids[0])["status"] in ("cancelled",)
    for tid in ids[1:]:
        assert store.get_task(tid)["status"] == "cancelled"
