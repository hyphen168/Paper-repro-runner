# 视觉系统重设计规范 v2 —— 布局节奏 · 全主题明暗氛围 · 控制台气场

> 基线：paper_repro_app（Streamlit 本地控制端，Windows/Edge 桌面，8505）。全部数值以 4px 栅格为基准，遵循硬约束：无 emoji、深色赛博基因保留、重度玻璃 blur ≤3 块、2s 轮询区零重放动画、无新框架、中文 UI。
> 本规范分「决策」（为何这样做）与「可执行变更」（直接抄用）。

## 决策

**D1 · 明暗即"氛围变量面"，不再是背景单变量。** 现状 `day_night.py` 已生成 13 个采样变量（`sky_top/mid/hor`、`day_factor`、`glow_c/m/y`、`card_alpha/bright`、`star_alpha`…），但 `app.py` 首帧与 60s tick 只注入 `--bg-color` 一个变量——这是"明暗只作用于背景"的根因。决策：改为注入"整块氛围变量"，在 `:root` 中用派生语义 token 把氛围接到每一类组件上：玻璃底色、描边、辉光强度、输入凹区、文字对比全部引用 `--amb-*`。这样阴天/雨天（天气系数压暗）与夜晚（昼夜因子走低）会让整站"变沉"，晴昼则整体"变通透"，而非只有背景在动。氛围变化频率 60s、无动画，与性能预算不冲突。

**D2 · 玻璃层次要分级配给，而不是每块卡片都 blur。** 性能预算只许 3 块重度玻璃（大 blur），故按"信息停留时长"配给：侧边栏（常驻）1 块、监控页步进主面板 1 块、实时日志面板 1 块（人眼停留最久，需玻璃质感）；其余面板一律"半透明实色 + 1px 描边 + 极弱 8px blur 或 0 blur"。提交表单页的多个 expander/container 全部走 0 blur 实色半透明层，视觉仍统一，帧率不塌。

**D3 · 密度面向宽屏桌面，做"留白呼吸"而非堆满。** 现 `block-container padding-top:0.7rem`（≈11px）过挤：头部与首屏内容贴死，玻璃卡之间也无段落感。桌面 1440–1920 应走宽松密度：主区顶部 ≥20px、卡片间距 ≥20px、卡片内距 ≥16px、区块间隔 ≥24px。表格区（遥测/日志）可适度收紧到 12–14px 级，形成"外围透气、内部精密"的控制台节奏。

**D4 · 轮询区"静态辉光 + 时间跳动"，禁止 infinite keyframe。** 现 `.live-dot`（`badgePulse`）与 `.fx-step.active .node`（`nodePulse`）都是 infinite 动画，而它们恰好渲染在 2s fragment 重挂载的 DOM 上——每 2s 重挂载即重放一次，表现为轻微"闪烁/卡拍"。决策：轮询区运行态一律改为静态径向辉光（多层 box-shadow）表达"活着"，"变化感"由时间文案（已执行 N 分 N 秒）承担。果冻 keyframe 只允许出现在非轮询的首帧区域（如提交成功 toast）。

**D5 · 无 emoji 严格化。** 巡检发现两处违规：监控页 `label_map` 中 `⛔ 执行失败`、`⏹ 已结束`。状态一律以"色点 + 文案"或"左侧色轨"表达，禁用任何 pictograph/emoji 字形（含 dingbat ✔/✕）。天气 chip 现有"色点 + 温度 + 城市"已合规，保留。

**D6 · 收敛 accent 用量，突出"仪表化"秩序。** 青 `#00f0ff` 为信息主色（标题、激活、数据）；黄 `#ffce00` 只给"当前进行"（active 步、主行动按钮）；品红 `#ff2a6d` 降级为点缀色，只出现在：Tab 激活指示条右端、顶部 hairline 右端、错误描边。每屏同框霓虹色 ≤3 处，其余靠 alpha 分层。

**D7 · 可读性优先。** 正文主文字对比度 ≥7:1（`#c9d8ee` on `#0a1120` 达标）；玻璃下文字永不透明化到 <0.72 等效；强调数据一律 `font-variant-numeric: tabular-nums`（等宽数字），日志区 `mono 12.5px` 是下限，不再减小。

