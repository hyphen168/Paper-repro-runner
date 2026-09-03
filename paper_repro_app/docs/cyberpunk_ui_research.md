# 赛博朋克风格桌面应用 UI 工程规范（配色 / 排版 / 组件，全部数值化可抄）

> 适用范围：深色主题 Streamlit 网页界面（Windows 桌面分发、**离线、不能加载 Google Fonts**）。
> 目标视觉：Cyberpunk 2077 黄黑警示体系 + HUD 角标/扫描线/等宽终端字，叠加 Synthwave 霓虹渐变与高端深色数据面板质感。
> 文档性质：工程可直接抄写的 CSS 级规范。所有颜色、字号、间距、动效参数均可直接复制。
> 落地方式：Streamlit 中用 `st.markdown("<style>…</style>", unsafe_allow_html=True)` 注入全局样式，再以 `unsafe_allow_html` 或 CSS 类名挂接组件（末尾有 Streamlit 类名映射提示，需按实际版本微调）。

---

## 0. 全局设计基调（先记住这 6 条，后面全是它的展开）

1. **暗是默认，亮是信号**：90% 面积保持低明度（#05060c~#0d1428 区间），霓虹色只做"信息信号 + 焦点装饰"，禁止大面积铺色。
2. **锐利 + 极小的圆角**：赛博朋克不是圆润玻璃拟态。卡片圆角 2–6px（推荐 2–4px），带切角（clip-path 45° 斜切）或直角 HUD 角标是灵魂。
3. **描边说话**：几乎所有结构都靠 1px 半透明霓虹描边而非阴影区分层级；阴影只用于"发光"。
4. **文字层级靠字号 + 字距 + 明度**：大标题用窄体/粗体 + 字距收窄；标签用大写 + 0.08–0.3em 字距 + 等宽字体。
5. **黄是行动，青是信息，品红是风险/激情，绿是运行**：Cyberpunk 2077 用黄黑警示表达"可操作/高优先级"。
6. **动效克制**：只有 hover/焦点/入场三类微动效；业务数据区禁止周期性强动效（每 2s 刷新内容时只更新文本不闪页面）。

---

## A. 配色体系（Design Tokens）

### A.1 基础变量块（可直接放入 :root）

```css
:root {
  /* ============ 背景层（由深到浅） ============ */
  --bg-void:        #04050a;   /* 页面最底/全屏渐变根部，几乎纯黑带蓝 */
  --bg-base:        #070a14;   /* 主背景，正文默认所在层 */
  --bg-raised:      #0b1120;   /* 侧边栏/次级面板 */
  --bg-surface:     #0d1526;   /* 卡片表面（玻璃时用 rgba 版，见下） */
  --bg-glass:       rgba(13, 21, 38, 0.72);  /* 毛玻璃表面 */
  --bg-inset:       #05070d;   /* 输入框/终端/代码块等"凹陷"区 */

  /* ============ 描边 ============ */
  --stroke-dim:     rgba(148, 163, 214, 0.14); /* 最弱分隔线 */
  --stroke:         rgba(0, 240, 255, 0.22);   /* 默认 1px 描边 */
  --stroke-strong:  rgba(0, 240, 255, 0.55);   /* hover / 焦点描边 */
  --stroke-magenta: rgba(255, 42, 109, 0.45);  /* 危险相关描边 */
  --stroke-yellow:  rgba(255, 206, 0, 0.55);   /* 警示描边 */

  /* ============ 霓虹主色（强调色，占约 10%） ============ */
  --cyan:           #00f0ff;   /* 信息主色：青 */
  --magenta:        #ff2a6d;   /* 次强调/危险情感觉醒色：品红 */
  --yellow:         #ffce00;   /* 警示黄 = 主行动按钮（CP2077 体系） */
  --green:          #00ffa3;   /* 成功/运行中（终端绿偏青） */
  --red:            #ff2b4a;   /* 失败/报错（比品红更正红） */
  --purple:         #7a2ff7;   /* 渐变铺陈用（底部光晕/图表渐变端） */
  --pink-synth:     #ff71ce;   /* synthwave 粉，仅渐变/图表点缀，慎用于文字 */

  /* ============ 文本层级 ============ */
  --text-strong:    #eaf6ff;   /* 标题/强调正文 */
  --text-primary:   #c9d8ee;   /* 正文主体 */
  --text-secondary: #8fa3c7;   /* 辅助说明 */
  --text-muted:     #5c6f96;   /* 次要标签/占位（≈4.5:1 边缘，仅用于 ≥13px） */
  --text-dim:       #3c4a6b;   /* 禁用/装饰性弱文字 */
  --text-cyan:      #00f0ff;   /* 数值/链接/高亮 */
  --text-yellow:    #ffce00;   /* 警告文字 */
  --text-red:       #ff5c6e;   /* 错误文字（比色块本身亮一档，保证对比） */
  --text-green:     #00ffa3;   /* 成功文字 */
}
```

### A.2 语义用途与数值速查表

