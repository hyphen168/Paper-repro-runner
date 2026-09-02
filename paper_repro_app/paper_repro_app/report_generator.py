from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


class ReproReportGenerator:
    """Generate a human-readable Chinese report from task metadata and analysis."""

    def __init__(self, output_dir: str | Path | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path.home() / "paper_repro_reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_report(self, task: Dict[str, Any], analysis: Dict[str, Any] | None = None) -> Dict[str, Any]:
        task_id = task.get("id") or "unknown-task"
        paper_url = task.get("paper_url") or "未知"
        repo_url = task.get("repo_url") or "未知"
        status = task.get("status") or "unknown"
        current_step = task.get("current_step") or "unknown"
        env_mode = task.get("environment_mode") or "conda"

        analysis = analysis or {}
        summary = analysis.get("summary", "本次复现中未生成详细分析内容。")
        innovations = analysis.get("possible_innovations") or ["未发现明确创新点信号。"]
        risks = analysis.get("risks") or ["未发现明显风险项。"]
        confidence = analysis.get("confidence", 0.5)

        report_lines: List[str] = []
        report_lines.append(f"# 论文复现评估报告（任务：{task_id}）")
        report_lines.append("")
        report_lines.append("## 1. 基本信息")
        report_lines.append(f"- 任务 ID：{task_id}")
        report_lines.append(f"- 论文链接：{paper_url}")
        report_lines.append(f"- 代码仓库：{repo_url}")
        report_lines.append(f"- 当前状态：{status}")
        report_lines.append(f"- 当前步骤：{current_step}")
        report_lines.append(f"- 运行环境：{env_mode}")
        report_lines.append("")
        report_lines.append("## 2. 复现执行总结")
        report_lines.append(summary)
        report_lines.append("")
        report_lines.append(f"- 分析置信度：{confidence:.2f}")
        report_lines.append("")
        report_lines.append("## 3. 可能的创新点")
        for idx, item in enumerate(innovations, start=1):
            report_lines.append(f"{idx}. {item}")
        report_lines.append("")
        report_lines.append("## 4. 主要风险")
        for idx, item in enumerate(risks, start=1):
            report_lines.append(f"{idx}. {item}")
        report_lines.append("")
        report_lines.append("## 5. 结论")
        report_lines.append(
            "综合论文信息、仓库描述以及复现日志，当前方法的价值通常体现在模型结构设计、特征表达能力、泛化能力和工程落地性方面。 "
            "如果复现结果稳定且指标达到论文宣称范围，则该方法具备较高研究和工程价值。"
        )
        report_lines.append("")
        report_lines.append("## 6. 建议")
        report_lines.append("- 进一步确认数据集版本和预处理脚本是否一致。")
        report_lines.append("- 检查是否存在 CUDA、Python 版本和依赖冲突。")
        report_lines.append("- 对关键实验指标进行表格化对比，便于后续汇报。")
        report_lines.append("- 将复现过程与结果整理成 GitHub 说明文档，方便项目展示和面试表达。")

        report_text = "\n".join(report_lines)
        file_path = self.output_dir / f"{task_id}_report.md"
        file_path.write_text(report_text, encoding="utf-8")

        payload = {
            "task_id": task_id,
            "report_path": str(file_path),
            "report_md": report_text,
            "summary": summary,
            "innovation_count": len(innovations),
            "risk_count": len(risks),
            "confidence": confidence,
        }
        (self.output_dir / f"{task_id}_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return payload


def generate_repro_report(task: Dict[str, Any], analysis: Dict[str, Any] | None = None, output_dir: str | Path | None = None) -> Dict[str, Any]:
    return ReproReportGenerator(output_dir).build_report(task, analysis)
