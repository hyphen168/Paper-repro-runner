# 圆润玻璃赛博（Rounded Glass Cyber）—— 桌面应用 UI 质感升级工程规范

> 适用范围：Windows 桌面浏览器中的 Streamlit 深色网页应用。
> 现状：已具"深色赛博霓虹"配色（青 `#00f0ff` / 品红 `#ff2a6d` / 黄 `#ffce00`），但几何锐利（2px 圆角、直角角标）。
> 目标：将 **玻璃毛玻璃 + 大圆角 + 弹性果冻动效 + 悬停微交互** 融合为"圆润玻璃赛博"，全部数值化、可直接抄。
>
> ⚠️ 本报告基于内置知识撰写（本次运行未暴露联网检索工具，URL 见 F 节，**一律需复核**）。

---

## 0. 融合设计哲学（先立规矩再抄代码）

赛博的"锐利"与玻璃的"圆润"是对立张力，靠 **分层职责** 调和，不是互相妥协：

| 视觉元素 | 归属 | 处理 |
|---|---|---|
| 面（卡片/面板/弹层/侧边栏） | **玻璃圆润** | 大圆角 + 半透明 + 模糊，负责"柔和与层次" |
| 线（描边/分隔/连接线） | **霓虹** | 1px 半透明白 + 关键处霓虹色发光描边 |
| 光（辉光/角标/高亮点） | **霓虹锐利** | 保留小圆角/切角，负责"锋利的赛博感" |
| 动（悬停/入场） | **弹性克制** | 位移 ≤4px、过冲 ≤10%，负责"活"而非"闹" |

口诀：**玻璃为体、霓虹为骨、弹性为息**。圆角是玻璃的"物理",霓虹描边是赛博的"棱角"。锐利元素每屏保留 **≤3 处**（切角角标、序号牌、代码块），其余全部圆润化。

配套的既有霓虹变量（假设已存在，规范统一引用，不重复定义）：

```css
:root {
  --neon-cyan:    #00f0ff;
  --neon-magenta: #ff2a6d;
  --neon-yellow:  #ffce00;
  --ink-hi:   #e8ecf4;          /* 主文字 */
  --ink-mid:  rgba(232,236,244,.66);
  --ink-low:  rgba(232,236,244,.42);
  --line:     rgba(255,255,255,.08);  /* 通用 1px 描边 */
  --bg-0: #05070d;              /* 页面最深 */
  --bg-1: #0a0f1c;              /* 基准深蓝黑 */
  --bg-2: #111827;
}
```

---

## A. 毛玻璃体系（数值化）

### A.0 三件事同时成立才有"玻璃感"

1. 元素背景 **半透明**（看得透）；
2. 背后 **有内容**（渐变光斑/粒子/图表，否则模糊=灰雾）；
3. 元素本身 `backdrop-filter` 生效（有 GPU 合成支持）。

背景场景我们给"深色渐变 + 天气粒子"，参数见 A.6。**毛玻璃必须配"背景有内容"才成立**，这是第一条验收红线。

### A.1 背景半透明档位表（rgba 基色 `12,17,30` 深蓝黑）

| 层级 | 变量 | 半透明底 | 说明 |
|---|---|---|---|
| 大面积卡片 | `--glass-bg-card` | `rgba(12,17,30,.50)` | 背后必有渐变/图表 |
| 长驻侧边栏 | `--glass-bg-sidebar` | `rgba(9,13,24,.64)` | 停留时间长，底稍实 |
| 弹层 / Modal | `--glass-bg-modal` | `rgba(8,12,22,.80)` | 强调焦点，可更实 |
| 输入建议/下拉浮层 | `--glass-bg-popover` | `rgba(18,24,40,.86)` | 小面积悬浮，字多必须可读（对应需求里 rgba .5–.85 的高端） |
| 状态徽章/chip | `--glass-bg-chip` | `rgba(30,38,58,.55)` | 小面积，透一点即可 |
| 输入框内底色 | `--glass-bg-input` | `rgba(255,255,255,.045)` | 比玻璃更"暗"，保证文字对比 |
| 玻璃内强调层 | `--glass-bg-cyan` / `--glass-bg-magenta` | `rgba(0,240,255,.10)` / `rgba(255,42,109,.10)` | 选中/激活态，霓虹染色玻璃 |

> 规则：**面积越大、停留越久、文字越密 → 底越实**。卡片 0.5 起步，浮层 ≥0.85，两者之间没有 0.4 以下的"裸透"（背后是深空背景时低于 0.45 会脏）。

### A.2 backdrop-filter 参数组合（强 / 中 / 弱 三套）

```css
:root {
  /* 强：Modal / 全屏搜索 / 大弹层 —— 模糊最大，隔离感最强 */
  --glass-blur-strong: blur(32px) saturate(160%) brightness(1.06);
  /* 中：卡片 / 指标卡 / 侧边栏 —— 日常主力 */
  --glass-blur-md:     blur(18px) saturate(150%) brightness(1.04);
  /* 弱：输入建议 / tooltip / 下拉 / 小 chip —— 看得见字，且省 GPU */
  --glass-blur-weak:   blur(9px)  saturate(140%) brightness(1.02);
}
```

使用模板（三档通用结构，抄这一份改变量即可）：

```css
.glass {
  background: var(--glass-bg-card);               /* ① 先给纯色兜底 */
  -webkit-backdrop-filter: var(--glass-blur-md);  /* ② 再叠模糊（Safari/老内核） */
  backdrop-filter: var(--glass-blur-md);
  border: 1px solid rgba(255,255,255,.08);        /* ③ 外描边 */
  box-shadow:
    inset 0 1px 0 rgba(255,255,255,.08),          /* ④ 顶部内高光 */
    0 8px 24px rgba(0,0,0,.28);                   /* ⑤ 投影 */
}
```

