import json
import os
import re
import shlex
import socket
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st

try:
    from tkinter import Tk
    from tkinter.filedialog import askdirectory
except Exception:  # pragma: no cover - GUI may not be available in headless environments
    Tk = None
    askdirectory = None

from paper_repro_app.artifacts import ArtifactCollector
from paper_repro_app.config_store import LocalConfigStore
from paper_repro_app.database import TaskStore
from paper_repro_app.diagnostics import EnvironmentDiagnostics
from paper_repro_app.comparison_table import generate_experiment_table
from paper_repro_app.innovation_analysis import PaperInnovationAnalyzer
from paper_repro_app.paper_parser import extract_repo_url
from paper_repro_app.project_summary import generate_project_summary
from paper_repro_app.remote_runner import RemoteRunner
from paper_repro_app.report_generator import generate_repro_report


DATA_DB_PATH = Path("paper_repro_app/data/tasks.db")


def format_log_preview(raw_log: str | None, max_entries: int = 3) -> str:
    if not raw_log:
        return "等待任务开始..."
    lines = [line.strip() for line in str(raw_log).splitlines() if line.strip()]
    formatted = []
    for line in lines:
        if re.match(r"^\[\d{2}:\d{2}:\d{2}\]", line):
            formatted.append(line)
        else:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
    if not formatted:
        return "等待任务开始..."
    return "\n".join(formatted[-max_entries:])


def parse_ssh_target(raw_target: str) -> dict[str, str]:
    target = (raw_target or "").strip()
    if not target:
        return {}

    candidate = {"user": "", "host": "", "port": "", "key": ""}
    words = shlex.split(target)
    if not words:
        return {}

    for index, token in enumerate(words):
        if token == "ssh":
            continue
        if token.startswith("-"):
            if token in {"-p", "-i"} and index + 1 < len(words):
                value = words[index + 1]
                if token == "-p":
                    candidate["port"] = value
                elif token == "-i":
                    candidate["key"] = value
            elif token.startswith("-p") and len(token) > 2:
                candidate["port"] = token[2:]
            elif token.startswith("-i") and len(token) > 2:
                candidate["key"] = token[2:]
            continue

        if "@" in token and candidate["host"] == "":
            user, host = token.split("@", 1)
            candidate["user"] = user.strip()
            candidate["host"] = host.strip()
            continue

        if candidate["host"] == "" and token not in {"ssh"}:
            candidate["host"] = token.strip()

    if candidate["host"] == "" and "@" in target:
        left, right = target.split("@", 1)
        candidate["user"] = left.strip().lstrip("ssh ")
        candidate["host"] = right.strip().split()[0]

    if candidate["host"] and not candidate["user"]:
        match = re.search(r"(?P<user>[A-Za-z0-9_.-]+)@(?P<host>[A-Za-z0-9_.-]+)", target)
        if match:
            candidate["user"] = match.group("user")
            candidate["host"] = match.group("host")

    if candidate["host"] and candidate["host"].isdigit() and candidate["port"]:
        candidate["host"] = ""

    return {key: value for key, value in candidate.items() if value}


def get_ssh_config_path() -> Path:
    return Path.home() / ".ssh" / "config"


def parse_ssh_config(host_hint: str = "") -> dict[str, str]:
    config_path = get_ssh_config_path()
    if not config_path.exists():
        return {}

    profile: dict[str, str] = {}
    current: dict[str, str] = {}
    target_host = (host_hint or "").strip().lower()

    try:
        lines = config_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return {}

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("host "):
            if current and target_host:
                hosts = [item.strip().lower() for item in current.get("host_aliases", "").split() if item.strip()]
                if target_host in hosts or target_host == current.get("hostname", "").lower():
                    profile = current
                    break
            current = {"host_aliases": line.split(None, 1)[1]}
            continue
        if not current:
            continue
        if " " not in line:
            continue
        key, value = line.split(None, 1)
        key_name = key.lower()
        if key_name == "hostname":
            current["hostname"] = value.strip()
        elif key_name == "user":
            current["user"] = value.strip()
        elif key_name == "port":
            current["port"] = value.strip()
        elif key_name == "identityfile":
            current["key"] = value.strip()

    if current and target_host:
        hosts = [item.strip().lower() for item in current.get("host_aliases", "").split() if item.strip()]
        if target_host in hosts or target_host == current.get("hostname", "").lower():
            profile = current

    if not profile and target_host:
        profile = {}

    hostname = profile.get("hostname") or profile.get("host_aliases", "").split()[0]
    resolved = {
        "host": hostname,
        "user": profile.get("user", ""),
        "port": profile.get("port", ""),
        "key": profile.get("key", ""),
    }
    return {key: value for key, value in resolved.items() if value}


def resolve_ssh_profile(raw_target: str = "", fallback_host: str = "", fallback_user: str = "", fallback_key: str = "") -> dict[str, str]:
    parsed = parse_ssh_target(raw_target)
    config = parse_ssh_config((parsed.get("host") or fallback_host or "").strip())
    final_host = parsed.get("host") or config.get("host") or fallback_host or ""
    final_user = parsed.get("user") or config.get("user") or fallback_user or ""
    final_port = parsed.get("port") or config.get("port") or "22"
    final_key = parsed.get("key") or config.get("key") or fallback_key or ""
    return {
        "host": final_host,
        "user": final_user,
        "port": final_port,
        "key": final_key,
    }


def detect_remote_workdir(repo_hint: str, user: str = "", host: str = "") -> str:
    repo_name = (repo_hint or "paper-repro").strip().rstrip("/")
    repo_name = repo_name.split("/")[-1].replace(".git", "") or "paper-repro"
    candidate_paths = [
        f"/home/{user}/paper-repro" if user else "/home/ubuntu/paper-repro",
        f"/workspace/{repo_name}",
        f"/workspace/{user}/{repo_name}" if user else "/workspace/paper-repro",
        f"/opt/{repo_name}",
        f"/home/{user}/{repo_name}" if user else "/home/ubuntu/paper-repro",
    ]
    for path in candidate_paths:
        if path not in {"", None}:
            return path
    return "/workspace/paper-repro"


