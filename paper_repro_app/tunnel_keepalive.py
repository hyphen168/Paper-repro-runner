# -*- coding: utf-8 -*-
"""公网远程隧道守护（mobile_access 规范 P0-6）：
在用户云服务器（AutoDL 等）上建立 SSH 反向隧道，把本机应用映射到云机回环端口，
再经云平台「自定义服务」或手机 SSH 客户端访问。断线自动退避重连。

用法：python tunnel_keepalive.py --local-port 8505 [--remote-port 18505]
凭据：复用 ~/.paper_repro_app/cloud_config.json 的 host/user/port + 私钥路径（须已免密注入公钥）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFIG_FILE = Path.home() / ".paper_repro_app" / "cloud_config.json"
LOCAL_PORT = 8505
REMOTE_PORT = 18505


def _log(msg: str) -> None:
    print(f"[tunnel] {msg}", flush=True)


def load_profile() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    return data


def build_command(profile: dict, local_port: int, remote_port: int) -> list:
    host = (profile.get("cloud_host") or "").strip().split("\n")[0].split(" ")[-1].strip()
    user = (profile.get("cloud_user") or "root").strip()
    port = str(profile.get("ssh_port") or "22").strip()
    key = (profile.get("ssh_key_path") or "").strip()
    cmd = [
        "ssh", "-N",
        "-R", f"127.0.0.1:{remote_port}:127.0.0.1:{local_port}",
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=accept-new",
        "-p", port,
    ]
    if key and Path(key).expanduser().exists():
        cmd += ["-i", str(Path(key).expanduser())]
    cmd.append(f"{user}@{host}")
    return cmd


def main() -> int:
    args = sys.argv[1:]
    local_port = LOCAL_PORT
    remote_port = REMOTE_PORT
    for i, arg in enumerate(args):
        if arg == "--local-port" and i + 1 < len(args):
            local_port = int(args[i + 1])
        if arg == "--remote-port" and i + 1 < len(args):
            remote_port = int(args[i + 1])
    profile = load_profile()
    host = (profile.get("cloud_host") or "").strip()
    if not host:
        _log("未找到云服务器配置（~/.paper_repro_app/cloud_config.json）。请先在应用内配置并测试 SSH 连接。")
        return 2
    if shutil.which("ssh") is None:
        _log("未找到系统 ssh 命令。Windows 请启用「可选功能 → OpenSSH 客户端」。")
        return 2
    cmd = build_command(profile, local_port, remote_port)
    _log("启动反向隧道（本机 :%d -> 云机 127.0.0.1:%d）" % (local_port, remote_port))
    _log("命令行: " + " ".join(cmd))
    _log("提示：云机回环端口需再映射为公网 URL——AutoDL 控制台「自定义服务」或手机 SSH 隧道。")
    attempt = 0
    while True:
        attempt += 1
        _log(f"第 {attempt} 次连接…")
        proc = subprocess.Popen(cmd)
        try:
            rc = proc.wait()
        except KeyboardInterrupt:
            proc.terminate()
            _log("已停止。")
            return 0
        if rc == 0:
            _log("连接已正常关闭（可能被外部结束）。")
            return 0
        _log(f"连接中断（退出码 {rc}），5 秒后重连…")
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())