- `brightness(1.02–1.06)`：深色背景下把背后暗部略提亮，玻璃边缘更"透亮"，不要低于 1.0（会显脏）。
- `saturate` 让背后的霓虹光斑透过玻璃仍带彩色，140–160% 即可，过高发腻。
- **避免 backdrop-filter 数值动画**（每帧重采样 = 卡顿源），详见 D.3。

### A.3 边框与高光

| 部件 | 数值 |
|---|---|
| 顶部内高光 | `inset 0 1px 0 rgba(255,255,255,.08)`（卡片），modal 用 `.06` |
| 外层描边（常态） | `1px solid rgba(255,255,255,.08)` |
| 外层描边（霓虹态/hover） | `1px solid rgba(0,240,255,.45)`（品红态 `rgba(255,42,109,.5)`） |
| 渐变"玻璃高光面"（可选） | `background-image: linear-gradient(180deg, rgba(255,255,255,.05), transparent 38%)`，叠加在半透明底之上 |
| 玻璃+霓虹双重辉光描边（accent 卡片） | `border:1px solid rgba(0,240,255,.22); box-shadow: 0 0 0 1px rgba(0,240,255,.08), 0 0 18px rgba(0,240,255,.10), inset 0 1px 0 rgba(255,255,255,.08)` |

> 让"描边"承担赛博锋利感：常态白 8% 描边收敛，hover/激活才点燃霓虹描边——锐利只在需要被注意时出现。

### A.4 阴影层级（玻璃投影 + 辉光分两套变量，避免混写）

```css
:root {
  --shadow-glass-sm: 0 1px 2px rgba(0,0,0,.25), 0 4px 12px rgba(0,0,0,.18);
  --shadow-glass-md: 0 2px 8px rgba(0,0,0,.22), 0 12px 32px rgba(0,0,0,.30);
  --shadow-glass-lg: 0 8px 24px rgba(0,0,0,.30), 0 24px 64px rgba(0,0,0,.45);

  --glow-cyan-sm:    0 0 10px rgba(0,240,255,.25);
  --glow-cyan-md:    0 0 24px rgba(0,240,255,.18);
  --glow-magenta-sm: 0 0 10px rgba(255,42,109,.28);
  --glow-yellow-sm:  0 0 12px rgba(255,206,0,.20);
}
```

卡片 hover 推荐合成：`var(--shadow-glass-md), 0 0 0 1px rgba(0,240,255,.22), var(--glow-cyan-sm)`。

### A.5 性能红线、防呆与降级（Windows 重点）

**同屏预算（硬性）：**
- 大面积毛玻璃面（面积 > 视口 20% 且 blur ≥ 16px）：**同屏 ≤ 3 块**（如 1 侧边栏 + 2 指标墙），再多会掉帧。
- 弹层打开时：毛玻璃 Modal **只允许 1 块全屏级**，且它打开时不要保留 3 块大卡同时满载——打开 Modal 时给 body 加 `.is-dialog` 类把大卡 blur 临时降到弱档。
- **禁止嵌套 backdrop-filter ≥ 2 层**（子层会对父层合成结果再次采样，成本翻倍且出现"双重模糊发白"）。弹层内部的小卡片用 `background: rgba(...)` 实色半透明即可，不要玻璃叠玻璃。
- 不要在带 backdrop-filter 的元素上做 transform/opacity 大面积动画（每帧重采样合成层）。要动画的"悬停上浮"发生在玻璃元素上可以，但**弹跳幅度大的果冻动画元素避免同时挂大 blur**——把 blur 留给容器，果冻交给里面的内容层。

**Windows / 远程桌面 / 集显：**
- backdrop-filter 由 GPU 合成器承担；**远程桌面(RDP/虚拟桌面)下合成常降级或禁用模糊**——降级路径必须存在。
- 集显 + 高分屏（Win 缩放 >125%）大 blur 成本放大，把强档 `32px` 降到 `20px`。
- 用 `@supports` 显式降级：无 backdrop-filter 时把半透明底提到 **0.92** 实色（保证可读，视觉仍可接受）：

```css
/* 兜底 1：根本不支持 backdrop-filter */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass, .glass-card, .glass-modal {
    background: rgba(10,14,24,.92) !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
  }
}
/* 兜底 2：低性能设备可手动关（Win 上检测不到的方案：暴露开关类） */
@media (max-width: 0px) {} /* 占位，勿用 */
html.reduce-glass .glass { backdrop-filter: none; -webkit-backdrop-filter: none;
  background: rgba(10,14,24,.9); }
```

```python
# Streamlit 中给用户一个侧边栏开关，写进 app 容器根元素
if st.sidebar.toggle("关闭毛玻璃(低配模式)", value=False):
    st.markdown("<style>html.reduce-glass{}</style>", unsafe_allow_html=True)
    # 并将 reduce-glass 写到全局样式挂载点（见 D.4 注入方式）
```

> `prefers-reduced-transparency` 媒体查询目前仅在较新 Chromium(macOS) 试验性存在，**不要作为唯一依据**，以上面开关类为准。

### A.6 玻璃的"背景内容"场景参数（深色渐变 + 天气粒子）

场景层固定在最底（z-index 0），所有玻璃在其上。数值：

```css
body, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(1100px 750px at 12% -8%,  rgba(0,240,255,.13), transparent 60%),
    radial-gradient(950px  700px at 88% 6%,   rgba(255,42,109,.11), transparent 55%),
    radial-gradient(900px  900px at 55% 112%, rgba(255,206,0,.06), transparent 60%),
    linear-gradient(160deg, #070a12 0%, #0a1020 46%, #0c0918 100%) !important;
  background-attachment: fixed;
}
```

- 光斑 alpha 控制在 **.06–.13**（太亮会穿过玻璃干扰文字）。
- **粒子**：3 层 CSS-only 悬浮点（`box-shadow` 批量画点，仅做慢速 `translate` 漂移），白 `rgba(255,255,255,.20–.35)`、直径 1–3px、`blur(.5px)`。位移 60–140s 一个循环，**永不触发大范围重绘**（只动 transform），且归入"禁用果冻"类（见 D.3）。

