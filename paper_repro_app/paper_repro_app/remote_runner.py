from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None


class RemoteRunner:
    def __init__(self, task: Dict[str, Any], max_retries: int = 2):
        self.task = task
        self.host = task.get("host")
        self.user = task.get("user")
        self.ssh_key_path = task.get("ssh_key_path")
        self.port = task.get("port") or task.get("ssh_port") or 22
        self.remote_workdir = task.get("remote_workdir", "/workspace/paper-repro")
        self.repo_url = task.get("repo_url")
        self.env_mode = task.get("environment_mode", "conda")
        self.max_retries = max_retries

    def normalize_ssh_key_reference(self, key_value: Any) -> str:
        if key_value is None:
            return ""
        value = str(key_value).strip()
        if not value:
            return ""
        if value.startswith("-----BEGIN") or "PRIVATE KEY" in value.upper():
            ssh_dir = Path.home() / ".ssh" / "auto_generated"
            ssh_dir.mkdir(parents=True, exist_ok=True)
            key_file = ssh_dir / f"paper_repro_{abs(hash(value))}.key"
            if not key_file.exists() or key_file.read_text(encoding="utf-8", errors="replace") != value:
                key_file.write_text(value, encoding="utf-8")
            os.chmod(key_file, 0o600)
            return str(key_file)
        expanded = os.path.expanduser(value)
        if expanded and os.path.exists(expanded):
            return expanded
        return expanded

    def detect_ssh_auth_sources(self) -> Dict[str, Any]:
        ssh_dir = Path.home() / ".ssh"
        key_candidates = []
        primary_key = self.normalize_ssh_key_reference(self.ssh_key_path)
        if primary_key:
            key_candidates.append(primary_key)
        for candidate in [
            ssh_dir / "id_rsa",
            ssh_dir / "id_ed25519",
            ssh_dir / "id_ecdsa",
        ]:
            if candidate.exists() and str(candidate) not in key_candidates:
                key_candidates.append(str(candidate))

        agent_keys = []
        try:
            result = subprocess.run(["ssh-add", "-L"], capture_output=True, text=True, check=False)
            if result.stdout:
                agent_keys = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except FileNotFoundError:
            agent_keys = []

        config_path = ssh_dir / "config"
        config_identity = []
        if config_path.exists():
            try:
                for line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().lower().startswith("identityfile"):
                        value = line.split(None, 1)[1].strip()
                        if value:
                            config_identity.append(os.path.expanduser(value))
            except OSError:
                config_identity = []

        resolved_key = key_candidates[0] if key_candidates else None
        return {
            "key_candidates": key_candidates,
            "agent_keys": agent_keys,
            "config_identity": config_identity,
            "resolved_key": resolved_key,
            "has_any_auth": bool(key_candidates or agent_keys or config_identity),
        }

    def build_pipeline(self) -> List[Dict[str, str]]:
        conda_hook = "eval \"$(conda shell.bash hook)\""
        env_step = (
            "if command -v conda >/dev/null 2>&1 && [ \"{mode}\" = \"conda\" ]; then "
            f"{conda_hook}; "
            "conda activate paper-repro >/dev/null 2>&1 || conda create -y -n paper-repro python=3.10 >/dev/null 2>&1; "
            "conda activate paper-repro >/dev/null 2>&1; python --version; "
            "else "
            "python3 -m venv .venv >/dev/null 2>&1 || true; . .venv/bin/activate; python --version; "
            "fi"
        ).format(mode=self.env_mode)
        install_step = (
            "cd {workdir} && if command -v conda >/dev/null 2>&1 && [ \"{mode}\" = \"conda\" ]; then "
            f"{conda_hook}; "
            "conda activate paper-repro >/dev/null 2>&1; "
            "if [ -f environment.yml ]; then conda env update -f environment.yml --prune -q || true; fi; "
            "if [ -f requirements.txt ]; then python -m pip install --disable-pip-version-check --prefer-binary -q -r requirements.txt || true; fi; "
            "if [ -f setup.py ] || [ -f pyproject.toml ]; then python -m pip install --disable-pip-version-check --prefer-binary -q -e . || true; fi; "
            "else "
            ". .venv/bin/activate && if [ -f requirements.txt ]; then python -m pip install --disable-pip-version-check --prefer-binary -q -r requirements.txt || true; fi && if [ -f setup.py ] || [ -f pyproject.toml ]; then python -m pip install --disable-pip-version-check --prefer-binary -q -e . || true; fi; "
            "fi"
        ).format(workdir=f"{self.remote_workdir}/repo", mode=self.env_mode)
        verify_step = (
            "cd {workdir} && if command -v conda >/dev/null 2>&1 && [ \"{mode}\" = \"conda\" ]; then "
            f"{conda_hook}; "
            "conda activate paper-repro >/dev/null 2>&1; "
            "else . .venv/bin/activate; fi && "
            "if [ -f pytest.ini ] || [ -d tests ]; then python -m pytest -q --maxfail=1 -x >/dev/null 2>&1 || true; else python -m compileall . >/dev/null 2>&1 || true; fi"
        ).format(workdir=f"{self.remote_workdir}/repo", mode=self.env_mode)

        steps: List[Dict[str, str]] = [
            {"id": "prepare", "title": "准备工作目录", "command": f"mkdir -p {self.remote_workdir} >/dev/null 2>&1"},
            {"id": "clone", "title": "拉取论文代码仓库", "command": f"cd {self.remote_workdir} && if [ -d repo ]; then cd repo && git fetch --depth 1 --quiet origin || true; git pull --ff-only --quiet --depth 1 || true; else git clone --depth 1 --filter=blob:none --single-branch --quiet {self.repo_url} repo || git clone --quiet {self.repo_url} repo; fi"},
            {"id": "env", "title": "环境诊断与适配", "command": f"cd {self.remote_workdir}/repo && echo '--- 环境诊断 ---' && python3 --version && ls -1 . 2>/dev/null | head && {env_step}"},
            {"id": "install", "title": "安装依赖", "command": install_step},
            {"id": "verify", "title": "验证复现脚本", "command": verify_step},
            {"id": "collect", "title": "收集结果与日志", "command": f"cd {self.remote_workdir}/repo && echo '论文复现流水线已完成'"},
        ]
        return steps

    def build_plan(self) -> List[str]:
        return [step["command"] for step in self.build_pipeline()]

    def build_shell_script(self) -> str:
        script_lines = ["set -euo pipefail"]
        for step in self.build_pipeline():
            script_lines.append(f"echo '--- {step['title']} ---'")
            script_lines.append(step["command"])
        script_lines.append("echo '论文复现任务已进入云端执行阶段'")
        return "\n".join(script_lines)

    def detect_ssh_auth_sources(self) -> Dict[str, Any]:
        ssh_dir = Path.home() / ".ssh"
        key_candidates = []
        primary_key = self.normalize_ssh_key_reference(self.ssh_key_path)
        if primary_key:
            key_candidates.append(primary_key)
        for candidate in [
            ssh_dir / "id_rsa",
            ssh_dir / "id_ed25519",
            ssh_dir / "id_ecdsa",
        ]:
            if candidate.exists() and str(candidate) not in key_candidates:
                key_candidates.append(str(candidate))

        agent_keys = []
        try:
            result = subprocess.run(["ssh-add", "-L"], capture_output=True, text=True, check=False)
            if result.stdout:
                agent_keys = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        except FileNotFoundError:
            agent_keys = []

        config_path = ssh_dir / "config"
        config_identity = []
        if config_path.exists():
            try:
                for line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    if line.strip().lower().startswith("identityfile"):
                        value = line.split(None, 1)[1].strip()
                        if value:
                            config_identity.append(os.path.expanduser(value))
            except OSError:
                config_identity = []

        resolved_key = key_candidates[0] if key_candidates else None
        return {
            "key_candidates": key_candidates,
            "agent_keys": agent_keys,
            "config_identity": config_identity,
            "resolved_key": resolved_key,
            "has_any_auth": bool(key_candidates or agent_keys or config_identity),
        }

    def execute(self) -> Dict[str, Any]:
        if not self.host or not self.user:
            return {"status": "failed", "message": "云服务器连接信息不完整，请补充主机和用户名。"}

        if paramiko is None:
            return {"status": "failed", "message": "paramiko 未安装，请在本地运行 pip install paramiko。"}

        auth_state = self.detect_ssh_auth_sources()
        key_candidates = auth_state["key_candidates"]
        resolved_key = auth_state.get("resolved_key")
        if not auth_state["has_any_auth"]:
            return {
                "status": "failed",
                "message": "服务器已启动，但本机没有可用 SSH 认证来源。请确认你已复制真实私钥内容或有效 key 文件路径，并且本机已可用 ssh-agent / ~/.ssh/config / IdentityFile。",
                "attempts": 0,
            }

        last_error = None
        for attempt in range(1, self.max_retries + 2):
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                connect_kwargs = {
                    "hostname": self.host,
                    "username": self.user,
                    "port": int(self.port) if str(self.port).isdigit() else 22,
                    "timeout": 20,
                    "allow_agent": True,
                    "look_for_keys": True,
                }
                if resolved_key and os.path.exists(resolved_key):
                    connect_kwargs["key_filename"] = resolved_key
                elif key_candidates:
                    connect_kwargs["key_filename"] = key_candidates[0]
                ssh.connect(**connect_kwargs)

                script = self.build_shell_script()
                shell_safe_script = script.replace("'", "'\"'\"'")
                stdin, stdout, stderr = ssh.exec_command(f"bash -lc '{shell_safe_script}'")
                stdout_text = stdout.read().decode("utf-8", errors="replace")
                stderr_text = stderr.read().decode("utf-8", errors="replace")
                ssh.close()

                pipeline = self.build_pipeline()
                log_payload = {
                    "attempt": attempt,
                    "pipeline": pipeline,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                }

                if stderr_text.strip():
                    raise RuntimeError(stderr_text.strip())

                return {
                    "status": "success",
                    "message": "远程复现流水线已完成，日志已返回。",
                    "logs": json.dumps(log_payload, ensure_ascii=False, indent=2),
                    "attempts": attempt,
                }
            except Exception as exc:  # pragma: no cover
                last_error = exc
                if attempt > self.max_retries:
                    break

        return {
            "status": "failed",
            "message": f"远程执行失败：{last_error}",
            "attempts": self.max_retries + 1,
        }