| Token | HEX | 用途 | 近似对比度（在 --bg-surface 上，估算） |
|---|---|---|---|
| --bg-void | #04050a | 页面最底层渐变 | — |
| --bg-base | #070a14 | 应用主背景 | 与主文字 ≈18:1（AAA） |
| --bg-raised | #0b1120 | 侧边栏、次级区域 | — |
| --bg-surface | #0d1526 | 卡片、面板表面 | — |
| --bg-glass | rgba(13,21,38,.72) | 毛玻璃卡（配合 blur 12px+saturate 1.4） | 同 surface |
| --bg-inset | #05070d | 输入框/终端凹区 | — |
| --cyan / #00f0ff | 信息主色 | 文本/描边/辉光 | 作文字 ≈13:1（仅用于短文本、大字号） |
| --magenta / #ff2a6d | 危险感/次强调 | 危险按钮、报错 | — |
| --yellow / #ffce00 | 警示+主行动 | 主按钮填充 | 黑字在其上 ≈12:1 |
| --green / #00ffa3 | 成功/运行 | 徽章点、Delta | 作文字 ≈12:1 |
| --red / #ff2b4a | 失败 | 错误块、危险描边 | — |
| --text-strong #eaf6ff | 标题 | ≥15:1（AAA） | — |
| --text-primary #c9d8ee | 正文 | ≈11:1（AAA） | — |
| --text-secondary #8fa3c7 | 辅助 | ≈7:1（AAA） | — |
| --text-muted #5c6f96 | 弱标签/占位 | ≈4.5:1（AA，仅限 ≥13px 且非关键信息） | — |
| --text-dim #3c4a6b | 禁用/装饰 | <3:1，不作为可读文字 | — |

**WCAG 建议**：正文/辅助 ≥ 4.5:1（AA，本方案多数达 AAA）；大标题与霓虹文字 ≥ 3:1；`--text-muted` 仅用于非关键信息；`--text-dim` 只用于禁用态装饰。

### A.3 60–30–10 用量纪律

- **60% 深色背景与留白**（bg-void/base/raised 家族，视觉上"压得住"）。
- **30% 结构层**：卡片表面、分隔线、正文（让信息可读、层级可见）。
- **10% 霓虹强调**：只给 —— 主 CTA、当前导航、关键数值、焦点描边、运行状态。
- 反例检查：一屏内发光元素超过 5 处就砍；每屏霓虹面积建议 < 10–15%。

### A.4 典型渐变配方（装饰用，不许承载文字）

```css
/* 背景合成：深蓝黑渐变 + 微青色顶光 */
background:
  radial-gradient(1200px 500px at 78% -10%, rgba(0,240,255,0.07), transparent 60%),
  radial-gradient(900px 420px at 8% 110%, rgba(122,47,247,0.08), transparent 60%),
  linear-gradient(180deg, #0a0f1f 0%, #070a14 55%, #04050a 100%);

/* 按钮/标题渐变光条：青→品红→黄 仅用于 1–2px 装饰条 */
linear-gradient(90deg, #00f0ff 0%, #7a2ff7 45%, #ff2a6d 75%, #ffce00 100%);
```

---

## B. 排版体系

### B.1 字体族回退栈（Windows 离线可 100% 生效）

```css
:root {
  /* 标题/数字大屏：Bahnschrift 自带 Windows 10+，窄几何感最接近 Rajdhani/Orbitron */
  --font-display: "Bahnschrift", "Rajdhani", "Orbitron", "Arial Narrow",
                  "Segoe UI", "Microsoft YaHei", sans-serif;

  /* 正文 */
  --font-body: "Segoe UI", "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;

  /* 终端/日志/角标序号/数据：等宽 */
  --font-mono: "Cascadia Mono", "Consolas", "Courier New", ui-monospace, monospace;

  /* 中文终端装饰字（可选）：思源黑体可能未装，回退微软雅黑 */
  --font-mono-cn: "Cascadia Mono", "Consolas", "Microsoft YaHei", sans-serif;
}
```

要点：
- **主推 Bahnschrift**：Win10/11 自带、含 300–700 多个字重、窄幅几何、未来感，零部署成本；标签用 **Light/SemiLight** 大写放大字距有 HUD 感。
- **等宽三件套用 Consolas/Cascadia** 即可；数字一律开 `font-variant-numeric: tabular-nums`（等宽数字，刷新不跳动）。
- 若你愿意在安装包内携带字体文件（assets/fonts/*.woff2，Rajdhani / Share Tech Mono 等 OFL 协议可随包分发），用下面的本地 `@font-face`，离线可用：

```css
@font-face { font-family: "Rajdhani"; src: url("assets/fonts/Rajdhani-SemiBold.woff2") format("woff2"); font-weight: 600; font-display: swap; }
@font-face { font-family: "Share Tech Mono"; src: url("assets/fonts/ShareTechMono-Regular.woff2") format("woff2"); font-weight: 400; font-display: swap; }
/* 之后 --font-display 的 "Rajdhani" 才真正生效，缺文件时仍自动落到 Bahnschrift */
```

### B.2 字号阶梯（6 档 + 2 个扩展档）

| 档 | px | rem | 用途 | 字重/字距 |
|---|---|---|---|---|
| micro | 10–11px | .625/.6875 | 角标序号、HUD 坐标、kbd | mono, 400 |
| caption | 12px | .75 | 辅助文字、徽章、图表标签 | 400 / label 态 500 |
| label | 13px | .8125 | 表单标签、按钮、Tab、正文弱强调 | 500–600 |
| body | 14px | .875 | 默认正文（Streamlit 默认即此） | 400 |
| body-lg | 16px | 1 | 强调正文、表头行 | 500 |
| h3/section | 18–20px | 1.125–1.25 | 卡片组标题 | display 600 |
| h2/title | 24px | 1.5 | 面板标题 | display 600–700 |
| h1/page | 30–32px | 1.875–2 | 页面主标题 | display 700 |
| hero | 40–48px | 2.5–3 | 大指标数字（可省略） | display 700, mono fallback |

**正文字号 14px，别低于 12px**（Windows 高分屏 100–125% 缩放下 12px 以下不可读）。

### B.3 字距（tracking）与行高规范

```css
/* 默认值 */
body { letter-spacing: 0.01em; line-height: 1.6; }

