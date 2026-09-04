"""圆润玻璃赛博 UI 主题 —— 依据 docs/glassmorphism_jelly_research.md 落地。

融合哲学：玻璃为体（大圆角+半透明+毛玻璃）、霓虹为骨（1px 发光描边）、弹性为息
（hover spring 上浮、按压回弹、果冻 pop 供首帧类）；锐利 accent 保留 ≤3 处。
防 2s 刷新闪烁：动画只挂 hover/active/首帧类；轮询区无重放动画。
"""
from __future__ import annotations

from typing import List, Tuple

APP_CSS = """
<style>
:root {
    /* 背景 */
    /* 描边（α 随氛围注入 --amb-line） */
    --stroke-dim: rgba(148, 163, 214, calc(var(--amb-line, 0.09) * 1.5));
    --stroke: rgba(255, 255, 255, var(--amb-line, 0.09));
    /* 霓虹 */
    --cyan: #00f0ff;
    --magenta: #ff2a6d;
    --yellow: #ffce00;
    --amber: #ffce00;
    --green: #00ffa3;
    --red: #ff2b4a;
    /* 文本（双锚：--txt-2/--txt-3 由注入按明暗切换，默认=深宵锚） */
    --text-strong: #eaf6ff;
    --text-primary: #c9d8ee;
    --text-secondary: var(--txt-2, #8fa3c7);
    --text-muted: var(--txt-3, #5c6f96);
    --muted: #5c6f96;
    /* 圆角阶梯（圆润玻璃赛博） */
    --radius-btn: 10px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-full: 999px;
    /* 毛玻璃 */
    --glass-blur-md: blur(18px) saturate(150%) brightness(1.05);
    --glass-blur-weak: blur(10px) saturate(140%) brightness(1.03);
    /* 弹性缓动（spring 仅按压/终态；hover 一律 ease） */
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
    --ease-spring-soft: cubic-bezier(0.22, 1.2, 0.36, 1);
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --dur-1: 0.15s;
    --dur-2: 0.22s;
    /* 阴影 */
    --shadow-glass-sm: 0 1px 2px rgba(0, 0, 0, 0.25), 0 4px 14px rgba(0, 0, 0, 0.2);
    --shadow-glass-md: 0 2px 8px rgba(0, 0, 0, 0.24), 0 14px 34px rgba(0, 0, 0, 0.34);
    /* 氛围注入面（专家组规范 v1.0：60s 注入覆写；以下为深宵兜底默认） */
    --bg-color: #0A1120;
    --amb-card: 0.50;
    --amb-line: 0.09;
    --amb-hi: 0.045;
    --amb-glow: 1.0;
    --amb-acc: #00f0ff;
    --amb-mag: #ff2a6d;
    --txt-2: #8fa3c7;
    --txt-3: #5c6f96;
    --scan-a: 0.011;
    --acc-dyn: var(--amb-acc);
    --glow-cyan-sm: 0 0 calc(12px * var(--amb-glow)) rgba(0, 240, 255, calc(0.22 * var(--amb-glow)));
    /* 字体 */
    --font-display: "Bahnschrift", "Rajdhani", "Segoe UI", "Microsoft YaHei", sans-serif;
    --font-body: "Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
    --font-mono: "Cascadia Mono", "Consolas", "Courier New", ui-monospace, monospace;
}
section[data-testid="stMain"] { font-size: 15px; line-height: 1.7; }

html, body { height: 100%; }
body {
    background-color: var(--bg-color);
    background-image:
        radial-gradient(1200px 700px at 10% -8%, rgba(0, 240, 255, 0.11), transparent 60%),
        radial-gradient(1000px 620px at 90% 4%, rgba(255, 42, 109, 0.09), transparent 58%),
        radial-gradient(900px 700px at 55% 112%, rgba(255, 206, 0, 0.05), transparent 60%),
        radial-gradient(1000px 600px at 8% 108%, rgba(122, 47, 247, 0.09), transparent 62%),
        linear-gradient(180deg, color-mix(in srgb, var(--bg-color) 82%, #223250) 0%, transparent 46%);
    background-attachment: fixed;
    color: var(--text-primary);
    font-family: var(--font-body);
    letter-spacing: 0.012em;
    line-height: 1.6;
}
/* 微网格（静态） */
body::before {
    content: "";
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background-image:
        linear-gradient(rgba(0, 240, 255, 0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 240, 255, 0.015) 1px, transparent 1px);
    background-size: 56px 56px;
    background-position: 0 0, 0 0;
}
body::after {
    content: "";
    position: fixed; inset: 0; z-index: 1; pointer-events: none;
    background: repeating-linear-gradient(0deg, rgba(255, 255, 255, var(--scan-a, 0.011)) 0 1px, transparent 1px 3px);
    opacity: 1;
}
.stApp { background: transparent; color: var(--text-primary); }
.stApp > div, .stSidebar > div { background: transparent; }
section[data-testid="stMain"] { position: relative; z-index: 2; }
section[data-testid="stSidebar"] { position: relative; z-index: 2; }

/* 侧边栏：玻璃面 */
.stSidebar > div {
    background: linear-gradient(180deg, rgba(9, 13, 26, calc(var(--amb-card, 0.5) + 0.15)), rgba(8, 11, 22, calc(var(--amb-card, 0.5) + 0.25)));
    border-right: 1px solid rgba(255, 255, 255, calc(var(--amb-line, 0.09) * 0.9));
    -webkit-backdrop-filter: var(--glass-blur-md);
    backdrop-filter: var(--glass-blur-md);
}
.stSidebar p, .stSidebar span { color: var(--text-secondary); }

/* 文本层级 */
h1, h2, h3, h4, h5, h6 {
    color: var(--text-strong);
    font-family: var(--font-display);
    font-weight: 600;
    letter-spacing: 0.03em;
    line-height: 1.2;
}
h1 { color: var(--text-strong); text-shadow: 0 0 2px rgba(0, 240, 255, 0.7), 0 0 22px rgba(0, 240, 255, 0.2); letter-spacing: 0.02em; }
.stMarkdown p, .stMarkdown li { color: var(--text-primary); }
label p { color: var(--text-secondary) !important; font-weight: 600 !important; }
.stCaption, .stCaption p { color: var(--text-muted) !important; }

/* 头部 */
.fresh-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; flex-wrap: wrap;
    padding: 0.5rem 0.4rem 0.1rem;
}
.fresh-kicker {
    font-family: var(--font-mono);
    color: var(--cyan);
    font-size: 0.72rem;
    letter-spacing: 0.22em;
    margin-bottom: 0.2rem;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);
}
.fresh-sub { color: var(--text-secondary); font-size: 0.92rem; margin-top: 0.3rem; letter-spacing: 0.05em; }
.weather-chip {
    display: inline-flex; align-items: center; gap: 0.55rem;
    font-family: var(--font-mono);
    border-radius: var(--radius-full);
    background: rgba(16, 23, 40, var(--amb-card, 0.5));
    border: 1px solid rgba(0, 240, 255, 0.4);
    padding: 0.45rem 1.05rem;
    color: #c9f8ff;
    font-size: 0.8rem;
    letter-spacing: 0.08em;
    -webkit-backdrop-filter: var(--glass-blur-weak);
    backdrop-filter: var(--glass-blur-weak);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), var(--glow-cyan-sm);
    transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out), border-color var(--dur-1);
}
.weather-chip:hover { transform: translateY(-2px); border-color: var(--cyan); box-shadow: inset 0 1px 0 rgba(255,255,255,.14), 0 0 22px rgba(0, 240, 255, 0.4); }
.weather-chip .dot-mark, .fx-card .dot-mark {
    width: 7px; height: 7px; border-radius: 50%;
    background: var(--cyan); box-shadow: 0 0 9px var(--cyan);
    flex-shrink: 0;
}

/* ===== 玻璃卡片（圆角 16，hover 果冻轻弹） ===== */
.panel {
    position: relative;
    z-index: 1;
    border-radius: var(--radius-lg);
    background: linear-gradient(180deg, rgba(255, 255, 255, var(--amb-hi, 0.045)), transparent 34%), rgba(9, 13, 26, var(--amb-card, 0.5));
    border: 1px solid var(--stroke);
    -webkit-backdrop-filter: var(--glass-blur-md);
    backdrop-filter: var(--glass-blur-md);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, var(--amb-hi, 0.045)), var(--shadow-glass-sm);
    padding: 1rem;
    overflow: hidden;
    transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out),
                border-color var(--dur-1) var(--ease-out);
}
.panel::before {
    content: ""; position: absolute; inset: 0 0 auto 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(0, 240, 255, 0.6) 32%, rgba(255, 42, 109, 0.45) 82%, transparent);
    pointer-events: none;
}
.panel:hover {
    z-index: 2;
    transform: translateY(-3px);
    border-color: rgba(0, 240, 255, 0.4);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), var(--shadow-glass-md), var(--glow-cyan-sm);
}
.panel-title {
    font-family: var(--font-display);
    color: var(--cyan);
    letter-spacing: 0.07em;
    font-size: 0.78rem;
    font-weight: 600;
    margin-bottom: 0.6rem;
    text-shadow: 0 0 10px rgba(0, 240, 255, 0.4);
}
.floating-card {
    border-radius: var(--radius-lg);
    background: linear-gradient(180deg, rgba(255, 255, 255, calc(var(--amb-hi, 0.045) * 0.9)), transparent 32%), rgba(9, 13, 26, var(--amb-card, 0.5));
    border: 1px solid var(--stroke);
    -webkit-backdrop-filter: var(--glass-blur-weak);
    backdrop-filter: var(--glass-blur-weak);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, calc(var(--amb-hi, 0.045) * 0.9)), var(--shadow-glass-sm);
    padding: 0.8rem 0.95rem;
    transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out), border-color var(--dur-1);
}
.floating-card:hover {
    transform: translateY(-2px);
    border-color: rgba(0, 240, 255, 0.45);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1), var(--shadow-glass-md), var(--glow-cyan-sm);
}
.mini-title {
    font-family: var(--font-mono);
    color: var(--text-muted);
    font-size: 0.7rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 0.4rem; vertical-align: middle; box-shadow: 0 0 8px currentColor; }

/* ===== 按钮：玻璃霓虹 + 按压果冻回弹 ===== */
.stButton > button,
div[data-testid="stFormSubmitButton"] button {
    font-family: var(--font-display);
    border-radius: var(--radius-btn);
    background: rgba(255, 255, 255, 0.05);
    color: var(--cyan);
    border: 1px solid rgba(0, 240, 255, 0.4);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    min-height: 38px;
    padding: 0 20px;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
    transition: transform var(--dur-2) var(--ease-out), background-color var(--dur-1) var(--ease-out),
                box-shadow var(--dur-2) var(--ease-out), border-color var(--dur-1), color var(--dur-1);
}
.stButton > button:hover,
div[data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-2px);
    background: rgba(0, 240, 255, 0.13);
    border-color: var(--cyan);
    color: #c9f8ff;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 0 20px rgba(0, 240, 255, 0.25);
}
.stButton > button:active,
div[data-testid="stFormSubmitButton"] button:active {
    transform: scale(0.93);
    transition: transform 0.1s cubic-bezier(0.4, 0, 0.6, 1);
}
/* 主行动：警示黄实心（胶囊圆角） */
button[kind="primary"] {
    background: linear-gradient(180deg, #ffd93b, #ffce00 55%, #e6b800) !important;
    color: #0b0f1a !important;
    border: 1px solid #ffce00 !important;
    border-radius: var(--radius-btn) !important;
    font-size: 14px !important;
    font-weight: 700 !important;
    letter-spacing: 0.14em !important;
    min-height: 46px !important;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5), 0 0 18px rgba(255, 206, 0, 0.28) !important;
    transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out), filter 0.15s ease !important;
}
button[kind="primary"]:hover {
    background: linear-gradient(180deg, #ffe14d, #ffd93b 55%, #f0c000) !important;
    transform: translateY(-2px);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), 0 0 30px rgba(255, 206, 0, 0.45) !important;
}
button[kind="primary"]:active { transform: scale(0.94); filter: brightness(0.96); }

/* ===== 输入：玻璃凹区 + 圆角聚焦辉光 ===== */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stNumberInput > div > div > input {
    font-family: var(--font-mono);
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.14);
    color: var(--text-primary);
    caret-color: var(--cyan);
    transition: border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out), background-color var(--dur-1);
}
.stTextInput > div > div > input:hover,
.stTextArea > div > div > textarea:hover,
.stNumberInput > div > div > input:hover { border-color: rgba(255, 255, 255, 0.3); }
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus,
.stNumberInput > div > div > input:focus {
    outline: none;
    border-color: rgba(0, 240, 255, 0.7);
    background: rgba(8, 14, 26, 0.9);
    box-shadow: 0 0 0 3px rgba(0, 240, 255, 0.14), 0 0 16px rgba(0, 240, 255, 0.12);
}
/* Selectbox / MultiSelect（1.62 data-testid 锚定，原 data-baseweb 已死） */
[data-testid="stSelectbox"] > div,
[data-testid="stMultiSelect"] > div {
    border-radius: var(--radius-md) !important;
    background: rgba(255, 255, 255, 0.045) !important;
    border: 1px solid rgba(255, 255, 255, 0.14) !important;
}
[data-testid="stSelectbox"] input[role="combobox"] {
    color: var(--text-primary) !important;
    caret-color: var(--cyan);
}
[data-testid="stSelectbox"]:focus-within > div,
[data-testid="stMultiSelect"]:focus-within > div {
    border-color: var(--acc-dyn, #00f0ff) !important;
    box-shadow: 0 0 0 3px rgba(0, 240, 255, 0.14), 0 0 16px rgba(0, 240, 255, 0.12) !important;
}
[data-testid="stSelectboxPortal"] [role="listbox"],
[data-testid="stMultiSelectPortal"] [role="listbox"] {
    background: rgba(18, 24, 40, 0.96) !important;
    border: 1px solid rgba(0, 240, 255, 0.25) !important;
    box-shadow: var(--shadow-glass-md) !important;
    border-radius: var(--radius-md) !important;
}
[data-testid="stSelectboxPortal"] [role="option"],
[data-testid="stMultiSelectPortal"] [role="option"] { border-radius: 6px; }

/* ===== Tabs：激活胶囊霓虹（1.62 role=tab） ===== */
[data-testid="stTabs"] [role="tablist"] { gap: 4px; border-bottom: 1px solid var(--stroke-dim); padding-bottom: 2px; }
[data-testid="stTabs"] button[role="tab"] {
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.06em;
    color: var(--text-muted);
    border-radius: 8px;
    padding: 8px 16px;
    transition: color var(--dur-1), background-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);
}
[data-testid="stTabs"] button[role="tab"]:hover { color: #fff; background: rgba(255, 255, 255, 0.06); }
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    color: #c9f8ff !important;
    background: rgba(0, 240, 255, 0.12) !important;
    box-shadow: inset 0 0 0 1px rgba(0, 240, 255, 0.35), 0 0 14px rgba(0, 240, 255, 0.12) !important;
}

/* ===== 指标卡（玻璃 + 等宽发光数字） ===== */
[data-testid="stMetric"] {
    border-radius: var(--radius-lg);
    background: rgba(9, 13, 26, var(--amb-card, 0.5));
    border: 1px solid var(--stroke);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), var(--shadow-glass-sm);
    padding: 14px 16px;
    transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out), border-color var(--dur-1);
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: var(--shadow-glass-md), 0 0 0 1px rgba(0, 240, 255, 0.2);
}
[data-testid="stMetricLabel"] p {
    font-family: var(--font-mono) !important;
    font-size: 11px !important;
    letter-spacing: 0.18em !important;
    text-transform: uppercase;
    color: var(--text-secondary) !important;
}
[data-testid="stMetricValue"] {
    font-family: var(--font-display), var(--font-mono) !important;
    font-size: 28px !important;
    font-weight: 600 !important;
    color: var(--cyan) !important;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
    text-shadow: 0 0 2px rgba(0, 240, 255, 0.7), 0 0 16px rgba(0, 240, 255, 0.3);
}

/* ===== 步骤节点：圆形圆环霓虹（E-8） ===== */
.fx-stepper { display: flex; align-items: flex-start; padding: 0.5rem 0.1rem 0.2rem; }
.fx-step { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 0.35rem; position: relative; min-width: 0; }
.fx-step .node {
    width: 34px; height: 34px;
    display: grid; place-items: center;
    font-family: var(--font-mono);
    font-size: 12px; font-weight: 700;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: var(--text-muted);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09);
    z-index: 1;
    transition: transform var(--dur-2) var(--ease-out), border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out), background 0.2s ease;
}
.fx-step .bar { position: absolute; top: 16px; left: 50%; width: 100%; height: 2px; background: rgba(255, 255, 255, 0.08); z-index: 0; }
.fx-step .bar::after {
    content: ""; position: absolute; inset: 0;
    background: linear-gradient(90deg, rgba(0, 240, 255, 0.85), rgba(122, 47, 247, 0.8));
    transform: scaleX(0); transform-origin: left;
    transition: transform 0.5s var(--ease-out);
}
.fx-step.done .node {
    border-color: rgba(0, 240, 255, 0.7); color: #04121a;
    background: linear-gradient(135deg, #00f0ff, #00c8d6);
    box-shadow: 0 0 16px rgba(0, 240, 255, 0.45);
}
.fx-step.done .bar::after { transform: scaleX(1); }
.fx-step.active .node {
    border-color: rgba(255, 206, 0, 0.75); color: var(--yellow);
    background: rgba(255, 206, 0, 0.1);
    box-shadow: 0 0 0 5px rgba(255, 206, 0, 0.12), 0 0 18px rgba(255, 206, 0, 0.32);
}
.fx-step.error .node {
    border-color: rgba(255, 43, 74, 0.75); color: #ff9aa8;
    background: rgba(255, 43, 74, 0.12);
    box-shadow: 0 0 0 5px rgba(255, 43, 74, 0.1), 0 0 16px rgba(255, 43, 74, 0.35);
}
.fx-step .cap { font-size: 0.68rem; color: var(--text-muted); letter-spacing: 0.03em; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fx-step.done .cap { color: var(--cyan); }
.fx-step.active .cap { color: var(--yellow); }
.fx-step.error .cap { color: var(--red); }
.fx-stepper-meta { display: flex; align-items: center; justify-content: space-between; gap: 0.6rem; margin-top: 0.5rem; flex-wrap: wrap; }
.fx-stepper-meta .meta-pill {
    font-family: var(--font-mono);
    padding: 0.3rem 0.8rem;
    border-radius: var(--radius-full);
    background: rgba(30, 38, 58, 0.55);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--text-secondary);
    font-size: 0.68rem;
    letter-spacing: 0.1em;
    -webkit-backdrop-filter: var(--glass-blur-weak);
    backdrop-filter: var(--glass-blur-weak);
}
.fx-stepper-meta .meta-pill b { color: var(--cyan); font-weight: 600; }

/* ===== 轮播 ===== */
.fx-carousel { position: relative; overflow: hidden; padding: 0.5rem 0 0.2rem;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 5%, #000 95%, transparent);
  mask-image: linear-gradient(90deg, transparent, #000 5%, #000 95%, transparent); }
.fx-track { display: flex; gap: 0.7rem; width: max-content; animation: fxScroll 32s linear infinite; }
.fx-carousel:hover .fx-track, .fx-carousel:focus-within .fx-track { animation-play-state: paused; }
@keyframes fxScroll { to { transform: translateX(-50%); } }
.fx-card {
    border-radius: var(--radius-md);
    background: rgba(14, 20, 36, var(--amb-card, 0.5));
    border: 1px solid var(--stroke);
    padding: 0.45rem 0.95rem;
    display: flex; align-items: center; gap: 0.5rem;
    white-space: nowrap;
    transition: transform var(--dur-2) var(--ease-out), border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);
}
.fx-card:hover { transform: translateY(-2px) scale(1.02); border-color: rgba(0, 240, 255, 0.5); box-shadow: var(--glow-cyan-sm); }
.fx-card .t { font-family: var(--font-display); color: #c9f8ff; font-weight: 600; font-size: 0.78rem; letter-spacing: 0.06em; }
.fx-card .s { color: var(--text-muted); font-size: 0.68rem; margin-left: 0.1rem; }

/* ===== 终端日志 ===== */
.telemetry-log {
    font-family: var(--font-mono) !important;
    font-size: 13px !important;
    line-height: 1.6 !important;
    background: rgba(2, 4, 10, 0.92) !important;
    border: 1px solid rgba(0, 240, 255, 0.16);
    border-left: 3px solid rgba(0, 240, 255, 0.55);
    border-radius: var(--radius-md);
    color: #b8e6ff !important;
    padding: 0.7rem;
    max-height: 340px;
    overflow: auto;
    white-space: pre-wrap;
    word-break: break-word;
}
.telemetry-log::-webkit-scrollbar { width: 8px; }
.telemetry-log::-webkit-scrollbar-thumb { background: rgba(0, 240, 255, 0.35); border-radius: var(--radius-full); }
.telemetry-log::-webkit-scrollbar-track { background: rgba(0, 240, 255, 0.05); }

/* 运行点（静态光晕：轮询区零重放动画） */
.live-dot {
    display: inline-block; width: 7px; height: 7px; border-radius: 50%;
    margin-right: 0.4rem; vertical-align: middle;
    background: var(--cyan);
    box-shadow: 0 0 0 4px rgba(0, 240, 255, 0.13);
}

/* ===== 历史任务行（实色卡，无 backdrop：预算释放） ===== */
.panel-row {
    border-radius: var(--radius-lg);
    background: rgba(11, 16, 30, 0.72);
    border: 1px solid var(--stroke);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, var(--amb-hi, 0.045)), var(--shadow-glass-sm);
    transition: border-color var(--dur-1) var(--ease-out), transform var(--dur-2) var(--ease-out);
}
.panel-row:hover { border-color: rgba(0, 240, 255, 0.4); }

/* ===== 代码 / expander ===== */
[data-testid="stCodeBlock"] {
    background: rgba(2, 4, 10, 0.92) !important;
    border: 1px solid rgba(0, 240, 255, 0.16);
    border-radius: var(--radius-md);
}
[data-testid="stCodeBlock"] code, .stCode code { color: #b8f7e0 !important; background: transparent !important; font-family: var(--font-mono) !important; }
code { background: rgba(0, 240, 255, 0.1); color: var(--cyan); border-radius: 4px; }
[data-testid="stExpander"] details {
    background: rgba(9, 13, 26, var(--amb-card, 0.5));
    border: 1px solid var(--stroke);
    border-radius: var(--radius-md);
    transition: border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);
}
[data-testid="stExpander"] details:hover { border-color: rgba(0, 240, 255, 0.4); box-shadow: var(--glow-cyan-sm); }
[data-testid="stExpander"] summary { font-family: var(--font-display); letter-spacing: 0.04em; }
[data-testid="stExpander"] summary::marker { color: var(--cyan); }
[data-testid="stExpander"] details + details { margin-top: 12px; }

/* ===== 遥测网格 ===== */
.telemetry-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0.75rem; margin-top: 0.5rem; }
.telemetry-metric {
    border-radius: var(--radius-md);
    background: rgba(255, 255, 255, 0.045);
    border: 1px solid rgba(255, 255, 255, 0.1);
    padding: 0.7rem 0.85rem;
    display: flex; flex-direction: column; gap: 0.15rem;
    transition: transform var(--dur-2) var(--ease-out), border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);
}
.telemetry-metric:hover { transform: translateY(-2px); border-color: rgba(0, 240, 255, 0.4); box-shadow: var(--glow-cyan-sm); }
.telemetry-label { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); }
.telemetry-metric strong { font-family: var(--font-mono); color: var(--cyan); font-size: 0.9rem; word-break: break-all; }
.telemetry-subpanel { margin-top: 0.8rem; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.07); border-radius: var(--radius-md); padding: 0.7rem 0.8rem; }
.directory-list { margin: 0.3rem 0 0; padding-left: 1rem; color: var(--text-primary); line-height: 1.8; }
.directory-list li { display: flex; justify-content: space-between; gap: 0.6rem; align-items: center; }
.directory-list code { font-family: var(--font-mono); color: var(--green); font-size: 0.7rem; background: rgba(0, 255, 163, 0.07); border-radius: 4px; padding: 0.05rem 0.3rem; white-space: nowrap; }

/* ===== 果冻关键帧（供首帧/按压类使用，轮询区不挂） ===== */
@keyframes jellyPop {
    0% { transform: scale(0.92); opacity: 0; }
    55% { transform: scale(1.04); opacity: 1; }
    76% { transform: scale(0.985); }
    100% { transform: scale(1); opacity: 1; }
}
@keyframes jellySquash {
    0% { transform: scale(1, 1); }
    30% { transform: scale(1.07, 0.93); }
    56% { transform: scale(0.95, 1.05); }
    78% { transform: scale(1.02, 0.98); }
    100% { transform: scale(1, 1); }
}

/* 玻璃兜底：无 backdrop-filter 时实色 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
    .panel, .floating-card, .fx-card, [data-testid="stSidebar"] > div,
    [data-testid="stMetric"], [data-testid="stExpander"] details, .meta-pill {
        background: rgba(10, 14, 24, 0.92) !important;
    }
}

.block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1500px; }
:focus-visible { outline: 2px solid var(--acc-dyn, #00f0ff); outline-offset: 2px; border-radius: 4px; }
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
@media (max-width: 1000px) {
    .telemetry-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .fx-step .cap { font-size: 0.54rem; }
}
@media (max-width: 620px) {
    .telemetry-grid { grid-template-columns: 1fr; }
    .fresh-header { flex-direction: column; align-items: flex-start; }
    .fx-step .cap { display: none; }
    /* 手机端（mobile_access 规范 c）：列强制堆叠、触控目标、禁 iOS 聚焦放大 */
    [data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.6rem !important; }
    [data-testid="stColumn"] { flex: 1 1 100% !important; min-width: 0 !important; width: 100% !important; }
    .stButton > button, div[data-testid="stFormSubmitButton"] button,
    .stTextInput input, .stTextArea textarea, .stNumberInput input,
    [data-testid="stSelectbox"] > div, .stTabs button[role="tab"] {
        min-height: 44px !important;
        font-size: 16px !important;
    }
    .stTabs [data-testid="stTabs"] button[role="tab"] { padding: 10px 12px !important; }
    [data-testid="stMetricValue"] { font-size: 24px !important; }
    .panel, .floating-card { padding: 0.75rem !important; }
    .block-container { padding-top: 0.8rem !important; }
    .fresh-header h1 { font-size: 1.7rem !important; }
    .telemetry-log { font-size: 12.5px !important; }
    .stRadio [role="radiogroup"] { flex-direction: column !important; align-items: stretch !important; }
    /* 对比表容器级横滑 */
    .stMarkdown table { display: block; overflow-x: auto; white-space: nowrap; max-width: 100%; }
}
/* ===== 头部仪表条集群（Step3：专家组 P2-2） ===== */
.header-cluster { display: flex; align-items: center; gap: 0.7rem; flex-wrap: wrap; justify-content: flex-end; }
.pr-pill {
    display: inline-flex; align-items: center; gap: 0.5rem;
    font-family: var(--font-mono);
    border-radius: var(--radius-full);
    background: rgba(16, 23, 40, var(--amb-card, 0.5));
    border: 1px solid rgba(255, 255, 255, 0.14);
    padding: 0.45rem 1rem;
    color: var(--text-secondary);
    font-size: 0.76rem;
    letter-spacing: 0.06em;
}
.weather-chip:active { transform: scale(0.94); transition: transform 0.1s cubic-bezier(0.4, 0, 0.6, 1); }

/* kicker 末端光标（打字机呼吸，非轮询 DOM） */
.kb-cursor {
    display: inline-block; width: 2px; height: 0.95em;
    margin-left: 0.35rem; vertical-align: -0.12em;
    background: var(--cyan);
    box-shadow: 0 0 8px rgba(0, 240, 255, 0.8);
    animation: kbBlink 1.1s steps(1) infinite;
}
@keyframes kbBlink { 0%, 55% { opacity: 1; } 56%, 100% { opacity: 0; } }

/* 首帧 rise-in（仅首屏一次；fragment/轮询 DOM 不挂此动画） */
.rise-in { animation: riseIn 0.45s var(--ease-out) both; }
@keyframes riseIn { from { opacity: 0; transform: translateY(9px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) {
    .rise-in, .kb-cursor { animation: none !important; }
    .kb-cursor { opacity: 1; }
}
/* SSH 连接健康条 */
.ssh-health {
    display: flex; align-items: center; gap: 0.5rem;
    font-family: var(--font-mono);
    font-size: 0.76rem;
    border-radius: var(--radius-md);
    padding: 0.5rem 0.85rem;
    margin: 0.4rem 0;
    border: 1px solid;
    letter-spacing: 0.03em;
}
.ssh-health.ok { color: #a9f5d0; border-color: rgba(0, 255, 163, 0.35); background: rgba(0, 255, 163, 0.06); }
.ssh-health.fail { color: #ffb3c0; border-color: rgba(255, 43, 74, 0.4); background: rgba(255, 43, 74, 0.07); }

/* ===== stepper 连线修正（v2.2.1）：每根连线 = 上一节点中心 → 本节点中心 ===== */
.fx-stepper { padding: 0.5rem 0 0.2rem; }
.fx-step .bar { left: -50%; width: 100%; top: 16px; }
.fx-step.done .bar::after,
.fx-step.active .bar::after,
.fx-step.error .bar::after { transform: scaleX(1); }

/* ===== 侧栏整理（更紧凑、少一层噪点） ===== */
[data-testid="stSidebar"] .block-container { padding-top: 0.9rem; padding-bottom: 2rem; }
[data-testid="stSidebar"] h5 { font-size: 0.78rem; margin: 0.9rem 0 0.3rem; letter-spacing: 0.08em; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { margin-bottom: 0.15rem; }
[data-testid="stSidebar"] hr { margin: 0.6rem 0; border-color: rgba(255, 255, 255, 0.05); }
[data-testid="stSidebar"] [data-testid="stExpander"] details { background: rgba(9, 13, 26, 0.42); border-color: rgba(255, 255, 255, 0.09); }
[data-testid="stSidebar"] [data-testid="stExpander"] details + details { margin-top: 8px; }
[data-testid="stSidebar"] .stButton > button,
[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] button { min-height: 32px; font-size: 12px; padding: 0 8px; }
[data-testid="stSidebar"] [data-testid="stTextInput"] input { font-size: 13px; }

/* ===== Popover 弹层主题化（与玻璃卡片一致） ===== */
[data-testid="stPopoverBody"],
[data-testid="stPopover"] [data-testid="stVerticalBlock"] > div { border-radius: 14px; }
[data-testid="stPopoverBody"] {
    background: rgba(16, 22, 38, 0.98);
    border: 1px solid rgba(0, 240, 255, 0.28);
    box-shadow: var(--shadow-glass-md);
    color: var(--text-primary);
}
[data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] span { color: var(--text-secondary); }
[data-testid="stPopoverBody"] button { min-height: 34px; }
</style>
"""

