from __future__ import annotations

import json
import base64
import os
import re
import shlex
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List

from paper_repro_app.dataset_discovery import DatasetDiscovery
from paper_repro_app.model_discovery import ModelDiscovery

try:
    from paper_repro_app.ssh_utils import classify_conn_error, parse_connection_profile, sanitize, ssh_connect
except ImportError:  # pragma: no cover
    def classify_conn_error(exc):  # noqa: ARG001
        return "other"

    def parse_connection_profile(line, ctx=None):  # noqa: ARG001
        return {"host": line or "", "user": "root", "port": 22}

    def sanitize(text):
        return text

    def ssh_connect(profile, timeout=12.0):
        raise RuntimeError("ssh_connect unavailable")

try:
    from paper_repro_app.logging_config import get_logger
    logger = get_logger("remote_runner")
except ImportError:  # pragma: no cover
    import logging
    logger = logging.getLogger("remote_runner")

try:
    from paper_repro_app.logger_utils import (
        StepLogger,
        build_trace_id_from_task,
        enrich_log_for_display,
        make_trace_id,
    )
except ImportError:
    StepLogger = None
    build_trace_id_from_task = None

    def enrich_log_for_display(x):  # noqa: ARG001
        return x

    def make_trace_id():
        return "task-unknown"

try:
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None


class RemoteStepError(RuntimeError):
    """远程步骤失败。"""


class TaskCancelled(RuntimeError):
    """任务被用户取消。"""
    """A remote command failure that cannot be resolved by reconnecting."""


def probe_host(host: str, port: int, timeout: float = 6.0, attempts: int = 2) -> bool:
    """L1 TCP 探测（分类用，不单独否决）：单次 6s、默认重试 1 次，容忍慢网络/DNS。"""
    if not host:
        return False
    for _ in range(max(1, attempts)):
        try:
            sock = socket.create_connection((host, int(port) if str(port).isdigit() else 22), timeout=timeout)
            sock.close()
            return True
        except (OSError, socket.timeout):
            continue
    return False


def parse_ssh_candidates(lines, default_user: str = "root", default_port: int = 22) -> List[Dict[str, Any]]:
    """多行候选解析（委托引擎 parse_connection_profile，R1 已修复：@ 后空白截断 + -p 任意形态）。"""
    from paper_repro_app.ssh_utils import build_connection_profiles
    profiles = build_connection_profiles(
        lines, ctx={"user": default_user or "root", "port": int(default_port or 22)},
    )
    candidates = []
    for prof in profiles:
        if "error" in prof or not prof.get("host"):
            continue
        cand = {
            "host": prof["host"],
            "port": int(prof.get("port") or default_port or 22),
            "user": prof.get("user") or default_user or "root",
        }
        if prof.get("key_path"):
            cand["key_path"] = prof["key_path"]
        if prof.get("alias"):
            cand["alias"] = prof["alias"]
        candidates.append(cand)
    return candidates


def _clean_clone_url(url: Any) -> str:
    """清洗仓库 URL：去掉粘贴带入的成对引号/首尾空白，避免进入 shell 后成字面引号。"""
    u = str(url or "").strip()
    if len(u) >= 2 and u[0] in ('"', "'") and u[-1] == u[0]:
        u = u[1:-1].strip()
    return u


def _unwrap_ghfast(url: str) -> str:
    """剥离任意数量 ghfast.top 前缀，还原官方 URL（幂等，杜绝 ghfast 套 ghfast → 403）。"""
    u = str(url or "").strip()
    while True:
        low = u.lower()
        if low.startswith("https://ghfast.top/https://"):
            u = u[len("https://ghfast.top/"):]
        elif low.startswith("https://ghfast.top/http://"):
            u = u[len("https://ghfast.top/"):]
        else:
            break
    return u


def _is_auth_exception(exc: BaseException) -> bool:
    """判断是否为 SSH 认证类失败（Authentication failed 一族）。

    认证失败意味着凭据/配置本身有问题，重试无意义；同时不同 paramiko
    版本对异常类的顶层导出位置有差异，这里逐项 getattr 容错，避免漏判。
    """
    if paramiko is None:
        return False
    for name in (
        "AuthenticationException",
        "BadAuthenticationType",
        "PartialAuthentication",
        "PasswordRequiredException",
    ):
        cls = getattr(paramiko, name, None)
        if cls is not None and isinstance(exc, cls):
            return True
    return False


