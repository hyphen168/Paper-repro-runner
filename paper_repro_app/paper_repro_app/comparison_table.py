from __future__ import annotations

from typing import Any, Dict, List


class ExperimentComparisonTable:
    """Convert metrics/logs into a markdown comparison table for reporting and interview use."""

    def __init__(self):
        self.default_rows = [
            {"metric": "Top-1 Acc", "paper": "N/A", "repro": "N/A", "gap": "N/A", "note": "待补充"},
            {"metric": "mAP", "paper": "N/A", "repro": "N/A", "gap": "N/A", "note": "待补充"},
            {"metric": "F1", "paper": "N/A", "repro": "N/A", "gap": "N/A", "note": "待补充"},
            {"metric": "Inference speed", "paper": "N/A", "repro": "N/A", "gap": "N/A", "note": "待补充"},
        ]

    def build_table(self, metrics: List[Dict[str, Any]] | None = None) -> str:
        rows = metrics or self.default_rows
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