**D8 · 中文 UI 的字体栈纪律。** 标题 `--font-display`（Bahnschrift 拉丁 + 中文回退 Microsoft YaHei UI Bold，`font-weight:600–700`）；正文 `--font-body`（Segoe UI / Microsoft YaHei UI）；所有机器标签、数值、日志 `--font-mono`（Cascadia Mono/Consolas）。汉字不做 uppercase/letter-spacing 拉伸，拉丁与代码才用 `0.08–0.3em` 字距。

## 可执行变更

### 0. 明暗全主题：注入与派生（先做这一步，其余视觉才成立）

改动点 1（Python，`app.py` 两处 `st.markdown(f"<style>:root{{ --bg-color… }}")` 均替换为整块注入）：

```python
def theme_css_block(kind: str, prev=None) -> str:
    v = weather_tint(now_day_night_vars(prev=prev), kind)   # 天空色被天气压灰
    v["bg_color"] = bg_color_for(kind, v["day_factor"])
    return css_vars_block(v) + _amb_block(v)

def _amb_block(v):
    df = v["day_factor"]                       # 0 深宵 … 1 正午
    # 辉光系数：白天收敛防泛白、夜晚放开
    return ("<style>:root{"
      f"--amb-glass:rgba({_mix_to_rgb('#101a30','#2b3b5e',df)},0.50);"
      f"--amb-inset:rgba({_mix_to_rgb('#070b16','#16213a',df)},0.85);"
      f"--amb-hairline:rgba({_mix_to_rgb('#00f0ff','#335',df)},0.5);"
      f"--amb-glow-cyan:{0.30+0.70*v['glow_c']:.2f};"
      f"--amb-stroke-a:{0.08+0.06*df:.2f};"
      f"--amb-text-dim:{0.42+0.20*df:.2f};"
      "}</style>")
```

改动点 2（`ui_theme.py` `:root` 增默认值与替换硬编码引用，注入缺席时兜底不崩）：

```css
:root{
  --amb-glass:rgba(16,26,48,0.50); --amb-inset:rgba(6,10,18,0.9);
  --amb-glow-cyan:0.8; --amb-stroke-a:0.1; --amb-text-dim:0.5;
}
.panel{ background:
  linear-gradient(180deg, rgba(255,255,255,calc(0.045*var(--amb-glow-cyan,0.8))), transparent 34%),
  var(--amb-glass, rgba(16,26,48,0.5)); }
.telemetry-log{ background:var(--amb-inset); border-left-color:rgba(0,240,255,calc(0.55*var(--amb-glow-cyan,0.8))); }
.panel-title, h1, .weather-chip .dot-mark{ text-shadow:0 0 10px rgba(0,240,255,calc(0.5*var(--amb-glow-cyan,0.8))); }
.stCaption,.fresh-sub,.mini-title{ color:rgba(143,163,199,var(--amb-text-dim,0.5)); }
```

效果量化：深夜 `glow_c=0.85` → 辉光与青字最亮、玻璃最沉；正午 `glow_c=0.30` → 辉光减 65%、玻璃底色抬升向 `#2b3b5e`，画面"日间通透"；雨天 `day_factor` 被天气系数压到 ~0.6 以下 → 卡片实度上升、描边变暗，呼应窗外。**约束核对：只替换数值，无动画、无 blur 增量，60s 一次注入。**

### 1. 间距节奏（px 数值表，4px 栅格）

| 场景 | 现值 | 目标 | 说明 |
|---|---|---|---|
| `block-container` padding-top | 0.7rem≈11px | **1.25rem=20px** | 现过挤，头部与内容贴死 |
| 同 padding 左右 / 底部 | 默认 / 2.5rem | 1.5rem=24px / 3rem=48px | 左右留白供粒子呼吸 |
| `block-container` max-width | 1500px | **1440px** | 中线信息、两侧见背景，长行更短 |
| 卡片之间垂直间距 | 0.45–1rem 混杂 | **统一 20px（1.25rem）** | 监控/历史两处 inline `margin` 一并改 |
| `.panel` 内距 | 16px | **20px（1.25rem）** | 正文/日志外圈留白 |
| `.floating-card` / 子面板 | 13–15px | **16px** | 次层卡片 |
| 卡片内分组标题到内容 | — | 标题下 12px、分隔线上下 8px | 用 hairline 而非空行分段 |
| 表单：行内两列 gap | Streamlit 默认 | **16px** | `st.columns` gap |
| 表单：纵向相邻控件 | 默认 1rem | **14px** | 组内紧凑、组间 24px 拉开 |
| 日志区 | padding 11px | **12px 14px**，max-height 340px | 密度最高的精密区 |
| 目录列表 | — | 行高 1.9、`li` 间距 4px | 次级文本可密 |
| 头部下缘到 hairline | 0 | **18px** | 呼吸分隔 |

