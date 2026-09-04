"""UI 主题与天气特效回归测试：小清新主题、天气粒子、装饰组件移除。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
PKG_DIR = APP_DIR / "paper_repro_app"


def test_weather_describe_mapping():
    """WMO 天气代码 → 粒子类型/中文名/emoji 映射正确。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.weather_fx import describe

    assert describe(None)["kind"] == "calm", "无天气数据必须优雅降级"
    assert describe({"code": 0, "is_day": 1})["kind"] == "clear"
    assert describe({"code": 0, "is_day": 0})["kind"] == "clear"
    assert "emoji" not in describe({"code": 0, "is_day": 0}), "不返回 emoji 字段（UI 无表情符号）"
    assert describe({"code": 61, "is_day": 1})["kind"] == "rain"
    assert describe({"code": 2, "is_day": 0})["is_day"] is False, "昼夜信息缺失"
    assert describe(None)["kind"] == "calm"
    assert describe({"code": 95, "is_day": 1})["kind"] == "storm"
    assert describe({"code": 3, "is_day": 1})["kind"] == "cloudy"
    assert describe({"code": 61, "is_day": 1})["kind"] == "rain"
    assert describe({"code": 75, "is_day": 1})["kind"] == "snow"
    assert describe({"code": 95, "is_day": 1})["kind"] == "storm"


def test_weather_particles_html_structure():
    """粒子 HTML 必须包含防重复的固定画布与请求动画帧循环。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.weather_fx import build_particles_html

    html = build_particles_html({"code": 61, "is_day": 1, "temp": 22.0, "city": "X"})
    assert "pr-weather-canvas" in html, "画布 id 缺失（防重复机制依赖它）"
    assert "requestAnimationFrame" in html, "缺少动画循环"
    assert "pointer-events:none" in html, "粒子不得拦截鼠标交互"


def test_fresh_theme_css():
    """主题 CSS 包含小清新关键样式，且不再包含赛博深色变量。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.ui_theme import APP_CSS

    # 赛博朋克主题关键标记
    assert "--cyan" in APP_CSS and "#00f0ff" in APP_CSS, "霓虹青缺失"
    assert "--magenta" in APP_CSS and "#ff2a6d" in APP_CSS, "品红缺失"
    assert "--yellow" in APP_CSS and "#ffce00" in APP_CSS, "警示黄缺失"
    assert "fresh-header" in APP_CSS, "头部样式缺失"
    assert "weather-chip" in APP_CSS, "天气胶囊样式缺失"
    assert "fx-stepper" in APP_CSS, "步进器样式缺失"
    assert "fx-carousel" in APP_CSS, "轮播样式缺失"
    assert "backdrop-filter" in APP_CSS, "毛玻璃缺失"
    # 专家组规范：轮询区零重放动画 —— 步进节点用静态光晕，不再有 infinite 动画
    assert "@keyframes nodePulse" not in APP_CSS and "@keyframes badgePulse" not in APP_CSS
    assert "animation: nodePulse" not in APP_CSS, "轮询区禁止重放动画"
    # 步进器当前节点的静态光环（Obsidian×Ember 琥珀系）
    assert "0 0 0 5px rgba(255,180,84,.12)" in APP_CSS or "rgba(255, 206, 0, 0.12), 0 0 18px" in APP_CSS, "静态光环缺失"
    assert "var(--amb-card" in APP_CSS, "氛围变量消费缺失"
    assert "z-index: 1" in APP_CSS, "内容层分离缺失"
    # 内容层在粒子之上的排版保障
    assert 'section[data-testid="stMain"]' in APP_CSS and "position: relative" in APP_CSS


def test_stepper_builder():
    """步进器：当前节点激活、已完成节点连线填充、状态元信息齐全。"""
    import re

    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.ui_theme import build_stepper_html

    html = build_stepper_html("env", status="running", progress=38, status_label="执行中")
    # 用正则精确数节点（避免 fx-stepper 外壳干扰）
    assert len(re.findall(r"class='fx-step[\s']", html)) == 10, "应渲染 10 个步骤节点（与 RemoteRunner 一致）"
    assert "fx-step done" in html and "fx-step active" in html
    assert "阶段 <b>3</b> / 10" in html, "阶段序号缺失"
    assert "38%" in html
    assert "执行中" in html
    # 第一个节点未完成时不应有 done 状态
    html0 = build_stepper_html("prepare", status="queued", progress=5, status_label="待开始")
    assert "fx-step active" in html0 and html0.count("fx-step done") == 0


def test_stepper_failed_state():
    """失败任务：步进器停在失败节点标红，不退回第一步。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.ui_theme import build_stepper_html

    html = build_stepper_html("dataset", status="failed", progress=68, status_label="失败")
    assert "fx-step error" in html, "失败节点应标红"
    # 失败前的节点保持 done
    assert html.count("fx-step done") == 5, "dataset 前 5 个步骤应已完成"
    # 无 emoji
    import re
    assert not re.search(r"[🌀-🫿]", html), "步进器不得含 emoji"


def test_carousel_builder():
    """轮播条：卡片复制两份实现无缝循环，包含防呆 hover 暂停。"""
    sys.path.insert(0, str(APP_DIR))
    from paper_repro_app.ui_theme import build_carousel_html, CAROUSEL_CARDS

    html = build_carousel_html()
    assert html.count("fx-card") == len(CAROUSEL_CARDS) * 2, "卡片应复制两份实现无缝循环"
    assert "emoji" not in html and not re.search(r"[🌀-🫿]", html), "轮播不得含 emoji"
    assert "fxScroll" in html or "fx-track" in html
    assert "hover" not in html  # 暂停逻辑在 CSS，不在这里


def test_decorative_blocks_removed_from_app():
    """纯装饰组件（无实际功能）必须已从 app.py 移除，改为轮播条承载。"""
    source = (APP_DIR / "app.py").read_text(encoding="utf-8")
    for dead_class in ("console-grid", "console-strip", "console-two-col", "visor-strip", "console-shell", "赛博配置面板", "工程化说明"):
        assert dead_class not in source, f"装饰组件未移除: {dead_class}"
    assert "build_carousel_html()" in source, "轮播条未接入"
    assert "build_stepper_html" in source, "步进器未接入"


def test_streamlit_dark_theme_config():
    """Streamlit 配置必须为赛博朋克深色主题。"""
    config = APP_DIR / ".streamlit" / "config.toml"
    assert config.exists(), ".streamlit/config.toml 缺失"
    text = config.read_text(encoding="utf-8")
    assert 'base = "dark"' in text
    assert "#00f0ff" in text
