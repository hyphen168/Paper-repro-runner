"""SSH 与密钥工具（自 app.py 外迁的纯逻辑，零 streamlit 依赖）。"""

from __future__ import annotations

import hashlib
import os
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

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

    # 无匹配档案（配置文件存在但没有该主机的 Host 块）：安全返回空 dict，绝不触发 IndexError
    if not profile:
        return {}

    _host_aliases = (profile.get("host_aliases") or "").split()
    hostname = profile.get("hostname") or (_host_aliases[0] if _host_aliases else "")
    resolved = {
        "host": hostname,
        "user": profile.get("user", ""),
        "port": profile.get("port", ""),
        "key": profile.get("key", ""),
    }
    return {key: value for key, value in resolved.items() if value}



# ================= 连接档案引擎（专家组规范 v1.0 第二节） =================
_SSH_ERR = {
    "auth": "认证失败",
    "refused": "连接被拒绝",
    "timeout": "连接超时",
    "dns": "主机名无法解析",
    "net_unreachable": "网络不可达",
    "proxy": "代理连接失败",
    "other": "未知错误",
}


def _split_ssh_words(line: str) -> list:
    """按空格拆分，保留 Windows 路径反斜杠（posix=False）；空串容错。"""
    try:
        return shlex.split(line, posix=False)
    except ValueError:
        return line.split()


def parse_connection_profile(raw_line, ctx=None) -> dict:
    """解析一行 SSH 连接信息为档案（host/user/port/key_path/alias/source）。

    支持形态：完整 ssh 命令（-p/-i 任意顺序与紧贴式 -p38662）、user@host[:port]、
    host[:port]、ssh 别名、纯 host。解析失败返回 {"error": 原因}。
    ctx: dict(user=..., port=..., key=...) UI 上下文兜底。
    """
    ctx = ctx or {}
    line = (raw_line or "").strip()
    if not line:
        return {"error": "空行"}
    words = _split_ssh_words(line)
    if not words:
        return {"error": f"无法解析：{line}"}

    profile = {
        "user": ctx.get("user") or "root",
        "port": int(ctx.get("port") or 22),
        "key_path": ctx.get("key") or "",
        "alias": "",
    }
    args_mode = False
    pos = 0
    while pos < len(words):
        tok = words[pos]
        if tok == "ssh":
            args_mode = True
            pos += 1
            continue
        if tok.startswith("-") and tok not in {"-"}:
            if tok in {"-p", "-i", "-J"}:
                if pos + 1 < len(words):
                    if tok == "-p":
                        profile["port"] = int(words[pos + 1]) if words[pos + 1].isdigit() else profile["port"]
                    elif tok == "-i":
                        profile["key_path"] = words[pos + 1]
                    else:  # -J proxy：仅记录，不执行
                        profile["proxy_jump"] = words[pos + 1]
                pos += 2
                continue
            if tok.startswith("-p") and len(tok) > 2 and tok[2:].isdigit():
                profile["port"] = int(tok[2:])
                pos += 1
                continue
            if tok.startswith("-i") and len(tok) > 2:
                profile["key_path"] = tok[2:]
                pos += 1
                continue
            pos += 1  # 其它 ssh 参数忽略（-o 等由 alias/config 承接）
            continue
        # 位置参数：user@host[:port] 或 host[:port]
        if "@" in tok:
            user_part, _, rest = tok.partition("@")
            if user_part:
                profile["user"] = user_part
            target = rest
        else:
            target = tok
        host, sep, port_s = target.partition(":")
        if host:
            profile["host"] = host
        if sep and port_s and port_s.isdigit():
            profile["port"] = int(port_s)
        pos += 1
    if not args_mode and len(words) == 1 and not profile.get("host") and "@" not in words[0]:
        # 单 token 且非 user@host：可能是 ~/.ssh/config 别名，尝试展开
        expanded = expand_ssh_config(words[0])
        if expanded.get("host"):
            profile.update(expanded)
            profile["alias"] = words[0]
    if profile.get("host") is None:
        profile["host"] = ""
    if not profile.get("host"):
        # 可能是别名：走 alias 展开
        alias = profile.get("alias") or words[0]
        expanded = expand_ssh_config(alias)
        if expanded.get("host"):
            profile.update(expanded)
            profile["alias"] = alias
        else:
            return {"error": f"无法解析主机名：{alias}（可填写 host / user@host:port / 完整 ssh 命令 / ~/.ssh/config 别名）"}
    return {k: v for k, v in profile.items() if v not in ("", None)}