/* 大写标签/菜单项：HUD 感核心手段 */
.cy-label { text-transform: uppercase; letter-spacing: 0.14em; font-size: 12px; font-weight: 600; }
.cy-label-wide { text-transform: uppercase; letter-spacing: 0.3em; font-size: 11px; font-weight: 500; } /* 用于面板标题上的小标签 */

/* 标题：字距收窄显"碑刻感" */
h1, .cy-title-lg { letter-spacing: 0.02em; line-height: 1.15; }
.cy-title { letter-spacing: 0.04em; line-height: 1.2; }

/* 数据数字：等宽+微宽字距 */
.cy-num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; letter-spacing: 0.02em; }

/* 正文长段落 */
p, .cy-body { letter-spacing: 0.012em; line-height: 1.6; }
```

行高速查：标题 1.15–1.25，正文 1.6，标签/按钮 1.2–1.4，等宽数据 1.2–1.4。

### B.4 HUD / 终端点缀做法（成本最低的"赛博感"来源）

1. **角标（corner ticks）**：面板四角 2–3px 短线（见 C.1 CSS）。
2. **等宽序号前缀**：每个卡片标题前加 `TX-01`、`NODE-03` 式 mono 11px 弱色序号。
3. **坐标水印**：页脚 `SYS://CITY-Δ-77 // NET OK // UPTIME 42:17:03`，mono 10–11px，--text-muted。
4. **标题后细横线** + 右侧小字状态（`ACTIVE` / `STANDBY`）。
5. 中文标题上方一行 10px 大写字母 tag（如 `DATA STREAM`），做出"设备面板"感。

---

## C. 组件样式规范

> 通用技巧：赛博风描边不要 `solid` 纯色，用低透明度霓虹色才有"辉光管"感；文字级霓虹可用 `text-shadow` 双层（1px 实色 + 8px 羽化）。

### C.0 可复用原子类

```css
/* 霓虹文字辉光 */
.glow-cyan  { color: var(--text-cyan);    text-shadow: 0 0 1px rgba(0,240,255,.9), 0 0 10px rgba(0,240,255,.45); }
.glow-green { color: var(--text-green);   text-shadow: 0 0 1px rgba(0,255,163,.9), 0 0 10px rgba(0,255,163,.4); }
.glow-yellow{ color: var(--text-yellow);  text-shadow: 0 0 1px rgba(255,206,0,.8),  0 0 10px rgba(255,206,0,.4); }

/* 45° 切角工具（按钮/输入框可用） */
.clip-notch { clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px); }
```

### C.1 页面卡片 / 面板（含 HUD 角标 + 顶部细线）

```css
.cy-card {
  position: relative;
  background: linear-gradient(180deg, rgba(0,240,255,0.03), transparent 28%), var(--bg-glass);
  -webkit-backdrop-filter: blur(12px) saturate(140%);
  backdrop-filter: blur(12px) saturate(140%);
  border: 1px solid var(--stroke);
  border-radius: 4px;               /* 赛博风：小圆角或直角 */
  box-shadow: 0 1px 0 rgba(255,255,255,0.04) inset, 0 12px 32px rgba(0,0,0,0.35);
  padding: 20px;
}

/* 顶部 1px 霓虹细线（面板"点亮"细节） */
.cy-card::before {
  content: "";
  position: absolute; inset: 0 0 auto 0; height: 1px;
  background: linear-gradient(90deg, transparent, rgba(0,240,255,.6) 30%, rgba(255,42,109,.4) 80%, transparent);
}

/* HUD 四角角标：用两个伪元素 + 背景渐变画 4 个 12x12 L 形短线 */
.cy-card::after {
  content: ""; position: absolute; inset: 6px;
  pointer-events: none;
  background:
    linear-gradient(var(--cyan), var(--cyan)) left  top    / 10px 2px,
    linear-gradient(var(--cyan), var(--cyan)) left  top    / 2px 10px,
    linear-gradient(var(--cyan), var(--cyan)) right top    / 10px 2px,
    linear-gradient(var(--cyan), var(--cyan)) right top    / 2px 10px,
    linear-gradient(var(--cyan), var(--cyan)) left  bottom / 10px 2px,
    linear-gradient(var(--cyan), var(--cyan)) left  bottom / 2px 10px,
    linear-gradient(var(--cyan), var(--cyan)) right bottom / 10px 2px,
    linear-gradient(var(--cyan), var(--cyan)) right bottom / 2px 10px;
  background-repeat: no-repeat;
  opacity: 0.8;
}

/* 面板标题行：大写 tag + 标题 + 右侧状态 */
.cy-card-header { display:flex; align-items:baseline; gap:12px; margin-bottom:16px;
  padding-bottom:10px; border-bottom:1px solid var(--stroke-dim); }
.cy-card-header .seq { font-family: var(--font-mono); font-size:11px; color: var(--cyan); opacity:.7; }
.cy-card-header h3 { font-family: var(--font-display); font-size:20px; font-weight:600; letter-spacing:.04em; }
.cy-card-header .state { margin-left:auto; font-family:var(--font-mono); font-size:11px;
  letter-spacing:.18em; color: var(--text-green); }
```

