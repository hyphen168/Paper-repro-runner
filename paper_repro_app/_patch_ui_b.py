# -*- coding: utf-8 -*-
"""UI 专家组规范落地 · 阶段 B（hover 改 ease / 动效静态化 / 死选择器重锚 / 字阶 / 日志 / 微细节）"""
from pathlib import Path

p = Path('paper_repro_app/ui_theme.py')
s = p.read_text(encoding='utf-8')


def rep(old, new, tag):
    global s
    assert old in s, '未找到: ' + tag
    s = s.replace(old, new, 1)


# ===== hover 一律 ease（去 spring，防 2s 重建跳变） =====
seg_hover_panel = (
    ".panel:hover {\n"
    "    transform: translateY(-3px) scale(1.012);\n"
    "    border-color: rgba(0, 240, 255, 0.4);\n"
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), var(--shadow-glass-md), var(--glow-cyan-sm);\n}"
)
assert seg_hover_panel in s, 'panel-hover'
s = s.replace(seg_hover_panel,
              ".panel:hover {\n    z-index: 2;\n    transform: translateY(-3px);\n"
              "    border-color: rgba(0, 240, 255, 0.4);\n"
              "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), var(--shadow-glass-md), var(--glow-cyan-sm);\n}", 1)

# ===== 动效静态化：轮询区无 animation =====
rep(
    "    box-shadow: 0 0 0 5px rgba(255, 206, 0, 0.12), 0 0 18px rgba(255, 206, 0, 0.32);\n"
    "    animation: nodePulse 1.5s ease-in-out infinite;\n}",
    "    box-shadow: 0 0 0 5px rgba(255, 206, 0, 0.12), 0 0 18px rgba(255, 206, 0, 0.32);\n}", 'nodePulse-off')
rep(
    "@keyframes nodePulse { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.09); } }\n", '', 'nodePulse-kf')
rep(
    "/* 运行点脉冲 */\n.live-dot {\n    display: inline-block; width: 7px; height: 7px; border-radius: 50%;\n"
    "    margin-right: 0.4rem; vertical-align: middle;\n    background: var(--cyan);\n"
    "    animation: badgePulse 1.6s ease-in-out infinite;\n}\n"
    "@keyframes badgePulse { 0%, 100% { box-shadow: 0 0 0 0 rgba(0, 240, 255, 0.5); } 50% { box-shadow: 0 0 0 5px rgba(0, 240, 255, 0); } }\n",
    "/* 运行点（静态光晕：轮询区零重放动画） */\n.live-dot {\n    display: inline-block; width: 7px; height: 7px; border-radius: 50%;\n"
    "    margin-right: 0.4rem; vertical-align: middle;\n    background: var(--cyan);\n"
    "    box-shadow: 0 0 0 4px rgba(0, 240, 255, 0.13);\n}\n", 'live-dot')