页面纵向节奏总则：**头部 20px 呼吸 → 1px 渐变 hairline → 18px → 内容区（卡片间距 20px）→ 底部 48px**。提交表单区内建议"外疏内密"：卡与卡 24px，卡内控件 14px。

### 2. 层级体系（完整字阶）

| 角色 | 字号/行高 | 字重 | 颜色 | 用途 |
|---|---|---|---|---|
| Kicker 系统行 | 11px mono / 1.6 | 600 | `--cyan` 发光 | 顶行"PAPER REPRO RUNNER" |
| H1 页头主标 | clamp(1.9rem,3.2vw,2.5rem) | **700** | `#eaf6ff` | 论文复现助手 |
| H1 副题 | 0.92rem | 400 | `#8fa3c7` | fresh-sub 一句话定位 |
| H3 区块标题 | 20px / 1.3 | 600 | `#dcebff` | st.subheader「复现流水线」 |
| H4/H5 卡片与分组标题 | 16px / 14px | 600 | `#cfe0f5` / `#b7c9e6` | 表单卡片、`#####` 组 |
| panel-title（机器条） | 0.75rem mono | 600 | `--cyan` | 面板英文/短标题，全大写 0.14em |
| 正文 | 15px / 1.7 | 400 | `--text-primary #c9d8ee` | 说明文字 |
| 次要文本 | 13px | 400 | `#8fa3c7` | help、占位、meta-pill |
| 辅助/禁用 | 12px | 400 | `#5c6f96` | caption、时间戳、次要状态 |
| 等宽标签 | 0.64–0.68rem mono | 600 | `--text-muted` | telemetry-label、mini-title |
| 数据值 | 15px mono | 600 | `--cyan` | telemetry-metric strong |
| 大指标值 | 30px display | 600 | `--cyan` | st.metric 数值 |

规则：字号阶梯 12/13/14/15/16/20 + 页头大号，不设中间杂值；同屏粗体（>600）数量 ≤8 处；"机器感"靠 mono + 字距，不靠斜体与下划线。

### 3. 头部 redesign（控制台仪表条，HTML 骨架）

保留 `.fresh-header` 外层类名，内部改三区（左品牌 / 中呼吸分隔 / 右状态群），把天气 chip 从"孤悬右上"升级为与"运行状态、时钟"成组的仪表条：

```html
<div class="fresh-header">
  <div class="hud-brand">
    <div class="fresh-kicker">PAPER-REPRO-RUNNER // LOCAL-CONTROL</div>
    <h1 class="hud-title">论文复现助手</h1>
    <div class="fresh-sub">本地控制端 · 云端执行器 · SSH 加密通道</div>
  </div>
  <div class="hud-spacer"></div>                     <!-- 弹性留白，横向细刻度装饰 -->
  <div class="hud-status">
    <div class="weather-chip"><span class="dot-mark"></span>中雨 14°C · 上海</div>
    <div class="sys-pill idle"><span class="status-dot"></span>云端空闲</div>
    <div class="clock-chip">14:32</div>
  </div>
</div>
```

配套 CSS（数值）：