### C.2 按钮

分层规则：**页面主行动 = 黄色实心（黄→黑字）**；**次行动 = 青色霓虹描边空心**；**危险 = 品红/红**；禁用一律 opacity .35 去辉光。

```css
/* 基础 */
.cy-btn {
  font-family: var(--font-display);
  font-size: 13px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase;
  padding: 9px 22px; min-height: 36px;
  border-radius: 2px; cursor: pointer;
  transition: transform .15s ease, box-shadow .15s ease, background-color .15s ease,
              border-color .15s ease, filter .15s ease;
  border: 1px solid transparent;
}
.cy-btn:focus-visible { outline: 2px solid var(--cyan); outline-offset: 2px; }

/* 主按钮：警示黄实心 + 黑字 + 黄辉光 */
.cy-btn--primary {
  background: linear-gradient(180deg, #ffd93b, #ffce00 55%, #e6b800);
  color: #0b0f1a; border-color: #ffce00;
  box-shadow: 0 0 0 1px rgba(0,0,0,.4) inset, 0 0 14px rgba(255,206,0,.25);
}
.cy-btn--primary:hover { transform: translateY(-1px); filter: brightness(1.06);
  box-shadow: 0 0 0 1px rgba(0,0,0,.3) inset, 0 0 26px rgba(255,206,0,.5); }
.cy-btn--primary:active { transform: translateY(0); filter: brightness(.96); }

/* 青色实心主按钮（数据面板常用"执行"） */
.cy-btn--cyan { background: rgba(0,240,255,.14); color: var(--text-cyan);
  border: 1px solid var(--stroke-strong); box-shadow: 0 0 12px rgba(0,240,255,.18) inset; }
.cy-btn--cyan:hover { background: rgba(0,240,255,.26); box-shadow: 0 0 22px rgba(0,240,255,.35) inset; transform: translateY(-1px); }

/* 霓虹描边空心（次行动/次级导航） */
.cy-btn--ghost {
  background: transparent; color: var(--text-cyan);
  border: 1px solid rgba(0,240,255,.4);
  box-shadow: 0 0 10px rgba(0,240,255,.12) inset;
}
.cy-btn--ghost:hover { border-color: var(--cyan);
  box-shadow: 0 0 16px rgba(0,240,255,.3) inset, 0 0 12px rgba(0,240,255,.2);
  text-shadow: 0 0 8px rgba(0,240,255,.6); transform: translateY(-1px); }

/* 危险按钮 */
.cy-btn--danger {
  background: linear-gradient(180deg, #ff3a63, var(--magenta) 60%, #d91a4e);
  color: #fff; border-color: var(--magenta);
  box-shadow: 0 0 14px rgba(255,42,109,.3);
}
.cy-btn--danger:hover { filter: brightness(1.08);
  box-shadow: 0 0 26px rgba(255,42,109,.5); transform: translateY(-1px); }

/* 禁用态：全局统一 */
.cy-btn:disabled, .cy-btn--disabled {
  cursor: not-allowed; opacity: .35; filter: grayscale(.6) !important;
  box-shadow: none !important; text-shadow: none !important; transform: none !important;
}
```

### C.3 输入框 / 下拉 / 单选 / 复选 / 开关

```css
/* 标签统一：大写小字距，13px 之上 */
.cy-field { display:flex; flex-direction:column; gap:6px; }
.cy-field label { font-size:12px; font-weight:600; letter-spacing:.12em;
  text-transform: uppercase; color: var(--text-secondary); }

/* 输入框/下拉：凹陷区 + 弱霓虹描边，聚焦全亮 */
.cy-input, .cy-select {
  font-family: var(--font-mono); font-size:14px; color: var(--text-primary);
  background: var(--bg-inset);
  border: 1px solid rgba(0,240,255,.18);
  border-radius: 2px; padding: 8px 12px; min-height: 34px;
  caret-color: var(--cyan);
  transition: border-color .15s ease, box-shadow .15s ease;
}
.cy-input::placeholder { color: var(--text-muted); }
.cy-input:hover, .cy-select:hover { border-color: rgba(0,240,255,.4); }
.cy-input:focus, .cy-select:focus {
  outline: none; border-color: var(--cyan);
  box-shadow: 0 0 0 1px rgba(0,240,255,.5), 0 0 14px rgba(0,240,255,.2);
  background: #060913;
}
.cy-input:disabled, .cy-select:disabled { opacity:.4; cursor:not-allowed; }

/* 自定义复选/单选（方形=复选、小圆点=单选，赛博风不追求圆） */
.cy-check, .cy-radio { appearance:none; width:16px; height:16px; flex:none;
  background: var(--bg-inset); border:1px solid var(--stroke);
  display:inline-grid; place-content:center; cursor:pointer; }
.cy-check { border-radius:2px; }
.cy-radio { border-radius:50%; }
.cy-check:checked, .cy-radio:checked { border-color: var(--cyan);
  box-shadow: 0 0 10px rgba(0,240,255,.35); background: rgba(0,240,255,.12); }
.cy-check:checked::before { content:""; width:10px; height:6px;
  border-left:2px solid var(--cyan); border-bottom:2px solid var(--cyan);
  transform: rotate(-45deg) translate(1px,-1px); }
.cy-radio:checked::before { content:""; width:8px; height:8px; border-radius:50%;
  background: var(--cyan); box-shadow: 0 0 8px rgba(0,240,255,.8); }
.cy-check:disabled, .cy-radio:disabled { opacity:.35; cursor:not-allowed; }

/* 开关：横条 + 方块滑块，开=青辉光 */
.cy-switch { position:relative; width:40px; height:20px; cursor:pointer; }
.cy-switch input { position:absolute; opacity:0; }
.cy-switch .track { position:absolute; inset:0; border-radius:2px; /* 保持方形感或 10px */
  background: var(--bg-inset); border:1px solid var(--stroke); transition:.18s ease; }
.cy-switch .thumb { position:absolute; top:3px; left:3px; width:12px; height:12px;
  background:#4a5a80; transition: transform .18s cubic-bezier(.2,.9,.3,1.4); }
.cy-switch input:checked + .track { border-color: var(--cyan);
  box-shadow: 0 0 12px rgba(0,240,255,.35); background: rgba(0,240,255,.15); }
.cy-switch input:checked ~ .thumb { transform: translateX(20px); background: var(--cyan);
  box-shadow: 0 0 8px rgba(0,240,255,.9); }
.cy-switch input:focus-visible + .track { outline: 2px solid var(--cyan); outline-offset: 2px; }
```

