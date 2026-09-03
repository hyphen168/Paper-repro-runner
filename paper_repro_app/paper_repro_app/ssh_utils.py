"""SSH 与密钥工具（自 app.py 外迁的纯逻辑，零 streamlit 依赖）。"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path

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


def ensure_ssh_key_file(key_value: str | os.PathLike[str] | None) -> str:
    if key_value is None:
        return ""
    value = str(key_value).strip()
    if not value:
        return ""
    if value.startswith("-----BEGIN") or "PRIVATE KEY" in value.upper():
        ssh_dir = Path.home() / ".ssh" / "paper_repro_generated"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        key_file = ssh_dir / f"paper_repro_{abs(hash(value))}.key"
        if not key_file.exists() or key_file.read_text(encoding="utf-8", errors="replace") != value:
            key_file.write_text(value, encoding="utf-8")
        key_file.chmod(0o600)
        return str(key_file)
    expanded = os.path.expanduser(value)
    if os.path.isfile(expanded):
        return expanded
    return ""


def ensure_default_ssh_keypair() -> tuple[str, str]:
    ssh_dir = Path.home() / ".ssh"
    key_path = ssh_dir / "id_ed25519"
    public_key_path = ssh_dir / "id_ed25519.pub"
    ssh_dir.mkdir(parents=True, exist_ok=True)

    if not key_path.exists():
        result = subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", "", "-q"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "ssh-keygen 执行失败。").strip()
            raise RuntimeError(f"无法自动生成 SSH 私钥：{message}")

    if not public_key_path.exists():
        result = subprocess.run(
            ["ssh-keygen", "-y", "-f", str(key_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or not result.stdout.strip():
            message = (result.stderr or result.stdout or "无法导出公钥。").strip()
            raise RuntimeError(f"无法生成 SSH 公钥：{message}")
        public_key_path.write_text(result.stdout.strip() + "\n", encoding="utf-8")

    return str(key_path), public_key_path.read_text(encoding="utf-8").strip()


def render_ssh_config_block(alias: str, host: str, user: str, port: str, key: str) -> str:
    alias_name = (alias or host or "papercloud").strip()
    host_name = (host or alias_name).strip()
    user_name = (user or "root").strip()
    port_value = (port or "22").strip()
    key_value = ensure_ssh_key_file(key)
    if not key_value:
        key_value = "~/.ssh/id_ed25519"
    return (
        f"Host {alias_name}\n"
        f"  HostName {host_name}\n"
        f"  User {user_name}\n"
        f"  Port {port_value}\n"
        f"  IdentityFile {os.path.expanduser(key_value)}\n"
        f"  IdentitiesOnly yes\n"
        f"  ServerAliveInterval 30\n"
    )


def write_ssh_profile(alias: str, host: str, user: str, port: str, key: str, config_path: str | os.PathLike[str] | None = None, force: bool = False) -> Path:
    ssh_config = Path(config_path) if config_path else Path.home() / ".ssh" / "config"
    ssh_config.parent.mkdir(parents=True, exist_ok=True)
    block = render_ssh_config_block(alias, host, user, port, key)
    if not ssh_config.exists():
        ssh_config.write_text(block, encoding="utf-8")
        ssh_config.chmod(0o600)
        return ssh_config

    existing = ssh_config.read_text(encoding="utf-8", errors="replace")
    host_pattern = rf"(?ms)^Host\s+{re.escape(alias or host or 'papercloud')}\s*$.*?(?=^Host\s|\Z)"
    match = re.search(host_pattern, existing)
    if match and not force:
        replacement = block.rstrip() + "\n"
        updated = existing[: match.start()] + replacement + existing[match.end():]
        ssh_config.write_text(updated, encoding="utf-8")
        ssh_config.chmod(0o600)
        return ssh_config

    appended = existing.rstrip() + "\n\n" + block
    ssh_config.write_text(appended, encoding="utf-8")
    ssh_config.chmod(0o600)
    return ssh_config


def test_ssh_connection(
    host: str,
    user: str,
    port: str,
    key: str,
    password: str = "",
    alias: str | None = None,
    timeout: int = 12,
) -> tuple[bool, str]:
    host_value = (host or "").strip()
    user_value = (user or "").strip()
    port_value = (port or "22").strip()
    key_value = ensure_ssh_key_file(key)
    if not host_value or not user_value:
        return False, "请先填写云服务器地址和用户名。"
    if password:
        try:
            import paramiko
        except ImportError:
            return False, "无法测试密码登录：缺少 paramiko 依赖。"
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                hostname=host_value,
                username=user_value,
                port=int(port_value) if port_value.isdigit() else 22,
                password=password,
                key_filename=key_value or None,
                timeout=timeout,
                allow_agent=True,
                look_for_keys=True,
            )
            ssh.close()
            return True, "SSH 密码认证测试成功，软件可以使用该密码连接云服务器。"
        except Exception as exc:
            return False, f"SSH 密码认证失败：{exc}"

    if not key_value:
        return False, "未找到有效的 SSH 私钥文件。请使用应用自动生成的私钥，或填写真实私钥路径。"

    if alias and alias.strip():
        ssh_cmd = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new", "-T", alias]
    else:
        args = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=accept-new", "-T"]
        if port_value and port_value != "22":
            args.extend(["-p", port_value])
        if key_value:
            args.extend(["-i", key_value])
        args.extend([f"{user_value}@{host_value}"])
        ssh_cmd = args

    try:
        result = subprocess.run(
            ssh_cmd + ["echo", "SSH_OK"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return False, f"SSH 测试执行失败：{exc}"

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()
    if result.returncode == 0 and "SSH_OK" in stdout:
        return True, "SSH 连接测试成功，当前环境已经可访问云服务器。"
    reason = stderr or stdout or "SSH 认证失败或目标主机不可达。"
    if "Permission denied" in reason or "no such identity" in reason.lower():
        reason = "SSH 认证失败：远程服务器没有接受当前私钥，或者本地提供的不是有效私钥文件。请先生成真实私钥并把对应公钥放到 /root/.ssh/authorized_keys。"
    return False, reason