```css
/* CSS-only 雨点/尘埃（约 30 点，慢速漂移） */
.particles { position: fixed; inset: 0; z-index: 0; pointer-events: none; }
.particles::before {
  content: ""; position: absolute; width: 2px; height: 2px; border-radius: 50%;
  background: rgba(255,255,255,.30);
  box-shadow:
    120px 80px 0 0 rgba(255,255,255,.28), 360px 220px 0 0 rgba(0,240,255,.35),
    640px 140px 0 0 rgba(255,255,255,.22), 900px 420px 0 0 rgba(255,255,255,.20),
    1180px 260px 0 0 rgba(255,42,109,.30), 220px 560px 0 0 rgba(255,255,255,.18),
    480px 700px 0 0 rgba(0,240,255,.22), 760px 880px 0 0 rgba(255,255,255,.24),
    1050px 640px 0 0 rgba(255,206,0,.22), 60px 960px 0 0 rgba(255,255,255,.20);
  animation: drift 90s linear infinite alternate;
}
@keyframes drift { from { transform: translateY(-40px) translateX(-20px); }
                   to   { transform: translateY(60px)  translateX(30px); } }
```

---

## B. 圆润化系统

### B.1 圆角阶梯与分配（token 化）

```css
:root {
  --radius-sm:   8px;   /* 状态徽章、小 chip、内嵌小块、切角弱化位 */
  --radius-btn:  10px;  /* 按钮、下拉、导航项 */
  --radius-md:   12px;  /* 输入框、选择器、Tab 容器内项 */
  --radius-lg:   16px;  /* 卡片、指标卡、图表面板（默认主力） */
  --radius-xl:   20px;  /* 弹层/Modal、侧边栏大面板、分组大容器 */
  --radius-2xl:  24px;  /* 超大 hero 面板 / 全屏抽屉 */
  --radius-full: 999px; /* 胶囊：进度条、开关、步骤节点、徽章 pill、搜索框 */
}
```

对照表（圆润度从外到内递减——**越大容器越圆**）：

| 部件 | 建议 | 备注 |
|---|---|---|
| 按钮 | 10px | 主/次/危险统一 |
| 输入框/搜索 | 12px | 胶囊形态（右操作区在框内）除外 |
| 卡片/指标卡 | 16px | 卡片内嵌小图块可回落 8–10 |
| 标签 chip/徽章 | 8px 或 999px | 小号方 chip 8、状态 pill 999 |
| Tab | 容器贴边 + 激活项胶囊 | 顶部主导航推荐"胶囊激活项" |
| 弹层/Modal | 20px | 屏幕小可降至 16 |
| 步骤节点 | 圆形 999px | 见 E-8 |
| 进度条 | 999px 胶囊 | 见 E-7 |

> 现有的 2px → 至少提到 8px 起步，否则玻璃 + 直角组合会像"贴了膜的纸片"。

### B.2 "圆润但仍是赛博"的边界（锐利保留清单）

保留小圆角/直角的 **accent 位（每屏 ≤3 处）**：

1. **序号角标**（如 Top 榜数字、步骤数字）—— 用 `4px` 或切角 `clip-path: polygon(0 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%)` 的赛博切角牌，霓虹描边。
2. **代码 / 终端块** —— `0px` 圆角 + 左侧 3px 霓虹竖线。
3. **表格** —— 不逐行圆角；表头/外框可 8px（st.dataframe 内嵌默认即可，不强改）。
4. **刻度、网格、扫描线** —— 直角，玻璃之外的数据皮肤。
5. 需要"被切割的赛博感"的单点：允许 1 处大切角卡片（hero 标题区），其余卡片必须 16px 整圆。

判断规则：**圆角给"容器和输入物"，直角/切角给"数据装饰与编号"**。全部圆了=发腻的糖果，全锐=老赛博——比例约 **85% 圆 : 15% 锐**。

### B.3 霓虹描边 × 大圆角 × 玻璃的组合样式（圆角上的光）

```css
.glass-card--neon {
  border-radius: var(--radius-lg);
  border: 1px solid rgba(0,240,255,.22);
  background: var(--glass-bg-card);
  -webkit-backdrop-filter: var(--glass-blur-md);
  backdrop-filter: var(--glass-blur-md);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), var(--shadow-glass-md);
}
.glass-card--neon:hover {
  border-color: rgba(0,240,255,.55);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.10), var(--shadow-glass-md),
              0 0 24px rgba(0,240,255,.14), 0 0 0 1px rgba(0,240,255,.08);
}
```

**圆角 + 描边的坑**：发光的 box-shadow 不会贴圆角偏移，但会沿圆角形状扩散（box-shadow 跟随 border-radius，天然正确）；`outline` 不跟随圆角——键盘焦点圈要用 `box-shadow: 0 0 0 3px ...` 模拟圆角 outline。

---

## C. 悬停微交互规范

### C.1 统一时长 / 缓动表

```css
:root {
  --dur-1: .15s;  /* 颜色、描边、背景填充 */
  --dur-2: .2s;   /* 位移、缩放、阴影 */
  --dur-3: .3s;   /* 大面板、多属性联动 */
  --ease-out:     cubic-bezier(.16, 1, .3, 1);       /* 快出缓停，日常 */
  --ease-in-out:  cubic-bezier(.65, 0, .35, 1);      /* 状态往返 */
  --ease-spring:      cubic-bezier(.34, 1.56, .64, 1); /* 弹 8–10% */
  --ease-spring-soft: cubic-bezier(.22, 1.2, .36, 1);  /* 弹 3–4% */
}
```

| 场景 | 属性 | 时长 | 缓动 |
|---|---|---|---|
| 颜色/描边 hover | border-color / color / background | 150ms | ease-out |
| 卡片/按钮 上浮+阴影 | transform / box-shadow | 200–220ms | ease-out |
| 图标微缩放 | transform: scale | 150ms | ease-out |
| Tab 激活滑动 | background / box-shadow | 200ms | ease-in-out |
| 按压态 | transform: scale | 100–120ms | ease-in（快按下去） |
| 松手回弹 | transform | 220–260ms | **ease-spring** |

