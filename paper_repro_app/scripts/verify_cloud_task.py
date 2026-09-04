"""云端论文复现验证驱动器（CLI，与应用同一套调度/流水线引擎）。

用法示例：
  CLOUD_PASSWORD=xxxx python scripts/verify_cloud_task.py \
      --paper "https://doi.org/10.48550/arXiv.2607.10851" \
      --repo "https://github.com/tonmoy-hossain/Locus" \
      --host "connect.cqa1.seetacloud.com" --port 13150 --user root \
      --command 'python -c "..."' --timeout-min 20

说明：密码只经环境变量进入进程内存（与 App 安全策略一致），不落盘、不入日志；
任务写入真实任务库（~/.paper_repro_app/tasks.db），完成后可在 App「历史记录」查看。
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from paper_repro_app.database import TaskStore  # noqa: E402
from paper_repro_app.paths import DB_PATH  # noqa: E402
from paper_repro_app.remote_workdir import detect_remote_workdir  # noqa: E402
from paper_repro_app.storage_utils import (  # noqa: E402
    _get_exec_state,
    start_pipeline_execution,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="云端论文复现验证（真实执行流水线）")
    parser.add_argument("--paper", default="", help="论文链接（可留空）")
    parser.add_argument("--repo", required=True, help="代码仓库地址")
    parser.add_argument("--host", required=True, help="云服务器 host（也支持整条 ssh 命令）")
    parser.add_argument("--port", default="22")
    parser.add_argument("--user", default="root")
    parser.add_argument("--command", default="", help="自定义运行命令（留空＝仅安全验证，不运行训练）")
    parser.add_argument("--data-config", default="",
                        help="数据集（YAML/直链）；对自带数据管理或不需数据的命令填 repo-managed 可跳过数据集步骤")
    parser.add_argument("--timeout-min", type=int, default=30, help="单步超时分钟数")
    parser.add_argument("--local-dir", default=str(os.path.expanduser("~/paper_repro_data")))
    args = parser.parse_args()

    password = os.environ.get("CLOUD_PASSWORD", "")
    if not password:
        print("[错误] 请通过环境变量 CLOUD_PASSWORD 提供云服务器密码（仅内存，不落盘）。")
        return 2

    # 主机输入即时解析（与应用表单同一入口，允许整行 ssh 命令）
    from paper_repro_app.ssh_utils import resolve_connection_fields
    host = resolve_connection_fields(args.host, args.user, args.port).get("host") or args.host
    user = args.user
    port = args.port

    remote_dir = detect_remote_workdir(args.repo or args.paper, user, host)
    store = TaskStore(DB_PATH)
    auto_train = not bool(args.command)  # 与 App 一致：给出命令＝自定义运行；不给＝仅安全验证/自动识别
    task = store.create_task(
        paper_url=args.paper,
        repo_url=args.repo,
        host=host,
        user=user,
        ssh_key_path="",
        port=str(port),
        remote_workdir=remote_dir,
        local_data_dir=os.path.expanduser(args.local_dir),
        environment_mode="conda",
        run_command=args.command,
        command_timeout=int(args.timeout_min * 60),
        data_config=args.data_config,
        auto_download_dataset=auto_train,
        auto_run=auto_train,
        status="queued",
        current_step="queued",
    )
    task_id = task["id"]
    print(f"[创建任务] {task_id}")
    print(f"[仓库] {args.repo}\n[远端目录] {remote_dir}")
    print(f"[运行命令] {args.command or '（安全验证，不训练）'} | [数据集] {args.data_config or '自动发现'}")

    store.update_task_status(task_id, "running", "云端验证已启动…", current_step="prepare")
    started, msg = start_pipeline_execution(task_id, password=password)
    if not started:
        print(f"[启动失败] {msg}")
        store.update_task_status(task_id, "failed", msg, current_step="failed")
        return 3
    print("[启动] 流水线已在后台运行，开始轮询（输出较大时只显示状态变化与末段）…\n")

    terminal = {"success", "failed", "cancelled"}
    last_key = ""
    while True:
        row = store.get_task(task_id)
        status = str(row.get("status", "unknown")).lower()
        step = str(row.get("current_step") or "")
        log = str(row.get("log") or "")
        lines = [ln for ln in log.splitlines() if ln.strip()]
        tail = " | ".join(lines[-2:])[:200]
        key = f"{status}|{step}|{tail}"
        if key != last_key:
            print(f"[{time.strftime('%H:%M:%S')}] {status.upper():9s} step={step:10s} {tail}", flush=True)
            last_key = key
        if status in terminal:
            break
        time.sleep(5)

    print("\n========== 验证结束 ==========")
    print(f"状态：{status}")
    if status == "success":
        import json
        payload = json.loads(str(row.get("log") or "{}"))
        metrics = payload.get("metrics") or {}
        stdout_metrics = payload.get("stdout_metrics") or {}
        if metrics or stdout_metrics:
            print("复现收集指标：")
            for k, v in {**metrics, **stdout_metrics}.items():
                print(f"  {k} = {v}")
        print("详见 App「历史记录 / 任务监控」或报告：",
              os.path.expanduser(args.local_dir))
        return 0
    print("末段日志：")
    print("\n".join((row.get("log") or "").strip().splitlines()[-40:]))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