### C.4 导航 Tabs 与侧边栏

```css
/* Tabs：底部分隔线 + 激活态 2px 青辉光下划线 */
.cy-tabs { display:flex; gap:2px; border-bottom:1px solid var(--stroke-dim); }
.cy-tab {
  font-family: var(--font-display); font-size:13px; font-weight:600;
  letter-spacing:.12em; text-transform:uppercase; color: var(--text-muted);
  background:transparent; border:0; padding:10px 18px 9px; cursor:pointer;
  border-bottom:2px solid transparent; margin-bottom:-1px;
  transition: color .15s ease, border-color .15s ease, text-shadow .15s ease;
}
.cy-tab:hover { color: var(--text-secondary); }
.cy-tab.active {
  color: var(--text-cyan); border-bottom-color: var(--cyan);
  text-shadow: 0 0 10px rgba(0,240,255,.55);
  box-shadow: 0 14px 18px -16px rgba(0,240,255,.45); /* 微光晕延伸 */
}
.cy-tab .badge-dot { display:inline-block; width:6px; height:6px; border-radius:50%;
  background:var(--magenta); margin-left:8px; vertical-align:2px;
  box-shadow:0 0 6px var(--magenta); }

/* 侧边栏条目 */
.cy-nav-item {
  display:flex; align-items:center; gap:10px; padding:9px 14px;
  font-size:13.5px; color: var(--text-secondary); border-left:2px solid transparent;
  border-radius:0 2px 2px 0; cursor:pointer; transition:.15s ease;
}
.cy-nav-item:hover { color: var(--text-primary); background: rgba(0,240,255,.06);
  border-left-color: rgba(0,240,255,.35); }
.cy-nav-item.active {
  color: var(--text-cyan); background: linear-gradient(90deg, rgba(0,240,255,.14), transparent 90%);
  border-left-color: var(--cyan);
  text-shadow: 0 0 8px rgba(0,240,255,.5);
}
```

### C.5 数据指标卡 / 数字

```css
.cy-metric {
  background: var(--bg-surface); border:1px solid var(--stroke); border-radius:4px;
  padding:16px 18px; position:relative; overflow:hidden;
}
.cy-metric::after { /* 底部青淡光晕，HUD 呼吸感但保持静态 */
  content:""; position:absolute; left:10%; right:10%; bottom:-18px; height:24px;
  background: radial-gradient(50% 100% at 50% 50%, rgba(0,240,255,.16), transparent 70%);
  pointer-events:none;
}
.cy-metric .label { font-family: var(--font-mono); font-size:11px;
  letter-spacing:.18em; text-transform:uppercase; color: var(--text-secondary); }
.cy-metric .value {
  font-family: var(--font-display), var(--font-mono);  /* Bahnschrift 数字极好 */
  font-size:32px; font-weight:600; color: var(--text-cyan);
  font-variant-numeric: tabular-nums; line-height:1.1; margin-top:6px;
  text-shadow: 0 0 2px rgba(0,240,255,.7), 0 0 14px rgba(0,240,255,.35);
}
.cy-metric .unit { font-size:15px; opacity:.75; margin-left:2px; }
.cy-metric .delta-up   { color: var(--text-green);  text-shadow:0 0 10px rgba(0,255,163,.5); }
.cy-metric .delta-down { color: var(--text-red);    text-shadow:0 0 10px rgba(255,43,74,.5); }
```

### C.6 进度条 / 步进器