class RemoteRunner:
    def __init__(self, task: Dict[str, Any], max_retries: int = 2):
        self.task = task
        self.host = task.get("host")
        # 自动识别候选（task 可携带多主机，运行时探测选可达者；缺省回落单机）
        raw_cands = task.get("hosts") or []
        parsed: List[Dict[str, Any]] = []
        for c in raw_cands:
            if isinstance(c, dict) and c.get("host"):
                parsed.append(c)
        if not parsed:
            parsed = parse_ssh_candidates(
                [str(task.get("host") or "")], default_user=task.get("user") or "root",
                default_port=int(task.get("port") or task.get("ssh_port") or 22),
            )
        self.candidates = parsed
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
        self.auto_run = bool(task.get("auto_run", False))
        self._last_step_id = ""
        self._last_step_title = ""

        # --- 日志增强: trace_id + 命令回放 ---
        tid = build_trace_id_from_task(task) if build_trace_id_from_task else None
        self._trace_id = tid or make_trace_id()
        self._log = StepLogger(logger, self._trace_id) if StepLogger else None

    @staticmethod
    def extract_collection_payload(log_text: str) -> Dict[str, Any]:
        """Decode the bounded result manifest emitted by the remote collect step."""
        marker = "PAPER_REPRO_RESULTS_JSON="
        for line in reversed(log_text.splitlines()):
            if not line.startswith(marker):
                continue
            try:
                return json.loads(base64.b64decode(line[len(marker):]).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                return {}
        return {}

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
            "if [ ! -f ~/.condarc ]; then cat > ~/.condarc <<'CONDARC_EOF' 2>/dev/null || true\n"
            'channels:\n'
            '  - defaults\n'
            'default_channels:\n'
            '  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main\n'
            '  - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r\n'
            'custom_channels:\n'
            '  conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n'
            '  pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud\n'
            'CONDARC_EOF\n'
            'fi; \n'
            'CONDA_BIN=$(command -v conda 2>/dev/null || true); \n'
            'if [ -z "$CONDA_BIN" ]; then \n'
            'for candidate in /root/miniconda3/bin/conda /opt/conda/bin/conda $HOME/miniconda3/bin/conda $HOME/anaconda3/bin/conda; do \n'
            'if [ -x "$candidate" ]; then CONDA_BIN=$candidate; break; fi; \n'
            'done; fi; \n'
            'if [ -n "$CONDA_BIN" ]; then export PATH="$(dirname "$CONDA_BIN"):$PATH"; fi; \n'
            '# conda 环境智能定位：优先已存在环境；系统盘 <8G 时新建到数据盘 /root/autodl-tmp/envs\n'
            'paper_env() { if [ -d /root/autodl-tmp/envs/paper-repro ]; then echo /root/autodl-tmp/envs/paper-repro; else echo paper-repro; fi; }; \n'
            'conda_activate_paperrepro() { conda activate "$(paper_env)" >/dev/null 2>&1; }; \n'
            'ensure_paper_env() { [ -d /root/autodl-tmp/envs/paper-repro ] && return 0; "$CONDA_BIN" env list 2>/dev/null | grep -qw paper-repro && return 0; _a=$(df -Pk / | sed -n "2p" | tr -s " " | cut -d" " -f4); if [ "$_a" -lt 8388608 ]; then mkdir -p /root/autodl-tmp/envs && "$CONDA_BIN" create -y -p /root/autodl-tmp/envs/paper-repro python=3.10 >/dev/null 2>&1; else "$CONDA_BIN" create -y -n paper-repro python=3.10 >/dev/null 2>&1; fi; }'
        )
        configured_pip_index = shlex.quote(self.pip_index_url) if self.pip_index_url else ""
        pip_install_helper = (
            "export PYTHON_BIN=${PYTHON_BIN:-$(command -v python 2>/dev/null || true)}; "
            "if [ -z \"$PYTHON_BIN\" ]; then echo '未找到可用的 Python（PYTHON_BIN 为空），请检查 Conda 环境激活'; exit 127; fi; "
            "pip_install_with_fallback() { "
            "export PIP_CACHE_DIR=\"${PIP_CACHE_DIR:-$HOME/.cache/pip}\"; mkdir -p \"$PIP_CACHE_DIR\"; "
            "candidates=\"" + (configured_pip_index + " " if configured_pip_index else "") + "https://pypi.tuna.tsinghua.edu.cn/simple https://mirrors.aliyun.com/pypi/simple https://pypi.org/simple\"; "
            "for idx in $candidates; do "
            "[ -n \"$idx\" ] || continue; "
            "echo \"尝试依赖源：$idx\"; "
            "if timeout 300 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --cache-dir \"$PIP_CACHE_DIR\" --index-url \"$idx\" \"$@\"; then "
            "echo \"依赖安装成功（源：$idx）\"; return 0; "
            "fi; "
            "echo \"当前依赖源安装失败或超时，自动切换下一个备用源重试...\"; "
            "done; "
            "return 1; "
            "}; "
            "torch_cuda_ok() { python -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; }; "
            "install_req_file() { "
            "if command -v nvidia-smi >/dev/null 2>&1 && ! torch_cuda_ok; then "
            "echo '检测到 GPU 但当前无可用 CUDA torch：从国内 CUDA 源安装（下载较大）'; "
            "_cu_ok=0; "
            "for _cu in https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128 https://mirrors.aliyun.com/pytorch-wheels/cu128 https://download.pytorch.org/whl/cu128; do "
            "echo \"--- 正在从 $_cu 安装 torch/torchvision（国内镜像优先，单源限时 420 秒）...\"; "
            "if timeout 420 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --index-url \"$_cu\" torch torchvision && \"$PYTHON_BIN\" -c 'import torch; assert torch.cuda.is_available()' >/dev/null 2>&1; then "
            "echo \"CUDA torch 安装完成（源：$_cu）\"; tail -12 /tmp/torch_install.log; _cu_ok=1; break; fi; "
            "tail -6 /tmp/torch_install.log 2>/dev/null || true; "
            "echo \"源 $_cu 失败或非 CUDA 版，切换下一个...\"; "
            "done; "
            "if [ \"$_cu_ok\" = 1 ]; then echo 'CUDA torch 就绪，安装 requirements 时跳过 torch 系升级'; "
            "grep -vE '^[[:space:]]*(torch|torchvision|torchaudio|nvidia-|--extra-index-url)' requirements.txt > .requirements.protected.txt || true; "
            "pip_install_with_fallback -r .requirements.protected.txt; rm -f .requirements.protected.txt; "
            "else echo 'CUDA torch 安装失败（两个源均不可用或验证未过）。GPU 实例禁用 CPU 回退以免训练崩溃；请检查网络后重试，或在仓库 requirements 固定可用 CUDA 源。'; return 1; "
            "pip_install_with_fallback -r requirements.txt; fi; "
            "elif torch_cuda_ok; then "
            "echo '检测到可用 CUDA torch，保护 GPU 环境：安装 requirements 时跳过 torch/torchvision/torchaudio/nvidia-* 相关行'; "
            "grep -vE '^[[:space:]]*(torch|torchvision|torchaudio|nvidia-|--extra-index-url)' requirements.txt > .requirements.protected.txt || true; "
            "pip_install_with_fallback -r .requirements.protected.txt; rm -f .requirements.protected.txt; "
            "else pip_install_with_fallback -r requirements.txt; fi; "
            "}; "
        )
        dependency_script = (
            "import ast, importlib.util, sys\n"
            "from pathlib import Path\n"
            "root = Path('.')\n"
            "local_modules = {path.stem for path in root.glob('*.py')}\n"
            "local_modules.update(path.name for path in root.iterdir() if path.is_dir() and (path / '__init__.py').exists())\n"
            "skip = set(sys.stdlib_module_names) | local_modules | {'__future__'}\n"
            "imports = set()\n"
            "for path in root.rglob('*.py'):\n"
            "    if any(part in {'.git', '.venv', 'venv', 'build', 'dist'} for part in path.parts): continue\n"
            "    try: tree = ast.parse(path.read_text(encoding='utf-8', errors='ignore'))\n"
            "    except (OSError, SyntaxError): continue\n"
            "    for node in ast.walk(tree):\n"
            "        if isinstance(node, ast.Import): imports.update(alias.name.split('.')[0] for alias in node.names)\n"
            "        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: imports.add(node.module.split('.')[0])\n"
            "mapping = {'cv2': 'opencv-python', 'PIL': 'pillow', 'yaml': 'pyyaml', 'sklearn': 'scikit-learn', 'Crypto': 'pycryptodome', 'flask': 'flask', 'pytest': 'pytest', 'pytest_cov': 'pytest-cov', 'ultralytics': 'ultralytics', 'transformers': 'transformers', 'timm': 'timm', 'einops': 'einops', 'omegaconf': 'omegaconf', 'albumentations': 'albumentations', 'wandb': 'wandb', 'shapely': 'shapely', 'datasets': 'datasets', 'tokenizers': 'tokenizers'}\n"
            "missing = sorted(name for name in imports if name not in skip and importlib.util.find_spec(name) is None)\n"
            "packages = [mapping[name] for name in missing if name in mapping]\n"
            "unmapped = [name for name in missing if name not in mapping]\n"
            "# 重型框架不自动补装（体积大且易装错 CUDA 版本），仅提示\n"
            "heavy = {'torch', 'torchvision', 'tensorflow', 'tensorflow-gpu', 'jax', 'mxnet', 'paddle', 'paddlepaddle', 'keras', 'nvidia', 'cuda', 'dgl', 'mmcv', 'mmdet', 'mmsegmentation', 'fairseq', 'fastai'}\n"
            "auto_try = [name for name in unmapped if name not in heavy and name.isidentifier()]\n"
            "heavy_hit = [name for name in unmapped if name in heavy]\n"
            "if heavy_hit: print('HEAVY_FRAMEWORK_IMPORTS=' + ' '.join(heavy_hit))\n"
            "if auto_try: print('AUTO_TRY_PACKAGES=' + ' '.join(auto_try))\n"
            "print('AUTO_DISCOVERED_PACKAGES=' + ' '.join(packages))"
        )
        env_step = (
            f"{conda_bootstrap}; "
            # 1) 探测系统 Python（而非硬编码 python3）
            "SYSTEM_PYTHON=$(command -v python3 || command -v python || true); "
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro >/dev/null 2>&1 || ensure_paper_env; "
            "conda_activate_paperrepro || {{ echo 'Conda 环境激活失败，请检查云端 Conda 安装'; exit 1; }}; "
            "export PYTHON_BIN=\"$(command -v python 2>/dev/null || true)\" || true; "
            "python --version; "
            "else "
            "echo '未检测到可用 Conda，自动回退到 Python venv'; "
            # 2) 系统无 Python 时自动安装 Miniconda（清华镜像），失败给出可读指引
            "if [ -z \"$SYSTEM_PYTHON\" ]; then "
            "echo '未找到系统 Python，尝试自动安装 Miniconda（清华镜像）...'; "
            "curl -fsSL --connect-timeout 20 --max-time 600 'https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh' -o /tmp/miniconda.sh || "
            "{{ echo 'Miniconda 下载失败：请手动下载 https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh 并执行 bash 安装后重试'; exit 1; }}; "
            "bash /tmp/miniconda.sh -b -p \"$HOME/miniconda3\" >/dev/null 2>&1 || "
            "{{ echo 'Miniconda 安装失败：请手动安装 Miniconda 后重试'; exit 1; }}; "
            "export PATH=\"$HOME/miniconda3/bin:$PATH\"; "
            "CONDA_BIN=\"$HOME/miniconda3/bin/conda\"; "
            "if ! ensure_paper_env; then echo 'Conda 环境创建失败'; exit 1; fi; "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro || {{ echo 'Conda 环境激活失败'; exit 1; }}; "
            "export PYTHON_BIN=\"$(command -v python 2>/dev/null || true)\" || true; "
            "python --version; "
            "else "
            # 3) 有系统 Python：优先 venv，失败则直接用系统 Python，未找到时报可读错误
            "echo \"使用系统 Python: $SYSTEM_PYTHON\"; "
            "if \"$SYSTEM_PYTHON\" -m venv .venv >/dev/null 2>&1; then "
            "echo 'Python venv 创建成功'; "
            "else "
            "echo '虚拟环境创建失败（可能缺少 ensurepip），将直接使用系统 Python'; "
            "fi; "
            "if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; "
            "PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
            "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=\"$SYSTEM_PYTHON\"; "
            "if command -v \"$PYTHON_BIN\" >/dev/null 2>&1; then \"$PYTHON_BIN\" --version; "
            "else echo '未找到可用的 Python 解释器，请先安装 Python 3.10+ 或 Miniconda 后重试'; exit 1; fi; "
            "fi; "  # 内层 if [ -z "$SYSTEM_PYTHON" ] 闭合
            "fi"    # 外层 if [ -n "$CONDA_BIN" ] && [ mode = conda ] 闭合（缺失会导致 bash: unexpected end of file）
        )
        # 注：conda_bootstrap 经 f-string 先展开，内含 bash 花括号，不能再走 .format（会二次解析）；
        # 用 replace 注入 {mode} 并还原双花括号转义
        env_step = env_step.replace("{{", "{").replace("}}", "}").replace("{mode}", shlex.quote(self.env_mode))
        install_step = (
            "cd {workdir} && {conda_bootstrap}; "
            "{pip_install_helper}"
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro >/dev/null 2>&1; "
            "export PYTHON_BIN=\"$(command -v python 2>/dev/null || true)\" || true; "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro >/dev/null 2>&1; "
            "export PYTHON_BIN=\"$(command -v python 2>/dev/null || true)\" || true; "
            "if command -v nvidia-smi >/dev/null 2>&1; then "
            "if ! \"$PYTHON_BIN\" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then "
            "echo \"GPU 实例缺少可用 CUDA torch（缺失或为 CPU 版），卸载旧版并从多镜像 CUDA 源安装（清华/阿里/官方）（国内镜像优先，单源限时 420s）...\"; "
            "\"$PYTHON_BIN\" -m pip uninstall -y torch torchvision >/dev/null 2>&1 || true; "
            "_cu_ok=0; "
            "for _cu in https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128 https://mirrors.aliyun.com/pytorch-wheels/cu128 https://download.pytorch.org/whl/cu128; do "
            "if timeout 420 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --index-url \"$_cu\" torch torchvision && \"$PYTHON_BIN\" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then "
            "echo \"CUDA torch 安装完成（源：$_cu）\"; tail -6 /tmp/torch_inst.log; _cu_ok=1; break; fi; "
            "echo \"源 $_cu 失败，切换下一个...\"; done; "
            "if [ \"$_cu_ok\" != 1 ]; then echo \"CUDA torch 安装失败（两个源均不可用）。请检查云端网络后重试。\"; exit 1; fi; "
            "fi; fi; "
            "if [ -f environment.yml ]; then echo '发现 environment.yml，更新 Conda 环境'; conda env update -f environment.yml --prune; fi; "
            "if [ -f requirements.txt ]; then echo '发现 requirements.txt，安装声明依赖'; install_req_file; fi; "
            "if [ -f setup.py ] || [ -f pyproject.toml ]; then echo '发现 Python 项目配置，尝试安装项目依赖'; if pip_install_with_fallback -e .; then echo '项目依赖安装成功'; else echo '项目安装未成功（常见于 flat-layout/旧版 setup.py），启用 PYTHONPATH 兼容模式继续'; export PYTHONPATH=$PWD:${{PYTHONPATH:-}}; fi; fi; "
            "else "
            "SYSTEM_PYTHON=python3; "
            "python3 --version >/dev/null 2>&1 || SYSTEM_PYTHON=python; "
            "if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; "
            "PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
            "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=\"$SYSTEM_PYTHON\"; "
            "[ -n \"$PYTHON_BIN\" ] || {{ echo '未找到 Python 可执行文件'; exit 127; }}; "
            "\"$PYTHON_BIN\" -m pip install --disable-pip-version-check --upgrade pip && "
            "if [ -f requirements.txt ]; then echo '发现 requirements.txt，安装声明依赖'; install_req_file; fi; "
            "if [ -f setup.py ] || [ -f pyproject.toml ]; then echo '发现 Python 项目配置，尝试安装项目依赖'; if pip_install_with_fallback -e .; then echo '项目依赖安装成功'; else echo '项目安装未成功（常见于 flat-layout/旧版 setup.py），启用 PYTHONPATH 兼容模式继续'; export PYTHONPATH=$PWD:${{PYTHONPATH:-}}; fi; fi; "
            "fi"
        ).format(
            workdir=f"{self.remote_workdir}/repo",
            mode=self.env_mode,
            conda_bootstrap=conda_bootstrap,
            pip_install_helper=pip_install_helper,
        )
        dep_scan_b64 = base64.b64encode(dependency_script.encode("utf-8")).decode("ascii")
        dependency_step = (
            f"cd {shlex.quote(str(self.remote_workdir))}/repo && "
            f"{conda_bootstrap}; "
            "SYSTEM_PYTHON=$(command -v python3 || command -v python || true); "
            "if [ -n \"$CONDA_BIN\" ] && [ "
            f"\"{self.env_mode}\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; conda_activate_paperrepro; "
            "PYTHON_BIN=$(command -v python || true); "
            "else "
            "PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
            "[ -f .venv/bin/activate ] && . .venv/bin/activate; "
            "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=\"$SYSTEM_PYTHON\"; "
            "fi; "
            # 落盘执行：先写 .dep_scan.py（用 Python base64 解码，不依赖远端 base64 命令），
            # 再执行脚本文件——彻底规避 bash 内联解析截断，脚本留档便于排查
            f"\"$PYTHON_BIN\" -c \"from pathlib import Path; import base64; Path('.dep_scan.py').write_text(base64.b64decode('{dep_scan_b64}').decode('utf-8'), encoding='utf-8')\"; "
            f"_scan_out=$(\"$PYTHON_BIN\" .dep_scan.py); "
            "missing=$(echo \"$_scan_out\" | sed -n 's/^AUTO_DISCOVERED_PACKAGES=//p'); "
            "autotry=$(echo \"$_scan_out\" | sed -n 's/^AUTO_TRY_PACKAGES=//p'); "
            "heavy_hit=$(echo \"$_scan_out\" | sed -n 's/^HEAVY_FRAMEWORK_IMPORTS=//p'); "
            "if [ -n \"$heavy_hit\" ]; then "
            "_need_torch=0; for _h in $heavy_hit; do case \"$_h\" in torch|torchvision|torchaudio) _need_torch=1;; esac; done; "
            "if [ \"_need_torch\" = 1 ] && ! \"$PYTHON_BIN\" -c 'import torch; raise SystemExit(0 if torch.cuda.is_available() else 1)' >/dev/null 2>&1; then "
            "echo '检测到仓库需要 CUDA torch 但当前环境缺失或为 CPU 版，先卸载旧版并安装 CUDA 版（国内镜像优先，单源限时 420s）...'; "
            "\"$PYTHON_BIN\" -m pip uninstall -y torch torchvision >/dev/null 2>&1 || true; "
            "_cu_ok=0; "
            "for _cu in https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cu128 https://mirrors.aliyun.com/pytorch-wheels/cu128 https://download.pytorch.org/whl/cu128; do "
            "if timeout 420 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --index-url \"$_cu\" torch torchvision && \"$PYTHON_BIN\" -c 'import torch; assert torch.cuda.is_available()' >/dev/null 2>&1; then "
            "echo \"CUDA torch 安装完成（源：$_cu）\"; tail -6 /tmp/torch_dep.log; _cu_ok=1; break; fi; "
            "echo \"源 $_cu 失败或非 CUDA 版，切换下一个...\"; done; "
            "if [ \"$_cu_ok\" != 1 ]; then echo 'torch CUDA 自动补装失败：两个源均不可用。请检查云端网络后重试。'; exit 1; fi; "
            "else echo \"检测到重型框架依赖（$heavy_hit）：CUDA torch 已可用或无需 torch，跳过自动补装。\"; fi; "
            "fi; "
            "install_with_fallback() { "
            "export PIP_CACHE_DIR=\"${PIP_CACHE_DIR:-$HOME/.cache/pip}\"; mkdir -p \"$PIP_CACHE_DIR\"; "
            "for idx in \"$candidates\"; do "
            "if timeout 300 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --cache-dir \"$PIP_CACHE_DIR\" --index-url \"$idx\" \"$@\"; then return 0; fi; "
            "echo \"当前依赖源失败，自动切换备用源重试...\"; done; return 1; }; "
            "_OPTIONAL_SKIP='albumentations flask wandb tensorflow tensorflowjs tensorrt openvino nncf mss hydra omegaconf datasets accelerate'; "
            "_missing_f=''; for _pkg in $missing; do case \" $_OPTIONAL_SKIP \" in *\" $_pkg \"*) echo \"  跳过可选/示例包 $_pkg（运行确需时会再提示）\";; *) _missing_f=\"$_missing_f $_pkg\";; esac; done; "
            "if [ -n \"$_missing_f\" ]; then "
            "echo \"依赖清单未覆盖的基础运行 import，尝试补装：$_missing_f\"; "
            "install_with_fallback $_missing_f || echo '(基础依赖补装失败，继续流程；若后续运行报 ImportError 请按日志处理)' ; "
            "fi; "
            "if [ -n \"$autotry\" ]; then "
            "echo \"发现未映射 import（$autotry），逐个尝试直装（可选包，失败自动跳过；重型可选包直接跳过避免卡流程）...\"; "
            "_t0=$(date +%s); "
            "for pkg in $autotry; do "
            "[ $(( $(date +%s) - _t0 )) -gt 240 ] && { echo \"可选包补装总预算 240s 已用尽，跳过剩余包。\"; break; }; "

            "case \"$pkg\" in tensorflow|tensorflowjs|tensorrt|albumentations|mmcv|mmdet|fairseq|fastai|openvino|nncf|mss|hydra|omegaconf|datasets|accelerate|transformers|flask|wandb|pkg_resources|setuptools|urllib2|shapely) echo \"  跳过可选重型包 $pkg\"; continue;; esac; "
            "timeout 150 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --index-url https://pypi.tuna.tsinghua.edu.cn/simple -q \"$pkg\" >/dev/null 2>&1 && echo \"  已补装 $pkg\" || echo \"  自动补装 $pkg 失败（已跳过，运行报错时请手动安装）\"; "
            "done; "
            "_t0=$(date +%s); "
            "for pkg in $autotry; do "
            "[ $(( $(date +%s) - _t0 )) -gt 240 ] && { echo \"可选包补装总预算 240s 已用尽，跳过剩余包。\"; break; }; "

            "timeout 240 \"$PYTHON_BIN\" -m pip install --disable-pip-version-check --prefer-binary --index-url https://pypi.tuna.tsinghua.edu.cn/simple -q \"$pkg\" >/dev/null 2>&1 && echo \"  已补装 $pkg\" || echo \"  自动补装 $pkg 失败（已跳过，运行报错时请手动安装）\"; "
            "done; "
            "fi; "
            "if [ -z \"$missing\" ] && [ -z \"$autotry\" ] && [ -z \"$heavy_hit\" ]; then echo '依赖扫描完成：未发现需补装的 import。'; fi; "
            "\"$PYTHON_BIN\" -m pip check || echo 'pip check 检测到依赖冲突，继续执行代码验证以便收集准确错误'"
        )
        configured_run_command = str(self.task.get("run_command") or "").strip()
        data_config = str(self.task.get("data_config") or "").strip()
        requires_dataset = bool(configured_run_command or self.auto_run)
        # auto 模式（系统自动推断训练）下数据集缺失时允许降级为安全检查，任务不因此失败
        degrade_on_missing = bool(self.auto_run and not configured_run_command)
        _repo_managed = data_config in {"__repo_managed__", "repo-managed", "skip-dataset"}
        if requires_dataset and self.task.get("auto_download_dataset", True) and not _repo_managed:
            dataset_step = (
                f"cd {shlex.quote(f'{self.remote_workdir}/repo')} && "
                f"{conda_bootstrap}; "
                "if [ -n \"$CONDA_BIN\" ] && [ \""
                f"{self.env_mode}"
                "\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
                "conda_activate_paperrepro >/dev/null 2>&1; PYTHON_BIN=python; "
                "else PYTHON_BIN=\"$PWD/.venv/bin/python\"; [ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
                "echo '自动发现仓库数据集配置、复用缓存或执行官方下载'; "
                # 注意：不能写 if ! A && B（bash 解析为 (!A)&&B 会短路跳过 B）；
                # 用 A && B || { 降级 } 保证数据集脚本真实执行
                + DatasetDiscovery.build_remote_command("\"$PYTHON_BIN\"", data_config)
                + (
                    " || { echo '[paper-repro-degrade] 数据集准备失败：仓库无匹配数据集配置或下载不可用；"
                    "自动降级为安全检查模式（不训练）。需要训练时请在“高级选项”填写数据集 YAML 或改用自定义命令。'; "
                    "touch .paper_repro_dataset_missing; exit 0; }"
                    if degrade_on_missing
                    else " || { echo '[paper-repro-degrade-fatal] 数据集准备失败（本次为实际训练模式，需要数据集）。'; exit 1; }"
                )
            )
            # —— 可选：按用户设定比例自动划分 train/val/test ——
            if str(self.task.get("data_split") or "").strip():
                _ss = str(self.task.get("data_split")).strip()
                _b64 = "IyDmlbDmja7pm4YgdHJhaW4vdmFsL3Rlc3Qg6Ieq5Yqo5YiS5YiG77yI5L6b5LqR56uvIGV4ZWMg5L2/55So77yJCiMg5Y+C5pWw77yac3lzLmFyZ3ZbMV095q+U5L6LICI3MCwyMCwxMCLvvIxzeXMuYXJndlsyXT3lt7LnlJ/miJDnmoTmlbDmja7pm4YgWUFNTO+8iOebuOWvuSByZXBvIOague+8iQojIOmAu+i+ke+8muagt+acrOaUtumbhihpbWFnZXMvbGFiZWxzIOWQjOaehCkg4oaSIOWbuuWumuenjeWtkOa0l+eJjCDihpIg5oyJ5q+U5L6L6L2v6ZO+5o6l5YiwICpfc3BsaXQg55uu5b2VIOKGkiDnlJ/miJDmlrAgWUFNTCDihpIg6KaG5YaZIGVudgppbXBvcnQganNvbgppbXBvcnQgb3MKaW1wb3J0IHJhbmRvbQppbXBvcnQgc2h1dGlsCmltcG9ydCBzeXMKZnJvbSBwYXRobGliIGltcG9ydCBQYXRoCgppbXBvcnQgeWFtbCBhcyBfeWFtbAoKX3NwbGl0X3NwZWMgPSAoc3lzLmFyZ3ZbMV0gaWYgbGVuKHN5cy5hcmd2KSA+IDEgZWxzZSAnJykuc3RyaXAoKQpfY2ZnX2FyZyA9IChzeXMuYXJndlsyXSBpZiBsZW4oc3lzLmFyZ3YpID4gMiBlbHNlICcnKS5zdHJpcCgpCmlmIG5vdCBfc3BsaXRfc3BlYyBvciBub3QgX2NmZ19hcmc6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOWPguaVsOe8uuWkse+8iOmcgOimgSDmr5Tkvosg5LiOIFlBTUwg6Lev5b6E77yJJykKCl9yb290ID0gUGF0aC5jd2QoKQp0cnk6CiAgICBfcGFydHMgPSBbaW50KHgpIGZvciB4IGluIF9zcGxpdF9zcGVjLnJlcGxhY2UoJ++8micsICc6JykucmVwbGFjZSgn77yMJywgJywnKS5yZXBsYWNlKCcsJywgJzonKS5zcGxpdCgnOicpXQpleGNlcHQgRXhjZXB0aW9uOgogICAgX3BhcnRzID0gW10KaWYgbGVuKF9wYXJ0cykgPCAyIG9yIHN1bShfcGFydHMpIDw9IDA6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOWIkuWIhuavlOS+i+aXoOaViO+8micgKyBfc3BsaXRfc3BlYykKX3RyX3AsIF92YV9wID0gX3BhcnRzWzBdLCBfcGFydHNbMV0KX3RlX3AgPSBfcGFydHNbMl0gaWYgbGVuKF9wYXJ0cykgPiAyIGVsc2UgMAppZiBfdHJfcCA8IDAgb3IgX3ZhX3AgPCAwIG9yIF90ZV9wIDwgMDoKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g5YiS5YiG5q+U5L6L5LiN6IO95Li66LSfJykKCl9jZmdfcGF0aCA9IFBhdGgoX2NmZ19hcmcpCmlmIG5vdCBfY2ZnX3BhdGguaXNfYWJzb2x1dGUoKToKICAgIF9jZmdfcGF0aCA9IChfcm9vdCAvIF9jZmdfcGF0aCkucmVzb2x2ZSgpCmlmIG5vdCBfY2ZnX3BhdGguZXhpc3RzKCk6CiAgICByYWlzZSBTeXN0ZW1FeGl0KCdbc3BsaXRdIOaVsOaNrumbhiBZQU1MIOS4jeWtmOWcqO+8micgKyBzdHIoX2NmZ19wYXRoKSkKdHJ5OgogICAgX2NmZyA9IF95YW1sLnNhZmVfbG9hZChfY2ZnX3BhdGgucmVhZF90ZXh0KGVuY29kaW5nPSd1dGYtOCcpKSBvciB7fQpleGNlcHQgRXhjZXB0aW9uIGFzIF9lOgogICAgcmFpc2UgU3lzdGVtRXhpdCgnW3NwbGl0XSDor7vlj5YgWUFNTCDlpLHotKXvvJonICsgc3RyKF9lKSkKCiMg5pWw5o2u6ZuG5qC5Cl9iYXNlID0gUGF0aChzdHIoX2NmZy5nZXQoJ3BhdGgnKSBvciAnLicpKS5leHBhbmR1c2VyKCkKaWYgbm90IF9iYXNlLmlzX2Fic29sdXRlKCk6CiAgICBfYmFzZSA9IChfY2ZnX3BhdGgucGFyZW50IC8gX2Jhc2UpLnJlc29sdmUoKQpfaW1hZ2VzID0gX2Jhc2UgLyAnaW1hZ2VzJwppZiBub3QgX2ltYWdlcy5pc19kaXIoKToKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g5pWw5o2u6ZuG55uu5b2V57y65bCRIGltYWdlcy/vvJonICsgc3RyKF9iYXNlKSkKCgpkZWYgX2NvbGxlY3RfcG9vbCgpOgogICAgIiIi5pS26ZuGICjlm74sIOagh+azqCkg5qC35pys5a+577yb5Zu+54mH55uu5b2V5bmz6ZO65oiWIHRyYWluKi92YWwqIOWtkOebruW9leWdh+WPr+OAgiIiIgogICAgcG9vbCA9IFtdCiAgICBfaW1nX2RpcnMgPSBbXQogICAgc3VicyA9IFtwIGZvciBwIGluIHNvcnRlZChfaW1hZ2VzLml0ZXJkaXIoKSkgaWYgcC5pc19kaXIoKV0KICAgIGlmIHN1YnM6CiAgICAgICAgX2ltZ19kaXJzID0gc3VicwogICAgZWxzZToKICAgICAgICBfaW1nX2RpcnMgPSBbX2ltYWdlc10KICAgIGZvciBfaWRpciBpbiBfaW1nX2RpcnM6CiAgICAgICAgZm9yIF9pbWcgaW4gc29ydGVkKF9pZGlyLml0ZXJkaXIoKSk6CiAgICAgICAgICAgIGlmIF9pbWcuc3VmZml4Lmxvd2VyKCkgbm90IGluICgnLmpwZycsICcuanBlZycsICcucG5nJywgJy5ibXAnLCAnLndlYnAnKToKICAgICAgICAgICAgICAgIGNvbnRpbnVlCiAgICAgICAgICAgIF9yZWwgPSBfaW1nLnJlbGF0aXZlX3RvKF9pbWFnZXMpCiAgICAgICAgICAgIF9sYWJfcmVsID0gX3JlbC53aXRoX3N1ZmZpeCgnLnR4dCcpCiAgICAgICAgICAgIF9sYWIgPSBfYmFzZSAvICdsYWJlbHMnIC8gX2xhYl9yZWwKICAgICAgICAgICAgaWYgbm90IF9sYWIuZXhpc3RzKCk6CiAgICAgICAgICAgICAgICBjb250aW51ZQogICAgICAgICAgICBwb29sLmFwcGVuZCgoc3RyKF9pbWcpLCBzdHIoX2xhYikpKQogICAgcmV0dXJuIHBvb2wKCgpkZWYgX2RldGVjdF9uYyhsYWJlbHNfcm9vdCk6CiAgICBuYyA9IDAKICAgIGZvciB0IGluIGxhYmVsc19yb290LnJnbG9iKCcqLnR4dCcpOgogICAgICAgIHRyeToKICAgICAgICAgICAgbXggPSBtYXgoaW50KGxuLnNwbGl0KClbMF0pIGZvciBsbiBpbiB0LnJlYWRfdGV4dChlcnJvcnM9J2lnbm9yZScpLnNwbGl0bGluZXMoKSBpZiBsbi5zdHJpcCgpKQogICAgICAgICAgICBuYyA9IG1heChuYywgbXggKyAxKQogICAgICAgIGV4Y2VwdCBFeGNlcHRpb246CiAgICAgICAgICAgIHBhc3MKICAgIHJldHVybiBuYyBvciAxCgoKX3Bvb2wgPSBfY29sbGVjdF9wb29sKCkKaWYgbm90IF9wb29sOgogICAgcmFpc2UgU3lzdGVtRXhpdCgnW3NwbGl0XSDmnKrmlLbpm4bliLDluKbmoIfms6jnmoTmoLfmnKzvvIhpbWFnZXMvIOS4jiBsYWJlbHMvIOmcgOWQjOe6p+S4lOS4gOS4gOWvueW6lO+8iScpCiMg5bey5pyJ5YiS5YiG5qOA5rWL77yIdHJhaW4vdmFsIOebruW9leWdh+mdnuepuuWImei3s+i/h++8iQpfZXhpc3RpbmcgPSBbX2Jhc2UgLyAnaW1hZ2VzJyAvIHggZm9yIHggaW4gKCd0cmFpbicsICd2YWwnLCAndGVzdCcpXQppZiBhbGwocC5pc19kaXIoKSBhbmQgYW55KHAuaXRlcmRpcigpKSBmb3IgcCBpbiBfZXhpc3RpbmdbOjJdKToKICAgIHByaW50KCdbc3BsaXRdIOaVsOaNrumbhuW3suWMheWQqyB0cmFpbi92YWwg5YiS5YiG77yM6Lez6L+H6Ieq5Yqo5YiS5YiG44CCJykKICAgIHJhaXNlIFN5c3RlbUV4aXQoMCkKCnJhbmRvbS5zZWVkKDIwMjYpCnJhbmRvbS5zaHVmZmxlKF9wb29sKQpuID0gbGVuKF9wb29sKQpuX3RlID0gaW50KG4gKiBfdGVfcCAvIDEwMC4wKQpuX3ZhID0gaW50KChuIC0gbl90ZSkgKiBfdmFfcCAvIDEwMC4wKQpuX3RyID0gbiAtIG5fdGUgLSBuX3ZhCmlmIG5fdHIgPD0gMDoKICAgIHJhaXNlIFN5c3RlbUV4aXQoJ1tzcGxpdF0g6K6t57uD5qC35pys5pWw5LiN6Laz77yI5oC75pWwICVk77yJJyAlIG4pCgpfc3BsaXRfcm9vdCA9IF9iYXNlLnBhcmVudCAvIChfYmFzZS5uYW1lICsgJ19zcGxpdCcpCmZvciBfcGFydCBpbiAoJ3RyYWluJywgJ3ZhbCcsICd0ZXN0Jyk6CiAgICBpZiAoX3BhcnQgPT0gJ3Rlc3QnIGFuZCBfdGVfcCA8PSAwKToKICAgICAgICBjb250aW51ZQogICAgKF9zcGxpdF9yb290IC8gJ2ltYWdlcycgLyBfcGFydCkubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQogICAgKF9zcGxpdF9yb290IC8gJ2xhYmVscycgLyBfcGFydCkubWtkaXIocGFyZW50cz1UcnVlLCBleGlzdF9vaz1UcnVlKQoKX29yZGVyID0gWyd0cmFpbiddICogbl90ciArIFsndmFsJ10gKiBuX3ZhICsgWyd0ZXN0J10gKiBuX3RlCmlkeCA9IDAKZm9yIChfc3JjX2ltZywgX3NyY19sYWIpLCBfcGFydCBpbiB6aXAoX3Bvb2wsIF9vcmRlcik6CiAgICBfaW1nX2RzdCA9IF9zcGxpdF9yb290IC8gJ2ltYWdlcycgLyBfcGFydCAvIFBhdGgoX3NyY19pbWcpLm5hbWUKICAgIF9sYWJfZHN0ID0gX3NwbGl0X3Jvb3QgLyAnbGFiZWxzJyAvIF9wYXJ0IC8gUGF0aChfc3JjX2xhYikubmFtZQogICAgdHJ5OgogICAgICAgIGlmIG5vdCBfaW1nX2RzdC5leGlzdHMoKToKICAgICAgICAgICAgb3Muc3ltbGluayhvcy5wYXRoLmFic3BhdGgoX3NyY19pbWcpLCBzdHIoX2ltZ19kc3QpKQogICAgICAgIGlmIG5vdCBfbGFiX2RzdC5leGlzdHMoKToKICAgICAgICAgICAgb3Muc3ltbGluayhvcy5wYXRoLmFic3BhdGgoX3NyY19sYWIpLCBzdHIoX2xhYl9kc3QpKQogICAgZXhjZXB0IE9TRXJyb3I6CiAgICAgICAgc2h1dGlsLmNvcHkyKF9zcmNfaW1nLCBfaW1nX2RzdCkKICAgICAgICBzaHV0aWwuY29weTIoX3NyY19sYWIsIF9sYWJfZHN0KQogICAgaWR4ICs9IDEKCl9uYyA9IF9kZXRlY3RfbmMoX3NwbGl0X3Jvb3QgLyAnbGFiZWxzJykKX25hbWVzID0gX2NmZy5nZXQoJ25hbWVzJykKaWYgbm90IGlzaW5zdGFuY2UoX25hbWVzLCBkaWN0KToKICAgIF9uYW1lcyA9IHtpOiAnY2xhc3NfJyArIHN0cihpKSBmb3IgaSBpbiByYW5nZShfbmMpfQoKX2xpbmVzID0gWwogICAgJ3BhdGg6ICcgKyBzdHIoX3NwbGl0X3Jvb3QucmVzb2x2ZSgpKSwKICAgICd0cmFpbjogaW1hZ2VzL3RyYWluJywKICAgICd2YWw6IGltYWdlcy92YWwnLApdCmlmIF90ZV9wID4gMDoKICAgIF9saW5lcy5hcHBlbmQoJ3Rlc3Q6IGltYWdlcy90ZXN0JykKX2xpbmVzLmFwcGVuZCgnbmM6ICcgKyBzdHIoX25jKSkKX2xpbmVzLmFwcGVuZCgnbmFtZXM6ICcgKyByZXByKGRpY3QoX25hbWVzKSkpCl9zcGxpdF95YW1sID0gX3NwbGl0X3Jvb3QgLyAncGFwZXJfcmVwcm9fc3BsaXQueWFtbCcKX3NwbGl0X3lhbWwud3JpdGVfdGV4dCgnXG4nLmpvaW4oX2xpbmVzKSArICdcbicsIGVuY29kaW5nPSd1dGYtOCcpCgojIOimhuWGmSBlbnbvvIzorq3nu4Plkb3ku6TlsIbkvb/nlKjmlrDliJLliIYKdHJ5OgogICAgX3JlbCA9IHN0cihfc3BsaXRfeWFtbC5yZWxhdGl2ZV90byhfcm9vdCkpCmV4Y2VwdCBWYWx1ZUVycm9yOgogICAgX3JlbCA9IHN0cihfc3BsaXRfeWFtbCkKX2VudiA9IF9yb290IC8gJy5wYXBlcl9yZXByb19kYXRhc2V0LmVudicKX2Vudi53cml0ZV90ZXh0KCdleHBvcnQgUEFQRVJfUkVQUk9fREFUQV9DT05GSUc9JyArIGpzb24uZHVtcHMoX3JlbCkgKyAnXG4nLCBlbmNvZGluZz0ndXRmLTgnKQpwcmludCgnW3NwbGl0XSDoh6rliqjliJLliIblrozmiJDvvJp0cmFpbj0lZCAvIHZhbD0lZCAvIHRlc3Q9JWTvvIjmgLvmlbAgJWTvvInvvIzphY3nva7vvJolcycKICAgICAgJSAobl90ciwgbl92YSwgbl90ZSwgbiwgX3JlbCkpCg=="
                split_step = (
                    "if [ -f .paper_repro_dataset.env ]; then "
                    "_dcfg=$(sed -n 's/^export PAPER_REPRO_DATA_CONFIG=//p' .paper_repro_dataset.env | tr -d '\"'); "
                    "if [ -n \"$_dcfg\" ]; then "
                    "echo '按设定比例自动划分 train/val/test（软链接实现，不复制大文件）...'; "
                    "\"$PYTHON_BIN\" -c \"from pathlib import Path; import base64; exec(base64.b64decode('" + _b64 + "'))\" \"" + _ss + "\" \"$_dcfg\"; "
                    "fi; "
                    "fi"
                )
                dataset_step = dataset_step.rstrip() + " && " + split_step

        else:
            dataset_step = (
                f"cd {shlex.quote(str(self.remote_workdir))}/repo && "
                "echo '自动数据集下载已关闭；仅扫描仓库中的数据集配置。'; "
                "find data -maxdepth 2 -type f -name '*.yaml' -print 2>/dev/null || true"
            )
        verify_step = (
            "cd {workdir} && {conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ \"{mode}\" = \"conda\" ]; then "
            "eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro >/dev/null 2>&1; "
            "PYTHON_BIN=python; "
            "else "
            "if [ -f .venv/bin/activate ]; then . .venv/bin/activate; fi; "
            "PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
            "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
            "[ -n \"$PYTHON_BIN\" ] || {{ echo '未找到 Python 可执行文件，无法执行验证'; exit 127; }}; "
            "if [ -f pytest.ini ] || [ -d tests ]; then "
            "if ! \"$PYTHON_BIN\" -c 'import pytest' >/dev/null 2>&1; then "
            "echo '验证需要 pytest，使用共享 pip 缓存补装'; "
            "PIP_CACHE_DIR=\"$HOME/.cache/pip\"; mkdir -p \"$PIP_CACHE_DIR\"; "
            "\"$PYTHON_BIN\" -m pip install --disable-pip-version-check --cache-dir \"$PIP_CACHE_DIR\" pytest; "
            "fi; "
            "if timeout 600 \"$PYTHON_BIN\" -m pytest -q --maxfail=1 -x > /tmp/verify_pytest.log 2>&1; then "
            "echo '仓库自带测试全部通过'; tail -8 /tmp/verify_pytest.log; "
            "elif grep -qE 'ERROR collecting|ImportError while importing|ModuleNotFoundError|no tests ran' /tmp/verify_pytest.log; then "
            "echo '仓库自带测试需外部依赖或无法收集（不阻断，转编译冒烟）'; tail -8 /tmp/verify_pytest.log; "
            "echo '编译冒烟：校验全部 Python 文件语法...'; "
            "timeout 300 \"$PYTHON_BIN\" -m compileall -q . && echo '编译检查通过：全部 .py 语法有效'; "
            "else echo '仓库自带测试存在失败项：'; tail -25 /tmp/verify_pytest.log; exit 1; fi; "
            "else \"$PYTHON_BIN\" -m compileall .; fi"
        ).format(
            workdir=f"{self.remote_workdir}/repo",
            mode=self.env_mode,
            conda_bootstrap=conda_bootstrap,
        )
        model_step = (
        f"cd {shlex.quote(f'{self.remote_workdir}/repo')} && "
        f"{conda_bootstrap}; "
        "if [ -n \"$CONDA_BIN\" ] && [ \""
        f"{self.env_mode}"
        "\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
        "conda_activate_paperrepro >/dev/null 2>&1; PYTHON_BIN=python; "
        "else PYTHON_BIN=\"$PWD/.venv/bin/python\"; [ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
        + ModelDiscovery.build_remote_command("\"$PYTHON_BIN\"")
        )
        if configured_run_command or self.auto_run:
            # 微调尾缀：把 UI 微调面板参数（batch/imgsz/epochs/...）追加到训练命令末尾，
            # argparse 后者覆盖前者，实现“改参数即改模型训练配置”。
            tune_args = str(self.task.get("tune_args") or "").strip()
            # auto 分支：变量不加外层双引号，bash -c 收到后正常展开并分词；
            # 加引号会把整条命令变成单个词导致 “No such file or directory”
            effective_run_command = configured_run_command or "${PAPER_REPRO_AUTO_RUN_COMMAND}"
            if tune_args:
                effective_run_command = effective_run_command.rstrip() + " " + tune_args
            safe_run_command = shlex.quote(effective_run_command)
            run_step = (
                f"cd {shlex.quote(f'{self.remote_workdir}/repo')} && "
                f"{conda_bootstrap}; "
                "if [ -n \"$CONDA_BIN\" ] && [ \""
                f"{self.env_mode}"
                "\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
                "conda_activate_paperrepro >/dev/null 2>&1; PYTHON_BIN=python; "
                "else PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
                "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
                "echo '准备执行模型运行阶段'; "
                + (
                    "# 数据集缺失已自动降级：跳过实际训练，只做入口安全启动检查\n"
                    "if [ -f .paper_repro_dataset_missing ] && [ -z \""
                    + ("1" if configured_run_command else "")
                    + "\" ]; then "
                    "ENTRYPOINT=''; for candidate in train.py detect.py predict.py main.py app.py; do "
                    "if [ -f \"$candidate\" ]; then ENTRYPOINT=\"$candidate\"; break; fi; done; "
                    "if [ -n \"$ENTRYPOINT\" ]; then echo \"数据集未就绪（已降级安全检查）：模型入口 $ENTRYPOINT 启动参数检查中...\"; "
                    "\"$PYTHON_BIN\" \"$ENTRYPOINT\" --help >/dev/null && echo '入口可正常启动（本次为安全检查，未执行训练）'; "
                    "else echo '数据集未就绪（已降级安全检查）：未识别到标准模型入口，已完成环境与代码验证。'; fi; "
                    "exit 0; "
                    "fi; "
                    if not configured_run_command
                    else ""
                )
                + f"if [ -f {DatasetDiscovery.env_file_name} ]; then . {DatasetDiscovery.env_file_name}; fi; "
                f"if [ -f {ModelDiscovery.env_file_name} ]; then . {ModelDiscovery.env_file_name}; fi; "
                "if [ -z \"${PAPER_REPRO_AUTO_RUN_COMMAND:-}\" ] && [ -z \""
                + ("1" if configured_run_command else "")
                + "\" ]; then echo '未能自动推断训练命令，请在页面填写 README 中的训练命令。' >&2; exit 65; fi; "
                # 用 bash -c 继承当前已激活的 conda 环境；bash -lc 会重置 PATH 导致切回 base
                f"timeout {self.command_timeout} bash -c {safe_run_command}"
            )
        else:
            run_step = (
                f"cd {shlex.quote(f'{self.remote_workdir}/repo')} && "
                f"{conda_bootstrap}; "
                "if [ -n \"$CONDA_BIN\" ] && [ \""
                f"{self.env_mode}"
                "\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
                "conda_activate_paperrepro >/dev/null 2>&1; PYTHON_BIN=python; "
                "else PYTHON_BIN=\"$PWD/.venv/bin/python\"; "
                "[ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
                "ENTRYPOINT=''; "
                "for candidate in train.py detect.py predict.py main.py app.py; do "
                "if [ -f \"$candidate\" ]; then ENTRYPOINT=\"$candidate\"; break; fi; done; "
                "if [ -n \"$ENTRYPOINT\" ]; then "
                "echo \"自动识别模型入口：$ENTRYPOINT（执行启动参数检查）\"; "
                "\"$PYTHON_BIN\" \"$ENTRYPOINT\" --help >/dev/null; "
                "echo '模型入口可正常启动，已完成安全启动检查'; "
                "else echo '未识别到标准模型入口，已完成环境和代码验证；请在任务配置中提供 run_command。'; fi"
            )
        collection_script = (
            "import base64, csv, json\n"
            "from pathlib import Path\n"
            "root = Path('.')\n"
            "metric_tokens = ('map', 'precision', 'recall', 'f1', 'accuracy', 'acc', 'loss')\n"
            "metrics, sources, artifacts = {}, [], []\n"
            "for path in sorted(root.rglob('*')):\n"
            "    if any(part in {'.git', '.venv', 'venv', '__pycache__'} for part in path.parts) or not path.is_file(): continue\n"
            "    relative = str(path.relative_to(root))\n"
            "    name = path.name.lower()\n"
            "    if name in {'best.pt', 'last.pt'} or path.suffix.lower() in {'.png', '.jpg', '.jpeg'}:\n"
            "        if len(artifacts) < 50: artifacts.append(relative)\n"
            "    if name not in {'results.csv', 'metrics.csv', 'results.json', 'metrics.json'}: continue\n"
            "    try:\n"
            "        if path.suffix.lower() == '.csv':\n"
            "            rows = list(csv.DictReader(path.open(encoding='utf-8-sig', newline='')))\n"
            "            values = rows[-1] if rows else {}\n"
            "        else:\n"
            "            values = json.loads(path.read_text(encoding='utf-8'))\n"
            "            if isinstance(values, list): values = values[-1] if values else {}\n"
            "        if not isinstance(values, dict): continue\n"
            "        extracted = {}\n"
            "        for key, value in values.items():\n"
            "            if any(token in str(key).lower() for token in metric_tokens):\n"
            "                try: extracted[str(key)] = float(value)\n"
            "                except (TypeError, ValueError): pass\n"
            "        if extracted:\n"
            "            metrics.update(extracted); sources.append(relative)\n"
            "    except (OSError, ValueError, json.JSONDecodeError): continue\n"
            "payload = {'metrics': metrics, 'metric_sources': sources, 'artifacts': artifacts}\n"
            "# 人类可读指标摘要：训练完成后在日志尾部直接可见（mAP/Precision/Recall/Loss 等）\n"
            "if metrics:\n"
            "    def _fmt(k, v):\n"
            "        return f'{k.strip()}={v:.6g}'\n"
            "    summary = ' | '.join(_fmt(k, v) for k, v in sorted(metrics.items()))\n"
            "    print('[指标结果] ' + summary)\n"
            "else:\n"
            "    print('[指标结果] 未发现 results.csv/metrics 等指标文件（本次可能未执行训练，或仓库未输出指标）')\n"
            "print('PAPER_REPRO_RESULTS_JSON=' + base64.b64encode(json.dumps(payload, ensure_ascii=False).encode('utf-8')).decode('ascii'))"
        )
        collection_step = (
            f"cd {shlex.quote(f'{self.remote_workdir}/repo')} && "
            f"{conda_bootstrap}; "
            "if [ -n \"$CONDA_BIN\" ] && [ \""
            f"{self.env_mode}"
            "\" = \"conda\" ]; then eval \"$(\"$CONDA_BIN\" shell.bash hook 2>/dev/null || true)\"; "
            "conda_activate_paperrepro >/dev/null 2>&1; PYTHON_BIN=python; "
            "else PYTHON_BIN=\"$PWD/.venv/bin/python\"; [ -x \"$PYTHON_BIN\" ] || PYTHON_BIN=python3; fi; "
            "\"$PYTHON_BIN\" -c \"from pathlib import Path; import base64; Path('.collect_results.py').write_text(base64.b64decode('"
            + base64.b64encode(collection_script.encode("utf-8")).decode("ascii")
            + "').decode('utf-8'), encoding='utf-8')\"; "
            "\"$PYTHON_BIN\" .collect_results.py"
        )
        # 首选/备用源互备：官方 GitHub <-> ghfast.top 加速自动互换（换网络/服务器也稳）
        raw_url = _clean_clone_url(self.clone_url or self.repo_url)
        # 先剥掉任意层加速前缀（防止历史保存/粘贴已含 ghfast 导致 ghfast 套 ghfast → 403）
        base_url = _unwrap_ghfast(raw_url)
        ghfast_prefix = "https://ghfast.top/https://github.com/"
        if base_url.startswith(ghfast_prefix):  # 理论上已被剥净，再兜底一次
            base_url = _unwrap_ghfast(base_url)
        if base_url.startswith("https://github.com/") or base_url.startswith("http://github.com/"):
            primary_url = "https://ghfast.top/" + base_url   # 加速源为主，国内机更快
            alt_url = base_url                                 # 官方为备
        else:
            primary_url = base_url
            alt_url = ""
        # 模板内 URL 均已用双引号包裹（"@SRC@"）：此处只嵌入“清洗后裸 URL”，绝不再 shlex.quote（
        # 否则会拼成 "'https://…'" 使 git 收到字面单引号 → protocol ''https' is not supported）
        clone_source = primary_url
        clone_alt_source = alt_url
        workdir = shlex.quote(str(self.remote_workdir))
        # —— 拉取代码：fetch 有超时；任一步失败自动清理后整库重克隆（最多两轮）；加速地址与官方源互备 ——
        clone_step = (
            "cd @WORKDIR@ && export GIT_LFS_SKIP_SMUDGE=1 && "
            "export GIT_TERMINAL_PROMPT=0 && "
            "git config --global http.version HTTP/1.1 && "
            "git config --global http.lowSpeedLimit 1024 && "
            "git config --global http.lowSpeedTime 45 && "
            "fetch_or_reclone() { cd repo && "
            "(timeout 150 git fetch --depth 1 --no-tags --progress origin && git reset --hard FETCH_HEAD && git clean -ffdx) && return 0; "
            "cd .. && rm -rf repo; return 1; }; "
            "_clone_once() { rm -rf repo; "
            "git clone --depth 1 --no-tags --single-branch --progress \"$1\" repo && return 0; "
            "rm -rf repo; timeout @CLONE_TIMEOUT@ "
            "git clone --depth 1 --no-tags --filter=blob:none --single-branch --progress \"$1\" repo; }; "
            "_try_sources() { "
            "_clone_once \"$1\" && return 0; "
            "[ -n \"$2\" ] && { echo '首选源失败，自动切换备用源...'; _clone_once \"$2\" && return 0; }; "
            "return 1; }; "
            "timeout 13 git ls-remote --heads \"@SRC@\" >/dev/null 2>&1 || echo '首选源 13 秒内无响应，将自动多源回退。' >&2; "
            "_done=0; "
            "for _round in 1 2; do "
            "if [ -d repo/.git ]; then "
            "fetch_or_reclone && _done=1 "
            "|| { echo '增量更新失败，清理后整库重克隆（第 $_round 轮）...'; _try_sources \"@SRC@\" \"@ALT@\" && _done=1; }; "
            "else "
            "_try_sources \"@SRC@\" \"@ALT@\" && _done=1; "
            "fi; "
            "[ $_done -eq 1 ] && break; "
            "[ $_round -eq 1 ] && { echo '第 1 轮拉取失败，稍候重试第 2 轮...'; sleep 5; }; "
            "done; "
            "[ $_done -eq 1 ] || { echo '仓库拉取失败：请检查网络，或在界面填写可用的加速仓库地址后重新提交。'; exit 66; }"
        ).replace("@WORKDIR@", workdir).replace("@CLONE_TIMEOUT@", str(self.clone_timeout)).replace("@SRC@", clone_source).replace("@ALT@", clone_alt_source)
        steps: List[Dict[str, str]] = [
            {"id": "prepare", "title": "准备工作目录", "command": f"mkdir -p {self.remote_workdir} >/dev/null 2>&1"},
            {"id": "clone", "title": "拉取论文代码仓库", "command": clone_step},
            {"id": "env", "title": "环境诊断与适配", "command": f"cd {self.remote_workdir}/repo && echo '--- 环境诊断 ---' && echo 'runner-python-fallback-v3' && python3 --version && ls -1 . 2>/dev/null | head && {env_step}"},
            {"id": "install", "title": "安装依赖", "command": install_step},
            {"id": "dependencies", "title": "扫描并补装缺失依赖", "command": dependency_step},
            {"id": "dataset", "title": "识别并准备数据集", "command": dataset_step},
            {"id": "verify", "title": "验证复现脚本", "command": verify_step},
            {"id": "model", "title": "识别模型训练入口", "command": model_step},
            {"id": "run", "title": "识别并启动模型", "command": run_step},
            {"id": "collect", "title": "收集指标与关键产物", "command": collection_step},
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

    def execute(
        self,
        on_step: Callable[[str, str, str], None] | None = None,
        cancel_event=None,
        resume_from: str = "",
    ) -> Dict[str, Any]:
        self._cancel_event = cancel_event
        if cancel_event is not None and cancel_event.is_set():
            return {"status": "cancelled", "message": "任务已被用户取消（尚未开始执行）。"}
        if not self.host and not self.candidates:
            return {"status": "failed", "message": "云服务器连接信息不完整，请补充主机和用户名。"}

        if paramiko is None:
            return {"status": "failed", "message": "paramiko 未安装，请在本地运行 pip install paramiko。"}

        # ---- 凭据前置（P0-3）：无任何认证源先报“缺凭据”，不做无谓网络探测 ----
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
                "message": "未找到可用 SSH 认证源：请填写云服务器密码，或提供有效私钥（真实文件路径或粘贴 PEM 全文），或在本机 ssh-agent 中加载密钥。",
                "attempts": 0,
            }

        # ---- L1：并行可达分类（只排序与诊断，不判死；单台 6s×2 重试，总预算 ≤12s） ----
        cands = self.candidates or [{"host": self.host, "port": int(self.port) if str(self.port).isdigit() else 22,
                                     "user": self.user}]
        try:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(cands))) as _ex:
                reach_flags = list(_ex.map(lambda c: probe_host(c["host"], c["port"]), cands))
        except Exception:
            reach_flags = [False] * len(cands)
        ok_list = [c for c, ok in zip(cands, reach_flags) if ok]
        rest_list = [c for c, ok in zip(cands, reach_flags) if not ok]
        order = ok_list + rest_list
        self._log.info(
            "自动识别：候选 " + str(len(cands)) + " 台（TCP 可达 " + str(len(ok_list))
            + "），按可达优先顺序进行真实凭据连接"
        )

        # ---- L2：真实凭据连接（决定性）——每台 12s，auth 短路，其它转台 ----
        last_err = None
        for cand in order:
            if cancel_event is not None and cancel_event.is_set():
                return {"status": "cancelled", "message": "任务已被用户取消（连接阶段）。"}
            profile = {
                "host": cand["host"],
                "port": int(cand.get("port") or self.port or 22),
                "user": cand.get("user") or self.user or "root",
                "password": self.password or "",
            }
            if cand.get("key_path"):
                profile["key_path"] = cand["key_path"]
            elif resolved_key and os.path.exists(resolved_key):
                profile["key_path"] = resolved_key
            elif key_candidates:
                profile["key_path"] = key_candidates[0]
            probe_ssh = None
            try:
                probe_ssh = ssh_connect(profile, timeout=12.0)
                self.host, self.port, self.user = profile["host"], profile["port"], profile["user"]
                self._log.info(f"自动识别：已真实连接 {self.user}@{self.host}:{self.port}（凭据握手通过）")
                probe_ssh.close()
                last_err = None
                break
            except Exception as exc:
                last_err = exc
                cat = classify_conn_error(exc)
                self._log.warning(f"候选 {cand.get('user')}@{cand['host']}:{cand.get('port')} 连接失败（{cat}）：{exc}")
                if cat == "auth":
                    # 同组凭据：首台认证失败即判定凭据级错误，短路返回精准诊断
                    return {
                        "status": "failed",
                        "message": (
                            f"SSH 认证失败（{type(exc).__name__}）：{profile['user']}@{profile['host']}:{profile['port']} "
                            "拒绝了当前凭据。排查：1) 密码是否正确（AutoDL 密码在控制台实例页设置）；"
                            "2) 私钥是否与公钥配对，公钥已加入服务器 authorized_keys（可点“注入公钥”）；"
                            "3) 确认端口为实例当前开放端口（AutoDL 通常 4xxxx）。"
                        ),
                        "attempts": 1,
                    }
            finally:
                if probe_ssh is not None:
                    try:
                        probe_ssh.close()
                    except Exception:
                        pass
        if last_err is not None:
            tried = "; ".join(
                f"{c.get('user')}@{c['host']}:{c.get('port')}（{classify_conn_error(last_err) if c is order[-1] else 'x'}）"
                for c in order
            )
            return {
                "status": "failed",
                "message": (
                    "自动识别 " + str(len(order)) + " 台候选均无法完成连接（" + tried + "）。"
                    "请确认实例已开机，且地址端口为控制台最新 SSH 登录信息（AutoDL 换机后地址会变；"
                    "可在填写框一次粘贴多台，程序自动选用可用者）。"
                ),
                "attempts": len(order),
            }

        self._log.info(f"开始在 {self.host}:{self.port} ({self.user}) 上执行远程复现流水线 (trace: {self._trace_id})")
        last_error = None
        for attempt in range(1, self.max_retries + 2):
            ssh = None
            try:
                self._log.info(f"第 {attempt} 次尝试建立 SSH 连接...")
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
                        if _is_auth_exception(ce):
                            raise  # 认证类失败重试无意义，立即上抛精准诊断
                        conn_err = ce
                        self._log.warning(f"SSH 连接重试 ({conn_try + 1}/3) 失败: {ce}")
                        time.sleep(2)
                if not connected:
                    raise conn_err or RuntimeError("SSH 连接失败")

                self._log.info("SSH 连接成功建立，开启 TCP Keep-Alive")
                transport = ssh.get_transport()
                if transport is not None:
                    transport.set_keepalive(15)

                logs: List[str] = []
                pipeline = self.build_pipeline()
                resume_flag = resume_from or str(self.task.get("resume_step") or "")
                _start_idx = 0
                if resume_flag:
                    _ids = [s["id"] for s in pipeline]
                    _start_idx = _ids.index(resume_flag) if resume_flag in _ids else 0
                if _start_idx > 0:
                    self._log.info(
                        f"断点续跑：跳过 {_start_idx} 个已完成步骤，从 [{pipeline[_start_idx]['id']}] 继续")
                for step in pipeline[_start_idx:]:
                    if cancel_event is not None and cancel_event.is_set():
                        raise TaskCancelled("任务已被用户取消")
                    step_id = step["id"]
                    step_title = step["title"]
                    self._log.info(f"开始步骤 [{step_id}]: {step_title}")
                    self._last_step_id = step_id
                    self._last_step_title = step_title
                    # 关键调试信息：记录即将执行的完整远程命令
                    self._log.log_command(step_id, step["command"])
                    step_header = f"--- {step_title} ---"
                    logs.append(step_header)
                    if on_step:
                        on_step(step_id, step_title, step_header)

                    # Sending the command through stdin prevents the SSH login shell
                    # from expanding variables before Bash receives the script.
                    stdin, stdout, stderr = ssh.exec_command("bash -s")
                    stdin.write(step["command"] + "\n")
                    stdin.flush()
                    stdin.channel.shutdown_write()
                    channel = stdout.channel
                    step_output: List[str] = []
                    _prog_last = {"t": 0.0}

                    def _on_chunk(chunk: str) -> None:
                        """真实多行日志实时转发；纯 \r 进度条每 ~12s 采样一次，避免刷屏/刷爆任务日志。"""
                        step_output.append(chunk)
                        if not chunk:
                            return
                        if "\n" in chunk:
                            if on_step:
                                on_step(step_id, step_title, chunk)
                            return
                        now = time.monotonic()
                        if "\r" in chunk and now - _prog_last["t"] >= 12.0:
                            _prog_last["t"] = now
                            segs = [p for p in chunk.split("\r") if p.strip()]
                            if segs and on_step:
                                on_step(step_id, step_title, "[下载进度] " + segs[-1].strip()[:160])

                    deadline = time.monotonic() + self.command_timeout
                    while not channel.exit_status_ready():
                        if channel.recv_ready():
                            _on_chunk(channel.recv(4096).decode("utf-8", errors="replace"))
                        if channel.recv_stderr_ready():
                            _on_chunk(channel.recv_stderr(4096).decode("utf-8", errors="replace"))
                        if time.monotonic() >= deadline:
                            channel.close()
                            msg = f"{step_title} 超过 {self.command_timeout // 60} 分钟仍未完成。"
                            self._log.error(f"步骤 [{step_id}] 执行超时: {msg}")
                            raise TimeoutError(msg)
                        if cancel_event is not None and cancel_event.is_set():
                            channel.close()
                            self._log.info(f"步骤 [{step_id}] 被用户取消，已断开远端连接。")
                            raise TaskCancelled("任务已被用户取消")
                        time.sleep(0.2)

                    while channel.recv_ready():
                        step_output.append(channel.recv(4096).decode("utf-8", errors="replace"))
                    while channel.recv_stderr_ready():
                        step_output.append(channel.recv_stderr(4096).decode("utf-8", errors="replace"))

                    exit_status = channel.recv_exit_status()
                    step_log = "".join(step_output).strip()
                    if step_log:
                        logs.append(step_log)
                    # 输出结果解码（\uXXXX → 中文），日志直接可读
                    self._log.log_result(step_id, exit_status, step_log)
                    if exit_status != 0:
                        err_msg = f"{step_title} 失败（退出码 {exit_status}）：{step_log or '远程命令未返回错误详情。'}"
                        # 数据集准备失败：给出可操作的中文诊断，避免裸 traceback 误导
                        if step_id == "dataset" and "Traceback" in step_log:
                            head = step_log.strip().splitlines()
                            tail = [line for line in head if "Error" in line or "error" in line]
                            err_msg = (
                                "数据集准备失败：仓库声明的官方下载脚本没有成功完成。\n"
                                "常见原因：① 仓库下载脚本依赖特定分支/镜像源已失效；"
                                "② 下载被中断导致目录结构不完整（本系统已自动跳过不存在的重命名操作）；"
                                "③ 数据集体积过大超出下载时限。\n"
                                "建议：在任务配置中填写可用的数据下载地址，或手动下载数据集到云端后重新执行。\n"
                                + ("关键错误：" + " | ".join(tail[:3]) if tail else "")
                            )
                        self._log.error(f"步骤 [{step_id}] 异常退出: {err_msg}")
                        raise RemoteStepError(err_msg)
                    self._log.info(f"步骤 [{step_id}] 执行成功")
                    if on_step:
                        on_step(step_id, step_title, f"{step_title} 已完成。")

                pipeline = self.build_pipeline()
                log_payload = {
                    "attempt": attempt,
                    "pipeline": pipeline,
                    "stdout": "\n".join(logs),
                    "stderr": "",
                }

                all_logs = "\n".join(logs)
                collection = self.extract_collection_payload(all_logs)
                dataset = DatasetDiscovery.extract_payload(all_logs)
                model = ModelDiscovery.extract_payload(all_logs)
                # 数据集缺失自动降级：任务仍成功，但标记原因供 UI 展示
                if "[paper-repro-degrade]" in all_logs and not dataset:
                    dataset = {"degraded": True, "reason": "仓库无匹配数据集配置或下载不可用，已自动降级为安全检查（未训练）"}
                return {
                    "status": "success",
                    "message": "远程复现流水线已完成，日志已返回。",
                    "logs": json.dumps(log_payload, ensure_ascii=False, indent=2),
                    "metrics": collection.get("metrics", {}),
                    "dataset": dataset,
                    "model": model,
                    "metric_sources": collection.get("metric_sources", []),
                    "artifacts": collection.get("artifacts", []),
                    "attempts": attempt,
                }
            except TaskCancelled as exc:
                last_error = exc
                break
            except Exception as exc:  # pragma: no cover
                last_error = exc
                if isinstance(exc, RemoteStepError):
                    break
                if _is_auth_exception(exc):
                    break  # 认证失败重试无意义：直接结束并输出精准诊断
                if attempt > self.max_retries:
                    break
                time.sleep(attempt * 3)
            finally:
                if ssh:
                    try:
                        ssh.close()
                    except Exception:
                        pass

        if isinstance(last_error, TaskCancelled):
            return {
                "status": "cancelled",
                "message": "任务已被用户中止。",
                "attempts": attempt if "attempt" in dir() else 0,
            }

        if _is_auth_exception(last_error):
            auth_state = self.detect_ssh_auth_sources()
            message = (
                f"SSH 认证失败（{type(last_error).__name__}）：云服务器 {self.user}@{self.host}:{self.port} "
                "拒绝了当前身份凭据，重试无意义，已尽快终止。可能原因："
                "1) “SSH 私钥路径”不是有效私钥（应填真实私钥文件路径或直接粘贴 -----BEGIN 私钥全文）；"
                "2) 本机公钥未加入云服务器 ~/.ssh/authorized_keys；"
                "3) 端口并非实例实际开放的 SSH 端口（AutoDL 等平台通常为 4xxxx 而非 22）；"
                "4) 密码认证时密码不正确。"
            )
            resolved = auth_state.get("resolved_key") or "无有效私钥文件"
            agent_count = len(auth_state.get("agent_keys") or [])
            message += f" 本地认证源检查：resolved_key={resolved}；ssh-agent 密钥数={agent_count}。"
            pub_hint = ""
            if resolved and resolved != "无有效私钥文件":
                pub_path = str(Path(resolved).with_suffix(".pub"))
                if os.path.isfile(pub_path):
                    try:
                        pub_content = Path(pub_path).read_text(
                            encoding="utf-8", errors="replace"
                        ).strip()
                        pub_hint = (
                            f" 本机配套公钥文件：{pub_path}（前 40 字符：{pub_content[:40]}…）。"
                            "若该公钥尚未授权，请将其全文复制并添加到云服务器 ~/.ssh/authorized_keys"
                            "（或 AutoDL 控制台的密钥管理页面）。"
                        )
                    except OSError:
                        pass
                else:
                    pub_hint = (
                        f" 未找到配套公钥文件 {pub_path}，请确认私钥对应的公钥已加入云服务器"
                        " ~/.ssh/authorized_keys。"
                    )
            message += pub_hint or " 若实例支持密码登录（AutoDL 创建实例时可设置 root 密码），也可改用密码认证。"
            return {"status": "failed", "message": message, "attempts": self.max_retries + 1}

        return {
            "status": "failed",
            "message": f"远程执行失败：{last_error}",
            "attempts": self.max_retries + 1,
            "failed_step": self._last_step_id,
            "failed_title": self._last_step_title,
        }
