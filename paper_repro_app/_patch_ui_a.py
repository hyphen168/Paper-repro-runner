# -*- coding: utf-8 -*-
"""UI 专家组规范落地 · 阶段 A（:root 清理/氛围面/卡片消费/网格/侧栏/面板）"""
from pathlib import Path

p = Path('paper_repro_app/ui_theme.py')
s = p.read_text(encoding='utf-8')


def rep(old, new, tag):
    global s
    assert old in s, '未找到: ' + tag
    s = s.replace(old, new, 1)


# ===== :root 清理 + 氛围默认/链 =====
old_root = """    --bg-void: #04050a;
    --bg-base: #070a14;
    --bg-raised: #0b1120;
    --bg-surface: #0d1526;
    --bg-glass: rgba(12, 17, 30, 0.5);
    --bg-inset: rgba(5, 7, 13, 0.9);
    /* 描边 */
    --stroke-dim: rgba(148, 163, 214, 0.14);
    --stroke: rgba(255, 255, 255, 0.09);
    --stroke-strong: rgba(0, 240, 255, 0.5);
    --stroke-magenta: rgba(255, 42, 109, 0.5);
    /* 霓虹 */
    --cyan: #00f0ff;
    --magenta: #ff2a6d;
    --yellow: #ffce00;
    --green: #00ffa3;
    --red: #ff2b4a;
    --purple: #7a2ff7;
    /* 文本 */
    --text-strong: #eaf6ff;
    --text-primary: #c9d8ee;
    --text-secondary: #8fa3c7;
    --text-muted: #5c6f96;
    /* 圆角阶梯（圆润玻璃赛博） */
    --radius-sm: 8px;
    --radius-btn: 10px;
    --radius-md: 12px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --radius-full: 999px;
    /* 毛玻璃 */
    --glass-blur-strong: blur(28px) saturate(160%) brightness(1.06);
    --glass-blur-md: blur(18px) saturate(150%) brightness(1.05);
    --glass-blur-weak: blur(10px) saturate(140%) brightness(1.03);
    /* 弹性缓动 */
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
    --ease-spring-soft: cubic-bezier(0.22, 1.2, 0.36, 1);
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --dur-1: 0.15s;
    --dur-2: 0.22s;
    /* 阴影 */
    --shadow-glass-sm: 0 1px 2px rgba(0, 0, 0, 0.25), 0 4px 14px rgba(0, 0, 0, 0.2);
    --shadow-glass-md: 0 2px 8px rgba(0, 0, 0, 0.24), 0 14px 34px rgba(0, 0, 0, 0.34);
    --glow-cyan-sm: 0 0 12px rgba(0, 240, 255, 0.22);
    --glow-magenta-sm: 0 0 12px rgba(255, 42, 109, 0.24);
    /* 背景亮度（按天气×昼夜 每 60s 注入单变量；固定底色由它在深/浅间插值） */
    --bg-color: #0A1120;"""
new_root = """    /* 描边（α 随氛围注入 --amb-line） */
    --stroke-dim: rgba(148, 163, 214, calc(var(--amb-line, 0.09) * 1.5));
    --stroke: rgba(255, 255, 255, var(--amb-line, 0.09));
    /* 霓虹 */
    --cyan: #00f0ff;
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
    --glow-cyan-sm: 0 0 calc(12px * var(--amb-glow)) rgba(0, 240, 255, calc(0.22 * var(--amb-glow)));"""
rep(old_root, new_root, 'root-block')

# ===== 网格 56px 弱化 + 扫描线消费 --scan-a =====
rep(
    "        linear-gradient(rgba(0, 240, 255, 0.02) 1px, transparent 1px),\n"
    "        linear-gradient(90deg, rgba(0, 240, 255, 0.02) 1px, transparent 1px);\n"
    "    background-size: 44px 44px;",
    "        linear-gradient(rgba(0, 240, 255, 0.015) 1px, transparent 1px),\n"
    "        linear-gradient(90deg, rgba(0, 240, 255, 0.015) 1px, transparent 1px);\n"
    "    background-size: 56px 56px;", 'grid')
rep(
    "    background: repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.014) 0 1px, transparent 1px 3px);\n"
    "    opacity: 0.8;",
    "    background: repeating-linear-gradient(0deg, rgba(255, 255, 255, var(--scan-a, 0.011)) 0 1px, transparent 1px 3px);\n"
    "    opacity: 1;", 'scanline')

