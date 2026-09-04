from __future__ import annotations

from typing import Any, Dict, List


class ExperimentComparisonTable:
    """Convert metrics/logs into a markdown comparison table for reporting and interview use."""

    _NO_DATA_ROWS = [
        {"metric": "实验指标", "paper": "—", "repro": "未收集", "gap": "—",
         "note": "论文基准未录入（paper_claims.json）或复现未输出指标，本次未做指标对比。"},
    ]

    def build_table(self, metrics: List[Dict[str, Any]] | None = None) -> str:
        rows = metrics or self._NO_DATA_ROWS
        headers = ["指标", "论文宣称", "复现结果", "差距", "说明"]
        lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        for row in rows:
            values = [
                str(row.get("metric", "")),
                str(row.get("paper", "")),
                str(row.get("repro", "")),
                str(row.get("gap", "")),
                str(row.get("note", "")),
            ]
            lines.append("| " + " | ".join(values) + " |")
        return "\n".join(lines)


def generate_experiment_table(metrics: List[Dict[str, Any]] | None = None) -> str:
    return ExperimentComparisonTable().build_table(metrics)