```css
.hud-status{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.sys-pill,.clock-chip{
  display:inline-flex; align-items:center; gap:8px; height:34px; padding:0 14px;
  font-family:var(--font-mono); font-size:0.74rem; letter-spacing:0.1em;
  border-radius:var(--radius-full); color:#c9f8ff;
  background:rgba(16,23,40,0.55); border:1px solid rgba(255,255,255,0.1);
  box-shadow:inset 0 1px 0 rgba(255,255,255,0.08);
}
.sys-pill.idle .status-dot{ background:var(--green); box-shadow:0 0 8px var(--green); } /* 静态辉光 */
.sys-pill.busy .status-dot{ background:var(--cyan); box-shadow:0 0 0 4px rgba(0,240,255,0.14),0 0 10px var(--cyan); }
.hud-spacer{ flex:1; min-width:24px;
  background:repeating-linear-gradient(90deg,rgba(0,240,255,0.10) 0 1px,transparent 1px 6px);
  height:1px; align-self:center; }
.fresh-header{ padding:1.0rem 0.4rem 1.1rem; }      /* 现 0.5/0.1 → 抬高呼吸 */
```

头部下方接一条 1px 渐变 hairline（`transparent → cyan0.5 → magenta0.35 → transparent`），18px 后再进轮播条与 Tabs。时钟为服务端渲染（每 60s 随昼夜 tick 自然更新一次，不进 2s 轮询），忙态 `sys-pill.busy` 文案由渲染端按任务状态切换为「执行中 · 已执行 N 分」。**气场来源 = 右区三件等高的 mono 胶囊 + 左区大标题的静默对比，不靠加大字号。**

### 4. 卡片内容排布

**监控页（Tab 2）——推荐"12 列两行格"：**
- 行 1：步进主面板（唯一重度玻璃，占满 12 列）：panel-title「复现流程监控」+ `fx-stepper` + `fx-stepper-meta`，padding 20px。
- 行 2：`grid-template-columns:minmax(260px,4fr) minmax(420px,8fr); gap:20px`。
  - 左 4fr：遥测 2×2 格（`telemetry-grid` 维持 2 列、格高自动）+ 折叠「本地目录结构」为 2 行内联 code 行（现 `li` 全宽铺开占高，改为一行两段截断）。
  - 右 8fr：实时日志 `telemetry-log`，max-height 340px。
- 比例依据：日志是人眼主战场（8fr），指标是扫读（4fr）；宽 <1100px 自动降为单列。

**提交页（Tab 1）——方案 A（推荐）："三段编号 + 底部 CTA 坞"。**
- 组 01「论文与代码仓库」：卡片顶 `01` mono 角标（CJK 前导序号，非 emoji）+ 卡片标题。
- 组 02「云服务器 SSH」：行排布改为两行四列控件的 12 列栅格：行一 = 服务器地址 7 + 端口 2 + 用户名 3；行二 = 密码 6 + SSH 连接串 6（连接串提示词自动解析，不抢宽度）。
- 组 03「运行方式」：横向 radio 改四枚分段胶囊（等宽，高 40px，激活项青色玻璃底 + 内侧 1px 发光描边）；tune 面板内嵌为实色子层。
- 底部 CTA 坞：玻璃坞（0 blur 实色 + 顶部 hairline，sticky bottom 8px），主按钮固定 280px 右对齐——现"黄色全宽按钮"在 1440 下过满，压成坞内右置更接近"控制台确认"气质。
- 高级/密钥两个 expander 标题前加 mono 序号 04/05，间距 24px。

**方案 B（省改版，保底）：** 仅做两件事——容器由 `st.container(border=True)` 换成自定义 `.panel`（统一 20px/16px 圆角/顶部 hairline），并把 CTA 上方 `st.markdown("---")` 换成 12px 渐变 hairline。改动量最小，先交付再叠 A。

### 5. Tab / 导航细节

```css
.stTabs [data-baseweb="tab-list"]{
  border-bottom:0; gap:6px; padding:6px;
  background:rgba(12,17,30,0.5);            /* 0 blur 实色胶囊条，非每格玻璃 */
  border:1px solid rgba(255,255,255,0.07); border-radius:14px;
  backdrop-filter:none !important;          /* 不占玻璃预算 */
}
.stTabs [data-baseweb="tab"]{
  min-height:40px; padding:8px 20px; border-radius:10px;
  font-size:13px; font-weight:500; letter-spacing:0.1em;
  color:var(--text-muted); transition:color .15s, background-color .15s, box-shadow .2s;
}
.stTabs [data-baseweb="tab"]:hover{ color:#eaf6ff; background:rgba(255,255,255,0.05); }
.stTabs [aria-selected="true"]{
  color:#eaf6ff !important; font-weight:600 !important;
  background:linear-gradient(180deg,rgba(0,240,255,0.16),rgba(0,240,255,0.05)) !important;
  box-shadow: inset 0 -2px 0 rgba(0,240,255,0.9),           /* 2px 底指示条 */
              inset 0 0 0 1px rgba(0,240,255,0.28),
              0 0 14px rgba(0,240,255,0.10) !important;
}
```