def open_directory_dialog(default_path: str) -> str:
    base_dir = default_path or str(Path.home() / "paper_repro_data")
    if Tk is None or askdirectory is None:
        return base_dir
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = askdirectory(initialdir=base_dir, title="选择本地存储目录")
    root.destroy()
    return selected or base_dir


def get_step_order() -> list[str]:
    return ["prepare", "clone", "env", "install", "verify", "collect"]


def estimate_completion(task: dict | None) -> str:
    if not task:
        return "待估算"
    status = str(task.get("status", "queued")).lower()
    if status in {"success", "failed", "cancelled"}:
        return "已结束"

    order = get_step_order()
    current_step = task.get("current_step") or "prepare"
    idx = order.index(current_step) if current_step in order else 0
    remaining_minutes = [2, 3, 4, 5, 4, 2][idx:]
    remaining = sum(remaining_minutes) if remaining_minutes else 3
    if task.get("status") == "running":
        eta = datetime.now() + timedelta(minutes=remaining)
        return eta.strftime("%H:%M")
    eta = datetime.now() + timedelta(minutes=max(3, remaining))
    return eta.strftime("%H:%M")


def render_particle_background() -> None:
    particles = []
    for idx in range(90):
        left = (idx * 7 + 9) % 100
        top = (idx * 11 + 13) % 100
        size = 3 + (idx % 9)
        delay = (idx % 16) * 0.45
        duration = 2.5 + (idx % 11) * 0.7
        drift_x = (-18 + (idx % 13) * 3)
        drift_y = (-22 + (idx % 9) * 5)
        opacity = 0.24 + (idx % 6) * 0.12
        particles.append(
            f"<span class='particle' style='left:{left}%; top:{top}%; width:{size}px; height:{size}px; opacity:{opacity}; transform: translate3d(0,0,0); animation-delay:{delay}s; animation-duration:{duration}s; --drift-x:{drift_x}px; --drift-y:{drift_y}px;'></span>"
        )
    st.markdown(
        f"""
        <div class="particle-field">{''.join(particles)}</div>
        """,
        unsafe_allow_html=True,
    )


def render_repro_progress(task: dict | None) -> None:
    steps = get_step_order()
    order = {name: idx for idx, name in enumerate(steps)}
    current = (task or {}).get("current_step") or "prepare"
    current_idx = order.get(current, 0)
    progress = min(100, max(8, int(((current_idx + 1) / len(steps)) * 100)))
    status_value = str((task or {}).get("status", "queued")).lower()
    status_labels = {
        "queued": "待开始",
        "running": "执行中",
        "success": "已完成",
        "failed": "失败",
        "cancelled": "已结束",
        "unknown": "待配置",
    }

    panel_html = f"""
    <div class='panel' style='padding: 1rem; margin-top: 1rem; background: linear-gradient(135deg, rgba(9,18,31,0.86), rgba(22,12,27,0.9));'>
        <div class='panel-title'>复现过程可视化</div>
        <div style='display:flex; align-items:center; justify-content:space-between; margin-bottom: 0.5rem; color: var(--muted); font-size:0.78rem;'>
            <span>实时进度</span>
            <span style='color: var(--amber); font-weight: 700;'>{status_labels.get(status_value, '待开始')}</span>
        </div>
        <div class='progress-shell'><div class='progress-fill' style='width:{progress}%;'></div></div>
        <div class='compact-progress'>
            <div class='compact-step-row'>
    """
    step_html = []
    for idx, step in enumerate(steps):
        label = {
            "prepare": "准备工作目录",
            "clone": "拉取代码",
            "env": "环境诊断",
            "install": "安装依赖",
            "verify": "执行验证",
            "collect": "收集结果",
        }.get(step, step)
        if idx < current_idx:
            tone = "compact-step done"
        elif idx == current_idx:
            tone = "compact-step active"
        else:
            tone = "compact-step"
        step_html.append(f"<div class='{tone}'><span class='step-index'>{idx + 1}</span>{label}</div>")
    panel_html += "".join(step_html)
    panel_html += """
            </div>
        </div>
    </div>
    """
    st.markdown(panel_html, unsafe_allow_html=True)


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