```css
/* 进度条：4px 细轨 + 渐变亮条 + 尾端辉光 */
.cy-progress { height:4px; background: rgba(255,255,255,.06);
  border:1px solid rgba(148,163,214,.12); border-radius:2px; overflow:visible; }
.cy-progress .fill { height:100%; width:0%;
  background: linear-gradient(90deg, var(--cyan), #7a2ff7 60%, var(--magenta));
  box-shadow: 0 0 8px rgba(0,240,255,.8);
  transition: width .3s cubic-bezier(.2,.8,.2,1); }
.cy-progress.warn .fill { background: var(--yellow); box-shadow:0 0 8px rgba(255,206,0,.8); }

/* 步进器：方形节点 + 竖线连接 */
.cy-steps { display:flex; align-items:center; }
.cy-step { display:flex; align-items:center; gap:10px; color: var(--text-muted); }
.cy-step .idx { width:24px; height:24px; display:grid; place-content:center;
  font-family:var(--font-mono); font-size:12px; border:1px solid var(--stroke);
  background:var(--bg-inset); border-radius:2px; }
.cy-step.done .idx { color:#05070d; background:var(--cyan); border-color:var(--cyan);
  box-shadow:0 0 10px rgba(0,240,255,.5); }
.cy-step.current .idx { color:var(--cyan); border-color:var(--cyan);
  box-shadow:0 0 12px rgba(0,240,255,.6), 0 0 0 3px rgba(0,240,255,.12); }
.cy-step .line { flex:1; min-width:24px; height:1px; background:var(--stroke-dim); }
.cy-step.done .line, .cy-step.current + .cy-step .line { background: rgba(0,240,255,.5); }
```

### C.7 标签 chip / 状态徽章

```css
.cy-chip { display:inline-flex; align-items:center; gap:6px;
  font-family:var(--font-mono); font-size:11px; letter-spacing:.1em;
  padding:3px 10px; border-radius:2px; border:1px solid var(--stroke); color:var(--text-secondary);
  background: rgba(0,240,255,.04); }
.cy-chip .dot { width:6px; height:6px; border-radius:50%; background:currentColor; }

/* 状态徽章：脉冲点只做"正在运行"一种动态 */
.cy-badge { display:inline-flex; align-items:center; gap:6px; font-family:var(--font-mono);
  font-size:11px; letter-spacing:.14em; text-transform:uppercase; padding:2px 8px 2px 6px; }
.cy-badge::before { content:""; width:6px; height:6px; border-radius:50%; background:currentColor; }

.cy-badge--ok   { color: var(--text-green);  background:rgba(0,255,163,.08);  border:1px solid rgba(0,255,163,.35); text-shadow:0 0 8px rgba(0,255,163,.4); }
.cy-badge--run  { color: var(--cyan);        background:rgba(0,240,255,.08);  border:1px solid rgba(0,240,255,.4);  }
.cy-badge--run::before { animation: pulse 1.6s ease-in-out infinite; }
.cy-badge--fail { color: var(--text-red);    background:rgba(255,43,74,.1);   border:1px solid rgba(255,43,74,.45); }
.cy-badge--queued { color: var(--yellow);    background:rgba(255,206,0,.07);  border:1px solid rgba(255,206,0,.4); }

@keyframes pulse { 0%,100% { box-shadow:0 0 0 0 rgba(0,240,255,.5); }
                   50%     { box-shadow:0 0 0 4px rgba(0,240,255,0);   } }
```

### C.8 代码块 / 日志终端

```css
.cy-terminal {
  font-family: var(--font-mono); font-size:12.5px; line-height:1.55;
  background: #02040a;   /* 最暗 + 不带蓝，读感更"终端" */
  border:1px solid rgba(0,240,255,.16); border-radius:4px;
  padding:14px 16px; overflow:auto;
  color: #b8f7e0;        /* 白绿终端字 */
  box-shadow: inset 0 0 24px rgba(0,0,0,.6);
  white-space: pre; tab-size: 4;
}
/* 终端标题条 */
.cy-terminal-head { display:flex; align-items:center; gap:6px;
  font-family:var(--font-mono); font-size:11px; letter-spacing:.16em; color:var(--text-muted);
  padding:7px 12px; background:#070b14; border:1px solid rgba(0,240,255,.14); border-bottom:0; border-radius:4px 4px 0 0;
}
.cy-terminal-head .lt,.rt { color:var(--cyan); }
/* 三种终端色 */
.term-info   { color:#7ddcff; }   /* 青 */
.term-ok     { color:#2bff9a; }   /* 绿 */
.term-warn   { color:#ffce00; }
.term-err    { color:#ff5c6e; }
.term-prompt::before { content:"> "; color: var(--magenta); font-weight:700; }
.term-cursor::after { content:"▊"; color:var(--cyan); animation: blink 1.1s steps(2,start) infinite; }
@keyframes blink { 50% { opacity:0; } }
```

### C.9 空状态 / 提示 / 错误块

```css
/* 空状态：居中灰字 + 虚线框 + 单个霓虹图标，不喧宾夺主 */
.cy-empty { display:flex; flex-direction:column; align-items:center; gap:10px;
  padding:48px 24px; color: var(--text-muted); text-align:center;
  border:1px dashed rgba(148,163,214,.25); border-radius:4px; }
.cy-empty .ic { font-size:34px; color:#3c4a6b; }
.cy-empty .tip { font-size:13px; max-width:420px; line-height:1.6; }

/* 提示/告警块：左侧 3px 霓虹条 + 弱底色，不用亮色大块 */
.cy-alert { display:flex; gap:10px; align-items:flex-start;
  padding:10px 14px; border-radius:2px; font-size:13px; line-height:1.55;
  border:1px solid transparent; border-left-width:3px; }
.cy-alert .head { font-weight:600; margin-right:6px; letter-spacing:.06em; }

.cy-alert--info    { color:var(--text-primary); background:rgba(0,240,255,.05); border-color:rgba(0,240,255,.35); border-left-color:var(--cyan); }
.cy-alert--warn    { color:#ffe08a;            background:rgba(255,206,0,.06);  border-color:rgba(255,206,0,.3);  border-left-color:var(--yellow); }
.cy-alert--error   { color:#ffb3bd;            background:rgba(255,43,74,.08);  border-color:rgba(255,43,74,.3);  border-left-color:var(--red); }
```

