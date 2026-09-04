"""远程工作目录推导：为每个仓库生成稳定且隔离的云端目录名。

规则：
- 目录名 = 安全仓库名 + "__" + 仓库 URL 的 sha1 前 8 位
- 同名不同仓库 → 哈希不同 → 云端互不覆盖
- 同一论文/仓库 → 哈希稳定 → 重复运行时"重置复用"逻辑保持不变
"""
from __future__ import annotations

import hashlib
import re


def _safe_repo_name(raw: str) -> str:
    if raw and "/" in raw:
        repo_name = raw.split("/")[-1].replace(".git", "").strip()
    else:
        repo_name = raw or "paper-repro"

    if not repo_name or repo_name.lower() in {
        "http:",
        "https:",
        "github.com",
        "gitee.com",
        "paper-repro",
    }:
        repo_name = "paper-repro"

    # 只保留文件名安全字符，避免远程 shell 路径注入/截断
    return re.sub(r"[^A-Za-z0-9._-]+", "-", repo_name).strip("-_") or "paper-repro"


def detect_remote_workdir(repo_hint: str, user: str = "", host: str = "") -> str:
    raw = (repo_hint or "").strip().rstrip("/")
    repo_name = _safe_repo_name(raw)

    # 短哈希隔离：不同仓库即使同名也不会互相覆盖；
    # 同一论文/仓库 URL 保持同一目录，重复运行的重置复用逻辑不变。
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:8]
    dir_name = f"{repo_name}__{digest}"

    if user == "root":
        return f"/root/autodl-tmp/{dir_name}"
    elif user:
        return f"/home/{user}/{dir_name}"
    else:
        return f"/workspace/{dir_name}"