### C.2 逐类规范（可直接抄）

**卡片 hover** —— 上浮 2–3px + 微放大 + 霓虹描边点燃：

```css
.glass-card {
  border-radius: var(--radius-lg);
  background: var(--glass-bg-card);
  -webkit-backdrop-filter: var(--glass-blur-md);
  backdrop-filter: var(--glass-blur-md);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), var(--shadow-glass-sm);
  transform: translateY(0) scale(1);
  transition: transform var(--dur-2) var(--ease-out),
              box-shadow var(--dur-2) var(--ease-out),
              border-color var(--dur-1) var(--ease-out);
  will-change: transform;
}
.glass-card:hover {
  transform: translateY(-3px) scale(1.015);
  border-color: rgba(0,240,255,.4);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.1), var(--shadow-glass-md),
              0 0 22px rgba(0,240,255,.12);
}
.glass-card:active { transform: translateY(-1px) scale(.995); }
```

**按钮（主/次/危险）** —— hover 上移 2px + 辉光加深；按压果冻见 D.2：

```css
.btn-neon {
  border-radius: var(--radius-btn);
  padding: .55em 1.3em;
  border: 1px solid rgba(0,240,255,.55);
  background: rgba(0,240,255,.08);
  color: #bdf8ff;
  box-shadow: 0 0 0 rgba(0,240,255,0), inset 0 1px 0 rgba(255,255,255,.08);
  transform: translateY(0);
  transition: transform var(--dur-2) var(--ease-out),
              box-shadow var(--dur-2) var(--ease-out),
              background-color var(--dur-1) var(--ease-out),
              color var(--dur-1) var(--ease-out);
}
.btn-neon:hover {
  transform: translateY(-2px);
  background: rgba(0,240,255,.16);
  box-shadow: 0 0 18px rgba(0,240,255,.28), inset 0 1px 0 rgba(255,255,255,.10);
}
.btn-neon:active { transform: scale(.94); transition: transform .12s cubic-bezier(.4,0,.6,1); }
```

**输入框聚焦**：

```css
.field-glass input, .field-glass textarea, .field-glass [data-baseweb="input"] {
  border-radius: var(--radius-md);
  background: var(--glass-bg-input);
  border: 1px solid rgba(255,255,255,.14);
  transition: border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out),
              background-color var(--dur-1);
}
.field-glass input:focus, .field-glass :focus-visible {
  outline: none;
  border-color: rgba(0,240,255,.65);
  box-shadow: 0 0 0 3px rgba(0,240,255,.16), 0 0 14px rgba(0,240,255,.12);
  background: rgba(8,14,26,.85);
}
```

**导航 / Tab**：

```css
/* hover：文字提亮 + 底色浮现 */
nav a:hover, button[data-baseweb="tab"]:hover {
  color: #fff !important;
  background: rgba(255,255,255,.06);
}
/* 激活：胶囊霓虹（圆角承担圆润，光承担赛博） */
button[data-baseweb="tab"][aria-selected="true"] {
  background: rgba(0,240,255,.12) !important;
  color: #bdf8ff !important;
  box-shadow: inset 0 -2px 0 rgba(0,240,255,.9), 0 0 12px rgba(0,240,255,.10) !important;
  border-radius: var(--radius-btn) !important;
  transition: all var(--dur-2) var(--ease-out);
}
```

**图标 / 指标卡 icon**：

```css
.icon-btn, .metric-icon {
  transition: transform .15s var(--ease-spring-soft), color var(--dur-1), filter var(--dur-1);
}
.icon-btn:hover, .metric-icon:hover { transform: scale(1.12); color: var(--neon-cyan); filter: drop-shadow(0 0 6px rgba(0,240,255,.6)); }
.icon-btn:active, .metric-icon:active { transform: scale(.9); }
```

### C.3 反抖动 / 触发区防呆

- **transform 不改布局**：位移一律 transform，绝不 margin/top。布局类属性不进 transition 白名单。
- **transition 属性白名单**：`transform, box-shadow, border-color, background-color, color, opacity, filter, border-radius`。**禁**：`width/height/top/left/right/margin/padding`。
- 相邻可悬停元素之间留 ≥8px 物理间隔（或 hover 区域用 `::after` 外扩 4px 但不触发换行），避免指针在缝隙"抖动失焦"。
- 有内嵌交互的卡片：**hover 卡片特效只由外层触发一次**，内部按钮 hover 用 `pointer-events` 正常，但别让卡片:hover 与子:hover 互相"打架"（子元素不设同类 transform）。
- 触发区以元素 box 为准：卡片内容有空白 padding 属于 box 内，天然可触发，无需额外处理。
- 键盘可达性：所有 hover 效果同款映射到 `:focus-visible`（至少描边/辉光变化）。

---

## D. 果冻弹性动效规范（重点）

### D.1 弹性缓动曲线表（cubic-bezier 过冲族）

| 变量 | 曲线 | 过冲量级 | 用途 |
|---|---|---|---|
| `--ease-spring` | `cubic-bezier(.34,1.56,.64,1)` | ≈ 8–10%（明显一弹） | 按钮松手回弹、chip 出现、状态切换、小面积对象入场 |
| `--ease-spring-soft` | `cubic-bezier(.22,1.2,.36,1)` | ≈ 3–4%（克制轻弹） | 面板入场、指标数字变化、hover 微缩放 |
| 重弹（仅特殊强调位） | `cubic-bezier(.34,2,.4,1)` | ≈ 14–16%（慎用） | 0–1 个强调位（如成就达成、大状态翻转），全屏最多 1 处 |
| 按下（非弹性） | `cubic-bezier(.4,0,.6,1)` 100–120ms | 无 | 按钮/卡片 active 下压 |

