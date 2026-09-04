import importlib.util
from pathlib import Path

import pandas as pd

from paper_repro_app.comparison_charts import (
    PAPER_SERIES,
    REPRO_SERIES,
    comparison_points,
    extract_number,
    long_dataframe,
    wide_dataframe,
)


def _assert_no_streamlit_import():
    """对比图数据层必须可离线导入：不依赖 streamlit。"""
    spec = importlib.util.find_spec("streamlit") is not None
    # 我们不做“streamlit 已安装才算错”的断言——仓库环境本就装有 streamlit，
    # 只校验本模块源码不含 streamlit 顶层导入。
    source = Path(__file__).resolve().parents[1] / "paper_repro_app" / "comparison_charts.py"
    text = source.read_text(encoding="utf-8")
    assert "import streamlit" not in text
    assert "components.html" not in text


# ============ extract_number ============

def test_extract_number_plain_and_percent():
    assert extract_number("92.3") == 92.3
    assert extract_number("92.3%") == 92.3
    assert extract_number("90.2%") == 90.2
    assert extract_number("0.9123") == 0.9123


def test_extract_number_plusminus_error_value():
    # ± 后误差值仅参考，主值取第一个数字
    assert extract_number("93.4±0.5") == 93.4
    assert extract_number("91.2 ± 1.8") == 91.2


def test_extract_number_scientific_and_negative():
    assert extract_number("1e-3") == 1e-3
    assert extract_number("-0.5") == -0.5
    assert extract_number("+12.25") == 12.25


def test_extract_number_unparseable_inputs():
    assert extract_number("—") is None
    assert extract_number("未发现") is None
    assert extract_number("—") is None
    assert extract_number(None) is None
    assert extract_number("") is None
    assert extract_number("   ") is None
    assert extract_number("no metrics") is None


# ============ comparison_points ============

def test_comparison_points_filters_non_numeric_rows():
    rows = [
        {"metric": "mAP@.5", "paper": "92.3%", "repro": "90.1%", "gap": "-2.2 pp", "note": ""},
        {"metric": "Loss", "paper": "—", "repro": "0.35", "gap": "—", "note": "自动收集"},
        {"metric": "F1", "paper": "—", "repro": "未发现", "gap": "—", "note": "无"},
        {"metric": "", "paper": "90", "repro": "88", "gap": "", "note": ""},
        {"metric": "Recall", "paper": "0.87", "repro": None, "gap": "", "note": ""},
    ]
    points = comparison_points(rows)
    metrics = [p["metric"] for p in points]
    assert metrics == ["mAP@.5", "Loss", "Recall"]
    assert points[0] == {"metric": "mAP@.5", "paper": 92.3, "repro": 90.1}
    # 只有论文值，复现为 None
    assert points[1] == {"metric": "Loss", "paper": None, "repro": 0.35}
    # 只有复现为 None → 过滤（F1）；metric 空行丢弃
    assert points[2] == {"metric": "Recall", "paper": 0.87, "repro": None}


def test_comparison_points_handles_none_and_garbage_rows():
    assert comparison_points(None) == []
    assert comparison_points([]) == []
    assert comparison_points([None, "junk", 42]) == []


# ============ wide_dataframe ============

def test_wide_dataframe_shape_and_gap():
    points = [
        {"metric": "Accuracy", "paper": 92.3, "repro": 90.1},
        {"metric": "F1", "paper": 0.87, "repro": None},
    ]
    df = wide_dataframe(points)
    assert list(df.columns) == ["metric", PAPER_SERIES, REPRO_SERIES, "差距"]
    assert len(df) == 2
    row0 = df.iloc[0]
    assert row0["metric"] == "Accuracy"
    assert row0[PAPER_SERIES] == 92.3
    assert row0[REPRO_SERIES] == 90.1
    assert abs(row0["差距"] - 2.2) < 1e-9
    row1 = df.iloc[1]
    assert row1["metric"] == "F1"
    assert pd.isna(row1[REPRO_SERIES])
    assert pd.isna(row1["差距"])


def test_wide_dataframe_keeps_order_and_dedupes():
    points = [
        {"metric": "mAP", "paper": 80.0, "repro": 78.0},
        {"metric": "mAP", "paper": 81.0, "repro": None},  # paper 缺位补全?否——已有值优先，仅补 None 侧
        {"metric": "Precision", "paper": None, "repro": 0.91},
        {"metric": "Precision", "paper": 0.90, "repro": None},  # 补全 paper 缺位
    ]
    df = wide_dataframe(points)
    assert list(df["metric"]) == ["mAP", "Precision"]
    mrow = df[df["metric"] == "mAP"].iloc[0]
    assert mrow[PAPER_SERIES] == 80.0
    assert mrow[REPRO_SERIES] == 78.0
    prow = df[df["metric"] == "Precision"].iloc[0]
    assert prow[PAPER_SERIES] == 0.90
    assert prow[REPRO_SERIES] == 0.91


def test_wide_dataframe_empty_input():
    df = wide_dataframe([])
    assert df.empty
    assert list(df.columns) == ["metric", PAPER_SERIES, REPRO_SERIES, "差距"]
    assert wide_dataframe(None).empty


# ============ long_dataframe ============

def test_long_dataframe_shape_and_values():
    points = [
        {"metric": "Accuracy", "paper": 92.3, "repro": 90.1},
        {"metric": "F1", "paper": None, "repro": 0.87},
        {"metric": "Recall", "paper": 0.9, "repro": None},
    ]
    df = long_dataframe(points)
    assert list(df.columns) == ["metric", "series", "value"]
    assert len(df) == 4  # Accuracy×2 + F1×1 + Recall×1（None 丢弃）
    acc = df[df["metric"] == "Accuracy"]
    assert set(acc["series"]) == {PAPER_SERIES, REPRO_SERIES}
    f1 = df[df["metric"] == "F1"]
    assert list(f1["series"]) == [REPRO_SERIES]
    rec = df[df["metric"] == "Recall"]
    assert list(rec["series"]) == [PAPER_SERIES]


def test_long_dataframe_empty_input():
    assert long_dataframe([]).empty
    assert long_dataframe(None).empty