# ===== P0-1 死选择器重锚（Streamlit 1.62 data-testid） =====
old_sel = (
    ".stSelectbox [data-baseweb=\"select\"] > div,\n"
    ".stMultiSelect [data-baseweb=\"select\"] > div {\n"
    "    border-radius: var(--radius-md);\n"
    "    background: rgba(255, 255, 255, 0.045);\n"
    "    border: 1px solid rgba(255, 255, 255, 0.14);\n}\n"
    ".stSelectbox [data-baseweb=\"popover\"] [role=\"listbox\"] { background: rgba(18, 24, 40, 0.92); }\n\n"
    "/* ===== Tabs：激活胶囊霓虹 ===== */\n"
    ".stTabs [data-baseweb=\"tab-list\"] { gap: 4px; border-bottom: 1px solid var(--stroke-dim); padding-bottom: 2px; }\n"
    ".stTabs [data-baseweb=\"tab\"] {\n"
    "    font-family: var(--font-display);\n"
    "    font-size: 13px;\n"
    "    font-weight: 600;\n"
    "    letter-spacing: 0.12em;\n"
    "    text-transform: uppercase;\n"
    "    color: var(--text-muted);\n"
    "    border-radius: 8px;\n"
    "    padding: 8px 16px;\n"
    "    transition: color var(--dur-1), background-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);\n}\n"
    ".stTabs [data-baseweb=\"tab\"]:hover { color: #fff; background: rgba(255, 255, 255, 0.06); }\n"
    ".stTabs [aria-selected=\"true\"] {\n"
    "    color: #c9f8ff !important;\n"
    "    background: rgba(0, 240, 255, 0.12) !important;\n"
    "    box-shadow: inset 0 0 0 1px rgba(0, 240, 255, 0.35), 0 0 14px rgba(0, 240, 255, 0.12) !important;\n}"
)
new_sel = (
    "/* Selectbox / MultiSelect（1.62 data-testid 锚定，原 data-baseweb 已死） */\n"
    "[data-testid=\"stSelectbox\"] > div,\n"
    "[data-testid=\"stMultiSelect\"] > div {\n"
    "    border-radius: var(--radius-md) !important;\n"
    "    background: rgba(255, 255, 255, 0.045) !important;\n"
    "    border: 1px solid rgba(255, 255, 255, 0.14) !important;\n}\n"
    "[data-testid=\"stSelectbox\"] input[role=\"combobox\"] {\n"
    "    color: var(--text-primary) !important;\n"
    "    caret-color: var(--cyan);\n}\n"
    "[data-testid=\"stSelectbox\"]:focus-within > div,\n"
    "[data-testid=\"stMultiSelect\"]:focus-within > div {\n"
    "    border-color: var(--acc-dyn, #00f0ff) !important;\n"
    "    box-shadow: 0 0 0 3px rgba(0, 240, 255, 0.14), 0 0 16px rgba(0, 240, 255, 0.12) !important;\n}\n"
    "[data-testid=\"stSelectboxPortal\"] [role=\"listbox\"],\n"
    "[data-testid=\"stMultiSelectPortal\"] [role=\"listbox\"] {\n"
    "    background: rgba(18, 24, 40, 0.96) !important;\n"
    "    border: 1px solid rgba(0, 240, 255, 0.25) !important;\n"
    "    box-shadow: var(--shadow-glass-md) !important;\n"
    "    border-radius: var(--radius-md) !important;\n}\n"
    "[data-testid=\"stSelectboxPortal\"] [role=\"option\"],\n"
    "[data-testid=\"stMultiSelectPortal\"] [role=\"option\"] { border-radius: 6px; }\n\n"
    "/* ===== Tabs：激活胶囊霓虹（1.62 role=tab） ===== */\n"
    "[data-testid=\"stTabs\"] [role=\"tablist\"] { gap: 4px; border-bottom: 1px solid var(--stroke-dim); padding-bottom: 2px; }\n"
    "[data-testid=\"stTabs\"] button[role=\"tab\"] {\n"
    "    font-family: var(--font-display);\n"
    "    font-size: 13px;\n"
    "    font-weight: 600;\n"
    "    letter-spacing: 0.06em;\n"
    "    color: var(--text-muted);\n"
    "    border-radius: 8px;\n"
    "    padding: 8px 16px;\n"
    "    transition: color var(--dur-1), background-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out);\n}\n"
    "[data-testid=\"stTabs\"] button[role=\"tab\"]:hover { color: #fff; background: rgba(255, 255, 255, 0.06); }\n"
    "[data-testid=\"stTabs\"] button[role=\"tab\"][aria-selected=\"true\"] {\n"
    "    color: #c9f8ff !important;\n"
    "    background: rgba(0, 240, 255, 0.12) !important;\n"
    "    box-shadow: inset 0 0 0 1px rgba(0, 240, 255, 0.35), 0 0 14px rgba(0, 240, 255, 0.12) !important;\n}"
)
rep(old_sel, new_sel, 'selectors')

# ===== 字阶 / tracking / 中文可读下限 =====
rep(".telemetry-label { font-family: var(--font-mono); font-size: 0.64rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--text-muted); }",
    ".telemetry-label { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); }", 'tele-label')
rep(".mini-title {\n    font-family: var(--font-mono);\n    color: var(--text-muted);\n    font-size: 0.66rem;\n    letter-spacing: 0.2em;\n    text-transform: uppercase;\n    margin-bottom: 0.4rem;\n}",
    ".mini-title {\n    font-family: var(--font-mono);\n    color: var(--text-muted);\n    font-size: 0.7rem;\n    letter-spacing: 0.12em;\n    text-transform: uppercase;\n    margin-bottom: 0.4rem;\n}", 'mini-title')
rep(".fx-step .cap { font-size: 0.6rem; color: var(--text-muted); letter-spacing: 0.06em; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }",
    ".fx-step .cap { font-size: 0.68rem; color: var(--text-muted); letter-spacing: 0.03em; max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }", 'step-cap')
rep("    font-size: 13px;\n    font-weight: 600;\n    letter-spacing: 0.1em;\n    text-transform: uppercase;\n    min-height: 38px;",
    "    font-size: 13px;\n    font-weight: 600;\n    letter-spacing: 0.05em;\n    text-transform: uppercase;\n    min-height: 38px;", 'btn-track')