激活态 = "底条 + 淡青玻璃底"，与 D6 一致（品红仅出现在最右 Tab 激活底条可选的 `linear-gradient(90deg,cyan 0 70%,magenta 100%)` 末端）。`st.tabs` 文案可带序号（"01 提交任务"等）强化仪表感；分隔线：胶囊条与内容之间 16px，不另画线。

### 6. 空态 / 进行中 / 完成态

统一"状态块"组件（三态同构，只有轨色与文案不同），替换裸 `st.info/warning/success` 观感：

```css
.state-rail{ position:relative; border-radius:12px; padding:14px 18px 14px 20px;
  background:rgba(255,255,255,0.03); border:1px solid var(--stroke);
  border-left:3px solid var(--rail,var(--cyan)); font-size:14px; line-height:1.7; }
.state-empty{ border-style:dashed; --rail:#5c6f96; color:var(--text-secondary); text-align:center;
  padding:36px 20px; display:grid; gap:8px; place-items:center; }
.state-empty .state-cta{ height:34px; padding:0 18px; border-radius:10px; font-size:13px;
  background:rgba(0,240,255,0.1); border:1px solid rgba(0,240,255,0.4); color:#c9f8ff; }
```

| 状态 | 轨色 rail | 说明（数值化） |
|---|---|---|
| 空态（无任务/历史空） | `--rail:#5c6f96` | dashed 描边、垂直居中、min-height 160px；文案 14px 灰青 + 一个"前往提交"胶囊按钮（34px 高）；历史页同构 |
| 排队 queued | `--rail:#ffce00` | 实线态块 + 黄点；提示"队列等待自动执行" |
| 运行 running | `--rail:#00f0ff` | **静态**辉光点 + `已执行 N 分 N 秒` 文案每 2s 变；步进 active 节点用 `box-shadow:0 0 0 5px rgba(255,206,0,.12),0 0 16px rgba(255,206,0,.3)` 替掉 `nodePulse`；`.live-dot` 同法去掉 animation 保留辉光 |
| 成功 success | `--rail:#00ffa3` | 完成态主块 + 指标卡；文案"已完成 · 用时 xx:xx"，不用对勾字形 |
| 失败 failed | `--rail:#ff2b4a` | 主块下接诊断 expander；错误摘要等宽 13px、行高 1.8 |
| 取消 cancelled | `--rail:#5c6f96` | 灰轨 + 灰点，弱化存在感 |

同时把 Streamlit 原生告警整体驯化到玻璃语汇（提交页多处 `st.error/warning/success/info` 会沿用）：`[data-testid="stAlert"]` 背景 `rgba(255,255,255,0.03)`、`border:1px solid var(--stroke)`、左侧 3px 轨按类型取色、内边距 12px 16px、图标保留官方 SVG（非 emoji）但降饱和。状态表达顺序一律 **色 → 字 → 区块**，禁止引入任何 pictograph。

---

### 附：实施顺序与回归清单

1. 注入整块氛围变量（改动点 0）→ 2. 头部 + hairline + Tabs 胶囊条 → 3. 监控页 4/8 分栏与步进静态辉光 → 4. 提交页三组与 CTA 坞 → 5. 状态块替换裸提示。回归核对：2s 轮询 Tab 切到监控再切走，观察无 keyframe 重放闪烁；Edge 窗口缩放至 1280 与 1680 两档检查分栏断点；昼夜手工预览（侧栏 weather preview）确认文字对比度全程 ≥7:1；玻璃预算清点（侧栏 + 步进面板 + 日志面板 = 3 块重度 blur，其余 0 blur 实色）。
