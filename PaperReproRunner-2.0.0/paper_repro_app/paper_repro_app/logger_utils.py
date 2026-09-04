from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Dict


class TraceIdFilter(logging.Filter):
    """Attach a task-level trace_id to every log record."""

    def __init__(self, trace_id: str = ""):
        super().__init__()
        self.trace_id = trace_id

    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = self.trace_id
        return True


def make_trace_id() -> str:
    return f"task-{uuid.uuid4().hex[:8]}"


def _extract_trace_id(msg: str) -> str:
    """Pull trace_id from log message if present."""
    m = re.search(r"\[trace:([a-z0-9-]+)\]", msg)
    return m.group(1) if m else ""


def _decode_unicode_escapes(text: str) -> str:
    """Convert \\uXXXX escaped sequences back to real Unicode chars."""
    if not text:
        return ""

    def _replace(m):
        try:
            return chr(int(m.group(1), 16))
        except (ValueError, OverflowError):
            return m.group(0)

    return re.sub(r"\\u([0-9a-fA-F]{4})", _replace, text)


def enrich_log_for_display(raw_log: str) -> str:
    """Decode unicode escapes so the user sees readable Chinese in the UI."""
    return _decode_unicode_escapes(raw_log)


class StepLogger:
    """Thread-safe logger that prepends trace_id and logs the full command."""

    def __init__(self, logger: logging.Logger, trace_id: str):
        self._logger = logger
        self._trace_id = trace_id
        # Ensure the filter is attached only once
        if not any(isinstance(f, TraceIdFilter) and f.trace_id == trace_id
                    for f in logger.filters):
            logger.addFilter(TraceIdFilter(trace_id))

    def info(self, msg: str, *args, **kwargs):
        self._logger.info(f"[trace:{self._trace_id}] {msg}", *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._logger.warning(f"[trace:{self._trace_id}] {msg}", *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._logger.error(f"[trace:{self._trace_id}] {msg}", *args, **kwargs)

    def log_command(self, step_name: str, command: str):
        """Log the shell command about to be executed — truncated to keep the log readable.

        完整命令仍保存在任务记录 JSON（logs.pipeline）中，随时可查。
        """
        display_cmd = _decode_unicode_escapes(command)
        if len(display_cmd) > 1200:
            display_cmd = display_cmd[:900] + f"\n…(命令过长已截断，共 {len(command)} 字符，完整命令见任务结果 JSON)…" + display_cmd[-200:]
        self.info(
            f"▶ 即将执行 [{step_name}]:\n{display_cmd}",
        )

    def log_result(self, step_name: str, exit_code: int, stdout: str = "", stderr: str = ""):
        """Log step result with decoded output."""
        decoded_out = _decode_unicode_escapes(stdout)
        decoded_err = _decode_unicode_escapes(stderr)
        status = "OK" if exit_code == 0 else f"FAIL(code={exit_code})"
        self.info(f"✔ [{step_name}] 完成 — {status}")
        if decoded_out.strip():
            if len(decoded_out) > 600:
                clipped = decoded_out[:400] + f"\n…(中间 {len(decoded_out) - 600} 字符省略)…\n" + decoded_out[-200:]
            else:
                clipped = decoded_out
            self.info(f"  └ stdout ({len(decoded_out)} chars): {clipped}")
        if decoded_err.strip():
            self.warning(f"  └ stderr ({len(decoded_err)} chars): {decoded_err[:500]}")


def build_trace_id_from_task(task: Dict[str, Any]) -> str:
    """Reuse existing task.id if available, otherwise generate new one."""
    tid = task.get("id", "")
    if tid:
        # Keep existing short format like "task-643577d9"
        if tid.startswith("task-"):
            return tid
    return make_trace_id()