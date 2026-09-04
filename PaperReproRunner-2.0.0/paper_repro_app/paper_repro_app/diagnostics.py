from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Any, Dict, List


class EnvironmentDiagnostics:
    """Analyze local and remote execution environment requirements before reproduction starts."""

    def __init__(self, repo_dir: str | Path | None = None):
        self.repo_dir = Path(repo_dir) if repo_dir else None

    def detect_python_version(self) -> Dict[str, Any]:
        version = platform.python_version()
        major, minor, patch = version.split(".")
        return {
            "python_version": version,
            "major": int(major),
            "minor": int(minor),
            "patch": int(patch),
            "recommended": "3.10+",
        }

    def inspect_repo_files(self) -> Dict[str, Any]:
        if not self.repo_dir or not self.repo_dir.exists():
            return {"exists": False, "files": [], "notes": ["仓库目录不存在，无法进行环境诊断。"]}

        files = [str(p.name) for p in self.repo_dir.iterdir()]
        result = {"exists": True, "files": files}
        notes: List[str] = []

        if (self.repo_dir / "requirements.txt").exists():
            notes.append("检测到 requirements.txt，优先使用 pip 安装。")
        if (self.repo_dir / "environment.yml").exists():
            notes.append("检测到 environment.yml，建议优先使用 conda。")
        if (self.repo_dir / "setup.py").exists() or (self.repo_dir / "pyproject.toml").exists():
            notes.append("检测到项目安装配置，适合执行 pip install -e .。")
        if (self.repo_dir / ".git").exists():
            notes.append("Git 仓库已存在，可进一步执行 git pull / git checkout。")

        result["notes"] = notes
        return result

    def infer_runtime_profile(self, repo_dir: str | Path | None = None) -> Dict[str, Any]:
        target = Path(repo_dir) if repo_dir else self.repo_dir
        if not target or not target.exists():
            return {"mode": "unknown", "confidence": 0.0, "notes": ["无法定位仓库目录。"]}

        files = [p.name for p in target.iterdir()]
        if "environment.yml" in files:
            return {"mode": "conda", "confidence": 0.95, "notes": ["仓库声明了 conda 环境。"]}
        if "requirements.txt" in files:
            return {"mode": "venv", "confidence": 0.8, "notes": ["仓库使用 requirements.txt 进行依赖导出。"]}
        if "Dockerfile" in files or "docker-compose.yml" in files:
            return {"mode": "docker", "confidence": 0.9, "notes": ["仓库提供 Docker 运行方案。"]}
        return {"mode": "venv", "confidence": 0.5, "notes": ["无法明确识别环境类型，默认使用 venv。"]}

    def detect_cuda_requirement(self, repo_dir: str | Path | None = None) -> Dict[str, Any]:
        target = Path(repo_dir) if repo_dir else self.repo_dir
        if not target or not target.exists():
            return {"cuda_required": False, "evidence": [], "notes": ["无法检测 CUDA。"]}

        evidence: List[str] = []
        for pattern in ["requirements.txt", "environment.yml", "Dockerfile", "setup.py", "pyproject.toml"]:
            file_path = target / pattern
            if file_path.exists():
                try:
                    text = file_path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if re.search(r"cuda|torch==|torch>=|pytorch|cudatoolkit|gpu", text, re.IGNORECASE):
                    evidence.append(pattern)

        cuda_required = bool(evidence)
        return {
            "cuda_required": cuda_required,
            "evidence": evidence,
            "notes": ["项目中存在 GPU 相关依赖声明。" if cuda_required else "未发现明显的 CUDA 依赖声明。"],
        }

    def diagnose(self, repo_dir: str | Path | None = None) -> Dict[str, Any]:
        target = Path(repo_dir) if repo_dir else self.repo_dir
        python_info = self.detect_python_version()
        repo_info = self.inspect_repo_files() if target else {"exists": False, "files": [], "notes": ["未提供仓库路径。"]}
        profile = self.infer_runtime_profile(target)
        cuda_info = self.detect_cuda_requirement(target)

        diagnosis = {
            "python": python_info,
            "repo": repo_info,
            "profile": profile,
            "cuda": cuda_info,
        }
        diagnosis["recommendation"] = self._build_recommendation(diagnosis)
        return diagnosis

    def _build_recommendation(self, diagnosis: Dict[str, Any]) -> str:
        python_major = diagnosis["python"]["major"]
        profile_mode = diagnosis["profile"]["mode"]
        cuda_required = diagnosis["cuda"]["cuda_required"]

        if python_major < 3:
            return "请升级 Python 至 3.10 或更高版本。"
        if profile_mode == "conda":
            return "优先使用 conda 环境，并在云端执行 conda env update -f environment.yml。"
        if profile_mode == "docker":
            return "建议优先使用 Docker 容器，并对 GPU 相关依赖进行镜像适配。"
        if cuda_required:
            return "检测到 GPU 依赖，建议使用 conda 或 Docker，并确认云端具备 CUDA 运行环境。"
        return "当前仓库更适合使用 venv + requirements.txt 方式进行安装，并保留重试与日志收集。"

    def export_json(self, repo_dir: str | Path | None = None) -> str:
        return json.dumps(self.diagnose(repo_dir), ensure_ascii=False, indent=2)