rep(".panel-title {\n    font-family: var(--font-display);\n    color: var(--cyan);\n    letter-spacing: 0.14em;\n    font-size: 0.75rem;\n    font-weight: 600;\n    text-transform: uppercase;\n    margin-bottom: 0.6rem;\n    text-shadow: 0 0 10px rgba(0, 240, 255, 0.4);\n}",
    ".panel-title {\n    font-family: var(--font-display);\n    color: var(--cyan);\n    letter-spacing: 0.07em;\n    font-size: 0.78rem;\n    font-weight: 600;\n    margin-bottom: 0.6rem;\n    text-shadow: 0 0 10px rgba(0, 240, 255, 0.4);\n}", 'panel-title')
rep(".fresh-kicker {\n    font-family: var(--font-mono);\n    color: var(--cyan);\n    font-size: 0.72rem;\n    letter-spacing: 0.3em;\n    text-transform: uppercase;\n    margin-bottom: 0.2rem;\n    text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);\n}",
    ".fresh-kicker {\n    font-family: var(--font-mono);\n    color: var(--cyan);\n    font-size: 0.72rem;\n    letter-spacing: 0.22em;\n    margin-bottom: 0.2rem;\n    text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);\n}", 'kicker')

# ===== 正文 15px 与主区密度 =====
rep("    --font-mono: \"Cascadia Mono\", \"Consolas\", \"Courier New\", ui-monospace, monospace;\n}",
    "    --font-mono: \"Cascadia Mono\", \"Consolas\", \"Courier New\", ui-monospace, monospace;\n}\n"
    "section[data-testid=\"stMain\"] { font-size: 15px; line-height: 1.7; }", 'main-font')
rep(".block-container { padding-top: 0.7rem; padding-bottom: 2.5rem; max-width: 1500px; }",
    ".block-container { padding-top: 1.25rem; padding-bottom: 2.5rem; max-width: 1500px; }", 'container-pad')

# ===== 日志：13px 青系 / 去暗角 / 滚动条 8px =====
rep("    font-size: 12px !important;\n    line-height: 1.55 !important;",
    "    font-size: 13px !important;\n    line-height: 1.6 !important;", 'log-size')
rep("    color: #b8f7e0 !important;\n    box-shadow: inset 0 0 26px rgba(0, 0, 0, 0.55);\n    padding: 0.7rem;\n    max-height: 340px;",
    "    color: #b8e6ff !important;\n    padding: 0.7rem;\n    max-height: 340px;", 'log-color')
rep(".telemetry-log::-webkit-scrollbar { width: 6px; }", ".telemetry-log::-webkit-scrollbar { width: 8px; }", 'log-scroll')

# ===== metric 28px =====
rep("    font-size: 30px !important;\n    font-weight: 600 !important;",
    "    font-size: 28px !important;\n    font-weight: 600 !important;", 'metric-size')

# ===== expander 细节 =====
rep("[data-testid=\"stExpander\"] summary { font-family: var(--font-display); letter-spacing: 0.04em; }",
    "[data-testid=\"stExpander\"] summary { font-family: var(--font-display); letter-spacing: 0.04em; }\n"
    "[data-testid=\"stExpander\"] summary::marker { color: var(--cyan); }\n"
    "[data-testid=\"stExpander\"] details + details { margin-top: 12px; }", 'expander-detail')

# ===== panel-row：历史行实色卡（无 blur，预算释放） =====
rep("/* ===== 代码 / expander ===== */",
    "/* ===== 历史任务行（实色卡，无 backdrop：预算释放） ===== */\n"
    ".panel-row {\n"
    "    border-radius: var(--radius-lg);\n"
    "    background: rgba(11, 16, 30, 0.72);\n"
    "    border: 1px solid var(--stroke);\n"
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, var(--amb-hi, 0.045)), var(--shadow-glass-sm);\n"
    "    transition: border-color var(--dur-1) var(--ease-out), transform var(--dur-2) var(--ease-out);\n"
    "}\n"
    ".panel-row:hover { border-color: rgba(0, 240, 255, 0.4); }\n"
    "\n"
    "/* ===== 代码 / expander ===== */", 'panel-row')

# ===== focus 环 amb-acc =====
rep(":focus-visible { outline: 2px solid var(--cyan); outline-offset: 2px; border-radius: 4px; }",
    ":focus-visible { outline: 2px solid var(--acc-dyn, #00f0ff); outline-offset: 2px; border-radius: 4px; }", 'focus-ring')

p.write_text(s, encoding='utf-8')
print('阶段 B 完成')
