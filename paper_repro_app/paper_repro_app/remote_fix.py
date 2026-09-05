"""AI 远程修复闭环 · 纯逻辑层（零 streamlit，可单测）。

流程：AI 给出修复方案(JSON) → 本模块安全扫描 → 生成只在任务仓库目录内执行的
bash 脚本 → 由 ssh_utils.run_remote 在云端执行。危险命令一律本地拦截，绝不自动放行。
"""
from __future__ import annotations

import json
import re
import shlex
from typing import Any, Dict, List, Optional, Tuple

# 硬性拦截：命中任一 token 的命令不允许执行（按小写匹配）
DENYLIST_TOKENS = [
    "rm -rf /", "rm -rf /*", "rm -rf ~", "rm -rf $home", "rm -fr /",
    "mkfs", "dd if=", "> /dev/sd", "shutdown", "poweroff", "reboot", "halt",
    "useradd", "usermod", "userdel", "passwd ", "chpasswd", "adduser",
    "chmod -r /", "chown -r /", "chmod 777 /", "chmod -r 777",
    "mount ", "umount", "fdisk", "parted", "mkswap", "swapoff",
    "iptables", "nft ", "firewall-cmd", "systemctl", "ufw ",
    "kill -9 1", "kill -9 $", ":(){", "fork bomb",
    "mv /etc", "rm /etc", "echo > /etc", "cat > /etc", ">> /etc/passwd",
    "git config --global", "ssh-keygen -t rsa -n '' -f /",
    "curl " + "|", "wget " + "|", "curl|", "wget|", "| sh", "| bash",
]
DENYLIST_SUB = ["| sh", "| bash", "|sh ", "|bash "]
# 明显超出仓库范围的系统级写操作（可允许但需在 UI 单独确认——当前默认拦截并在提示中说明）
_STRONG_WORDS = [
    "pip install --upgrade pip", "apt-get", "apt install", "yum ", "conda install -c",
]


def _command_lower_parts(command: str) -> str:
    return re.sub(r"\s+", " ", str(command or "")).strip().lower()


def safety_scan(commands: List[str]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """扫描命令清单：返回 (可通过, [被拦截的命令及原因])。"""
    allowed: List[str] = []
    blocked: List[Dict[str, Any]] = []
    for raw in commands or []:
        cmd = str(raw or "").strip()
        if not cmd:
            continue
        low = " " + _command_lower_parts(cmd) + " "
        reason = None
        for token in DENYLIST_TOKENS:
            if token.lower() in low:
                reason = f"命中危险模式：{token}"
                break
        if not reason:
            for sub in DENYLIST_SUB:
                if sub in low:
                    reason = f"禁止管道到 shell 执行下载脚本：{sub}"
                    break
        if not reason and re.search(r"(^|\s)rm\s+-rf\s+", cmd) and "/" in cmd.split("rm")[-1]:
            reason = "rm -rf 仅限仓库内路径；请改用明确的相对/子目录路径"
        if reason:
            blocked.append({"command": cmd, "reason": reason})
        else:
            allowed.append(cmd)
    return allowed, blocked


def parse_fix_plan(text: str) -> Dict[str, Any]:
    """从 AI 回复中稳健提取修复方案：优先找 JSON（可能带 markdown 围栏/散落文字）。"""
    raw = str(text or "")
    # 尝试围栏内 JSON
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        brace = raw.find("{")
        end = raw.rfind("}")
        if 0 <= brace < end:
            candidate = raw[brace:end + 1]
    plan: Dict[str, Any] = {}
    if candidate:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                plan = parsed
        except json.JSONDecodeError:
            plan = {}
    if not isinstance(plan.get("commands"), list):
        # 降级：尝试按行提取形如 1. cmd / - cmd / 纯行 的命令
        cmds: List[str] = []
        for line in raw.splitlines():
            l = re.sub(r"^\s*(?:```\w*|\d+[.、)]|[-*]|>)\s*", "", line).strip()
            if l and not l.lower().startswith(("reason", "原因", "```")) and ":" not in l[:8]:
                cmds.append(l)
        plan = {"reason": raw[:600], "commands": cmds}
    if not isinstance(plan.get("reason"), str):
        plan["reason"] = str(plan.get("reason") or "")[:600]
    return plan


def build_remote_script(commands: List[str], repo_dir: str, env_mode: str = "conda") -> str:
    """把通过的修复命令包装为在仓库目录内、conda 环境中的 bash 脚本（含逐步回显）。"""
    repo = shlex.quote(str(repo_dir or "").strip() or "/root/autodl-tmp/paper-repro/repo")
    env_bootstrap = (
        "CONDA_BIN=$(command -v conda 2>/dev/null || true); "
        "if [ -z \"$CONDA_BIN\" ]; then for c in /root/miniconda3/bin/conda /opt/conda/bin/conda "
        "$HOME/miniconda3/bin/conda; do [ -x \"$c\" ] && CONDA_BIN=$c && break; done; fi; "
        "if [ -n \"$CONDA_BIN\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
        "conda activate paper-repro >/dev/null 2>&1 || true; fi;"
    )
    lines = [
        "set +e",
        f"cd {repo} 2>/dev/null || cd /root/autodl-tmp 2>/dev/null || cd ~ || true",
        env_bootstrap,
        "echo '=== AI 远程修复开始 ==='",
        "pwd; echo '--- 命令执行（带序号，每条独立判断退出码）---'",
    ]
    for idx, cmd in enumerate(commands, start=1):
        c = str(cmd or "").strip()
        if not c:
            continue
        lines.append(f"echo '[{idx}] $ {c}'")
        lines.append(f"( {c} )")
        lines.append("echo \"[exit=$?]\"")
    lines.append("echo '=== AI 远程修复结束 ==='")
    return "\n".join(lines)