**用法铁律**：
- 弹性曲线只作用于 **transform / opacity**；**box-shadow、filter、backdrop-filter 永不套弹性曲线**（会糊、会掉帧）。
- 一维过冲（cubic-bezier 超出 1）其实是对目标值越过的 1D 近似，本质上是"scale/translate 朝着目标走过头再回来"，等效果冻但**只压 x 或 y**；想要"扁+宽"的立体果冻用 D.2 的双轴 keyframes（squash & stretch）。
- 大面板用 soft，小对象用标准，宁可欠弹不要过弹。

### D.2 果冻关键帧（可直接复制，3 套 + 按压）

**① 弹入（pop-in）—— 卡片/chip/弹层首次挂载**，基准 420–500ms：

```css
@keyframes jelly-pop {
  0%   { transform: scale(.9); opacity: 0; }
  55%  { transform: scale(1.05); opacity: 1; }
  74%  { transform: scale(.98); }
  88%  { transform: scale(1.015); }
  100% { transform: scale(1); opacity: 1; }
}
.jelly-in { animation: jelly-pop 460ms var(--ease-spring-soft) both; }
```

**② 果冻挤压回弹（squash & stretch，体积守恒）** —— 单次状态翻转/开关/数字卡顿，520ms：

```css
@keyframes jelly-squash {
  0%   { transform: scale(1, 1); }
  30%  { transform: scale(1.08, .92); }   /* 横向拉伸时纵向压缩 */
  55%  { transform: scale(.94, 1.06); }   /* 纵向拉伸时横向压缩 */
  76%  { transform: scale(1.02, .98); }
  100% { transform: scale(1, 1); }
}
.jelly-squash { animation: jelly-squash 520ms var(--ease-out) both; }
```

> 体积守恒校验：`1.08 × .92 ≈ .994`、`.94 × 1.06 ≈ .996`，任一时刻两轴乘积 ≈ 1 → 看起来"是同一个物体在挤"，不是"变大变小"。scaleX/scaleY 只差 **4–8%**，超过 10% 就变卡通。

**③ 呼吸强调（小范围循环，默认关，仅手动开启）**：

```css
@keyframes jelly-breathe {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.04, .96); }
}
.jelly-breathe { animation: jelly-breathe 1.6s ease-in-out infinite; }
```

**④ 按压果冻（按钮/卡片）** —— 组合 CSS，无需 JS 区分按下/松手：

```css
.pressable { transition: transform .24s var(--ease-spring); }          /* 松手：弹性回弹 */
.pressable:active {
  transform: scale(.93);
  transition: transform .1s cubic-bezier(.4, 0, .6, 1);                /* 按下：快而直 */
}
```

时长规范：pop 类 **400–500ms**，squash 类 **500–600ms**，按压释放 **220–260ms**，hover 弹性 **150–240ms**。所有果冻首帧若要隐藏，用 `animation-fill-mode: both` + 0% opacity:0（注意仅在真正入场时使用，避免每次 rerun 闪白）。

**防呆（必读）**：
- 多元素入场要 **stagger**：相邻元素 `animation-delay: 40–80ms` 递增，同屏最多错开 8 个元素，超过就分组（先组后元素）。
- `transform-origin` 统一 `center`（横向生长的进度条除外，见 E-7 用 `left`）。
- 果冻元素上若必须挂毛玻璃，blur 用弱档且动画幅度收小（否则每次 squash 触发玻璃重采样）。

### D.3 适用清单与禁用清单

**✅ 适合果冻/弹性的地方**
- 页面首次加载的卡片入场（≤8 个，stagger）
- 按钮按下→松手回弹（最安全、最高频的使用点）
- 开关/切换钮（滑块到位 + 轻微 squash）
- 状态徽章变化（在线→离线翻转）
- 指标数字变化（换数字时的 1 次 pop，而非数值滚动）
- 列表新 chip / 标签增删
- 弹层/抽屉打开（整体 soft 弹入，注意单层 blur 预算）

**🚫 禁用**
- **数据轮询 2s 刷新区**（每 2 秒弹一次 = 视觉噪音 + 掉帧，见 D.4）
- 表格逐行动画 / 大面积图表重绘
- 背景粒子 / 背景光斑（粒子只能慢速漂移）
- **任何无限循环的大范围动画**（可循环的只有 ≤4% 幅度、≤1.6s 周期的小对象，且默认关闭）
- 带 backdrop-filter 大面积的元素做 transform 弹性动画
- `box-shadow` / `filter` / `width` 上套过冲曲线

**防误用全局开关：**

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
```

### D.4 Streamlit 落地建议（重点：防每 2 秒重播）

**注入方式（CSS keyframes 全部写进一段全局样式，首帧注入一次）**：

```python
import streamlit as st

@st.cache_data(show_spinner=False)
def _global_css() -> str:
    return open("assets/glass_cyber.css", encoding="utf-8").read()

st.markdown(f"<style>{_global_css()}</style>", unsafe_allow_html=True)
```

**机理（决定动画会不会重播）**：
1. Streamlit `st.rerun` 是 React 增量 patch：**内容和结构不变的 DOM 节点会保留**，不会重新挂载 → 已播完的 CSS animation 不会重播。
2. CSS animation 重播的三个触发：元素被重新插入 DOM、`animation-name`/class 变化、元素整体被替换。
3. 所以问题不出在"节点还在"的刷新上，而出在 **条件渲染导致子树卸载重建**（`if` 切换、`st.empty().container()` 每次新建、`@st.fragment` 结构变化）——这些场合动画会重播。

**防重播技巧（给具体做法）**：

```python
# 技巧 1：入场动画类只在首帧写进 HTML，之后不带该类 → 即使重建也不重播
if "booted" not in st.session_state:
    st.session_state.booted = True
    _cls = "jelly-in"
else:
    _cls = "steady"