# 复现流程步骤：(id, 标题, 节点文字)
PIPELINE_STEPS: List[Tuple[str, str, str]] = [
    ("prepare", "准备", "准"),
    ("clone", "拉取", "拉"),
    ("env", "环境诊断", "环"),
    ("install", "装依赖", "装"),
    ("dependencies", "补装", "补"),
    ("dataset", "数据集", "数"),
    ("verify", "验证", "验"),
    ("model", "入口", "入"),
    ("run", "运行", "运"),
    ("collect", "收集", "收"),
]

# 装饰轮播小卡片：(标题, 副标题)（无 emoji）
CAROUSEL_CARDS: List[Tuple[str, str]] = [
    ("云端执行", "conda / venv / docker 自动适配"),
    ("日志回流", "实时滚动 + 一键根因诊断"),
    ("数据安全", "任务产物只存本机"),
    ("仓库智选", "全网匹配最优复现仓库"),
    ("环境自检", "Python / 依赖 / CUDA 诊断"),
    ("GPU torch", "自动匹配 CUDA 版本"),
]


def build_carousel_html() -> str:
    """装饰轮播条：内容复制两遍实现无缝循环；hover 暂停。"""
    cards = "".join(
        f"<div class='fx-card'><span class='dot-mark'></span>"
        f"<span class='t'>{title}</span><span class='s'>{sub}</span></div>"
        for title, sub in CAROUSEL_CARDS
    )
    return '<div class="fx-carousel"><div class="fx-track">' + cards + cards + "</div></div>"


