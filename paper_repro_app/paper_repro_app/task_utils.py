"""任务展示辅助（自 app.py 外迁纯逻辑，零 streamlit 依赖）。"""

from __future__ import annotations

import re
import socket
from datetime import datetime, timedelta

from paper_repro_app.logger_utils import enrich_log_for_display
from paper_repro_app.logging_config import DEFAULT_LOG_FILE

def format_log_preview(raw_log: str | None, max_entries: int = 3) -> str:
    if not raw_log:
        return "等待任务开始..."
    # 解码 \uXXXX 序列化转义，避免界面显示乱码
    text = enrich_log_for_display(str(raw_log))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    formatted = []
    for line in lines:
        if len(line) > 120:  # P0-3：长行截断，控制 2s 轮询 payload 体积
            line = line[:120] + "..."
        if re.match(r"^\[\d{2}:\d{2}:\d{2}\]", line):
            formatted.append(line)
        else:
            formatted.append(f"[{datetime.now().strftime('%H:%M:%S')}] {line}")
    if not formatted:
        return "等待任务开始..."
    return "\n".join(formatted[-max_entries:])


def read_log_tail(max_lines: int = 20) -> str:
    """高效读取后台日志文件尾部（滚动播放窗口），避免整文件读入导致的页面卡顿。"""
    if not DEFAULT_LOG_FILE.exists():
        return ""
    try:
        size = DEFAULT_LOG_FILE.stat().st_size
        with DEFAULT_LOG_FILE.open("rb") as fh:
            fh.seek(max(0, size - 48 * 1024))
            data = fh.read().decode("utf-8", errors="replace")
        lines = [line.strip() for line in data.splitlines() if line.strip()]
        return "\n".join(lines[-max_lines:]) if lines else ""
    except OSError:
        return ""

def get_step_order() -> list[str]:
    """流水线展示步骤（与 RemoteRunner.build_pipeline 真实执行步骤一致，共 10 步）。"""
    return ["prepare", "clone", "env", "install", "dependencies", "dataset", "verify", "model", "run", "collect"]


def get_status_color(status: str) -> str:
    """任务状态 → 霓虹色（赛博主题）。"""
    palette = {
        "queued": "#ffce00",
        "running": "#00f0ff",
        "success": "#00ffa3",
        "failed": "#ff2b4a",
        "cancelled": "#5c6f96",
        "unknown": "#8fa3c7",
    }
    return palette.get(str(status).lower(), "#8fa3c7")


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


# 各步骤单步耗时估计（分钟），供 ETA 估算
_STEP_MINUTES: dict[str, int] = {
    "prepare": 1,
    "clone": 2,
    "env": 2,
    "install": 4,
    "dependencies": 2,
    "dataset": 3,
    "verify": 2,
    "model": 1,
    "run": 3,
    "collect": 1,
}


def estimate_completion(task: dict | None) -> str:
    """估算任务预计完成时间（HH:MM）。"""
    if not task:
        return "待估算"
    status = str(task.get("status", "queued")).lower()
    if status in {"success", "failed", "cancelled"}:
        return "已结束"

    order = get_step_order()
    current_step = task.get("current_step") or "prepare"
    idx = order.index(current_step) if current_step in order else 0
    remaining = sum(_STEP_MINUTES.get(step, 2) for step in order[idx:])
    eta = datetime.now() + timedelta(minutes=remaining)
    return eta.strftime("%H:%M")
