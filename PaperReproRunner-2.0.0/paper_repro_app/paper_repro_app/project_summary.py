from __future__ import annotations

from typing import Any, Dict


class ProjectSummaryGenerator:
    """Create a GitHub-ready summary page combining task information, architecture, innovation, and report links."""

    def build_summary(self, task: Dict[str, Any], analysis: Dict[str, Any] | None = None, report_path: str | None = None) -> str:
        analysis = analysis or {}
        summary = (
            "# 论文复现项目总结\n\n"
            "## 项目定位\n"
            "本项目旨在构建一个轻量化、可落地的论文复现助手，核心思路是：本地控制 + 云端执行 + 本地数据保留。用户在本地填写论文链接，\n"
            "系统会尝试定位代码仓库，并通过用户自有云服务器完成依赖安装、代码拉取和复现验证。\n\n"
            "## 核心架构\n"
            "- 本地应用：Streamlit + SQLite + 配置管理\n"
            "- 云端执行：SSH + Python 环境适配\n"
            "- 数据保留：本地任务日志、产物和报告\n"
            "- 智能分析：论文内容、仓库说明与复现日志的联合分析\n\n"
            "## 任务信息\n"
            f"- 任务 ID：{task.get('id', 'unknown')}\n"
            f"- 论文链接：{task.get('paper_url', 'unknown')}\n"
            f"- 仓库链接：{task.get('repo_url', 'unknown')}\n"
            f"- 运行环境：{task.get('environment_mode', 'conda')}\n"
            f"- 当前状态：{task.get('status', 'unknown')}\n\n"
            "## 智能分析结论\n"
            f"{analysis.get('summary', '本次分析暂未产出详细结论。')}\n\n"
            "## 可能的创新点\n"
        )

        for idx, item in enumerate(analysis.get("possible_innovations") or ["未发现明确创新点信号。"], start=1):
            summary += f"{idx}. {item}\n"

        summary += "\n## 主要风险\n"
        for idx, item in enumerate(analysis.get("risks") or ["未发现明显风险项。"], start=1):
            summary += f"{idx}. {item}\n"

        summary += "\n## 实验结论\n"
        summary += "综合论文内容、仓库实现方式和复现日志，本项目能够在工程上支持论文代码复现流程，并将复现过程沉淀为报告和任务记录，适合用于研究项目展示、GitHub 展示和面试说明。\n"
        if report_path:
            summary += f"\n## 报告链接\n- {report_path}\n"
        return summary


def generate_project_summary(task: Dict[str, Any], analysis: Dict[str, Any] | None = None, report_path: str | None = None) -> str:
    return ProjectSummaryGenerator().build_summary(task, analysis, report_path)
