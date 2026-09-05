"""任务编排与本地存储（自 app.py 外迁纯逻辑，零 streamlit 依赖）。"""

from __future__ import annotations

import json
import os
import re
import threading
import time
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


# ================= G3 + P0-1：stdout 指标兜底与论文基准对比 =================
_STDOUT_METRIC_PATTERNS = [
    ("test_acc_pct", r"Accuracy of the network on the 10000 test images:\s*([\d.]+)\s*%", 1),
    ("test_acc_pct", r"Test set:.*?Accuracy:\s*([\d.]+)\s*%", 1),
    ("test_acc_pct", r"Accuracy:\s*([\d.]+)\s*%", 1),
    ("loss_d", r"Loss_D:\s*([\d.eE+-]+)\s+Loss_G:\s*([\d.eE+-]+)", 1),
    ("loss_g", r"Loss_D:\s*([\d.eE+-]+)\s+Loss_G:\s*([\d.eE+-]+)", 2),
    ("d_fake", r"D\(G\(z\)\):\s*([\d.eE+-]+)", 1),
]
_CLAIMS_CACHE = None


def _load_paper_claims() -> list:
    global _CLAIMS_CACHE
    if _CLAIMS_CACHE is None:
        try:
            claims_path = Path(__file__).resolve().parent / "paper_claims.json"
            _CLAIMS_CACHE = json.loads(claims_path.read_text(encoding="utf-8")).get("claims", [])
        except Exception:
            _CLAIMS_CACHE = []
    return _CLAIMS_CACHE


def merge_stdout_metrics(result: dict) -> dict:
    """从回传全量日志正则兜底提取 stdout 指标（accuracy/Loss 等），并入 result metrics。"""
    logs = str(result.get("logs") or "")
    stdout_metrics: dict = {}
    for name, pattern, group in _STDOUT_METRIC_PATTERNS:
        matches = re.findall(pattern, logs)
        if not matches:
            continue
        last = matches[-1]
        try:
            if isinstance(last, tuple):
                stdout_metrics[name] = float(last[group - 1])
            else:
                stdout_metrics[name] = float(last)
        except (TypeError, ValueError):
            continue
    metrics = dict(result.get("metrics") or {})
    merged = dict(metrics)
    for key, value in stdout_metrics.items():
        merged.setdefault(key, value)
    result["metrics"] = merged
    result["stdout_metrics"] = stdout_metrics
    if merged:
        result["metric_verdict"] = "metrics_collected"
    else:
        result["metric_verdict"] = "no_metrics_output"
    return merged


def _match_paper_claims(text: str) -> list:
    lowered = (text or "").lower()
    return [entry for entry in _load_paper_claims()
            if any(keyword.lower() in lowered for keyword in entry.get("keywords", []))]


def _claim_repro_value(claim: dict, metrics: dict):
    derive = claim.get("derive")
    if derive:
        raw = metrics.get(derive.get("from"))
        if raw is None:
            return None
        try:
            if derive.get("op") == "100-x":
                return 100.0 - float(raw)
        except (TypeError, ValueError):
            return None
        return None
    return metrics.get(claim.get("metric_key"))


def build_comparison_table(result: dict, task: dict) -> str:
    """按 paper_claims.json 基准组装对比表（无基准录入时给单行说明，杜绝伪造占位行）。"""
    metrics = merge_stdout_metrics(result)
    blob = " ".join([
        str(task.get("repo_url") or ""),
        str(task.get("paper_url") or ""),
        str(task.get("run_command") or ""),
    ])
    matched = _match_paper_claims(blob)
    rows: list = []
    for entry in matched:
        level = entry.get("level", "L3")
        for claim in entry.get("claims", []):
            label = claim.get("metric_label") or claim.get("metric_key") or "指标"
            paper_value = claim.get("paper_value")
            rv = _claim_repro_value(claim, metrics)
            direction = claim.get("direction", "higher")
            unit = claim.get("unit", "")
            paper_txt = (str(paper_value) + unit) if paper_value is not None else "执行期回填"
            repro_txt = ""
            if rv is not None:
                repro_txt = f"{rv:.6g}".rstrip("0").rstrip(".")
                if unit:
                    repro_txt += unit
            else:
                repro_txt = "未发现"
            gap_txt = "—"
            if rv is not None and paper_value is not None:
                try:
                    diff = float(rv) - float(paper_value)
                    if unit == "%":
                        gap_txt = f"{diff:+.2f} pp"
                    else:
                        gap_txt = f"{diff:+.4g}"
                except (TypeError, ValueError):
                    gap_txt = "—"
            note = f"口径：{entry.get('caliber') or ''}；级别 {level}"
            if claim.get("note"):
                note += "；" + claim["note"]
            rows.append({
                "metric": label,
                "paper": paper_txt + (f"[{claim.get('source') or ''}]" if paper_value is not None else ""),
                "repro": repro_txt,
                "gap": gap_txt,
                "note": note,
            })
    for name, value in sorted(metrics.items()):
        if name in {"test_acc_pct", "loss_d", "loss_g", "d_fake"}:
            continue
        if any(name == (c.get("metric_key") or "") for entry in matched for c in entry.get("claims", [])):
            continue
        rows.append({
            "metric": str(name),
            "paper": "—",
            "repro": f"{value:.6g}" if isinstance(value, (int, float)) else str(value),
            "gap": "—",
            "note": "自动收集（无论文基准录入，不参与对比）",
        })
    if not rows:
        rows = [{
            "metric": "实验指标",
            "paper": "—",
            "repro": "未发现",
            "gap": "—",
            "note": "论文基准未录入（paper_claims.json）或复现未输出指标，本次未做指标对比。",
        }]
    # 结构化对比行随任务结果落库，供界面渲染结果对比图（条形/分组柱状）
    result["comparison_rows"] = rows
    return generate_experiment_table(rows)


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
    # 断点续跑 / 命令覆盖（AI 修复后从失败步继续）：仅内存传递
    _rs = str(_get_exec_state().get("task_resume", {}).get(task_id) or "")
    if _rs:
        task["resume_step"] = _rs
    _ov = _get_exec_state().get("task_override_cmd", {}).get(task_id)
    if _ov:
        task["run_command"] = _ov
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
        result = runner.execute(on_step=on_step, cancel_event=cancel_event,
                                resume_from=str(task.get("resume_step") or ""))
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
        comparison_table = build_comparison_table(result, task)
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


