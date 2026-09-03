from __future__ import annotations

import re
from typing import Any, Dict, List


class LogAnalyzer:
    """Automated error detection and diagnosis engine for paper reproduction tasks."""

    ERROR_PATTERNS = [
        {
            "category": "SSH认证与连接",
            "regex": r"(WinError 10054|Permission denied|no such identity|banner_timeout|auth_timeout|Error reading SSH protocol banner)",
            "cause": "与云服务器建立 SSH 连接失败或连接断开。可能原因是主机地址端口错填、公钥未放入 /root/.ssh/authorized_keys，或网络代理频次超限被云端阻断。",
            "suggestion": "1. 检查 SSH 主机与端口是否正确；2. 确认已将本地公钥追加到云端的 ~/.ssh/authorized_keys；3. 若使用 AutoDL，请测试使用密码方式连接或减少频繁试错重试。",
        },
        {
            "category": "Conda/Python环境缺失",
            "regex": r"(conda: command not found|python3: command not found|No module named venv)",
            "cause": "云端系统的 Conda 或 Python3 可执行文件未加入系统的环境变量 PATH 中。",
            "suggestion": "系统已开启自动 Conda 路径补全（export PATH）。请确保远程主机安装了 Miniconda/Anaconda 并位于默认路径（/root/miniconda3/bin）。",
        },
        {
            "category": "PyPI依赖安装超时或失败",
            "regex": r"(pip_install_with_fallback|Could not find a version that satisfies the requirement|DistributionNotFound|HTTPError 404|read timeout)",
            "cause": "网络原因导致 PyPI 镜像下载失败或特定版本的 pip 依赖包在指定源不存在。",
            "suggestion": "1. 检查 requirements.txt 中是否包含无法在 Linux 安装的 Windows 专有包；2. 系统会自动尝试清华、阿里云源切换，亦可在前端配置指定的加速镜像源。",
        },
        {
            "category": "Git 仓库拉取鉴权/不存在",
            "regex": r"(could not read Username|No such device or address|Authentication failed|Repository not found)",
            "cause": "输入的 Git 仓库（如 Gitee / GitHub）需要用户登录认证（私有仓库），或者仓库地址拼写有误（如使用了示例占位符 your-username）。",
            "suggestion": "1. 确认填写的 Git 地址拼写正确；2. 若使用 Gitee，请登录 Gitee 并在“仓库管理”中将仓库属性设置为“公开 (Public)”；3. 也可以直接使用 GHProxy 等公共加速节点。",
        },
        {
            "category": "Git 仓库拉取超时",
            "regex": r"(git clone|git ls-remote|fatal: unable to access|RPC failed|HTTP 504|Connection refused)",
            "cause": "远程 Git 仓库网络连接超时或地址不可达（例如 GitHub 访问受限）。",
            "suggestion": "1. 检查仓库 URL 是否正确；2. 在“加速仓库地址”中填入 Gitee/GitCode 镜像；3. 系统设置了 13 秒探测与 10 分钟平滑重试。",
        },
        {
            "category": "缺失 Python 模块 (ImportError)",
            "regex": r"(ModuleNotFoundError: No module named ['\"]([^'\"]+)['\"]|ImportError: cannot import name)",
            "cause": "项目代码中使用了未在 requirements.txt 中声明的第三方 Python 库。",
            "suggestion": "系统具备 AST 智能扫描补齐功能，会自动补装缺少 import 的第三方库。若仍缺失，请在 requirements.txt 中手动补充该包名。",
        },
        {
            "category": "CUDA / GPU 显存异常",
            "regex": r"(CUDA out of memory|nvcc: command not found|Torch not compiled with CUDA enabled)",
            "cause": "云端算力节点显存不足，或 PyTorch 未正确安装 CUDA 驱动版本。",
            "suggestion": "1. 在代码或命令中调小 batch_size；2. 检查云端 GPU 驱动与 torch.cuda.is_available() 状态；3. 清理无用进程以释放显存。",
        },
        {
            "category": "SQLite 结构/列缺失错误",
            "regex": r"(no such column:|OperationalError: no such table)",
            "cause": "本地数据库 Schema 版本不一致，尝试查询不存在的表列。",
            "suggestion": "系统内置 SQLiteOpenHelper 已支持自动 onUpgrade 平滑迁移。程序启动时会自动添加缺失列。",
        },
    ]

    def analyze_log(self, raw_log: str | None) -> Dict[str, Any]:
        if not raw_log:
            return {
                "has_error": False,
                "summary": "日志为空，尚未记录执行信息。",
                "failed_step": "未知",
                "error_category": "无",
                "error_snippet": "",
                "cause": "",
                "suggestion": "等待任务提交并产生日志。",
            }

        text = str(raw_log)

        # Locate failed step header
        failed_step = "未知"
        step_match = re.findall(r"--- (.*?) ---", text)
        if step_match:
            failed_step = step_match[-1]

        # Find error lines
        lines = text.splitlines()
        error_lines: List[str] = []
        for idx, line in enumerate(lines):
            line_lower = line.lower()
            if any(k in line_lower for k in ["error", "failed", "exception", "traceback", "fatal", "command not found", "winerror"]):
                # Grab surrounding lines context
                start = max(0, idx - 2)
                end = min(len(lines), idx + 4)
                snippet = "\n".join(lines[start:end])
                error_lines.append(snippet)

        error_snippet = "\n---\n".join(error_lines[:3]) if error_lines else (lines[-10:] if len(lines) > 10 else text)

        # Match error patterns
        matched_category = "未归类错误"
        matched_cause = "任务在中途执行异常中断，详细报错可查看上方日志片段。"
        matched_suggestion = "根据提示的命令行输出检查对应配置文件、网路连接或依赖清单。"

        for pattern in self.ERROR_PATTERNS:
            if re.search(pattern["regex"], text, re.IGNORECASE):
                matched_category = pattern["category"]
                matched_cause = pattern["cause"]
                matched_suggestion = pattern["suggestion"]
                break

        has_error = bool(error_lines or "failed" in text.lower() or "error" in text.lower())

        return {
            "has_error": has_error,
            "failed_step": failed_step,
            "error_category": matched_category,
            "error_snippet": error_snippet,
            "cause": matched_cause,
            "suggestion": matched_suggestion,
        }