st.markdown(
    f'<div class="glass-card {_cls}" style="border-radius:16px;padding:1rem">'
    f"指标标题</div>",
    unsafe_allow_html=True,
)
# 说明：steady 类上不定义 animation，.jelly-in 只在首帧出现。
# 若 Streamlit 保留了旧节点（大多数情况），动画首帧播一次后永不重播；
# 即使节点被重建，重建时带的是 steady，也不会播。
```

```python
# 技巧 2：2 秒轮询的局部区域用 fragment，且保持子树结构恒定
@st.fragment(run_every=2)
def poll_zone():
    # 永远渲染同一个外壳容器（固定 key、固定 HTML 结构），只更新里面文本
    st.metric("温度", f"{val:.1f}°C", delta=..., key="t_metric")
```

**轮询区规范**：
- 轮询区元素（卡片/指标）**一律不加入场动画类**；要提示"有更新"，只允许数字自身的 1 次 120ms `color→opacity` 闪烁（150ms 内，只动 opacity/color，不重排）。
- 轮询容器 **结构固定**：不要在每次轮询里先 `st.empty()` 再重建，改用 `st.metric`/固定 key 的组件让 React 走文本 patch。
- **纯 CSS 技巧的兜底承诺**：上述"类名由 session_state 控制 + 结构固定"两条同时满足时，无论 Streamlit 是保留节点还是重建节点，入场动画都只会播一次。这是不需要 JS 的可靠方案。
- 若把动画绑到交互态（hover/active/focus-within 上的 animation），天然每次交互播放一次、轮询不干扰——**按钮按压果冻就该这么绑**。

**选择器说明**：Streamlit 样式挂 `data-testid` 与 baseweb 类上（版本间有差异，以下为 1.3x–1.4x 常见值，**需在当前版本实测**）：

```css
[data-testid="stSidebar"] { background: var(--glass-bg-sidebar); ... }
[data-testid="stMetric"] { border-radius: var(--radius-lg); }
.stButton > button { border-radius: var(--radius-btn); }
[data-testid="stTextInput"] input { border-radius: var(--radius-md); }
button[data-baseweb="tab"] { border-radius: var(--radius-btn); }
[data-testid="stExpander"] { border-radius: var(--radius-lg); }
[data-testid="stAlert"] { border-radius: var(--radius-md); }
[data-testid="stProgressBar"], [role="progressbar"] { border-radius: var(--radius-full); }
```

> 用 `st.html()`（1.33+）比 `st.markdown(unsafe_allow_html=True)` 注入样式更干净，二选一即可。所有针对 Streamlit 内部 DOM 的选择器都写进"测试清单"逐条截图验证。

---

## E. 融合落地组件样式（8 个可直接复制块）

> 以下组件同时包含 **:root 新增 token** 与完整 CSS。Streamlit 落地时把 token 段合并到全局注入 CSS，组件段既可套在 `st.markdown(HTML)` 自制组件上，也可用 data-testid 选择器指向原生组件。

### E.0 本套组件需新增的 :root tokens（合并到既有 cyber 主题）

```css
:root {
  /* 圆角阶梯 */
  --radius-sm:8px; --radius-btn:10px; --radius-md:12px; --radius-lg:16px;
  --radius-xl:20px; --radius-2xl:24px; --radius-full:999px;
  /* 玻璃 */
  --glass-bg-card:rgba(12,17,30,.50); --glass-bg-sidebar:rgba(9,13,24,.64);
  --glass-bg-modal:rgba(8,12,22,.80); --glass-bg-popover:rgba(18,24,40,.86);
  --glass-bg-input:rgba(255,255,255,.045); --glass-bg-chip:rgba(30,38,58,.55);
  --glass-blur-strong:blur(32px) saturate(160%) brightness(1.06);
  --glass-blur-md:blur(18px) saturate(150%) brightness(1.04);
  --glass-blur-weak:blur(9px) saturate(140%) brightness(1.02);
  /* 缓动与时长 */
  --ease-spring:cubic-bezier(.34,1.56,.64,1);
  --ease-spring-soft:cubic-bezier(.22,1.2,.36,1);
  --ease-out:cubic-bezier(.16,1,.3,1);
  --dur-1:.15s; --dur-2:.2s; --dur-3:.3s;
  /* 阴影 / 辉光 */
  --shadow-glass-sm:0 1px 2px rgba(0,0,0,.25), 0 4px 12px rgba(0,0,0,.18);
  --shadow-glass-md:0 2px 8px rgba(0,0,0,.22), 0 12px 32px rgba(0,0,0,.30);
  --shadow-glass-lg:0 8px 24px rgba(0,0,0,.30), 0 24px 64px rgba(0,0,0,.45);
  --glow-cyan-sm:0 0 10px rgba(0,240,255,.25);
  --glow-magenta-sm:0 0 10px rgba(255,42,109,.28);
}
```

### E-1 玻璃卡片（圆角 16 + hover 果冻轻弹）

```css
.glass-card {
  border-radius: var(--radius-lg);
  background: var(--glass-bg-card);
  -webkit-backdrop-filter: var(--glass-blur-md);
  backdrop-filter: var(--glass-blur-md);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), var(--shadow-glass-sm);
  transition: transform .24s var(--ease-spring-soft), box-shadow var(--dur-2) var(--ease-out),
              border-color var(--dur-1) var(--ease-out);
}
.glass-card:hover {
  transform: translateY(-3px) scale(1.015);
  border-color: rgba(0,240,255,.45);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.1), var(--shadow-glass-md), var(--glow-cyan-sm);
}
.glass-card:active { transform: translateY(-1px) scale(.99); }
.glass-card.is-enter { animation: jelly-pop 480ms var(--ease-spring-soft) both; } /* 见 D.2 */
```

### E-2 霓虹玻璃按钮（主 / 次 / 危险）

```css
.btn-glass {
  position: relative;
  border-radius: var(--radius-btn);
  padding: .55em 1.35em;
  font-weight: 600; letter-spacing: .02em;
  border: 1px solid rgba(255,255,255,.14);
  background: rgba(255,255,255,.05);
  color: var(--ink-hi);
  transition: transform .22s var(--ease-spring), background-color var(--dur-1) var(--ease-out),
              box-shadow var(--dur-2) var(--ease-out), border-color var(--dur-1), color var(--dur-1);
  cursor: pointer;
}
.btn-glass:hover  { transform: translateY(-2px); background: rgba(255,255,255,.09); }
.btn-glass:active { transform: scale(.93); transition: transform .1s cubic-bezier(.4,0,.6,1); }