def expand_ssh_config(alias_or_host: str) -> dict:
    """ssh_config 别名展开：优先 ssh -G（含 Include）；失败回落本地解析；再失败返回 {}。"""
    hint = (alias_or_host or "").strip()
    if not hint:
        return {}
    # fast-path：本地 config 无该 Host 块（按行首 Host 判断）直接返回，避免每行一次 ssh -G 开销
    try:
        cfg_text = get_ssh_config_path().read_text(encoding="utf-8", errors="replace")
        if not any(ln.strip().lower().startswith("host " + hint.lower()) for ln in cfg_text.splitlines()):
            return {}
    except OSError:
        return {}
    try:
        result = subprocess.run(
            ["ssh", "-G", hint], capture_output=True, text=True, timeout=1.5,
        )
        if result.returncode == 0:
            out = {k: v for k, v in (ln.split(None, 1) for ln in result.stdout.splitlines() if " " in ln)}
            resolved: dict = {}
            if out.get("hostname") and out["hostname"] != hint:
                resolved["host"] = out["hostname"]
            if out.get("user"):
                resolved["user"] = out["user"]
            if out.get("port") and out["port"] != "22":
                resolved["port"] = int(out["port"])
            if out.get("identityfile"):
                resolved["key_path"] = out["identityfile"].strip().splitlines()[0] if out.get("identityfile") else ""
            return resolved
    except (OSError, subprocess.TimeoutExpired):
        pass
    # 回落本地 config 解析
    cfg = parse_ssh_config(hint)
    resolved = {}
    if cfg.get("host"):
        resolved["host"] = cfg["host"]
    if cfg.get("user"):
        resolved["user"] = cfg["user"]
    if cfg.get("port"):
        resolved["port"] = int(cfg["port"])
    if cfg.get("key"):
        resolved["key_path"] = cfg["key"]
    return resolved


def resolve_connection_fields(raw_host: str, user: str = "", port: str = "", key: str = "") -> dict:
    """把「主机输入框」任意文本归一化为 (host, user, port, key)。

    支持：完整 ssh 命令（ssh -p 38662 -i key root@host）、user@host[:port]、host[:port]、
    ssh 别名、多行（每行一条候选）。能解析出 host 时才覆盖调用方给出的兜底值，
    解析失败保持原样，绝不抛异常——解决“换云服务器粘贴 ssh 命令时报错”类问题。
    """
    raw = (raw_host or "").strip()
    out = {
        "host": raw,
        "user": (user or "").strip(),
        "port": (port or "22").strip(),
        "key": (key or "").strip(),
    }
    if not raw:
        return out
    lines = [ln for ln in re.split(r"[\n;,]+\s*", raw) if ln.strip()] or [raw]
    ctx = {"user": out["user"] or "root", "port": int(out["port"] or 22)}
    for line in lines:
        prof = parse_connection_profile(line, ctx=ctx)
        if prof.get("error") or not prof.get("host"):
            continue
        out["host"] = prof["host"]
        if prof.get("user"):
            out["user"] = prof["user"]
        if prof.get("port"):
            out["port"] = str(prof["port"])
        if prof.get("key_path"):
            out["key"] = prof["key_path"]
        break
    return out


def build_connection_profiles(lines, ctx=None) -> list:
    """逐行解析为连接档案列表；error 行保留在 {"error"} 条目；去重键 (host, port, user)。"""
    profiles: list = []
    seen = set()
    for raw in lines:
        line = (raw or "").strip()
        if not line or line.startswith("#"):
            continue
        prof = parse_connection_profile(line, ctx=ctx)
        if "error" in prof:
            prof.setdefault("source", line)
            profiles.append(prof)
            continue
        prof["source"] = line
        key = (prof.get("host"), prof.get("port"), prof.get("user"))
        if key not in seen:
            seen.add(key)
            profiles.append(prof)
    return profiles


def classify_conn_error(exc: Exception) -> str:
    """连接异常分类：auth / refused / timeout / dns / net_unreachable / proxy / other。"""
    if exc is None:
        return "other"
    try:
        import paramiko
        auth_names = ("AuthenticationException", "BadAuthenticationType", "PartialAuthentication",
                      "PasswordRequiredException", "SSHException")
        for name in auth_names:
            cls = getattr(paramiko, name, None)
            if cls is not None and isinstance(exc, cls):
                return "auth"
    except ImportError:
        pass
    errno = getattr(getattr(exc, "socket", None), "errno", None) or getattr(exc, "errno", None)
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if errno is not None:
        if errno == 111 or "connection refused" in text:
            return "refused"
        if errno == 110 or "timed out" in text or "timeout" in text:
            return "timeout"
        if errno == 113 or "no route to host" in text or "network unreachable" in text:
            return "net_unreachable"
        if errno == -2 or "getaddrinfo" in text or "name or service not known" in text or "nodename nor servname" in text:
            return "dns"
    if "getaddrinfo" in text or "name or service not known" in text:
        return "dns"
    if "timed out" in text or "timeout" in text:
        return "timeout"
    if "refused" in text:
        return "refused"
    if "proxy" in text or "proxycommand" in text:
        return "proxy"
    if "auth" in name or "authentication" in text:
        return "auth"
    return "other"


