from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

# Force UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
elif hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "paper_repro_app"))

from paper_repro_app.database import TaskStore
from paper_repro_app.log_analyzer import LogAnalyzer
from paper_repro_app.logging_config import DEFAULT_LOG_FILE


def main():
    parser = argparse.ArgumentParser(description="论文复现助手 - 后台运行日志快速定位与诊断工具")
    parser.add_argument("--task-id", type=str, help="指定需要分析的任务 ID（如 task-bd6699a7）")
    parser.add_argument("--db-path", type=str, help="SQLite 任务数据库路径")
    parser.add_argument("--tail", type=int, default=30, help="显示日志结尾行数 (默认 30)")
    args = parser.parse_args()

    db_path = Path(args.db_path) if args.db_path else PROJECT_ROOT / "paper_repro_app" / "data" / "tasks.db"
    if not db_path.exists():
        db_path = PROJECT_ROOT / "paper_repro_app" / "paper_repro_app" / "data" / "tasks.db"

    print("=" * 60)
    print(" 🛠️  论文复现助手 - 运行日志快速定位与诊断系统")
    print("=" * 60)

    # 1. Inspect System Application Log File
    if DEFAULT_LOG_FILE.exists():
        print(f"\n📂 本地后台系统日志文件: {DEFAULT_LOG_FILE}")
        lines = DEFAULT_LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        print(f"   (系统总日志条数: {len(lines)} 行)")
        if lines:
            print("\n系统最新 5 条后台运行日志:")
            for line in lines[-5:]:
                print(f"   {line}")
    else:
        print(f"\n📂 系统日志文件尚未生成 (路径: {DEFAULT_LOG_FILE})")

    # 2. Inspect Task Database Logs
    if not db_path.exists():
        print(f"\n❌ 未找到任务数据库: {db_path}")
        sys.exit(1)

    store = TaskStore(db_path)
    tasks = store.list_tasks(limit=10)

    if not tasks:
        print("\nℹ️  数据库中尚无任务记录。")
        sys.exit(0)

    target_task = None
    if args.task_id:
        target_task = store.get_task(args.task_id)
        if not target_task:
            print(f"\n❌ 未找到指定 ID 的任务: {args.task_id}")
            sys.exit(1)
    else:
        # Find latest failed task, or default to the most recent task
        failed_tasks = [t for t in tasks if t.get("status") in {"failed", "error"}]
        target_task = failed_tasks[0] if failed_tasks else tasks[0]

    print("\n" + "-" * 60)
    print(f"📌 当前分析任务 ID : {target_task['id']}")
    print(f"   任务状态       : {target_task.get('status')}")
    print(f"   当前/失败步骤   : {target_task.get('current_step')}")
    print(f"   云端主机       : {target_task.get('host')}:{target_task.get('port')}")
    print(f"   代码仓库       : {target_task.get('repo_url')}")
    print(f"   创建时间       : {target_task.get('created_at')}")
    print("-" * 60)

    raw_log = target_task.get("log") or ""
    analyzer = LogAnalyzer()
    report = analyzer.analyze_log(raw_log)

    print("\n🔍 【智能错误定位与根因诊断报告】")
    print(f"  • 错误类别 : {report['error_category']}")
    print(f"  • 触发步骤 : {report['failed_step']}")
    print("\n📍 【精确报错代码/日志片段】:")
    print("--------------------------------------------------")
    print(report['error_snippet'])
    print("--------------------------------------------------")
    print(f"\n💡 【根因分析】:\n  {report['cause']}")
    print(f"\n🔧 【推荐解决方案】:\n  {report['suggestion']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