# ===== 侧栏消费 amb =====
rep(
    "    background: linear-gradient(180deg, rgba(10, 14, 26, 0.68), rgba(8, 11, 22, 0.78));\n"
    "    border-right: 1px solid rgba(255, 255, 255, 0.08);",
    "    background: linear-gradient(180deg, rgba(9, 13, 26, calc(var(--amb-card, 0.5) + 0.15)), rgba(8, 11, 22, calc(var(--amb-card, 0.5) + 0.25)));\n"
    "    border-right: 1px solid rgba(255, 255, 255, calc(var(--amb-line, 0.09) * 0.9));", 'sidebar')

# ===== 卡片族背景消费 --amb-card / --amb-hi =====
rep(
    "    background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), transparent 34%), rgba(9, 13, 26, 0.52);\n"
    "    border: 1px solid var(--stroke);",
    "    background: linear-gradient(180deg, rgba(255, 255, 255, var(--amb-hi, 0.045)), transparent 34%), rgba(9, 13, 26, var(--amb-card, 0.5));\n"
    "    border: 1px solid var(--stroke);", 'panel-bg')
rep(
    "    background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent 32%), rgba(9, 13, 26, 0.52);\n"
    "    border: 1px solid var(--stroke);",
    "    background: linear-gradient(180deg, rgba(255, 255, 255, calc(var(--amb-hi, 0.045) * 0.9)), transparent 32%), rgba(9, 13, 26, var(--amb-card, 0.5));\n"
    "    border: 1px solid var(--stroke);", 'floating-bg')
rep(
    "[data-testid=\"stMetric\"] {\n"
    "    border-radius: var(--radius-lg);\n"
    "    background: var(--bg-glass);\n"
    "    border: 1px solid var(--stroke);\n"
    "    -webkit-backdrop-filter: var(--glass-blur-weak);\n"
    "    backdrop-filter: var(--glass-blur-weak);",
    "[data-testid=\"stMetric\"] {\n"
    "    border-radius: var(--radius-lg);\n"
    "    background: rgba(9, 13, 26, var(--amb-card, 0.5));\n"
    "    border: 1px solid var(--stroke);", 'metric-bg')
rep(
    "[data-testid=\"stExpander\"] details {\n"
    "    background: rgba(12, 17, 30, 0.62);\n"
    "    border: 1px solid rgba(255, 255, 255, 0.09);\n"
    "    border-radius: var(--radius-md);\n"
    "    -webkit-backdrop-filter: var(--glass-blur-weak);\n"
    "    backdrop-filter: var(--glass-blur-weak);",
    "[data-testid=\"stExpander\"] details {\n"
    "    background: rgba(9, 13, 26, var(--amb-card, 0.5));\n"
    "    border: 1px solid var(--stroke);\n"
    "    border-radius: var(--radius-md);", 'expander-bg')
rep(
    "    background: rgba(16, 23, 40, 0.55);",
    "    background: rgba(16, 23, 40, var(--amb-card, 0.5));", 'chip-bg')
rep(
    "    background: rgba(18, 26, 46, 0.55);\n"
    "    border: 1px solid rgba(255, 255, 255, 0.09);\n"
    "    padding: 0.45rem 0.95rem;\n"
    "    display: flex; align-items: center; gap: 0.5rem;\n"
    "    white-space: nowrap;\n"
    "    -webkit-backdrop-filter: var(--glass-blur-weak);\n"
    "    backdrop-filter: var(--glass-blur-weak);",
    "    background: rgba(14, 20, 36, var(--amb-card, 0.5));\n"
    "    border: 1px solid var(--stroke);\n"
    "    padding: 0.45rem 0.95rem;\n"
    "    display: flex; align-items: center; gap: 0.5rem;\n"
    "    white-space: nowrap;", 'fxcard-bg')

# 顶部高光 inset 消费 amb-hi
rep(
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09), var(--shadow-glass-sm);\n"
    "    padding: 1rem;",
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, var(--amb-hi, 0.045)), var(--shadow-glass-sm);\n"
    "    padding: 1rem;", 'panel-inset')
rep(
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08), var(--shadow-glass-sm);",
    "    box-shadow: inset 0 1px 0 rgba(255, 255, 255, calc(var(--amb-hi, 0.045) * 0.9)), var(--shadow-glass-sm);", 'floating-inset')

# panel z-index 防叠
rep(
    ".panel {\n"
    "    position: relative;\n"
    "    border-radius: var(--radius-lg);",
    ".panel {\n"
    "    position: relative;\n"
    "    z-index: 1;\n"
    "    border-radius: var(--radius-lg);", 'panel-z')

p.write_text(s, encoding='utf-8')
print('阶段 A 完成')