def _attempt_password_client(host: str, user: str, port, password: str, timeout: float):
    """纯密码认证尝试（不带私钥/agent）。"""
    import paramiko
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        hostname=host, username=user, port=int(port or 22),
        password=password, key_filename=None,
        allow_agent=False, look_for_keys=False,
        timeout=timeout, banner_timeout=min(20.0, timeout + 8),
        auth_timeout=min(20.0, timeout + 8),
    )
    return ssh


def _interactive_client(host: str, user: str, port, password: str, timeout: float):
    """keyboard-interactive 兜底：部分 SSH 服务仅接受该方式承载密码。"""
    import paramiko
    t = paramiko.Transport((host, int(port or 22)))
    t.banner_timeout = min(20.0, timeout + 8)
    t.auth_timeout = min(20.0, timeout + 8)
    t.connect()

    def _handler(title, instructions, prompt_list):
        return [password for _ in prompt_list]

    try:
        t.auth_password(user, password)
    except Exception:
        t.auth_interactive(user, _handler)
    client = paramiko.SSHClient()
    client._transport = t  # 复用已认证 transport，向调用方提供 exec_command 等接口
    return client


def _password_candidates(password: str):
    """生成待尝试的密码变体：原文 → 去首尾空白（复制粘贴最常见的坑）。"""
    base = str(password or "")
    out = [base]
    for variant in (base.strip(), base.rstrip(), base.lstrip()):
        if variant and variant not in out:
            out.append(variant)
    return out or [base]


def connect_with_password(host: str, user: str, port, password: str, timeout: float = 15.0):
    """密码登录总入口：纯密码 → 退避重试 → keyboard-interactive 兜底。

    分两类失败处理：
    - 握手/网络级（banner、连接被重置/关闭、EOF）：实例多半启动中或登录风控，短退避后给出明确提示，
      不做无意义的交互认证（还没到认证阶段）；
    - 认证级（Bad authentication type / allowed types 空）：服务器已受理但拒绝该方式，退避重试后再交互兜底。
    """
    import time as _t
    import paramiko as _pk
    _NETWORK_MARKERS = (
        "banner", "WinError 10054", "WinError 10053", "WinError 10061",
        "Connection reset", "Connection aborted", "EOF", "closed", "reset by peer",
        "[Errno 54]", "[Errno 104]", "NoValidConnections", "Unable to connect",
        "timed out", "Connection refused", "No route to host", "Network is unreachable",
        "getaddrinfo", "Name or service not known", "[Errno 110]", "[Errno 113]",
    )
    _METHOD_MARKERS = ("Bad authentication type", "allowed types", "No acceptable", "method not allowed")

    def _attempt(pw):
        return _attempt_password_client(host, user, port, pw, timeout)

    try:
        return _attempt(password)
    except Exception as exc:  # noqa: BLE001 - 分类后统一处理
        msg = str(exc)

    # —— 网络/握手级：实例未就绪或风控（banner 重置/不可达等）——短退避再试两次后给出明确提示
    if any(m in msg for m in _NETWORK_MARKERS):
        for i in (1, 2):
            _t.sleep(3 if i == 1 else 6)
            try:
                return _attempt(password)
            except Exception as e2:
                exc = e2
                msg = str(e2)
        raise RuntimeError(
            "服务器握手/网络层连接失败（%s）。这通常是：实例正在开机尚未就绪、地址端口已变化、网络波动，"
            "或短时间多次登录触发风控。请确认控制台实例为「运行中」且复制最新登录指令，等待 30-60 秒后重试一次（勿连点）。"
            % exc
        ) from exc

    # —— 认证方式级：服务器没给可用方法（Bad authentication type / allowed 空）——退避重试后键盘交互兜底
    if any(m in msg for m in _METHOD_MARKERS) or isinstance(exc, _pk.BadAuthenticationType):
        for i in (1, 2):
            _t.sleep(3 if i == 1 else 5)
            try:
                return _attempt(password)
            except Exception as e2:
                exc = e2
                msg = str(e2)
                if not (any(m in msg for m in _METHOD_MARKERS) or isinstance(e2, _pk.BadAuthenticationType)):
                    break
        try:
            return _interactive_client(host, user, port, password, timeout)
        except Exception as ike:
            raise RuntimeError(
                "密码认证方式不被服务器接受（已自动退避重试并尝试 keyboard-interactive）：%s | 交互认证：%s"
                % (exc, ike)
            ) from exc

    # —— 凭据级：Authentication failed（密码被拒）——极可能是密码不完整/带空格，自动试变体后再给出精确指引
    for cand in _password_candidates(password):
        try:
            return _attempt(cand)
        except Exception as e2:
            exc = e2
    raise RuntimeError(
        "密码认证失败：服务器拒绝了该密码（已自动尝试去除首尾空格的变体）。常见原因：密码复制不完整或带了空格、"
        "大小写或特殊字符（如 +）不符、或不是当前实例最新密码。请到控制台当前实例页重新复制登录密码后重试。原始错误：%s"
        % exc
    ) from exc