---

## D. 排版与布局节奏

### D.1 间距阶梯（4px 基数，只允许用下列值）

| 令牌 | px | 用途 |
|---|---|---|
| --sp-1 | 4 | 图标/文字微距 |
| --sp-2 | 8 | 表单内 label↔控件、chip 间距 |
| --sp-3 | 12 | 紧凑控件组间距、卡片内小块间距 |
| --sp-4 | 16 | 面板内边距、表单组内默认间距 |
| --sp-5 | 24 | 卡片组之间、section 内间距 |
| --sp-6 | 32 | 大区块（页面 section）间距 |
| --sp-7 | 48 | 页面留白/折叠区间距 |

面板标准内边距 20px（介于 16/24），相邻同层级卡片 gap 16px，卡片组与组 gap 24px，页面顶部标题区与内容 gap 24–32px。侧边栏 padding 16px；主内容区 max-width 建议 1280px 居中。

### D.2 面板分组与视觉层级法则

- **越重要的越亮**：标题文字（strong 色）> 内容（primary）> 辅助（secondary）> 水印（muted/dim）；不要用字号把一切放大——先用明度分层，再决定字号。
- **一层一框**：卡片内不要再套带描边卡片；子分组用分隔线（--stroke-dim）或间距表达，避免"千层饼描边"。
- **一屏一个主 CTA**：黄色按钮只允许同时出现 1 个（真主行动）；其余用青色 ghost。
- **数据优先顺序**：指标数字 > 面板标题 > 表头 > 正文 > 水印/角标。
- 文本"发光"只允许出现在：关键数值、激活 Tab、当前步骤、hover 词条。发光 + 高饱和大面积 = 劣质感。

### D.3 表单流建议

- 单列表单：label(12px 大写) 上、控件下，组内 gap 8，字段组 gap 24，行内控件纵向基线对齐。
- 双列：左 label 固定宽 140–160px 右对齐，控件左对齐。
- 提交按钮右对齐或与输入同行尾端；校验错误用字段内红字 12px + 控件描边转红，且错误文本不发光只标红。

### D.4 背景装饰：网格 / 扫描线 / 噪点（克制用法 + 性能）

```css
/* 1) 全局微网格（最推荐，WebGL/Canvas 不可用时）：纯 CSS，静态 */
body::before {
  content:""; position:fixed; inset:0; z-index:0; pointer-events:none;
  background-image:
    linear-gradient(rgba(0,240,255,.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0,240,255,.035) 1px, transparent 1px);
  background-size: 44px 44px;          /* 大格 */
  mask-image: radial-gradient(120% 90% at 50% 0%, #000 30%, transparent 78%);
}
/* 2) 扫描线：1px 重复 + 12% 透明度，静态纯色即可，禁止动画整页 */
body::after {
  content:""; position:fixed; inset:0; z-index:1; pointer-events:none;
  background: repeating-linear-gradient(0deg, rgba(255,255,255,.018) 0 1px, transparent 1px 3px);
  mix-blend-mode: overlay;
}
/* 3) 噪点：若不需要可省略；SVG feTurbulence dataURI，opacity 3–5% */
.noise-overlay { pointer-events:none; opacity:.035;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2'/%3E%3C/filter%3E%3Crect width='120' height='120' filter='url(%23n)' opacity='1'/%3E%3C/svg%3E"); }
```

- 性能与可用性红线：
  - 装饰层一律 `position:fixed + z-index 底层 + pointer-events:none`，置于内容之下或之上但永不遮挡点击与阅读（扫描线 overlay 透明度 ≤2%，且建议 `mix-blend-mode:overlay` 在大面积低端 GPU 上若卡顿就整体去掉）。
  - 网格尺寸 ≥44px 且不随滚动动画；**禁止**整页扫描线滚动动画与整页背景模糊。
  - `backdrop-filter`（毛玻璃）别超过同时 3–4 个大卡片，Windows 老 GPU/远程桌面会明显掉帧。
  - 动画只挂在 `transform / opacity / filter` 上；大面板发光用预设静态阴影，不要 hover 时用 JS 改 box-shadow 引起大面积重绘。
  - 主体内容容器 `z-index:2`，确保在装饰层之上。

---

## E. 微动效规范

| 场景 | 参数（数值可直接抄） |
|---|---|
| 按钮/链接 hover | `transform: translateY(-1px)`；辉光 shadow 半径 +12~+14px（如 14→26px）；时长 150ms `ease`；去色用 `filter: brightness(1.05~1.08)` |
| 按钮 active/按压 | `transform: translateY(0)`，辉光减半或去除，时长 80ms |
| 焦点环 | `outline: 2px solid var(--cyan); outline-offset: 2px`（键盘可达性必须保留） |
| 面板入场 | `opacity: 0→1; translateY(8px)→0`，320ms，`cubic-bezier(.2,.85,.25,1)`，批处理时按 index `delay: 40ms` 级联（≤6 个面板） |
| 卡片 hover | 上移 2px（translateY(-2px)），边框透明度 .22→.45，外加静态预置辉光层显隐（用 opacity 控制 shadow 层而非改 shadow 值） |
| Tab 激活/进度条 | 颜色/下划线 150ms；进度宽度 300ms `cubic-bezier(.2,.8,.2,1)`；不弹跳 |
| 运行状态点 | `pulse` 动画 1.6s，只允许出现在单个 6px 圆点 |
| 终端光标 | `blink 1.1s steps(2,start)`，仅光标一个字符 |

