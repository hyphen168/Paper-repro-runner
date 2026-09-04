"""任务编排与本地存储（自 app.py 外迁纯逻辑，零 streamlit 依赖）。"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from paper_repro_app.artifacts import ArtifactCollector
from paper_repro_app.comparison_table import generate_experiment_table
from paper_repro_app.database import TaskStore
from paper_repro_app.innovation_analysis import PaperInnovationAnalyzer
from paper_repro_app.paths import DB_PATH
from paper_repro_app.project_summary import generate_project_summary
from paper_repro_app.remote_runner import RemoteRunner
from paper_repro_app.remote_workdir import detect_remote_workdir as detect_remote_workdir  # noqa: F401
from paper_repro_app.report_generator import generate_repro_report

def _get_exec_state() -> dict:
    # 模块级惰性状态：Streamlit rerun 重跑脚本时会覆盖顶层赋值，
    # 因此只在缺失时创建，保证跨 rerun 保留后台线程引用。
    if "_EXEC_STATE" not in globals() or globals()["_EXEC_STATE"] is None:
        globals()["_EXEC_STATE"] = {}
    return globals()["_EXEC_STATE"]


def _run_pipeline_in_background(task_id: str) -> None:
    """后台线程执行完整复现流水线：逐步回调实时落库（30 行滚动窗口），
    完成后把分析/报告等结果写回任务记录。线程内不触碰任何 Streamlit API。"""
    store = TaskStore(DB_PATH)
    task = store.get_task(task_id)
    if not task:
        return
    # 密码只存在于进程内存（提交时注入），不落库：按任务 id 从内存密码表取回
    task["password"] = str(_get_exec_state().get("task_passwords", {}).get(task_id) or "")
    # 自动识别候选机（多台候选仅内存传递，不落库；重跑旧任务回落单机）
    task["hosts"] = _get_exec_state().get("task_hosts", {}).get(task_id) or []
    cancel_event = _get_exec_state().get("cancel_events", {}).get(task_id)
    runner = RemoteRunner(task)
    live_log: list[str] = []

    try:
        from paper_repro_app.ssh_utils import sanitize
    except ImportError:
        def sanitize(x):
            return x

    def on_step(step_id: str, step_title: str, message: str) -> None:
        timestamped = f"[{datetime.now().strftime('%H:%M:%S')}] [{step_id}] {sanitize(message.strip())}"
        live_log.append(timestamped)
        trimmed_log = "\n".join(live_log[-30:])
        store.update_task_status(task_id, "running", trimmed_log, current_step=step_id)

    on_step(
        "prepare",
        "准备工作目录",
        "已开始连接云端。若代码源在 13 秒内无响应，系统会立即提示网络或仓库地址问题。",
    )
    try:
        result = runner.execute(on_step=on_step, cancel_event=cancel_event)
    except Exception as exc:  # 兜底：线程内任何异常都必须落库，避免页面永远停留在“运行中”
        result = {"status": "failed", "message": f"流水线执行异常：{exc}"}
        store.update_task_status(task_id, "failed", json.dumps(result, ensure_ascii=False, indent=2), current_step="failed")
        return

    try:
        task = store.get_task(task_id)
        storage_layout = ensure_local_storage_tree(
            os.path.expanduser(task.get("local_data_dir") or str(Path.home() / "paper_repro_data")), task_id
        )

        # 失败/取消：只落日志与诊断，不再生成“成功报告”（避免误导）
        if str(result.get("status", "")).lower() != "success":
            payload = json.dumps(result, ensure_ascii=False, indent=2)
            status = str(result.get("status", "failed")).lower()
            if status == "cancelled":
                status = "cancelled"
            store.update_task_status(task_id, status, payload, current_step=result.get("failed_step") or status)
            return

        analyzer = PaperInnovationAnalyzer()
        analysis = analyzer.analyze(
            paper_url=task.get("paper_url", ""),
            repo_url=task.get("repo_url", ""),
            reproduction_logs=result.get("logs", "") if isinstance(result.get("logs"), str) else "",
            repo_dir=None,
        )
        result["analysis"] = analysis
        report = generate_repro_report(task, analysis)
        project_summary = generate_project_summary(task, analysis, report["report_path"])
        collected_metrics = result.get("metrics", {})
        comparison_table = generate_experiment_table(
            [
                {
                    "metric": name,
                    "paper": "待填充",
                    "repro": f"{value:.6g}" if isinstance(value, (int, float)) else str(value),
                    "gap": "待论文指标",
                    "note": "自动从 " + ", ".join(result.get("metric_sources", [])),
                }
                for name, value in collected_metrics.items()
            ]
            or [
                {
                    "metric": "实验指标",
                    "paper": "待填充",
                    "repro": "未发现",
                    "gap": "待比较",
                    "note": "请检查训练输出是否生成 results.csv 或 metrics.json。",
                }
            ]
        )
        result["report"] = report
        result["comparison_table"] = comparison_table
        result["project_summary"] = project_summary

        payload = json.dumps(result, ensure_ascii=False, indent=2)
        status = result.get("status", "unknown")
        store.update_task_status(task_id, status, payload, current_step=status)
        artifact_store = ArtifactCollector()
        artifact_store.collect(task_id, result)
        persist_task_artifacts(task, result, storage_layout, report, project_summary)
    except Exception as exc:  # 结果整理失败不影响主体执行结论
        store.update_task_status(task_id, "failed", f"结果整理阶段异常：{exc}", current_step="failed")


def start_pipeline_execution(task_id: str, password: str = "", hosts: list | None = None) -> tuple[bool, str]:
    """启动后台流水线线程；已有线程存活时拒绝重复启动。

    hosts: 自动识别候选（多台机器每行一条），执行时探测选可达者；None 回落任务单机。
    """
    state = _get_exec_state()
    thread = state.get("thread")
    if thread is not None and thread.is_alive():
        return False, "已有流水线正在后台运行，请等待其结束后再重试。"
    state.setdefault("task_passwords", {})[task_id] = password or state.get("task_passwords", {}).get(task_id, "")
    if hosts:
        state.setdefault("task_hosts", {})[task_id] = hosts
    state.setdefault("cancel_events", {})[task_id] = threading.Event()
    new_thread = threading.Thread(
        target=_run_pipeline_in_background,
        args=(task_id,),
        daemon=True,
        name=f"pipeline-{task_id}",
    )
    state["thread"] = new_thread
    state["task_id"] = task_id
    state["started_at"] = datetime.now()
    new_thread.start()
    return True, "流水线已在后台启动，页面每 2 秒自动刷新实时进度。"


def cancel_task(task_id: str, wait_seconds: float = 8.0) -> bool:
    """请求中止任务：置取消事件并等待后台线程退出（尽力而为）。

    远端 SSH 读取循环会在 0.2s 内感知并断开连接，使远端命令进程随之终止。
    返回线程是否已退出。
    """
    state = _get_exec_state()
    evt = state.get("cancel_events", {}).get(task_id)
    if evt is not None:
        evt.set()
    thread = state.get("thread")
    if thread is not None and thread.is_alive():
        thread.join(timeout=wait_seconds)
        return not thread.is_alive()
    return True


def is_task_running(task_id: str) -> bool:
    """当前是否有该任务的后台线程正在执行。"""
    state = _get_exec_state()
    thread = state.get("thread")
    return bool(thread is not None and thread.is_alive() and state.get("task_id") == task_id)


def resolve_repo_url(repo_hint: str, detected_repo: str | None) -> str:
    explicit_repo = (repo_hint or "").strip()
    if explicit_repo:
        return explicit_repo
    detected = (detected_repo or "").strip()
    if detected.rstrip("/") == "https://huggingface.co/huggingface":
        return ""
    return detected


def ensure_local_storage_tree(base_dir: str, task_id: str | None = None) -> dict[str, str]:
    root = Path(base_dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    structure = {
        "root": str(root),
        "logs": str(root / "logs"),
        "reports": str(root / "reports"),
        "artifacts": str(root / "artifacts"),
        "checkpoints": str(root / "checkpoints"),
        "tasks": str(root / "tasks"),
    }
    for folder in structure.values():
        Path(folder).mkdir(parents=True, exist_ok=True)
    if task_id:
        task_dir = root / "tasks" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        structure["task_dir"] = str(task_dir)
    return structure


def persist_task_artifacts(task: dict, result: dict, local_structure: dict[str, str], report: dict | None = None, project_summary: str | None = None) -> None:
    if not task:
        return
    root = Path(local_structure["root"])
    task_id = task.get("id", "unknown-task")
    logs_dir = Path(local_structure["logs"])
    reports_dir = Path(local_structure["reports"])
    artifacts_dir = Path(local_structure["artifacts"])
    task_dir = Path(local_structure.get("task_dir", root / "tasks" / task_id))
    for path in (logs_dir, reports_dir, artifacts_dir, task_dir):
        path.mkdir(parents=True, exist_ok=True)

    (logs_dir / f"{task_id}-run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if report and report.get("report_md"):
        (reports_dir / f"{task_id}-report.md").write_text(report["report_md"], encoding="utf-8")
    if project_summary:
        (reports_dir / f"{task_id}-summary.md").write_text(project_summary, encoding="utf-8")

    manifest = {
        "task_id": task_id,
        "status": task.get("status"),
        "current_step": task.get("current_step"),
        "host": task.get("host"),
        "user": task.get("user"),
        "remote_workdir": task.get("remote_workdir"),
        "local_data_dir": task.get("local_data_dir"),
        "generated_files": [
            str(logs_dir / f"{task_id}-run.json"),
            str(reports_dir / f"{task_id}-report.md"),
            str(reports_dir / f"{task_id}-summary.md"),
        ],
    }
    (task_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