def ssh_connect(profile: dict, timeout: float = 12.0):
    """统一真实连接入口（paramiko 凭据握手）。认证类异常原样上抛；其它异常包装后上抛。

    返回已连接的 SSHClient；调用方负责 close()。
    凭据策略：有密码时走 connect_with_password（纯密码＋退避重试＋交互式兜底，杜绝
    “Bad authentication type / allowed types 为空”类瞬时报错）；无密码才用私钥。
    """
    import paramiko
    password = profile.get("password") or ""
    host = profile.get("host")
    user = profile.get("user") or "root"
    port = profile.get("port") or 22
    if password:
        return connect_with_password(host, user, port, password, timeout=timeout)
    key_path = profile.get("key_path") or ""
    if key_path and not os.path.isfile(os.path.expanduser(key_path)):
        key_path = ensure_ssh_key_file(key_path) or key_path
    has_key = bool(key_path and os.path.isfile(os.path.expanduser(key_path)))
    kwargs = {
        "hostname": host,
        "username": user,
        "port": int(port or 22),
        "timeout": timeout,
        "banner_timeout": min(20.0, timeout + 8),
        "auth_timeout": min(20.0, timeout + 8),
        "allow_agent": not has_key,
        "look_for_keys": not has_key,
    }
    if has_key:
        kwargs["key_filename"] = os.path.expanduser(key_path)
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(**kwargs)
    except Exception:
        ssh.close()
        raise
    return ssh


def sanitize(text: str) -> str:
    """脱敏：密码原文 / PEM 私钥全文 / 私钥路径(留 basename)。供日志与落库前调用。"""
    if not text:
        return text or ""
    out = str(text)
    out = re.sub(r"-----BEGIN[^-]*PRIVATE KEY-----.*?-----END[^-]*PRIVATE KEY-----", "<redacted-key>", out, flags=re.S)
    # 形如 -p 密码混排难以可靠识别，只处理已知形状：紧跟 ssh 命令尾部 token 与 key= 值
    out = re.sub(r"(?i)(password|passwd|pwd)\s*[=:]\s*\S+", r"\1=<redacted>", out)
    out = re.sub(r"(?i)(BEGIN (?:RSA|OPENSSH|EC|DSA) PRIVATE KEY)", "<redacted-key>", out)
    return out


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
        stable = hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
        key_file = ssh_dir / f"paper_repro_{stable}.key"
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
    # 归一化：允许在 host 处直接粘贴完整 ssh 命令 / user@host / 多行候选，避免把整条命令当主机名
    _norm = resolve_connection_fields(host, user, port, key)
    host_value = _norm["host"]
    user_value = _norm["user"]
    port_value = _norm["port"] or "22"
    key_value = ensure_ssh_key_file(_norm.get("key") or key)
    if not host_value or not user_value:
        return False, "请先填写云服务器地址和用户名（支持整行粘贴 ssh -p 端口 user@host 登录命令）。"
    if password:
        try:
            ssh = connect_with_password(host_value, user_value, port_value, password, timeout=timeout)
            ssh.close()
            return True, "SSH 密码认证测试成功，软件可以使用该密码连接云服务器。"
        except Exception as exc:
            reason = str(exc)
            hint = ""
            if "Bad authentication type" in reason or "allowed types" in reason:
                hint = "（已自动退避重试并尝试 keyboard-interactive；若仍报错：请确认密码复制无多余空格/换行、" \
                       "实例已完全开机、密码为控制台当前实例的最新密码，并避免连续快速重试触发风控）"
            elif "NoValidConnections" in reason or "Connection refused" in reason or "timed out" in reason:
                hint = "（实例可能未开机、地址/端口已变化或网络不通——请到控制台确认实例运行中，并复制最新 SSH 登录指令）"
            return False, f"SSH 密码认证失败：{exc}{hint}"

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
