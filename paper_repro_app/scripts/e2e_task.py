"""端到端验证驱动：模拟 UI 提交任务 → 后台流水线 → 落库，输出关键结果。

用法:
    python scripts/e2e_task.py --host connect.cqa1.seetacloud.com --port 47754 --user root --password <你的云服务器密码> ^
        --paper "https://arxiv.org/abs/2407.02988" --repo "https://github.com/hyphen168/Yolov5m-NEU-DET.git" ^
        --clone "https://ghfast.top/https://github.com/hyphen168/Yolov5m-NEU-DET.git" --mode safe
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paper_repro_app.database import TaskStore  # noqa: E402
from paper_repro_app.remote_runner import RemoteRunner  # noqa: E402
from paper_repro_app.paths import DB_PATH  # noqa: E402


def build_task(args: argparse.Namespace) -> dict:
    """与 UI 提交路径一致地构造任务。"""
    mode = args.mode
    auto_run = mode == "auto"
    run_command = args.run_command or ""
    task = {
        "paper_url": args.paper,
        "repo_url": args.repo,
        "host": args.host,
        "user": args.user,
        "port": str(args.port),
        "password": args.password,
        "ssh_key_path": "",
        "clone_url": args.clone or args.repo,
        "pip_index_url": args.pip_index or "",
        "remote_workdir": args.workdir or f"/root/autodl-tmp/{args.tag}",
        "local_data_dir": str(Path.home() / "e2e_local_out"),
        "environment_mode": args.env or "conda",
        "run_command": run_command,
        "command_timeout": int(args.timeout) * 60,
        "data_config": args.data_config or "",
        "data_split": args.data_split or "",
        "model_weights": "",
        "auto_download_dataset": bool(args.auto_download),
        "auto_run": auto_run,
        "status": "queued",
        "current_step": "prepare",
    }
    return task


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", required=True)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--paper", required=True, help="论文链接")
    parser.add_argument("--repo", required=True, help="代码仓库")
    parser.add_argument("--clone", default="", help="加速克隆地址（可空）")
    parser.add_argument("--mode", choices=["safe", "auto", "run"], default="safe",
                        help="safe=安全检查; auto=自动训练; run=实际运行(配 --run-command)")
    parser.add_argument("--run-command", default="", help="run 模式的仓库命令")
    parser.add_argument("--data-config", default="", help="显式数据集 YAML 相对路径")
    parser.add_argument("--data-split", default="", help="train/val/test 比例，如 70,20,10")
    parser.add_argument("--pip-index", default="", help="pip 镜像源（可空）")
    parser.add_argument("--auto-download", type=int, default=1)
    parser.add_argument("--env", default="conda")
    parser.add_argument("--timeout", type=int, default=20, help="单步超时(分钟)")
    parser.add_argument("--tag", default="e2e", help="云端工作目录名")
    parser.add_argument("--workdir", default="", help="完整云端工作目录（可空，默认 /root/autodl-tmp/<tag>）")
    args = parser.parse_args()

    store = TaskStore(DB_PATH)
    task = build_task(args)
    # 显式建 task id 落库（与 UI 一致）
    from uuid import uuid4
    task_id = f"task-{uuid4().hex[:8]}"
    task["id"] = task_id
    store.create_task(
        id=task_id,
        paper_url=task["paper_url"], repo_url=task["repo_url"], host=task["host"],
        user=task["user"], ssh_key_path="", port=task["port"], clone_url=task["clone_url"],
        pip_index_url=task["pip_index_url"], remote_workdir=task["remote_workdir"],
        local_data_dir=task["local_data_dir"], environment_mode=task["environment_mode"],
        run_command=task["run_command"], command_timeout=task["command_timeout"],
        data_config=task["data_config"], data_split=task["data_split"], model_weights="",
        auto_download_dataset=task["auto_download_dataset"], auto_run=task["auto_run"],
        status="queued", current_step="prepare",
    )

    print(f"[E2E] task={task_id} mode={args.mode} host={args.host}")
    live: list[str] = []

    def on_step(step_id: str, step_title: str, message: str) -> None:
        ts = f"[{datetime.now().strftime('%H:%M:%S')}] [{step_id}] {str(message).strip()[:200]}"
        live.append(ts)
        store.update_task_status(task_id, "running", "\n".join(live[-30:]), current_step=step_id)
        line = str(message).strip().replace("\n", " ")[:140]
        print(f"  · {line}", flush=True)

    runner = RemoteRunner(task)
    t0 = time.time()
    try:
        result = runner.execute(on_step=on_step)
    except Exception as exc:
        result = {"status": "failed", "message": f"流水线异常: {exc}", "failed_step": getattr(runner, "_last_step_id", "")}

    store.update_task_status(task_id, result.get("status", "failed"),
                             json.dumps(result, ensure_ascii=False, indent=2),
                             current_step=result.get("failed_step") or result.get("status", "failed"))
    dur = int(time.time() - t0)
    print(f"\n[E2E] 结果 status={result.get('status')} 耗时 {dur}s")
    msg = str(result.get("message", ""))[:500]
    print(f"[E2E] message={msg}")
    if result.get("status") != "success":
        print("[E2E] 失败！关键输出尾部：")
        print(str(result.get("logs", ""))[-1200:])
        return 1
    print(f"[E2E] 指标: {result.get('metrics')}")
    print(f"[E2E] 数据集: {result.get('dataset')}")
    print(f"[E2E] 模型: {result.get('model')}")
    print("[E2E] SUCCESS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