def build_stepper_html(current_step: str, status: str = "", progress: int = 0, status_label: str = "") -> str:
    """复现流程步进器：圆形霓虹节点 —— 完成青色渐变、当前黄色圆环脉冲、失败红色。"""
    order = [step_id for step_id, _, _ in PIPELINE_STEPS]
    failed = str(status).lower() == "failed"
    current_idx = order.index(current_step) if current_step in order else 0

    nodes: List[str] = []
    for idx, (step_id, title, icon) in enumerate(PIPELINE_STEPS):
        if failed and idx == current_idx:
            state = "error"
        elif idx < current_idx:
            state = "done"
        elif idx == current_idx:
            state = "active"
        else:
            state = ""
        bar = "" if idx == 0 else "<div class='bar'></div>"
        nodes.append(
            f"<div class='fx-step {state}'><div class='node'>{icon}</div>{bar}"
            f"<div class='cap'>{title}</div></div>"
        )

    progress = max(0, min(100, int(progress)))
    meta_html = (
        f"<div class='fx-stepper-meta'>"
        f"<span class='meta-pill'>{status_label or '待开始'}</span>"
        f"<span class='meta-pill'>阶段 <b>{current_idx + 1}</b> / {len(order)}</span>"
        f"<span class='meta-pill'>进度 <b>{progress}%</b></span>"
        f"</div>"
    ) if status or progress else ""

    return f"<div class='fx-stepper'>{''.join(nodes)}</div>{meta_html}"