def render_task_telemetry(task: dict | None, local_structure: dict[str, str] | None = None, logs: str = "") -> None:
    if not task:
        return
    summary = local_structure or {}
    status = str(task.get("status", "queued")).lower()
    current_step = task.get("current_step") or "prepare"
    log_preview = format_log_preview(logs or task.get("log") or "暂无日志")
    metrics = [
        ("任务状态", status or "queued"),
        ("当前阶段", current_step),
        ("云端主机", task.get("host") or "未配置"),
        ("远程目录", task.get("remote_workdir") or "未配置"),
    ]
    metric_html = "".join(
        f"<div class='telemetry-metric'><span class='telemetry-label'>{label}</span><strong>{value}</strong></div>" for label, value in metrics
    )
    local_paths = "".join(
        f"<li><span>{name}</span><code>{path}</code></li>" for name, path in summary.items() if path
    ) or "<li>未生成本地目录</li>"
    st.markdown(
        f"""
        <div class='panel' style='padding: 1rem; margin-top: 1rem;'>
            <div class='panel-title'>云端训练监控</div>
            <div class='telemetry-grid'>{metric_html}</div>
            <div class='telemetry-subpanel'>
                <div class='mini-title'>本地目录结构</div>
                <ul class='directory-list'>{local_paths}</ul>
            </div>
            <div class='telemetry-subpanel'>
                <div class='mini-title'>实时日志</div>
                <pre class='telemetry-log'>{log_preview}</pre>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_task_state(task_id: str, status: str, current_step: str, message: str) -> None:
    store = TaskStore(DATA_DB_PATH)
    store.update_task_status(task_id, status, message, current_step=current_step)
    st.session_state["task_log_preview"] = (message or "")[:4000]
    render_repro_progress({"status": status, "current_step": current_step})


def get_local_ips() -> list[str]:
    ips: list[str] = []
    try:
        for family, _, _, _, sockaddr in socket.getaddrinfo(
            socket.gethostname(), None, type=socket.SOCK_DGRAM
        ):
            ip = sockaddr[0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips or ["127.0.0.1"]


def get_status_color(status: str) -> str:
    palette = {
        "queued": "orange",
        "running": "blue",
        "success": "green",
        "failed": "red",
        "unknown": "gray",
    }
    return palette.get(status, "gray")


def render_pipeline_steps(task: dict) -> None:
    runner = RemoteRunner(task)
    steps = runner.build_pipeline()
    st.subheader("复现流水线")
    for idx, step in enumerate(steps, start=1):
        st.markdown(f"### {idx}. {step['title']}")
        st.code(step["command"])


def render_app() -> None:
    st.set_page_config(page_title="论文复现助手", layout="wide")
    st.markdown(
        """
        <style>
        :root {
            --bg-0: #02070d;
            --bg-1: #091928;
            --bg-2: #160f1c;
            --panel: rgba(11, 19, 32, 0.86);
            --panel-strong: rgba(14, 24, 40, 0.96);
            --line: rgba(86, 240, 255, 0.42);
            --cyan: #56f0ff;
            --pink: #ff4fd8;
            --purple: #8a7dff;
            --green: #8ff7c6;
            --amber: #ffc857;
            --text: #ebf7ff;
            --muted: #9bb3c9;
            --red: #ff5a8a;
            --shadow: rgba(86, 240, 255, 0.26);
            --bright-cyan: #7ef7ff;
            --bright-pink: #ff7ae9;
        }
        .stApp {
            background:
                radial-gradient(circle at 8% 10%, rgba(86, 240, 255, 0.17), transparent 22%),
                radial-gradient(circle at 92% 10%, rgba(255, 79, 216, 0.14), transparent 18%),
                radial-gradient(circle at 50% 80%, rgba(138, 125, 255, 0.12), transparent 28%),
                linear-gradient(135deg, var(--bg-0), var(--bg-1) 38%, var(--bg-2));
            color: var(--text);
        }
        .stApp > div, .stSidebar > div {
            background: transparent;
        }
        .stSidebar > div {
            background: linear-gradient(180deg, rgba(8, 16, 28, 0.76), rgba(8, 13, 22, 0.86));
            border-right: 1px solid var(--line);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
        }
        h1, h2, h3, h4 {
            color: var(--cyan);
            letter-spacing: 0.08em;
            text-shadow: 0 0 12px rgba(86, 240, 255, 0.8);
        }
        .block-container {
            padding-top: 0.8rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }
        .stTextInput > div > div > input, .stSelectbox > div > div, .stTextArea > div > div {
            background: rgba(9, 17, 29, 0.9);
            border: 1px solid var(--line);
            border-radius: 12px;
            color: var(--text);
            box-shadow: inset 0 0 12px rgba(86, 240, 255, 0.04);
        }
        .particle-field {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }
        .particle {
            position: absolute;
            display: block;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(126,247,255,0.95), rgba(255,122,233,0.78), rgba(138,125,255,0.15), transparent 78%);
            box-shadow: 0 0 14px rgba(126,247,255,0.9), 0 0 28px rgba(255,122,233,0.42);
            animation: floatParticle linear infinite alternate;
            filter: blur(0.4px);
        }
        @keyframes floatParticle {
            0% { transform: translate3d(0, 0, 0) scale(0.8); opacity: 0.15; }
            25% { transform: translate3d(calc(var(--drift-x) * 0.5), calc(var(--drift-y) * -0.4), 0) scale(1.2); opacity: 0.75; }
            50% { transform: translate3d(var(--drift-x), calc(var(--drift-y) * -0.8), 0) scale(1.7); opacity: 1; }
            75% { transform: translate3d(calc(var(--drift-x) * -0.7), var(--drift-y), 0) scale(1.3); opacity: 0.82; }
            100% { transform: translate3d(calc(var(--drift-x) * -0.3), calc(var(--drift-y) * 0.8), 0) scale(0.85); opacity: 0.4; }
        }
        .main-layout > div:nth-child(1) {
            z-index: 1;
            position: relative;
        }
        .main-layout > div:nth-child(2) {
            z-index: 1;
            position: relative;
        }
        .progress-shell {
            height: 14px;
            background: rgba(255,255,255,0.06);
            border: 1px solid rgba(87,240,255,0.22);
            border-radius: 999px;
            overflow: hidden;
            margin-bottom: 0.8rem;
        }
        .progress-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--cyan), var(--pink), var(--amber));
            box-shadow: 0 0 18px rgba(87,240,255,0.35);
            transition: width 0.35s ease;
        }
        .compact-progress {
            display: grid;
            gap: 0.55rem;
            margin-top: 0.5rem;
        }
        .compact-step-row {
            display: flex;
            gap: 0.45rem;
            overflow-x: auto;
            padding-bottom: 0.25rem;
            scrollbar-width: thin;
        }
        .compact-step {
            flex: 0 0 auto;
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.35rem 0.55rem;
            border-radius: 999px;
            border: 1px solid rgba(86,240,255,0.22);
            background: rgba(15,22,35,0.72);
            color: var(--muted);
            font-size: 0.68rem;
            white-space: nowrap;
        }
        .compact-step.done {
            border-color: rgba(127,245,201,0.5);
            background: rgba(10,25,22,0.7);
            color: var(--green);
        }
        .compact-step.active {
            border-color: rgba(255,85,216,0.5);
            background: rgba(34, 12, 29, 0.9);
            color: var(--amber);
            box-shadow: 0 0 18px rgba(255,85,216,0.18);
        }
        .step-index {
            width: 22px;
            height: 22px;
            display: inline-flex;
            justify-content: center;
            align-items: center;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(87,240,255,0.24), rgba(143,126,255,0.2));
            color: var(--cyan);
            font-weight: 800;
            font-size: 0.68rem;
        }
        .floating-mini {
            background: rgba(10,16,28,0.76);
            border: 1px solid rgba(86,240,255,0.24);
            border-radius: 12px;
            padding: 0.8rem 0.9rem;
            box-shadow: 0 0 18px rgba(86,240,255,0.08);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }
        .mini-title {
            color: var(--cyan);
            font-size: 0.7rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }
        div[data-testid="stFormSubmitButton"] button,
        .stButton > button {
            background: linear-gradient(135deg, rgba(86, 240, 255, 0.28), rgba(154, 123, 255, 0.24), rgba(255, 79, 216, 0.16));
            color: var(--text);
            border: 1px solid var(--cyan);
            border-radius: 14px;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            box-shadow: 0 0 24px rgba(86, 240, 255, 0.22), 0 0 18px rgba(255, 79, 216, 0.15);
            min-height: 52px;
            font-size: 0.96rem;
        }
        div[data-testid="stFormSubmitButton"] button:hover,
        .stButton > button:hover {
            border-color: var(--pink);
            box-shadow: 0 0 28px rgba(255, 79, 216, 0.28), 0 0 20px rgba(86, 240, 255, 0.22);
            transform: translateY(-1px);
        }
        [data-testid="stCodeBlock"] {
            background: rgba(5, 10, 18, 0.8);
            border: 1px solid rgba(86, 240, 255, 0.25);
            border-radius: 12px;
        }
        .telemetry-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 0.7rem;
            margin-top: 0.6rem;
        }
        .telemetry-metric {
            background: rgba(10,17,27,0.72);
            border: 1px solid rgba(86,240,255,0.22);
            border-radius: 12px;
            padding: 0.7rem 0.8rem;
            display: flex;
            flex-direction: column;
            gap: 0.2rem;
        }
        .telemetry-label {
            color: var(--muted);
            font-size: 0.7rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .telemetry-metric strong {
            color: var(--bright-cyan);
            font-size: 0.92rem;
            word-break: break-all;
        }
        .telemetry-subpanel {
            margin-top: 0.9rem;
            background: rgba(9, 17, 29, 0.74);
            border: 1px solid rgba(86,240,255,0.2);
            border-radius: 12px;
            padding: 0.8rem 0.85rem;
        }
        .directory-list {
            margin: 0.4rem 0 0;
            padding-left: 1rem;
            color: var(--text);
            line-height: 1.8;
        }
        .directory-list li {
            display: flex;
            justify-content: space-between;
            gap: 0.6rem;
            align-items: center;
        }
        .directory-list code {
            color: var(--green);
            font-size: 0.72rem;
            background: rgba(8, 12, 18, 0.75);
            border-radius: 8px;
            padding: 0.1rem 0.3rem;
            white-space: nowrap;
        }
        .telemetry-log {
            margin: 0.5rem 0 0;
            white-space: pre-wrap;
            word-break: break-word;
            font-size: 0.75rem;
            line-height: 1.6;
            color: var(--text);
            background: rgba(3, 8, 15, 0.82);
            border: 1px solid rgba(86,240,255,0.2);
            border-radius: 10px;
            padding: 0.7rem;
            max-height: 220px;
            overflow: auto;
        }
        .console-shell {
            background: linear-gradient(180deg, rgba(12, 18, 30, 0.70), rgba(17, 26, 42, 0.92));
            border: 1px solid rgba(86, 240, 255, 0.38);
            border-radius: 20px;
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            box-shadow: inset 0 0 18px rgba(86, 240, 255, 0.08), 0 0 22px rgba(86, 240, 255, 0.09);
            padding: 0.8rem 1rem 0.9rem;
            margin-bottom: 1rem;
        }
        .console-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(86, 240, 255, 0.28);
            padding: 0.3rem 0 0.75rem;
            color: var(--muted);
            font-size: 0.75rem;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }
        .traffic-lights {
            display: flex;
            gap: 0.45rem;
        }
        .dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        .dot.red { background: var(--red); }
        .dot.yellow { background: var(--amber); }
        .dot.green { background: var(--green); }
        .console-grid {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.9rem;
            margin: 1rem 0 1.2rem;
        }
        .console-card {
            background: rgba(11, 19, 32, 0.72);
            border: 1px solid rgba(86, 240, 255, 0.22);
            border-radius: 14px;
            padding: 0.95rem 1rem;
            min-height: 132px;
            box-shadow: inset 0 0 12px rgba(86, 240, 255, 0.04), 0 0 12px rgba(86, 240, 255, 0.04);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
        }
        .console-card:hover {
            transform: translateY(-2px);
            border-color: rgba(255, 79, 216, 0.42);
            box-shadow: inset 0 0 12px rgba(255, 79, 216, 0.06), 0 0 16px rgba(255, 79, 216, 0.10);
        }
        .main-stack {
            display: grid;
            grid-template-columns: 2.2fr 0.8fr;
            gap: 1rem;
            align-items: start;
        }
        .primary-panel {
            background: rgba(8, 17, 28, 0.8);
            border: 1px solid rgba(86, 240, 255, 0.35);
            border-radius: 18px;
            box-shadow: inset 0 0 16px rgba(86, 240, 255, 0.06), 0 0 20px rgba(86, 240, 255, 0.08);
            padding: 1rem 1rem 1.1rem;
            min-height: 200px;
        }
        .secondary-stack {
            display: grid;
            gap: 0.8rem;
            position: relative;
        }
        .floating-card {
            background: rgba(12, 19, 32, 0.78);
            border: 1px solid rgba(86, 240, 255, 0.22);
            border-radius: 16px;
            padding: 0.8rem 0.9rem;
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            box-shadow: 0 0 18px rgba(86, 240, 255, 0.06);
        }
        .floating-card.small {
            transform: translateX(6px);
            opacity: 0.9;
        }
        .console-card .label {
            color: var(--muted);
            text-transform: uppercase;
            letter-spacing: 0.1em;
            font-size: 0.7rem;
            margin-bottom: 0.5rem;
        }
        .console-card .value {
            color: var(--cyan);
            font-size: 1.8rem;
            font-weight: 700;
            text-shadow: 0 0 10px rgba(86, 240, 255, 0.46);
        }
        .console-card .meta {
            margin-top: 0.4rem;
            color: var(--green);
            font-size: 0.82rem;
        }
        .console-strip {
            background: linear-gradient(90deg, rgba(86, 240, 255, 0.18), rgba(255, 79, 216, 0.12), rgba(138, 125, 255, 0.18));
            border: 1px solid rgba(86, 240, 255, 0.28);
            border-radius: 10px;
            padding: 0.65rem 0.9rem;
            letter-spacing: 0.06em;
            color: var(--text);
        }
        .visor-strip {
            display: flex;
            gap: 0.6rem;
            flex-wrap: wrap;
            margin: 0.8rem 0 1rem;
        }
        .visor-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.45rem;
            padding: 0.34rem 0.7rem;
            border-radius: 999px;
            background: rgba(12, 21, 35, 0.74);
            border: 1px solid rgba(86,240,255,0.26);
            color: var(--text);
            font-size: 0.7rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
        }
        .visor-pill::before {
            content: "";
            width: 7px;
            height: 7px;
            border-radius: 50%;
            background: var(--green);
            box-shadow: 0 0 10px rgba(143,247,198,0.7);
        }
        .console-two-col {
            display: grid;
            grid-template-columns: 1.2fr 0.8fr;
            gap: 1rem;
            margin-top: 0.7rem;
        }
        .panel {
            background: rgba(10, 18, 32, 0.72);
            border: 1px solid rgba(86, 240, 255, 0.22);
            border-radius: 16px;
            padding: 1rem;
            box-shadow: inset 0 0 12px rgba(86, 240, 255, 0.04), 0 0 12px rgba(86, 240, 255, 0.04);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }
        .panel:hover {
            transform: translateY(-2px);
            border-color: rgba(86, 240, 255, 0.42);
        }
        .panel-title {
            color: var(--cyan);
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-size: 0.72rem;
            margin-bottom: 0.75rem;
        }
        @media (max-width: 1000px) {
            .console-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .console-two-col {
                grid-template-columns: 1fr;
            }
            .main-stack {
                grid-template-columns: 1fr;
            }
            .secondary-stack {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        @media (max-width: 620px) {
            .console-grid {
                grid-template-columns: 1fr;
            }
            .secondary-stack {
                grid-template-columns: 1fr;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    render_particle_background()

    st.markdown(
        """
        <div class="console-shell">
            <div class="console-header">
                <div class="traffic-lights">
                    <span class="dot red"></span>
                    <span class="dot yellow"></span>
                    <span class="dot green"></span>
                </div>
                <div>System // Hyperlane // Active</div>
            </div>
            <div style="margin-bottom: 0.55rem; color: var(--muted); font-size: 0.72rem; letter-spacing: 0.12em; text-transform: uppercase;">赛博网关 // 论文复现控制单元</div>
            <h1 style="margin: 0.3rem 0; font-size: clamp(2rem, 4vw, 3rem);">论文复现助手</h1>
            <div style="color: #d3eaff; font-size: 1rem; margin-top: 0.45rem;">本地轻量控制端 • 云端重计算执行器 • 赛博 2077 大屏控制台</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="console-grid">
            <div class="console-card">
                <div class="label">任务状态</div>
                <div class="value">在线</div>
                <div class="meta">实时监控与任务回流</div>
            </div>
            <div class="console-card">
                <div class="label">环境检测</div>
                <div class="value">自动</div>
                <div class="meta">conda / venv / docker 适配</div>
            </div>
            <div class="console-card">
                <div class="label">分析引擎</div>
                <div class="value">AI</div>
                <div class="meta" style="color: var(--pink);">创新点与风险评估</div>
            </div>
            <div class="console-card">
                <div class="label">输出报告</div>
                <div class="value">报告</div>
                <div class="meta" style="color: var(--amber);">Markdown / JSON / 结论清单</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="console-strip">
            系统状态 // 本地数据安全 // 云端复现已启用 // 局域网与移动端访问就绪 // 科研引擎在线
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        """
        <div class="console-two-col">
            <div class="panel">
                <div class="panel-title">执行拓扑</div>
                <div style="color: var(--text); line-height: 1.8;">
                    <div>01. 输入论文链接</div>
                    <div>02. 识别代码仓库候选</div>
                    <div>03. 配置云端凭据与运行环境</div>
                    <div>04. 自动拉取代码并安装依赖</div>
                    <div>05. 执行验证与日志回流</div>
                    <div>06. 创新点分析与报告输出</div>
                </div>
            </div>
            <div class="panel">
                <div class="panel-title">网络接入</div>
                <div style="color: var(--text); line-height: 1.8;">
                    <div>本机: http://127.0.0.1:8505</div>
                    <div>局域网: http://[本机IP]:8505</div>
                    <div>移动端: 同一 Wi‑Fi 可访问</div>
                    <div>模式: 本地控制 + 云端计算</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    store = TaskStore(DATA_DB_PATH)
    config_store = LocalConfigStore()
    artifact_store = ArtifactCollector()
    saved = config_store.load()

    with st.sidebar:
        st.header("云端配置")
        st.write("本地保留任务与日志，云端只负责代码执行与实验重跑。")
        st.write("推荐方式：SSH 私钥 + 用户自有云服务器 + 本地数据目录挂载。")
        st.caption(f"用户配置目录：{config_store.config_dir}")
        ips = get_local_ips()
        if len(ips) > 1:
            st.caption("同一局域网可用地址：" + " / ".join(f"http://{ip}:8505" for ip in ips if ip != "127.0.0.1"))
        else:
            st.caption("本机访问：http://127.0.0.1:8505")
        st.caption("手机端访问：在同一 Wi‑Fi 下打开局域网地址即可。")
        if "task_id" in st.session_state:
            st.info(f"当前任务：{st.session_state['task_id']}")

        st.markdown("---")
        st.subheader("工程化说明")
        st.markdown(
            """
            1. 输入论文链接  
            2. 识别代码仓库候选  
            3. 提交云端任务  
            4. 在远程环境拉取代码并安装依赖  
            5. 执行验证并回收日志  
            """
        )

    storage_state_key = "selected_local_data_dir"
    storage_default = st.session_state.get(storage_state_key) or saved.get("local_data_dir", str(Path.home() / "paper_repro_data"))
    if storage_state_key not in st.session_state:
        st.session_state[storage_state_key] = storage_default

    st.caption("本地存储目录")
    storage_col, action_col = st.columns([5, 1.6])
    with storage_col:
        local_data_dir = st.text_input(
            "本地存储目录",
            key="local_data_dir_input",
            value=st.session_state.get(storage_state_key, storage_default),
            label_visibility="collapsed",
        )
        st.session_state[storage_state_key] = local_data_dir
    with action_col:
        if st.button("选择目录", key="choose_local_storage", use_container_width=True):
            selected = open_directory_dialog(st.session_state.get(storage_state_key, storage_default))
            if selected:
                st.session_state[storage_state_key] = selected
                st.rerun()

    st.markdown(
        """
        <div class="visor-strip">
            <span class="visor-pill">本地控制中枢</span>
            <span class="visor-pill">远程计算执行</span>
            <span class="visor-pill">实时日志回流</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="panel" style="margin-bottom: 1rem;">
            <div class="panel-title">赛博配置面板</div>
            <div style="color: var(--muted); line-height: 1.8;">
                本地控制端同步收集参数，云端执行器按配置完成任务编排与日志回流。
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.form("paper_form"):
        left_col, center_col, right_col = st.columns([1.8, 1.2, 0.9])

        with left_col:
            paper_url = st.text_input("论文链接", value=saved.get("paper_url", "https://arxiv.org/abs/2401.00001"))
            repo_hint = st.text_input("代码仓库候选（可选）", value=saved.get("repo_hint", ""))
            ssh_target = st.text_input(
                "SSH 连接串（可选，可直接填 user@host 或 ssh user@host -i ~/.ssh/id_rsa）",
                value=saved.get("ssh_target", ""),
                placeholder="ubuntu@123.45.67.89 -p 22 -i ~/.ssh/id_rsa",
            )
            ssh_meta = resolve_ssh_profile(ssh_target, saved.get("cloud_host", ""), saved.get("cloud_user", ""), saved.get("ssh_key_path", ""))
            if ssh_meta:
                st.caption(
                    "已自动识别："
                    + ", ".join(f"{key}={value}" for key, value in ssh_meta.items())
                )

            default_cloud_host = ssh_meta.get("host") or saved.get("cloud_host") or "my-server.example.com"
            default_cloud_user = ssh_meta.get("user") or saved.get("cloud_user") or "ubuntu"
            default_ssh_key = ssh_meta.get("key") or saved.get("ssh_key_path") or "~/.ssh/id_rsa"

            cloud_host = st.text_input(
                "云服务器地址 / IP",
                value=default_cloud_host,
            )
            cloud_user = st.text_input(
                "云服务器用户名",
                value=default_cloud_user,
            )
            ssh_key_path = st.text_input(
                "SSH 私钥路径",
                value=default_ssh_key,
            )
            auto_remote_dir = detect_remote_workdir(repo_hint or paper_url, cloud_user, cloud_host)
            remote_workdir = st.text_input(
                "远程工作目录",
                value=saved.get("remote_workdir", auto_remote_dir),
            )
            st.caption("建议：系统会优先根据 SSH 用户名和仓库名称自动推导工作目录。")
            repo_probe_dir = st.text_input("本地仓库校验目录（可选，便于提前诊断环境）", value=saved.get("repo_probe_dir", ""))
            env_mode = st.selectbox("运行环境方式", ["conda", "venv", "docker"], index=0)

        with center_col:
            monitoring_container = st.container()
            with monitoring_container:
                preview_host = (cloud_host or "").strip() or "未配置"
                preview_user = (cloud_user or "").strip() or "未配置"
                preview_remote = (remote_workdir or "").strip() or "未配置"
                preview_local = (st.session_state.get(storage_state_key, local_data_dir) or "").strip() or "未配置"
                preview_env = env_mode or "conda"

                required_fields = [
                    (paper_url or "").strip(),
                    (cloud_host or "").strip(),
                    (cloud_user or "").strip(),
                    (remote_workdir or "").strip(),
                ]
                task_ready = all(required_fields)
                active_task = None
                if st.session_state.get("task_id"):
                    active_task = store.get_task(st.session_state["task_id"])
                preview_step = (active_task or {}).get("current_step", "prepare") if active_task else "prepare"
                if not task_ready:
                    preview_step = "prepare"
                    preview_eta = "待估算"
                    preview_status_display = "待配置"
                else:
                    active_status = str((active_task or {}).get("status", "queued")).lower()
                    status_map = {
                        "queued": "已就绪",
                        "running": "执行中",
                        "success": "已完成",
                        "failed": "失败",
                        "cancelled": "已取消",
                        "unknown": "待配置",
                    }
                    preview_status_display = status_map.get(active_status, "已就绪") if active_task else "已就绪"
                    preview_eta = estimate_completion({
                        "status": (active_task or {}).get("status", "queued"),
                        "current_step": preview_step,
                    })

                current_preview_task = {
                    "status": (active_task or {}).get("status", "queued") if active_task else ("queued" if task_ready else "unknown"),
                    "current_step": preview_step,
                }
                st.markdown(
                    f"""
                    <div class="floating-card small" style="padding: 1rem; min-height: 100%;">
                        <div class="panel-title">任务预览</div>
                        <div style="color: var(--text); font-size: 0.8rem; line-height: 1.8;">
                            <div>目标主机: <span style="color: var(--cyan);">{preview_host}</span></div>
                            <div>用户名: <span style="color: var(--cyan);">{preview_user}</span></div>
                            <div>远程目录: <span style="color: var(--cyan);">{preview_remote}</span></div>
                            <div>本地输出: <span style="color: var(--cyan);">{preview_local}</span></div>
                            <div>执行环境: <span style="color: var(--green);">{preview_env}</span></div>
                            <div>任务状态: <span style="color: var(--amber);">{preview_status_display}</span></div>
                            <div>预计完成时间: <span style="color: var(--amber);">{preview_eta}</span></div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                render_repro_progress(current_preview_task)
                task_log_preview = (st.session_state.get("task_log_preview") or "等待提交任务后，日志将在这里实时更新").strip()
                st.markdown(
                    f"""
                    <div class="floating-card small" style="padding: 0.8rem; margin-top: 1rem;">
                        <div class="panel-title">实时日志流</div>
                        <pre class="telemetry-log" style="max-height: 180px;">{task_log_preview}</pre>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        with right_col:
            local_tree = ensure_local_storage_tree((st.session_state.get(storage_state_key, local_data_dir) or str(Path.home() / "paper_repro_data")).strip(), st.session_state.get("task_id"))
            tree_html = "".join(f"<li><span>{name}</span><code>{path}</code></li>" for name, path in local_tree.items())
            st.markdown(
                f"""
                <div class="floating-card small" style="padding: 0.8rem;">
                    <div class="panel-title">任务目录</div>
                    <ul class="directory-list">{tree_html}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                """
                <div class="floating-card small" style="padding: 0.8rem; margin-top: 1rem;">
                    <div class="panel-title">系统提示</div>
                    <div style="color: var(--muted); line-height: 1.8; font-size: 0.82rem;">
                        1. 建议保留本地数据目录独立存储<br>
                        2. SSH 私钥请勿提交到 GitHub<br>
                        3. 真实复现仍需根据目标仓库适配<br>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        submitted = st.form_submit_button("提交复现任务", use_container_width=True)

    st.markdown("---")

    if submitted:
        detected_repo = extract_repo_url(paper_url)
        repo_url = detected_repo or repo_hint.strip() or "https://github.com/example/project"

        ssh_target_value = ssh_target.strip()
        resolved_profile = resolve_ssh_profile(ssh_target_value, cloud_host.strip(), cloud_user.strip(), ssh_key_path.strip())
        resolved_cloud_host = resolved_profile.get("host") or cloud_host.strip() or "my-server.example.com"
        resolved_cloud_user = resolved_profile.get("user") or cloud_user.strip() or "ubuntu"
        resolved_ssh_key = resolved_profile.get("key") or ssh_key_path.strip() or "~/.ssh/id_rsa"
        resolved_ssh_port = resolved_profile.get("port") or ssh_meta.get("port") or "22"
        resolved_remote_dir = remote_workdir.strip() or detect_remote_workdir(repo_hint or paper_url, resolved_cloud_user, resolved_cloud_host)
        resolved_local_dir = (st.session_state.get("selected_local_data_dir") or local_data_dir or str(Path.home() / "paper_repro_data")).strip()

        active_tasks = [task for task in store.list_tasks(limit=20) if task.get("status") in {"queued", "running"}]
        if active_tasks:
            st.warning("检测到已有未结束任务，系统将自动中止旧任务并直接开始新任务。")
            for active_task in active_tasks:
                store.update_task_status(active_task["id"], "cancelled", "已被更高优先级任务替换，旧任务被终止。", current_step="cancelled")

        config_store.save(
            {
                "paper_url": paper_url,
                "repo_hint": repo_hint,
                "ssh_target": ssh_target_value,
                "cloud_host": resolved_cloud_host,
                "cloud_user": resolved_cloud_user,
                "ssh_key_path": resolved_ssh_key,
                "ssh_port": resolved_ssh_port,
                "remote_workdir": resolved_remote_dir,
                "local_data_dir": resolved_local_dir,
                "repo_probe_dir": repo_probe_dir,
                "env_mode": env_mode,
            }
        )

        probe_dir = Path(repo_probe_dir).expanduser() if repo_probe_dir.strip() else None
        if probe_dir and probe_dir.exists():
            diagnosis = EnvironmentDiagnostics(probe_dir).diagnose()
            with st.expander("自动环境诊断结果", expanded=True):
                st.json(diagnosis)
        else:
            st.caption("若你本地已有代码仓库，可填入仓库目录进行预诊断；未填则在云端执行阶段自动完成环境适配。")

        if not detected_repo and repo_hint.strip():
            st.info("已使用用户提供的代码仓库候选值继续执行。")
        elif not detected_repo:
            st.warning("未从论文页面中自动识别到代码仓库，已使用默认候选值继续执行。")

        task = store.create_task(
            paper_url=paper_url,
            repo_url=repo_url,
            host=resolved_cloud_host,
            user=resolved_cloud_user,
            ssh_key_path=os.path.expanduser(resolved_ssh_key),
            port=resolved_ssh_port,
            remote_workdir=resolved_remote_dir,
            local_data_dir=os.path.expanduser(resolved_local_dir),
            environment_mode=env_mode,
            status="queued",
            current_step="prepare",
        )

        st.session_state["task_id"] = task["id"]
        st.session_state["task_log_preview"] = "任务已创建，等待云端执行开始..."
        storage_layout = ensure_local_storage_tree(resolved_local_dir, task["id"])
        st.success(f"任务已创建：{task['id']}")
        st.info(f"本地存储目录已自动生成：{storage_layout['root']}")
        st.code(
            "\n".join(
                [
                    f"已识别仓库：{repo_url}",
                    f"运行环境：{env_mode}",
                    f"云服务器：{resolved_cloud_host} ({resolved_cloud_user})",
                    f"远程目录：{resolved_remote_dir}",
                    f"本地数据目录：{os.path.expanduser(resolved_local_dir)}",
                    f"预计完成时间：{estimate_completion(task)}",
                    "本地目录结构：",
                    *[f"- {name}: {path}" for name, path in storage_layout.items()],
                ]
            )
        )

        render_task_telemetry(task, storage_layout, task.get("log") or "等待云端执行开始...")
        render_pipeline_steps(task)

        runner = RemoteRunner(task)
        pipeline = runner.build_pipeline()
        st.session_state["task_log_preview"] = "正在执行论文复现流水线..."

        for step in pipeline:
            current_status = "running"
            store.update_task_status(task["id"], current_status, f"执行 {step['title']}：{step['id']}", current_step=step["id"])
            st.session_state["task_log_preview"] = f"[{step['id']}] {step['title']}\n" + (st.session_state.get("task_log_preview") or "")
            render_repro_progress({"status": current_status, "current_step": step["id"]})

        store.update_task_status(task["id"], "running", "任务已进入云端执行阶段，准备按流水线执行复现步骤。", current_step="prepare")
        with st.spinner("正在按论文复现流水线执行..."):
            result = runner.execute()

        task = store.get_task(task["id"])
        st.session_state["task_log_preview"] = result.get("logs", "")[:4000] if isinstance(result.get("logs"), str) else json.dumps(result, ensure_ascii=False, indent=2)[:4000]
        storage_layout = ensure_local_storage_tree(os.path.expanduser(task.get("local_data_dir") or str(Path.home() / "paper_repro_data")), task["id"])
        render_task_telemetry(task, storage_layout, st.session_state["task_log_preview"])

        analyzer = PaperInnovationAnalyzer()
        analysis = analyzer.analyze(
            paper_url=paper_url,
            repo_url=repo_url,
            reproduction_logs=result.get("logs", ""),
            repo_dir=repo_probe_dir if repo_probe_dir.strip() else None,
        )
        result["analysis"] = analysis
        report = generate_repro_report(task, analysis)
        project_summary = generate_project_summary(task, analysis, report["report_path"])
        comparison_table = generate_experiment_table([
            {"metric": "Top-1 Acc", "paper": "待填充", "repro": "待填充", "gap": "待填充", "note": "需结合实际实验结果更新"},
            {"metric": "mAP", "paper": "待填充", "repro": "待填充", "gap": "待填充", "note": "需结合实际实验结果更新"},
            {"metric": "F1", "paper": "待填充", "repro": "待填充", "gap": "待填充", "note": "需结合实际实验结果更新"},
        ])
        result["report"] = report
        result["comparison_table"] = comparison_table
        result["project_summary"] = project_summary

        payload = json.dumps(result, ensure_ascii=False, indent=2)
        status = result.get("status", "unknown")
        st.session_state["task_log_preview"] = payload[:4000]
        store.update_task_status(task["id"], status, payload, current_step=status)
        artifact_store.collect(task["id"], result)
        persist_task_artifacts(task, result, storage_layout, report, project_summary)

        task = store.get_task(task["id"])
        render_task_telemetry(task, storage_layout, payload)

        with st.expander("智能创新点分析", expanded=True):
            st.metric("分析置信度", f"{analysis['confidence']:.2f}")
            st.write(analysis["summary"])
            st.markdown("### 可能的创新点")
            for item in analysis["possible_innovations"]:
                st.markdown(f"- {item}")
            if analysis["risks"]:
                st.markdown("### 主要风险")
                for item in analysis["risks"]:
                    st.markdown(f"- {item}")
            st.json({"signals": analysis["signals"]})

        with st.expander("实验对比表", expanded=True):
            st.markdown(comparison_table)

        with st.expander("GitHub-ready 项目总结", expanded=True):
            st.code(project_summary)

        st.success(f"复现报告已生成：{report['report_path']}")
        st.code(report["report_md"][:3000])
        st.write(result)

        current_task_id = st.session_state.get("task_id")
        if current_task_id and st.button("结束当前任务", key=f"cancel_{current_task_id}"):
            store.update_task_status(current_task_id, "cancelled", "用户主动结束当前任务。", current_step="cancelled")
            st.warning("当前任务已结束，新的任务可以继续提交。")

        if st.button("重新执行流水线", key=f"run_{task['id']}"):
            runner = RemoteRunner(task)
            pipeline = runner.build_pipeline()
            st.session_state["task_log_preview"] = "正在执行论文复现流水线..."

            for step in pipeline:
                current_status = "running"
                store.update_task_status(task["id"], current_status, f"执行 {step['title']}：{step['id']}", current_step=step["id"])
                st.session_state["task_log_preview"] = f"[{step['id']}] {step['title']}\n" + (st.session_state.get("task_log_preview") or "")
                render_repro_progress({"status": current_status, "current_step": step["id"]})

            with st.spinner("正在按论文复现流水线执行..."):
                result = runner.execute()
            st.session_state["task_log_preview"] = result.get("logs", "")[:4000] if isinstance(result.get("logs"), str) else json.dumps(result, ensure_ascii=False, indent=2)[:4000]
            st.rerun()

    st.subheader("最近任务")
    for task in store.list_tasks(limit=10):
        with st.container():
            status_color = get_status_color(task["status"])
            task_log_preview = (task.get("log") or "")[:180]
            eta_value = estimate_completion(task)
            st.markdown(
                f"<div style='border-left: 4px solid {status_color}; padding: 8px 12px; margin: 6px 0;'>"
                f"<strong>{task['id']}</strong> | 状态: {task['status']} | 当前步骤: {task.get('current_step', 'queued')} | 仓库: {task['repo_url']}<br>"
                f"预计完成时间: {eta_value} | 日志: {task_log_preview}</div>",
                unsafe_allow_html=True,
            )


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    app_path = script_dir / "app.py"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            "8503",
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        check=False,
    )


if __name__ == "__main__":
    render_app()