def start_pipeline_execution(task_id: str, password: str = "", hosts: list | None = None,
                             resume_step: str = "", run_command: str | None = None) -> tuple[bool, str]:
    """启动后台流水线线程；已有线程存活时拒绝重复启动。

    hosts: 自动识别候选（多台机器每行一条），执行时探测选可达者；None 回落任务单机。
    resume_step: 非空时从该步骤断点续跑（跳过前面已完成步骤）。
    run_command: 非空时覆盖任务的训练/验证命令（AI 修复场景）。
    """
    state = _get_exec_state()
    thread = state.get("thread")
    if thread is not None and thread.is_alive():
        return False, "已有流水线正在后台运行，请等待其结束后再重试。"
    state.setdefault("task_passwords", {})[task_id] = password or state.get("task_passwords", {}).get(task_id, "")
    if hosts:
        state.setdefault("task_hosts", {})[task_id] = hosts
    if resume_step:
        state.setdefault("task_resume", {})[task_id] = resume_step
    if run_command:
        state.setdefault("task_override_cmd", {})[task_id] = run_command
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


# ================= 批量串行调度器（队列中任务按创建顺序依次执行，同一时刻只跑一个） =================
def _drainer_loop() -> None:
    """批量调度线程：空闲时等 kick；有 queued 任务时标记 running、启动流水线线程并等待其结束，
    结束后取下一个。任何异常都不退出线程（置当前任务 failed 后继续），避免批量任务被卡死。"""
    state = _get_exec_state()
    store = TaskStore(DB_PATH)
    while not state.get("drain_stop", False):
        try:
            task = store.get_oldest_queued()
            if not task:
                evt = state.get("wake")
                if evt is None:
                    state["wake"] = threading.Event()
                    evt = state["wake"]
                evt.clear()
                evt.wait(timeout=6.0)
                continue
            task_id = str(task.get("id") or "")
            if not task_id:
                continue
            # 先创建取消事件，再置 running，避免“取消发生在取件与启动之间”的竞态丢事件
            state.setdefault("cancel_events", {})[task_id] = threading.Event()
            try:
                store.update_task_status(
                    task_id, "running",
                    "批量任务开始执行：调度器已接管，批次内任务按创建顺序依次运行（同一时刻仅一个任务占用云端）。",
                    current_step="prepare",
                )
            except Exception:
                pass
            # 二次确认：置 running 期间若已被外部取消/跳过则直接取下一件
            try:
                _cur = store.get_task(task_id)
                if str((_cur or {}).get("status", "")).lower() != "running":
                    continue
            except Exception:
                pass
            t = threading.Thread(
                target=_run_pipeline_in_background,
                args=(task_id,),
                daemon=True,
                name=f"pipeline-{task_id}",
            )
            state["thread"] = t
            state["task_id"] = task_id
            state["started_at"] = datetime.now()
            t.start()
            t.join()
            # 兜底：流水线线程意外崩溃且未落终态时，标记失败以免“永远 running”
            try:
                after = store.get_task(task_id)
                if str((after or {}).get("status", "running")).lower() in {"queued", "running"}:
                    store.update_task_status(task_id, "failed",
                                             "批量执行器检测到流水线线程异常退出（可能应用被关闭）。可到「任务监控」点击重新执行。",
                                             current_step="failed")
            except Exception:
                pass
        except Exception:
            # 线程内任何异常都不得中断调度循环
            try:
                time.sleep(1.0)
            except Exception:
                pass


def ensure_batch_drainer() -> None:
    """确保批量调度线程存在并唤醒；幂等。"""
    state = _get_exec_state()
    evt = state.get("wake")
    if evt is not None:
        evt.set()
    drainer = state.get("drainer")
    if drainer is not None and drainer.is_alive():
        return
    state["wake"] = threading.Event()
    new_drainer = threading.Thread(target=_drainer_loop, daemon=True, name="batch-drainer")
    state["drainer"] = new_drainer
    new_drainer.start()


def wake_batch_drainer() -> None:
    """有新排队任务时调用：立即唤醒调度线程去取件。"""
    state = _get_exec_state()
    evt = state.get("wake")
    if evt is not None:
        evt.set()
    drainer = state.get("drainer")
    if drainer is None or not drainer.is_alive():
        ensure_batch_drainer()


def cancel_batch(batch_id: str) -> int:
    """取消整批：排队任务直接标记结束，正在运行的请求中止。返回受影响数量。"""
    store = TaskStore(DB_PATH)
    tasks = store.list_tasks_by_batch(batch_id)
    affected = 0
    for task in tasks:
        status = str(task.get("status", "")).lower()
        if status in {"queued", "running"}:
            store.update_task_status(
                task["id"], "cancelled", "批量任务已由用户取消。", current_step="cancelled")
            cancel_task(task["id"], wait_seconds=2.0)
            affected += 1
    return affected


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