def _resolve_key_file(key_value: Any) -> str:
    """将私钥引用解析为真实文件路径：PEM 全文写入本机密钥文件，或校验路径存在。"""
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
            try:
                os.chmod(key_file, 0o600)
            except OSError:
                pass
        return str(key_file)
    expanded = os.path.expanduser(value)
    if expanded and os.path.isfile(expanded):
        return expanded
    return ""


def inject_public_key(
    host: str,
    user: str,
    port: str,
    key: str,
    password: str = "",
    public_key: str = "",
    timeout: int = 30,
) -> tuple[bool, str]:
    """将公钥一键注入云服务器 ~/.ssh/authorized_keys（幂等，等价于 ssh-copy-id）。

    使用密码（或已有私钥）临时登录一次，把公钥追加到服务器 authorized_keys，
    之后即可全程使用公钥认证登录——解决“AutoDL 控制台无密钥绑定入口”的问题。
    公钥以 base64 传输，避免引号/特殊字符在远端 shell 中展开出错。
    """
    host_value = (host or "").strip()
    user_value = (user or "").strip()
    port_value = (port or "22").strip()
    key_value = _resolve_key_file(key)
    # 归一化：host 处允许直接粘贴完整 ssh 命令 / user@host / 别名（换云服务器场景）
    try:
        from paper_repro_app.ssh_utils import resolve_connection_fields as _rcf
        _norm = _rcf(host, user, port, key)
        host_value = _norm["host"]
        user_value = _norm["user"]
        port_value = _norm["port"] or "22"
        key_value = _resolve_key_file(_norm.get("key") or key)
    except Exception:
        pass
    pub_value = (public_key or "").strip()
    if not host_value or not user_value:
        return False, "请先填写云服务器地址和用户名。"
    if not pub_value:
        return False, "本机公钥为空，无法注入。请先确认已生成 SSH 密钥对。"
    if not password and not key_value:
        return False, "注入公钥需要登录凭据：请填写云服务器密码，或确认已填写的私钥路径有效。"
    if paramiko is None:
        return False, "无法执行公钥注入：缺少 paramiko 依赖。"

    b64_pub = base64.b64encode(pub_value.encode("utf-8")).decode("ascii")
    remote_cmd = (
        "mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && "
        f"LINE=$(echo '{b64_pub}' | base64 -d) && "
        "(grep -qF \"$LINE\" ~/.ssh/authorized_keys || echo \"$LINE\" >> ~/.ssh/authorized_keys) && "
        "echo PUBKEY_INJECTED"
    )
    ssh = None
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=host_value,
            username=user_value,
            port=int(port_value) if port_value.isdigit() else 22,
            password=password or None,
            key_filename=None if password else (key_value or None),
            timeout=timeout,
            allow_agent=not bool(password),
            look_for_keys=not bool(password),
        )
        _stdin, stdout, stderr = ssh.exec_command(remote_cmd, timeout=timeout)
        out = (stdout.read().decode("utf-8", errors="replace") or "").strip()
        err = (stderr.read().decode("utf-8", errors="replace") or "").strip()
        code = stdout.channel.recv_exit_status()
        if code == 0 and "PUBKEY_INJECTED" in out:
            return True, (
                f"公钥已成功注入 {user_value}@{host_value}：~/.ssh/authorized_keys "
                "（不存在时已自动追加）。现在提交任务直接使用自动生成的私钥即可，密码可留空。"
            )
        return False, f"公钥注入命令执行失败（退出码 {code}）：{err or out or '无输出'}"
    except Exception as exc:
        if _is_auth_exception(exc):
            return False, (
                f"SSH 认证失败：{user_value}@{host_value}:{port_value} 拒绝了当前凭据。"
                "请确认密码与实例 root 密码一致，或使用已获授权的私钥。"
            )
        return False, f"公钥注入失败：{exc}"
    finally:
        if ssh:
            try:
                ssh.close()
            except Exception:
                pass