.btn-primary {
  border-color: rgba(0,240,255,.55); color: #bdf8ff;
  background: rgba(0,240,255,.08);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.1);
}
.btn-primary:hover {
  border-color: var(--neon-cyan); background: rgba(0,240,255,.16);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.12), 0 0 20px rgba(0,240,255,.3);
}
.btn-danger {
  border-color: rgba(255,42,109,.55); color: #ffd7e2;
  background: rgba(255,42,109,.08);
}
.btn-danger:hover {
  border-color: var(--neon-magenta); background: rgba(255,42,109,.16);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.1), 0 0 20px rgba(255,42,109,.28);
}
/* 次按钮 hover 用描边提亮代替填色，安静 */
.btn-ghost:hover { border-color: rgba(255,255,255,.32); color:#fff; }
```

### E-3 圆润输入

```css
.field-glass {
  border-radius: var(--radius-md);
  border: 1px solid rgba(255,255,255,.14);
  background: var(--glass-bg-input);
  padding: .5em .85em;
  color: var(--ink-hi);
  caret-color: var(--neon-cyan);
  transition: border-color var(--dur-1), box-shadow var(--dur-2) var(--ease-out),
              background-color var(--dur-1);
}
.field-glass:hover  { border-color: rgba(255,255,255,.28); }
.field-glass:focus,
.field-glass:focus-visible {
  outline: none;
  border-color: rgba(0,240,255,.7);
  background: rgba(8,14,26,.85);
  box-shadow: 0 0 0 3px rgba(0,240,255,.16), 0 0 16px rgba(0,240,255,.14);
}
.field-glass::placeholder { color: var(--ink-low); }
```

### E-4 玻璃 Tab

```css
.glass-tabs { display:flex; gap:4px; padding:4px;
  border-radius: var(--radius-btn); background: var(--glass-bg-input);
  border:1px solid rgba(255,255,255,.06); }
.glass-tab {
  border:0; background:transparent; color:var(--ink-mid);
  padding:.45em 1.1em; border-radius: 8px;
  transition: background-color var(--dur-1), color var(--dur-1), box-shadow var(--dur-2);
  cursor:pointer;
}
.glass-tab:hover  { color:#fff; background: rgba(255,255,255,.06); }
.glass-tab.is-active {
  color:#bdf8ff; background: rgba(0,240,255,.12);
  box-shadow: inset 0 0 0 1px rgba(0,240,255,.3), 0 0 12px rgba(0,240,255,.12);
}
```

### E-5 指标卡玻璃（数值走 tabular-nums 防抖动）

```css
.metric-glass {
  border-radius: var(--radius-lg);
  background: var(--glass-bg-card);
  -webkit-backdrop-filter: var(--glass-blur-weak);
  backdrop-filter: var(--glass-blur-weak);
  border: 1px solid rgba(255,255,255,.08);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08), var(--shadow-glass-sm);
  padding: 1.1em 1.3em;
  transition: transform var(--dur-2) var(--ease-out), box-shadow var(--dur-2) var(--ease-out);
}
.metric-glass:hover { transform: translateY(-2px); box-shadow: var(--shadow-glass-md), 0 0 0 1px rgba(0,240,255,.18); }
.metric-glass .value { font-size: 1.9rem; font-weight: 700; font-variant-numeric: tabular-nums;
  color: var(--ink-hi); text-shadow: 0 0 14px rgba(0,240,255,.25); }
.metric-glass .delta-up   { color: var(--neon-cyan); }
.metric-glass .delta-down { color: var(--neon-magenta); }
/* 数值变化时整卡轻弹一次：由 D.4 的“值更新仅对值容器打一次 class”控制，轮询区禁用 */
```

### E-6 状态徽章玻璃

```css
.badge-glass {
  display:inline-flex; align-items:center; gap:.45em;
  border-radius: var(--radius-full);
  padding: .22em .85em;
  background: var(--glass-bg-chip);
  border: 1px solid rgba(255,255,255,.12);
  color: var(--ink-mid); font-size: .82em;
  -webkit-backdrop-filter: var(--glass-blur-weak);
  backdrop-filter: var(--glass-blur-weak);
}
.badge-glass .dot { width:7px; height:7px; border-radius:50%; }
.badge-glass.ok    .dot { background: var(--neon-cyan);  box-shadow: 0 0 8px rgba(0,240,255,.9); }
.badge-glass.warn  .dot { background: var(--neon-yellow); box-shadow: 0 0 8px rgba(255,206,0,.8); }
.badge-glass.crit  .dot { background: var(--neon-magenta); box-shadow: 0 0 8px rgba(255,42,109,.9); }
.badge-glass.crit  { border-color: rgba(255,42,109,.35); color:#ffd7e2; }
/* 状态切换时给徽章加 jelly-squash 520ms（D.2）播放一次 */
```

### E-7 进度条（圆角胶囊 + 弹性填充）

```css
.progress-glass {
  height: 10px; border-radius: var(--radius-full);
  background: rgba(255,255,255,.07);
  border: 1px solid rgba(255,255,255,.06);
  box-shadow: inset 0 1px 3px rgba(0,0,0,.5);
  overflow: hidden;
}
.progress-glass .bar {
  height:100%; width: var(--p, 0%);
  border-radius: var(--radius-full);
  background: linear-gradient(90deg, rgba(0,240,255,.9), rgba(255,42,109,.85));
  box-shadow: 0 0 12px rgba(0,240,255,.45);
  transform-origin: left center;
  transition: width .6s var(--ease-out);
}
/* 首次填充弹入：宽不参与弹性动画，用 scaleX 做果冻（只动 transform） */
.progress-glass .bar.is-enter { animation: bar-grow 600ms var(--ease-spring-soft) both; }
@keyframes bar-grow {
  0%   { transform: scaleX(0); }
  62%  { transform: scaleX(1.06); }
  82%  { transform: scaleX(.97); }
  100% { transform: scaleX(1); }
}
```

### E-8 步骤节点圆形化（圆环霓虹）

```css
.step-node {
  width: 44px; height: 44px; border-radius: 50%;
  display:grid; place-items:center;
  border: 1px solid rgba(255,255,255,.18);
  background: rgba(255,255,255,.04);
  color: var(--ink-mid); font-weight:700;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.08);
  transition: transform .2s var(--ease-spring-soft), border-color var(--dur-1), box-shadow var(--dur-2);
}
.step-node.done {
  border-color: rgba(0,240,255,.6); color:#06121a;
  background: linear-gradient(135deg, #00f0ff, #00c8d6);
  box-shadow: 0 0 16px rgba(0,240,255,.45);
}
.step-node.active {
  border-color: rgba(255,206,0,.7); color: var(--neon-yellow);
  background: rgba(255,206,0,.10);
  box-shadow: 0 0 0 5px rgba(255,206,0,.10), 0 0 18px rgba(255,206,0,.30);
}
.step-node:hover { transform: scale(1.06); }
/* 连接线（两节点之间）用霓虹渐变细线 + 直角端点，承担“锐利 accent” */
.step-link { height:2px; flex:1; min-width:24px;
  background: linear-gradient(90deg, rgba(0,240,255,.8), rgba(255,42,109,.5)); }
```

### E-9（赠品）输入建议浮层 / popover

```css
.suggest-glass {
  border-radius: var(--radius-md);
  background: var(--glass-bg-popover);
  -webkit-backdrop-filter: var(--glass-blur-weak);
  backdrop-filter: var(--glass-blur-weak);
  border: 1px solid rgba(255,255,255,.10);
  box-shadow: var(--shadow-glass-md);
  padding: .35em;
}
.suggest-glass .item { padding:.45em .7em; border-radius:8px; color:var(--ink-mid); cursor:pointer;
  transition: background-color var(--dur-1), color var(--dur-1); }
.suggest-glass .item:hover,
.suggest-glass .item.is-active { background: rgba(0,240,255,.10); color:#bdf8ff; }
```

### E-10 完整降级 + 无障碍收尾（全局粘贴段）

```css
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass-card, .metric-glass, .glass-card--neon, [data-testid="stSidebar"] {
    background: rgba(10,14,24,.92) !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
/* 大屏高刷可放开弹性幅度；小屏/低配用类名收紧（手动开关） */
html.reduce-glass [data-testid="stSidebar"],
html.reduce-glass .glass-card,
html.reduce-glass .metric-glass { backdrop-filter: none; }
```

---

## F. 参考来源 URL 列表（需复核）

本次运行**未联网**，下列 URL 来自内置知识，属"记忆来源"，**使用前必须复核可达性与内容**：

**Glassmorphism / backdrop-filter**
- glassmorphism.com — CSS 玻璃生成器与参数组合参考（需复核当前是否在线）
- MDN: `backdrop-filter` — https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter （语法、浏览器兼容、性能注意事项）
- MDN: `filter` / `will-change` — 合成层与性能说明
- Can I Use: `backdrop-filter` — https://caniuse.com/css-backdrop-filter （确认 Win 端 Chrome/Edge/Safari 覆盖）
- CSS-Tricks: "backdrop-filter: it's getting pretty" 及 glassmorphism 相关文章（URL 需搜索复核）

**弹性缓动 / 果冻**
- https://cubic-bezier.com （Lea Verou 曲线调试）
- https://easings.net — easeOutBack / easeOutElastic 数值对照（本规范 spring 曲线即其近似）
- Framer Motion 文档 "Animation / springs"（spring 物理参数 → cubic-bezier 近似参考）

**动画性能 / 无障碍**
- web.dev: "Animations and performance" / "prefers-reduced-motion: sometimes less is more"（复合层属性白名单依据）
- MDN: `prefers-reduced-motion`

**视觉风向（glass dashboard / jelly UI 检索入口）**
- https://dribbble.com/search/glassmorphism-dashboard
- https://www.awwwards.com/websites/glassmorphism/
- https://dribbble.com/search/jelly-ui (jelly 动效风格参考)
- Linear / Vercel / Apple 官网暗色玻璃感组件截图（自行抓取，不作外链）

---

## 验收清单（建议放进工程 PR 模板）

- [ ] 同屏大毛玻璃面 ≤3；无嵌套 backdrop-filter ≥2 层
- [ ] 无 backdrop-filter 设备实测降级路径（@supports 段生效、文字可读）
- [ ] RDP/远程桌面 + 集显各跑一遍 60fps（DevTools Performance 抽查 3s 轮询区间）
- [ ] 2s 轮询区无入场动画重播（用 session_state 类名技巧验证）
- [ ] `prefers-reduced-motion: reduce` 下无动画
- [ ] 所有 hover 态有 `:focus-visible` 等价物
- [ ] transition 白名单内无布局属性
- [ ] 锐利 accent ≤3 处/屏，其余全圆角化
- [ ] Streamlit 选择器在当前版本逐条截图核对

## 已知缺口
- 未联网核验 F 节 URL 与 backdrop-filter 在"当前 Windows 浏览器 + RDP"下的真实行为（数值红线基于经验而非本机基准，建议在目标机跑一次 3-blur-card 掉帧测试再定稿强/中/弱档位）。
- Streamlit DOM 选择器版本敏感（本规范标注 1.3x–1.4x 常见值），需在应用实际版本上核对。
- 数值弹跳的"舒适度"取决于内容密度与刷新频率，建议在真实数据流下 A/B 两版（soft vs 标准 spring）再固化。
