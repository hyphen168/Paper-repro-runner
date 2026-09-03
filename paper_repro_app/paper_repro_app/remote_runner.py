from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

try:
    from paper_repro_app.logging_config import get_logger
    logger = get_logger("remote_runner")
except ImportError:  # pragma: no cover
    import logging
    logger = logging.getLogger("remote_runner")

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
        self.password = task.get("password")
        self.port = task.get("port") or task.get("ssh_port") or 22
        self.remote_workdir = task.get("remote_workdir", "/workspace/paper-repro")
        self.repo_url = task.get("repo_url")
        self.clone_url = task.get("clone_url") or self.repo_url
        self.pip_index_url = task.get("pip_index_url", "").strip()
        self.env_mode = task.get("environment_mode", "conda")
        self.max_retries = max_retries
        self.command_timeout = int(task.get("command_timeout", 900))
        self.clone_timeout = int(task.get("clone_timeout", 600))

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
        if expanded and os.path.isfile(expanded):
            return expanded
        return ""

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
        conda_bootstrap = (
            "CONDA_BIN=$(command -v conda 2>/dev/null || true); "
            "if [ -z \"$CONDA_BIN\" ]; then "
            "for candidate in /root/miniconda3/bin/conda /opt/conda/bin/conda "
            "$HOME/miniconda3/bin/conda $HOME/anaconda3/bin/conda /root/anaconda3/bin/conda; do "
            "if [ -x \"$candidate\" ]; then CONDA_BIN=$candidate; break; fi; "
            "done; fi; "
            "if [ -n \"$CONDA_BIN\" ]; then export PATH=\"$(dirname \"$CONDA_BIN\"):$PATH\"; fi"
        )
        configured_pip_index = shlex.quote(self.pip_index_url) if self.pip_index_url else ""
        pip_install_helper = (
            "pip_install_with_fallback() { "
            f"candidates=\"{configured_pip_index} https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://pypi.org/simple\"; "
            "installed=0; "
            "for index in $candidates; do "
            "[ -n \"$index\" ] || continue; "
            "echo \"尝试依赖源：$index\"; "
            "if timeout 120 python -m pip install --disable-pip-version-check --prefer-binary --index-url \"$index\" \"$@\"; then "
            "echo \"依赖安装成功（源：$index）\"; installed=1; break; "
            "fi; "
            "echo \"当前依赖源安装失败或超时，自动切换下一个备用源重试...\"; "
            "done; "
            "[ $installed -eq 1 ] || return 0; "
            "}; "
        )
        dependency_discovery = (
            "python - <<'PY'\n"
            "import ast\n"
            "import importlib.util\n"
            "import sys\n"
            "from pathlib import Path\n"
            "\n"
            "root = Path('.')\n"
            "local_modules = {path.stem for path in root.glob('*.py')}\n"
            "local_modules.update(path.name for path in root.iterdir() if path.is_dir() and (path / '__init__.py').exists())\n"
            "skip = set(sys.stdlib_module_names) | local_modules | {'__future__'}\n"
            "imports = set()\n"
            "for path in root.rglob('*.py'):\n"
            "    if any(part in {'.git', '.venv', 'venv', 'build', 'dist'} for part in path.parts):\n"
            "        continue\n"
            "    try:\n"
            "        tree = ast.parse(path.read_text(encoding='utf-8', errors='ignore'))\n"
            "    except (OSError, SyntaxError):\n"
            "        continue\n"
            "    for node in ast.walk(tree):\n"
            "        if isinstance(node, ast.Import):\n"
            "            imports.update(alias.name.split('.')[0] for alias in node.names)\n"
            "        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:\n"
            "            imports.add(node.module.split('.')[0])\n"
            "mapping = {'cv2': 'opencv-python', 'PIL': 'pillow', 'yaml': 'pyyaml', 'sklearn': 'scikit-learn', 'Crypto': 'pycryptodome', 'mpl_toolkits': 'matplotlib'}\n"
            "missing = sorted(name for name in imports if name not in skip and importlib.util.find_spec(name) is None)\n"
            "packages = [mapping.get(name, name) for name in missing]\n"
            "print('AUTO_DISCOVERED_PACKAGES=' + ' '.join(packages))\n"
            "PY"
        )
        env_step = (
            f"{conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda activate paper-repro >/dev/null 2>&1 || \"$CONDA_BIN\" create -y -n paper-repro python=3.10; "
            "conda activate paper-repro; python --version; "
            "else "
            "echo '未检测到可用 Conda，自动回退到 Python venv'; "
            "python3 -m venv .venv; . .venv/bin/activate; python --version; "
            "fi"
        ).format(mode=shlex.quote(self.env_mode))
        install_step = (
            "cd {workdir} && {conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda activate paper-repro >/dev/null 2>&1; "
            "{pip_install_helper}"
            "if [ -f environment.yml ]; then echo '发现 environment.yml，更新 Conda 环境'; conda env update -f environment.yml --prune; fi; "
            "if [ -f requirements.txt ]; then echo '发现 requirements.txt，安装声明依赖'; pip_install_with_fallback -r requirements.txt; fi; "
            "if [ -f setup.py ] || [ -f pyproject.toml ]; then echo '发现 Python 项目配置，安装项目依赖'; pip_install_with_fallback -e .; fi; "
            "else "
            ". .venv/bin/activate && {pip_install_helper} && python -m pip install --disable-pip-version-check --upgrade pip && "
            "if [ -f requirements.txt ]; then echo '发现 requirements.txt，安装声明依赖'; pip_install_with_fallback -r requirements.txt; fi && "
            "if [ -f setup.py ] || [ -f pyproject.toml ]; then echo '发现 Python 项目配置，安装项目依赖'; pip_install_with_fallback -e .; fi; "
            "fi"
        ).format(
            workdir=f"{self.remote_workdir}/repo",
            mode=self.env_mode,
            conda_bootstrap=conda_bootstrap,
            pip_install_helper=pip_install_helper,
        )
        dependency_step = (
            f"cd {shlex.quote(str(self.remote_workdir))}/repo && "
            f"{conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ "
            f"\"{self.env_mode}\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; conda activate paper-repro; "
            "else . .venv/bin/activate; fi; "
            f"missing=$({dependency_discovery} | sed -n 's/^AUTO_DISCOVERED_PACKAGES=//p'); "
            "if [ -n \"$missing\" ]; then "
            "echo \"依赖清单未覆盖的 import，尝试补装：$missing\"; "
            f"python -m pip install --disable-pip-version-check --prefer-binary {'--index-url ' + configured_pip_index if configured_pip_index else ''} $missing; "
            "else echo '依赖扫描完成：未发现缺失的第三方 import。'; fi; "
            "python -m pip check"
        )
        dataset_step = (
            f"cd {shlex.quote(str(self.remote_workdir))}/repo && "
            "echo '扫描数据集配置文件（data/*.yaml、*.yml）'; "
            "configs=$(find data -maxdepth 2 -type f \\( -name '*.yaml' -o -name '*.yml' \\) 2>/dev/null || true); "
            "if [ -z \"$configs\" ]; then "
            "echo '未发现数据集 YAML 配置；跳过自动数据集准备，训练前请提供论文指定的数据集。'; "
            "else echo \"$configs\"; "
            "grep -HnE '^(path|train|val|test|download):' $configs || true; "
            "echo '已识别数据集配置。仅当配置提供官方 download 脚本时才允许自动下载，避免误用未经授权或错误的数据集。'; fi"
        )
        verify_step = (
            "cd {workdir} && {conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$($CONDA_BIN shell.bash hook)\"; "
            "conda activate paper-repro >/dev/null 2>&1; "
            "else . .venv/bin/activate; fi && "
            "if [ -f pytest.ini ] || [ -d tests ]; then python -m pytest -q --maxfail=1 -x >/dev/null 2>&1 || true; else python -m compileall . >/dev/null 2>&1 || true; fi"
        ).format(
            workdir=f"{self.remote_workdir}/repo",
            mode=self.env_mode,
            conda_bootstrap=conda_bootstrap,
        )
        clone_source = shlex.quote(str(self.clone_url))
        workdir = shlex.quote(str(self.remote_workdir))
        clone_step = (
            f"cd {workdir} && export GIT_LFS_SKIP_SMUDGE=1 && "
            "export GIT_TERMINAL_PROMPT=0 && "
            "git config --global http.version HTTP/1.1 && "
            "git config --global http.lowSpeedLimit 1024 && "
            "git config --global http.lowSpeedTime 45 && "
            f"timeout 13 git ls-remote --heads {clone_source} >/dev/null || "
            "echo '代码源 13 秒内无响应：将尝试拉取；若网络超时，建议在界面填写公开的加速仓库地址。' >&2; "
            "if [ -d repo/.git ]; then "
            "cd repo && "
            "(git fetch --depth 1 --no-tags --progress origin && git reset --hard FETCH_HEAD && git clean -ffdx) || "
            f"(cd .. && rm -rf repo && timeout {self.clone_timeout} git clone --depth 1 --no-tags --filter=blob:none --single-branch --progress {clone_source} repo); "
            "else "
            f"timeout {self.clone_timeout} git clone --depth 1 --no-tags --filter=blob:none --single-branch --progress {clone_source} repo || "
            f"(rm -rf repo && timeout 120 git clone --depth 1 --no-tags --single-branch --progress {clone_source} repo); "
            "fi"
        )

        steps: List[Dict[str, str]] = [
            {"id": "prepare", "title": "准备工作目录", "command": f"mkdir -p {self.remote_workdir} >/dev/null 2>&1"},
            {"id": "clone", "title": "拉取论文代码仓库", "command": clone_step},
            {"id": "env", "title": "环境诊断与适配", "command": f"cd {self.remote_workdir}/repo && echo '--- 环境诊断 ---' && python3 --version && ls -1 . 2>/dev/null | head && {env_step}"},
            {"id": "install", "title": "安装依赖", "command": install_step},
            {"id": "dependencies", "title": "扫描并补装缺失依赖", "command": dependency_step},
            {"id": "dataset", "title": "识别并准备数据集", "command": dataset_step},
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

    def execute(
        self,
        on_step: Callable[[str, str, str], None] | None = None,
    ) -> Dict[str, Any]:
        if not self.host or not self.user:
            return {"status": "failed", "message": "云服务器连接信息不完整，请补充主机和用户名。"}

        if paramiko is None:
            return {"status": "failed", "message": "paramiko 未安装，请在本地运行 pip install paramiko。"}

        auth_state = self.detect_ssh_auth_sources()
        key_candidates = auth_state["key_candidates"]
        resolved_key = auth_state.get("resolved_key")
        login_methods = []
        if auth_state["has_any_auth"]:
            login_methods.append("key")
        if self.password:
            login_methods.append("password")
        if not login_methods:
            return {
                "status": "failed",
                "message": "服务器已启动，但本机没有可用 SSH 认证来源。请确认你已复制真实私钥内容或有效 key 文件路径，并且本机已可用 ssh-agent / ~/.ssh/config / IdentityFile。",
                "attempts": 0,
            }

        task_id = self.task.get("id", "unknown_task")
        logger.info(f"[Task: {task_id}] 开始在 {self.host}:{self.port} ({self.user}) 上执行远程复现流水线")
        last_error = None
        for attempt in range(1, self.max_retries + 2):
            ssh = None
            try:
                logger.info(f"[Task: {task_id}] 第 {attempt} 次尝试建立 SSH 连接...")
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                has_specific_key = bool((resolved_key and os.path.exists(resolved_key)) or key_candidates)
                use_agent = not has_specific_key and not self.password

                connect_kwargs = {
                    "hostname": self.host,
                    "username": self.user,
                    "port": int(self.port) if str(self.port).isdigit() else 22,
                    "timeout": 30,
                    "banner_timeout": 60,
                    "auth_timeout": 60,
                    "allow_agent": use_agent,
                    "look_for_keys": use_agent,
                }
                if resolved_key and os.path.exists(resolved_key):
                    connect_kwargs["key_filename"] = resolved_key
                elif key_candidates:
                    connect_kwargs["key_filename"] = key_candidates[0]
                if self.password:
                    connect_kwargs["password"] = self.password

                connected = False
                conn_err = None
                for conn_try in range(3):
                    try:
                        ssh.connect(**connect_kwargs)
                        connected = True
                        break
                    except Exception as ce:
                        conn_err = ce
                        logger.warning(f"[Task: {task_id}] SSH 连接重试 ({conn_try + 1}/3) 失败: {ce}")
                        time.sleep(2)
                if not connected:
                    raise conn_err or RuntimeError("SSH 连接失败")

                logger.info(f"[Task: {task_id}] SSH 连接成功建立，开启 TCP Keep-Alive")
                transport = ssh.get_transport()
                if transport is not None:
                    transport.set_keepalive(15)

                logs: List[str] = []
                for step in self.build_pipeline():
                    step_id = step["id"]
                    step_title = step["title"]
                    logger.info(f"[Task: {task_id}] 开始步骤 [{step_id}]: {step_title}")
                    step_header = f"--- {step_title} ---"
                    logs.append(step_header)
                    if on_step:
                        on_step(step_id, step_title, step_header)

                    stdin, stdout, stderr = ssh.exec_command(
                        f"bash -lc {json.dumps(step['command'])}"
                    )
                    channel = stdout.channel
                    step_output: List[str] = []
                    deadline = time.monotonic() + self.command_timeout
                    while not channel.exit_status_ready():
                        if channel.recv_ready():
                            chunk = channel.recv(4096).decode("utf-8", errors="replace")
                            step_output.append(chunk)
                            if on_step:
                                on_step(step_id, step_title, chunk)
                        if channel.recv_stderr_ready():
                            chunk = channel.recv_stderr(4096).decode("utf-8", errors="replace")
                            step_output.append(chunk)
                            if on_step:
                                on_step(step_id, step_title, chunk)
                        if time.monotonic() >= deadline:
                            channel.close()
                            msg = f"{step_title} 超过 {self.command_timeout // 60} 分钟仍未完成。"
                            logger.error(f"[Task: {task_id}] 步骤 [{step_id}] 执行超时: {msg}")
                            raise TimeoutError(msg)
                        time.sleep(0.2)

                    while channel.recv_ready():
                        step_output.append(channel.recv(4096).decode("utf-8", errors="replace"))
                    while channel.recv_stderr_ready():
                        step_output.append(channel.recv_stderr(4096).decode("utf-8", errors="replace"))

                    exit_status = channel.recv_exit_status()
                    step_log = "".join(step_output).strip()
                    if step_log:
                        logs.append(step_log)
                    if exit_status != 0:
                        err_msg = f"{step_title} 失败（退出码 {exit_status}）：{step_log or '远程命令未返回错误详情。'}"
                        logger.error(f"[Task: {task_id}] 步骤 [{step_id}] 异常退出: {err_msg}")
                        raise RuntimeError(err_msg)
                    logger.info(f"[Task: {task_id}] 步骤 [{step_id}] 执行成功")
                    if on_step:
                        on_step(step_id, step_title, f"{step_title} 已完成。")

                pipeline = self.build_pipeline()
                log_payload = {
                    "attempt": attempt,
                    "pipeline": pipeline,
                    "stdout": "\n".join(logs),
                    "stderr": "",
                }

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
                time.sleep(attempt * 3)
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        return {
            "status": "failed",
            "message": f"远程执行失败：{last_error}",
            "attempts": self.max_retries + 1,
        }