- **入场 JS 模板原则**：给元素初始加 `.is-in` 样式 `opacity:0`，请求下一帧后移除或加 `.in`。所有动效必须包裹 `@media (prefers-reduced-motion: reduce){ *{ animation:none !important; transition:none !important } }`。
- **关于"每 2 秒刷新导致整页闪烁"**：这是 Streamlit 默认 `st.rerun` 全量重渲造成的观感问题。对策：
  1. 页面级 CSS/图片等资源放 Streamlit 主题或 CDN 不随 rerun 重注入——把 `<style>` 放每页顶部常量区即可（Streamlit 会去重），避免动态拼接样式字符串。
  2. 轮询数据用 `st.fragment(run_every=2)`（新版本）只刷新局部，或改用前端组件/`st_autorefresh` 限定区域；不要在数据区放置会变化的入场动画（入场动画只用于首次挂载：用 `session_state` 标记"已入场"后不再重放）。
  3. 数字更新靠 `tabular-nums` 等宽 + 静态辉光，不逐帧加动画，避免"跳字闪屏"。
  4. 列表/表格每次仅更新变化行，整表重绘前先隐藏表体再插入（batch DOM 操作），或用 CSS `contain: content` 隔离重绘区。
  5. 终极克制：数据区默认**无动画**；动画预算全部预留给 hover/焦点/首次入场三类微交互。

---

## F. 参考来源（需人工复核有效性）

> 本会话无联网检索工具，下列 URL 为凭记忆列出的官方/权威入口，**全部需要人工打开复核**；无法访问时建议直接搜索关键词替代。

**官方与一手参考**
1. Cyberpunk 2077 官方网站（黄黑主视觉、字体与 UI 氛围）：https://www.cyberpunk.net — 复核入口与视觉素材。
2. Cyberpunk 2077 概念艺术/UI 设定（ArtStation 官方向导栏目）：https://www.artstation.com/ 搜索 "Cyberpunk 2077 UI / interface" — 复核具体作品链接。
3. CP2077 字体事实核查：标题风格近似 **Rajdhani/Orbitron**、正文窄体无衬线、UI 常配等宽——社区考证见 Reddit r/cyberpunkgame 与 fontsinuse 站内检索 "Cyberpunk 2077"（https://fontsinuse.com/）— 复核。
4. REDengine / CD PROJEKT 官方图库（截图与 HUD 静态图用于对色）：https://www.cyberpunk.net/en/news — 复核。

**网页设计案例入口**
5. Awwwards 赛博朋克站点聚合：https://www.awwwards.com/websites/cyberpunk/ — 复核 tag 路径是否仍有效（可能需登录筛选）。
6. Awwwards synthwave/outrun：同站搜索 "synthwave" 或 "retrowave" — 复核。
7. Dribbble 高质仪表盘霓虹案例：https://dribbble.com/search/neon-dashboard 与 https://dribbble.com/search/cyberpunk-ui — 复核。
8. Mobbin/landing page 数据库内搜 "cyberpunk dashboard / neon finance" — 复核。

**实现向参考**
9. 字体分发页（OFL，可离线随包）：Rajdhani https://fonts.google.com/specimen/Rajdhani ；Orbitron https://fonts.google.com/specimen/Orbitron ；Share Tech Mono https://fonts.google.com/specimen/Share+Tech+Mono — 复核并下载 woff2 自托管。
10. Streamlit 官方主题文档（config.toml 基础色/字体钩子）：https://docs.streamlit.io/develop/concepts/configuration/theming — 复核版本。
11. CSS 切角/HUD 角标技法：CSS-Tricks "clip-path" 文章：https://css-tricks.com/almanac/properties/c/clip-path/ — 复核。
12. WCAG 对比度在线核算：https://webaim.org/resources/contrastchecker/ — 复核（用于最终对色签收）。

**复核重点提醒**：#5/#6/#7 这类聚合站的 tag 路径与登录策略会变；#1/#4 的视觉素材版权仅可参考不可商用复制；本规范 B.2/C 部分数字为工程建议，最终以你 1200×900 目标窗口上的实际观感做 ±10% 微调。

---

## G. 收尾自查清单（上线前过一遍）

- [ ] 每屏霓虹元素 ≤5 处，霓虹面积 <15%。
- [ ] 正文字符全部 ≥13px，弱文字 ≥4.5:1（WebAIM 复核一次）。
- [ ] 黄实心按钮同屏仅 1 个；禁用态统一 opacity .35 + 去辉光。
- [ ] 焦点环（2px cyan + offset 2px）覆盖所有可交互元素。
- [ ] 字体回退在"无 Rajdhani/Orbitron + 有 Bahnschrift/Segoe"环境下肉眼验收一次。
- [ ] 每 2s 刷新区域无入场/闪烁动画；数字为等宽制表符排布。
- [ ] 远程桌面/集显环境跑一遍：无整页扫描线动画、毛玻璃卡片 ≤4、滚动流畅。
- [ ] `prefers-reduced-motion: reduce` 生效。
