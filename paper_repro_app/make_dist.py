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
    ".ruff_cache",
    ".git",
    "logs",
    "data",
    "assets",
    "scripts",
    "tests",
    "docs",
}
ZIP_EXCLUDE_PATTERNS = ("*.egg-info",)
# 额外剔除：根级临时脚本与桌面快捷方式脚本（纯开发/个人工具）
ZIP_EXCLUDE_FILES = {
    "create_desktop_shortcut.py",
    "requirements-dev.txt",
}
_DOCS_KEEP = {"docs", "troubleshoot", "GUIDE.md"}  # 仅保留排障手册

# 本地清理仅移除小型缓存（不碰 .venv/数据/日志，安全快速）
LOCAL_CLEAN_DIRS = {"__pycache__", ".pytest_cache", "*.egg-info"}

VERSION = "2.0.0"

FRIEND_GUIDE = """============================================================
  Paper Repro Runner（论文复现助手）使用说明（v2.0.0）
============================================================

【本版新增 v2.0.0】
- 实时天气与昼夜明暗主题（本地真实天气驱动整体界面氛围）
- SSH 自动连接：多台候选自动选用可达者；粘贴整行 ssh 登录指令/别名/私钥均可自动识别
- 换论文自适应：粘贴新论文链接即可跑；同一仓库第二次提交自动预填上次成功配置
- 复现结果与论文对比可见：训练指标卡、复现 vs 论文对比表（带口径级别）、结果说明与证据日志
- 自助排障：失败诊断卡（错误码+建议动作+可复制诊断摘要）、侧栏速查、完整排障手册（解压目录 docs/troubleshoot/GUIDE.md）
- 云端健壮性：CUDA torch 自动重装、依赖多源与预算、数据集 URL 直链自动解压与配置生成

【网络与隐私】
本工具为本地单机应用，无账号、无遥测、无后台回传。运行时请求以下第三方服务完成定位与加速：
ip-api.com（公网 IP 换粗粒度城市定位）、Open-Meteo（天气与地理编码）、GitHub/Gitee/arXiv（论文仓库检索）、
清华/阿里等 pip 镜像（测速择优）、download.pytorch.org（CUDA PyTorch）、ghfast.top（GitHub 加速）——
云端下载均在您自己的云服务器上发起。凭据安全：云服务器密码只保存在本机进程内存（重启即失效），
不落盘、不进日志、不入安装包；粘贴私钥保存在本机 ~/.ssh/ 目录。日志输出已脱敏。
提醒：数据集直链若携带签名 token 会随下载日志明文显示，请使用短期签名链接。
许可：本工具 MIT 协议；依赖库均宽松许可（paramiko 为 LGPL-2.1，经 pip 安装使用）；
天气数据与昼夜算法来自 Open-Meteo 与 NOAA 公开模型；公开数据集请核对各自原始许可。
仅供研究与学习用途；复现指标与论文数值对比口径见任务报告级别注记。

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
- AutoDL 用户三步：控制台复制「SSH 登录指令」整行粘贴到服务器地址框
  （形如 ssh -p 38662 root@connect.xxx.seetacloud.com，整行即可自动解析）
  → 粘贴实例密码或点「注入公钥」 → 点「测试 SSH 连接」变绿再提交
  换实例/换机器：只需更新这一行地址（支持一次填多台，自动选用可达者）

【换新论文 / 换仓库怎么跑】
1. 「提交任务」页粘贴新论文链接（arXiv 等）或直接填代码仓库地址
2. 系统自动完成：找仓库（多加速源）→ 建环境 → 装依赖 → 准备数据 → 识别训练入口 → 训练
3. 识别入口不确定时会列出候选命令让你点选确认，不会让你看技术报错
4. 同一仓库第二次跑：自动预填上次成功配置，秒级提交
5. 跑完在「任务监控 / 历史记录」看：训练指标 + 论文 vs 复现对比表 + 复现报告

【遇到问题速查】
- 连不上：实例开机了吗？地址是最新控制台整行登录指令吗？（G-2）
- 认证失败：密码核对 / 点「注入公钥到服务器」（G-2）
- 报 CUDA / CPU torch 错误：重新执行任务即可自动重装 CUDA 版（G-3.3）
- 报缺少包 ModuleNotFoundError：重新执行任务（G-3.4）
- 没训练/没指标：任务详情写明原因，一般是没填数据集——高级选项填数据直链（G-5.1）
- 识别不到入口：选「实际运行」粘贴仓库 README 训练命令（G-4.2）
- 失败卡片有「复制诊断摘要」，可贴给朋友或 AI 助手
- 完整手册：解压目录内 docs/troubleshoot/GUIDE.md（应用侧栏也有「遇到问题？先看这里」）

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
            parts = rel.parts
            if any(part.endswith(".egg-info") for part in parts):
                continue
            # 剔除根级临时/个人脚本
            if len(parts) == 1 and (name.startswith("_") or name in ZIP_EXCLUDE_FILES):
                continue
            # docs 只保留 docs/troubleshoot/GUIDE.md
            if parts and parts[0] == "docs":
                if parts != ("docs", "troubleshoot", "GUIDE.md"):
                    continue
            files.append((str(rel), path))

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, path in sorted(files):
            zf.write(path, arcname=f"{APP_NAME}/{rel}")
        # 使用说明入包顶层（P0-3：只发 zip 也不丢引导）
        guide = write_friend_guide()
        zf.write(guide, arcname=f"{APP_NAME}/{guide.name}")
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
