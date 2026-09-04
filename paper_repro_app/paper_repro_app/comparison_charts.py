"""结果对比图数据层（纯逻辑，零 streamlit/网络依赖）。

把「论文宣称 vs 复现结果」的对比行转成可绘图的数值点与 DataFrame，
供 app.py 用 altair/原生图表渲染分组柱状图等可视化；本模块不 import
streamlit，便于离线单测与复用。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

# 论文/复现两列的展示名（供 long_dataframe 的 series 列取值）
PAPER_SERIES = "论文宣称"
REPRO_SERIES = "复现结果"

# 行内字段名（与 comparison_table / storage_utils 生成的对比行一致）
_METRIC_KEY = "metric"
_PAPER_KEY = "paper"
_REPRO_KEY = "repro"

# 数字提取：支持 "92.3" "92.3%" "93.4±0.5" "0.9123" "1e-3" "-0.5" 等
_NUM_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def extract_number(text: Any) -> Optional[float]:
    """从文本中稳健提取首个可转 float 的数；无法解析返回 None。

    覆盖形态：
    - "92.3" / "92.3%" / "90.2%" → 92.3
    - "93.4±0.5" → 93.4（± 后的误差值仅参考，主值取第一个数字）
    - "0.9123" / "1e-3" / "-0.5" → 对应数值
    - "—" / "未发现" / None / "" → None
    """
    if text is None:
        return None
    match = _NUM_RE.search(str(text).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def comparison_points(rows: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    """把指标对比行过滤为可数值化的绘图点。

    输入行字典字段：metric/paper/repro/gap/note（与 comparison_table 对齐）。
    输出点：{"metric": str, "paper": float|None, "repro": float|None}；
    paper 与 repro 至少一方可解析才保留该行，metric 缺失或空白行丢弃。
    """
    points: List[Dict[str, Any]] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        metric = str(row.get(_METRIC_KEY) or "").strip()
        if not metric:
            continue
        paper = extract_number(row.get(_PAPER_KEY))
        repro = extract_number(row.get(_REPRO_KEY))
        if paper is None and repro is None:
            continue
        points.append({"metric": metric, "paper": paper, "repro": repro})
    return points


def _dedupe_keep_order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """按 metric 保序去重（同指标保留第一个点的论文值，repro 缺失时用后行补位）。"""
    seen: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for item in items:
        metric = str(item.get(_METRIC_KEY) or "")
        if metric not in seen:
            seen[metric] = dict(item)
            order.append(metric)
            continue
        existing = seen[metric]
        if existing.get("paper") is None and item.get("paper") is not None:
            existing["paper"] = item["paper"]
        if existing.get("repro") is None and item.get("repro") is not None:
            existing["repro"] = item["repro"]
    return [seen[key] for key in order]


def wide_dataframe(points: List[Dict[str, Any]] | None) -> pd.DataFrame:
    """宽表 DataFrame：列 metric/论文宣称/复现结果/差距。

    - 按 metric 保序去重；
    - 差距 = paper - repro（数值缺失 → NaN）。
    """
    cleaned = _dedupe_keep_order(comparison_points(points) if points is not None else [])
    rows = []
    for point in cleaned:
        paper = point.get("paper")
        repro = point.get("repro")
        gap = None
        if paper is not None and repro is not None:
            gap = paper - repro
        rows.append({
            _METRIC_KEY: point[_METRIC_KEY],
            PAPER_SERIES: paper,
            REPRO_SERIES: repro,
            "差距": gap,
        })
    return pd.DataFrame(rows, columns=[_METRIC_KEY, PAPER_SERIES, REPRO_SERIES, "差距"])


def long_dataframe(points: List[Dict[str, Any]] | None) -> pd.DataFrame:
    """长表 DataFrame：列 metric/series/value（供 altair/分组柱状图）。

    数值为 None 的行直接丢弃；series 仅取 {"论文宣称","复现结果"} 两档。
    """
    cleaned = _dedupe_keep_order(comparison_points(points) if points is not None else [])
    rows = []
    for point in cleaned:
        metric = point[_METRIC_KEY]
        paper = point.get("paper")
        repro = point.get("repro")
        if paper is not None:
            rows.append({"metric": metric, "series": PAPER_SERIES, "value": paper})
        if repro is not None:
            rows.append({"metric": metric, "series": REPRO_SERIES, "value": repro})
    return pd.DataFrame(rows, columns=["metric", "series", "value"])
