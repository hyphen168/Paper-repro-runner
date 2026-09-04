# -*- coding: utf-8 -*-
"""Phase 2 单机任务执行器（环境变量传参；凭据仅内存；每机独立进程）。
用法: HOST=... PORT=... PWD=... REPO=... RUN_CMD=... DATA_CFG=... PAPER_URL=... NAME=... python _phase2_task.py
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from paper_repro_app.config import DB_PATH  # noqa: E402
from paper_repro_app.database import TaskStore  # noqa: E402
from paper_repro_app.storage_utils import ensure_local_storage_tree, start_pipeline_execution  # noqa: E402

HOST = os.environ["HOST"]
PORT = int(os.environ["PORT"])
PWD = os.environ["PWD"]
REPO = os.environ["REPO"]
RUN_CMD = os.environ.get("RUN_CMD", "")
DATA_CFG = os.environ.get("DATA_CFG", "")
PAPER_URL = os.environ.get("PAPER_URL", "")
NAME = os.environ.get("NAME", "phase2")
OUT = os.environ.get("OUT", "/tmp/phase2_result.json")

store = TaskStore(DB_PATH)
local_dir = str(Path.home() / f"paper_repro_{NAME}_data")
task = store.create_task(
    paper_url=PAPER_URL,
    repo_url=REPO,
    clone_url=REPO,
    host=HOST,
    user="root",
    port=PORT,
    ssh_key_path="",
    remote_workdir="/workspace/paper-repro",
    local_data_dir=local_dir,
    environment_mode="conda",
    run_command=RUN_CMD,
    command_timeout=1500,
    data_config=DATA_CFG,
    model_weights="",
    auto_download_dataset=True,
    auto_run=False,
    tune_args="",
    data_split="",
    status="queued",
    current_step="prepare",
)
tid = task["id"]
ensure_local_storage_tree(local_dir, tid)
print(f"[{NAME}] task={tid} host={HOST}:{PORT}", flush=True)
ok, msg = start_pipeline_execution(tid, password=PWD, hosts=[{"host": HOST, "port": PORT, "user": "root"}])
print(f"[{NAME}] start={ok} {msg[:80]}", flush=True)

DEADLINE = time.time() + 55 * 60
final = None
last_len = 0
while time.time() < DEADLINE:
    time.sleep(8)
    t = store.get_task(tid)
    if not t:
        break
    status = str(t.get("status", ""))
    log = str(t.get("log") or "")
    if len(log) != last_len or status in ("success", "failed", "cancelled"):
        tail = log.splitlines()[-1]
        print(f"[{time.strftime('%H:%M:%S')}] {status} step={t.get('current_step')} | {tail[-110:]}", flush=True)
        last_len = len(log)
    if status in ("success", "failed", "cancelled"):
        final = t
        break
if final is None:
    final = store.get_task(tid)
    print(f"[{NAME}] TIMEOUT final={final.get('status') if final else 'none'}", flush=True)

raw = str(final.get("log") or "") if final else ""
out = {"task_id": tid, "status": final.get("status") if final else "lost", "log": raw}
Path(OUT).write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
print(f"[{NAME}] DONE status={out['status']} -> {OUT}", flush=True)
