"""一键打包分发：把应用文件夹清理成纯净可分发状态并压缩为 zip。

运行后会在上级目录生成：
    PaperReproRunner-<版本>.zip
    PaperReproRunner-<版本>-使用说明.txt

朋友拿到 zip 后：解压 → 双击 start_app.bat → 等待自动安装 → 浏览器自动打开。
"""
from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
APP_NAME = APP_DIR.name
OUT_DIR = APP_DIR.parent

# 打包时排除的运行残留（朋友不需要，还可能带着你的数据）
ZIP_EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "logs",
    "data",
    "assets",
}
ZIP_EXCLUDE_PATTERNS = ("*.egg-info",)

# 本地清理仅移除小型缓存（不碰 .venv/数据/日志，安全快速）
LOCAL_CLEAN_DIRS = {"__pycache__", ".pytest_cache", "*.egg-info"}

VERSION = "1.3.0"

FRIEND_GUIDE = """============================================================
  Paper Repro Runner（论文复现助手）使用说明
============================================================

【这是什么】
一个本地运行的论文复现工具：输入论文链接 → 自动找代码仓库 →
用你自己的云服务器完成环境搭建、依赖安装、模型验证。

【安装使用（一共 4 步）】
1. 解压本压缩包到任意文件夹（路径可含中文，别放系统盘需要管理员权限的目录）
2. 安装 Python 3.11+（已装过可跳过）：
   https://www.python.org/downloads/  （安装时勾选 Add python.exe to PATH）
3. 双击 start_app.bat
   首次启动会自动创建虚拟环境并安装依赖（约 1-5 分钟）：
   系统会并发测速自动选择最快可用镜像源（清华/阿里/腾讯/中科大/华为云等），
   失败自动切换下一个，之后每次启动都是秒开
   任务监控页自动每 2 秒刷新，云端进度实时滚动（无需手动刷新页面）
4. 浏览器会自动打开 http://127.0.0.1:8505 ，即可使用

【使用前需要准备】
- 一个自己的云服务器（如 AutoDL、恒源云、阿里云等），
  并拿到：IP/域名、SSH 端口、用户名、密码或私钥
- 应用内“设置”页可先“测试 SSH 连接”验证凭据

【数据保存在哪里】
- 所有任务数据、日志、产物都保存在你自己的电脑：
  C:\\Users\\<你的用户名>\\.paper_repro_app
- 应用文件夹本身是纯代码，可随时删除/替换/升级，不影响数据
- 换电脑时把 .paper_repro_app 文件夹和任务产物目录一起拷走即可迁移

【常见问题】
Q: 双击后窗口提示“未检测到 Python 环境”？
A: 安装 Python 3.11+（勾选 Add python.exe to PATH）后重试。

Q: 依赖安装失败？
A: 关闭窗口重试即可（自动切换国内镜像）；仍失败可手动执行：
   .venv\\Scripts\\python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

Q: 换一篇论文/换一个仓库会影响吗？
A: 不会。每篇论文独立目录，同名不同仓库自动哈希隔离，互不覆盖。

Q: 如何更新？
A: 删掉旧应用文件夹，解压新版，双击 start_app.bat。任务历史不受影响。
"""


def clean_tree() -> None:
    """仅清理小型缓存目录（跳过 .venv/数据，不破坏本地环境）。"""
    import os

    removed = 0
    for dirpath, dirnames, _filenames in os.walk(APP_DIR):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in {".venv", "data", "logs"} and not d.startswith(".git")
        ]
        for d in list(dirnames):
            if d in LOCAL_CLEAN_DIRS or d.endswith(".egg-info"):
                target = Path(dirpath) / d
                shutil.rmtree(target, ignore_errors=True)
                dirnames.remove(d)
                removed += 1
    if removed:
        print(f"[打包] 已清理 {removed} 个缓存目录（__pycache__ 等）")


def write_friend_guide() -> Path:
    guide = OUT_DIR / f"PaperReproRunner-{VERSION}-使用说明.txt"
    guide.write_text(FRIEND_GUIDE, encoding="utf-8")
    return guide


def make_zip() -> Path:
    import os

    zip_path = OUT_DIR / f"PaperReproRunner-{VERSION}.zip"
    files: list[tuple[str, Path]] = []
    for dirpath, dirnames, filenames in os.walk(APP_DIR):
        dirnames[:] = [
            d
            for d in dirnames
            if d not in ZIP_EXCLUDE_DIRS
            and not d.endswith(".egg-info")
            and not d.startswith(".git")
        ]
        for name in filenames:
            path = Path(dirpath) / name
            rel = path.relative_to(APP_DIR)
            if any(part.endswith(".egg-info") for part in rel.parts):
                continue
            files.append((str(rel), path))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in sorted(files):
            zf.write(path, arcname=f"{APP_NAME}/{rel}")
    return zip_path


def main() -> int:
    print("=" * 60)
    print("Paper Repro Runner 一键打包分发")
    print("=" * 60)
    clean_tree()
    zip_path = make_zip()
    guide_path = write_friend_guide()
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"[打包] 完成: {zip_path}  ({size_mb:.2f} MB)")
    print(f"[打包] 使用说明: {guide_path}")
    print("[打包] 把 zip 和说明一起发给朋友即可（或只发 zip，说明在本文档里）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
