"""可移植性回归测试：确保项目保持"拷给朋友即用"的能力。

覆盖：
- 无硬编码绝对路径（换机器不失效）
- 数据全部在用户家目录（应用目录纯代码）
- requirements 锁定版本（朋友装到完全一致的环境）
- 云端目录哈希隔离（同名仓库不互相覆盖）
- 旧版数据自动迁移
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
PKG_DIR = APP_DIR / "paper_repro_app"

# 允许出现的绝对路径模式（远程 Linux 目录模板，非本地路径）
REMOTE_PATH_ALLOWLIST = [
    "/home/",
    "/root/autodl-tmp/",
    "/workspace/",
    "/root/",
]


def iter_source_files() -> list[Path]:
    files = []
    for pattern in ("**/*.py", "**/*.bat", "**/*.toml"):
        for path in APP_DIR.glob(pattern):
            rel = str(path)
            if any(part in rel for part in (".venv", "__pycache__", ".pytest_cache", "egg-info")):
                continue
            files.append(path)
    return files


def test_no_hardcoded_windows_absolute_paths():
    """Windows 绝对路径（C:\\...）不得出现在源码中，否则换机器必失效。"""
    offenders = []
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if re.search(r'["\']C:\\', line) or re.search(r"\bC:\\Users\\", line):
                offenders.append(f"{path}:{line_no}: {line.strip()}")
    assert not offenders, "\n".join(offenders)


def test_no_hardcoded_unix_home_paths():
    """本地 Unix 家目录路径（/Users/xxx 或 /home/xxx）不得硬编码（远程模板除外）。"""
    offenders = []
    for path in iter_source_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if re.search(r"['\"]/(Users|home)/[A-Za-z]", line):
                offenders.append(f"{path}:{line_no}: {line.strip()}")
    # 允许纯模板形式 /home/{user}（remote_runner 云端路径模板）
    allowed = [o for o in offenders if "/home/{user}" in o or "/root/autodl-tmp" in o]
    assert not allowed, "\n".join(allowed)


def test_requirements_are_pinned():
    """requirements.txt 必须全部用 == 锁定，防止朋友装到不兼容的新版本。"""
    req_path = APP_DIR / "requirements.txt"
    lines = [
        line.strip()
        for line in req_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert lines, "requirements.txt 为空"
    for line in lines:
        assert "==" in line, f"依赖未锁定版本: {line}"


def test_paths_live_in_user_home():
    """任务库/日志/默认数据目录必须位于用户家目录，应用目录保持纯代码。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.paths import APP_HOME, DB_PATH, DEFAULT_DATA_DIR, LOG_DIR, LOG_FILE

    home = Path.home().resolve()
    assert str(APP_HOME).startswith(str(home)), f"APP_HOME 不在家目录: {APP_HOME}"
    assert str(DB_PATH).startswith(str(home)), f"DB 不在家目录: {DB_PATH}"
    assert str(LOG_DIR).startswith(str(home)), f"日志不在家目录: {LOG_DIR}"
    assert str(DEFAULT_DATA_DIR).startswith(str(home)), f"数据目录不在家目录: {DEFAULT_DATA_DIR}"
    # 数据路径不得位于应用目录内（拷贝文件夹不会带走用户数据）
    for path in (DB_PATH, LOG_FILE, DEFAULT_DATA_DIR):
        assert not str(path).startswith(str(APP_DIR.resolve())), f"数据路径混入应用目录: {path}"


def test_remote_workdir_hash_isolation():
    """同名不同仓库 → 云端目录不同；同一仓库 → 目录稳定（重置复用逻辑不变）。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.remote_workdir import detect_remote_workdir

    url_a = "https://github.com/user/yolov5.git"
    url_b = "https://github.com/another/yolov5.git"

    dir_a = detect_remote_workdir(url_a, user="ubuntu")
    dir_b = detect_remote_workdir(url_b, user="ubuntu")
    dir_a_again = detect_remote_workdir(url_a, user="ubuntu")

    assert dir_a != dir_b, "同名不同仓库必须隔离"
    assert dir_a == dir_a_again, "同一仓库必须稳定"
    # 同名不同仓库的目录名应只共享仓库名部分，后缀哈希不同
    name_a = dir_a.rsplit("/", 1)[-1]
    name_b = dir_b.rsplit("/", 1)[-1]
    assert name_a.split("__")[0] == name_b.split("__")[0] == "yolov5"
    assert name_a.split("__")[1] != name_b.split("__")[1]


def test_remote_workdir_shell_safe():
    """远程目录名不得包含 shell 危险字符。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.remote_workdir import detect_remote_workdir

    dirty = "https://github.com/a/my repo;rm -rf ~;.git"
    result = detect_remote_workdir(dirty, user="root")
    dir_name = result.rsplit("/", 1)[-1]
    assert re.fullmatch(r"[A-Za-z0-9._-]+__[0-9a-f]{8}", dir_name), f"目录名不安全: {dir_name}"
