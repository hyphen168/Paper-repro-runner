## Review（UI 专家组·审计官审查报告）

**审查范围**：`ui_theme.py` 全部 APP_CSS、`app.py` 所有 st.markdown/组件注入点、`weather_fx.py` chip/预览、`day_night.py` 输出面，并对照 pinned 运行时 `.venv` 内 Streamlit 1.62.0 前端产物与 `tests/test_ui_weather.py` 约束。
**正确且应保留**：玻璃三色阶、`.panel::before` 顶部描光、`:focus-visible` 辉光、`@supports` 兜底、`prefers-reduced-motion`、`font-variant-numeric` 等设计与防御本身是完整的；下述问题不推翻基因。

---

### 0）先报 5 条最硬的问题（有直接证据）

**P1-1 两大组件族的全部自定义 CSS 在当前运行时是死代码。** 证据：`.venv/Lib/site-packages/streamlit/static/static/js/` 全量 bundle 中 `data-baseweb`/`baseweb` **0 匹配**（已二次全目录核查）。即 ui_theme.py:297-303（`.stSelectbox/.stMultiSelect [data-baseweb="select"] > div` 与 listbox）与 306-320（`.stTabs [data-baseweb="tab-list"]`、`[data-baseweb="tab"]`）在 Streamlit 1.62 不会命中任何元素 → **selectbox/多选/下拉浮层/整条 Tab 栏全部裸露为原生深色样式**（灰底、圆角 4-6px、无描光），与玻璃霓虹体系割裂是当前"廉价感"第一大来源。最小修复：删除这 5 条死选择器，改为 1.62 实测的 `data-testid`（Selectbox 用 `[data-testid="stSelectbox"]` 容器锚定 + `input[role="combobox"]`/浮层 `[data-testid="stSelectboxPortal"]`；Tabs 用 `[data-testid="stTabs"] button[role="tab"]`，激活态改用 `[aria-selected="true"]`），属性值照抄现 CSS（`border-radius: var(--radius-md); background: rgba(255,255,255,0.045); border:1px solid rgba(255,255,255,0.14)`）。改动前务必 Edge F12 复核一次实际类名。

**P1-2 引用未定义变量 `--amber`/`--muted`。** `:root`（ui_theme.py:12-66）只定义了 `--red/--yellow/--cyan/...`，无 `--amber`、`--muted`；但 app.py:200/204-206/218-219/949-951 共 9 处 `color: var(--muted)`、`var(--amber)`。CSS 未定义变量使声明在计算值阶段失效 → 全部回退继承 `--text-primary` 亮蓝（#c9d8ee），导致"当前步骤/已结束/状态未知"等次级信息与主文字同亮度、层级消失。最小修复：在 `:root` 补两行 `--muted: #5c6f96;`（即 `--text-muted`）与 `--amber: #ffce00;`，或直接把 app.py 内联值替换为 `var(--text-muted)`/`var(--yellow)`。

**P1-3 监控横幅是唯一近白实色块。** app.py:216 `background: rgba(255,255,255,0.85)`，深色玻璃页面上突兀刺眼；且边框色 `rgba(77,171,151,0.3)`、字号色手工选（下面 P2）。最小修复：改玻璃态 `background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(9,13,26,0.55)); backdrop-filter: var(--glass-blur-weak); border-radius: var(--radius-md); border:1px solid rgba(0,240,255,0.25)`。

**P1-4 违反"UI 无 emoji"硬约束。** app.py:203 `"⛔ 执行失败"`、:204 `"⏹ 已结束"` 直出页面。最小修复：删 emoji，仅保留文案+`status-dot`（app.py:947 已用）。WMO_MAP 内 emoji（weather_fx.py:16-45）仅注释性存在、describe() 不返回，不构成 UI 泄露，可不动。

**P1-5 状态配色双源分叉 + 手工色。** app.py:201-202 运行中/已完成同用 `#3e9d89`，而全局语义色在 `task_utils.get_status_color`（running=#00f0ff、success=#00ffa3）；history 行内 id 色 app.py:948 `#2b6e5c` 又第三种绿。三处语义打架且均非 `--green/--cyan`。最小修复：label_map 改为引用 `get_status_color(status)`（history 行已复用该函数），行内 `<b>` 用 `var(--text-strong)` 即可。

---

### 1）逐组件缺陷清单（组件 · 缺陷 · 最小修复）

**Header/标题**
- h1 全局 text-shadow（ui_theme.py:118 附近）令"###### 微调参数"等 h6 均无碍，但页面多处 `#####` 硬标题与头部大标题抢辉光层级；建议 h1 辉光保留，为 `h5` 引入同一套 `letter-spacing:0.03em` 但无 text-shadow，靠 1px `--cyan` 左边条提层级。
- 中文长标题在 `font-family: var(--font-display)`（Bahnschrift 无 CJK）会整段 fallback 到雅黑，与 kicker 的等宽西文气质有细微割裂；建议中文标题沿用 `--font-body` 或雅黑加 `font-weight:700`，仅西文/kicker 用 display 字体。

**weather-chip**
- `border-radius: var(--radius-full)`（ui_theme.py:142-156）配 padding `0.45rem 1.05rem` 是对的；缺陷是 hover（:157）只加浮起与光晕、缺 `transform-origin`/按压缩放，与全局"按压回弹"语言断裂。最小修复：补 `.weather-chip:active{ transform: scale(0.94); }`。
- 内部色 `#c9f8ff` 是硬编码而非 `var(--text-strong)`，与按钮 hover 文字同值，建议改变量统一。
- 温度小数 `{temp:.0f}°C` 由 app.py:546 直出，`font-variant-numeric` 未开；补 `font-variant-numeric: tabular-nums` 防刷新跳动。

**panel / floating-card**
- 二者（ui_theme.py:165-186 与 198-211）90% 规则重复且 hover 位移/描边几乎一致，造成"两种卡片"无层级差。建议 panel 保留 md blur 用于监控大卡；floating-card 改 **no blur + 半透明实色**（`background: rgba(11,16,30,0.72)`），只留 inset 高光，形成"大卡重、小卡轻"的呼吸感，同时释放 blur 预算。
- `.panel:hover` 用 `--ease-spring-soft` + translateY(-3px) scale(1.012)，但**未加 overflow 层的 z 叠**，同区两块 panel 会互相压叠；给 `.panel` 加 `z-index:1`、hover 时 `z-index:2` 即可（仅静态样式）。

**stepper（fx-stepper）**
- `.fx-step .cap`（ui_theme.py:398 附近）字号 0.6rem/字距 0.06em，10 步全中文标签时横向贴死（2s 轮询中 text-overflow 触发率极高）；建议字号提到 0.64rem、字距降 0.03em。
- 激活脉冲 `nodePulse`（:386-401）挂在 `@st.fragment(run_every=2.0)` 重建的 DOM 上（app.py:191/358），fragment 每次 innerHTML 整体替换 → 动画每 2s 从 0% 重启（scale 1↔1.09 跳变）。这是"轮询区禁 CSS 重放动画"的违规面。最小修复：轮询渲染的 stepper 去掉 `animation: nodePulse`，改为静态 `box-shadow: 0 0 0 5px rgba(255,206,0,0.14)` 光环，首帧展示（提交成功后非轮询区）可保留。
- `.fx-step .bar`（:373）`top:16px` 与 node 34px 同心需 `top:16px` 正确；但 bar 连线的首尾颜色 `linear-gradient(90deg, cyan, purple)` 与节点完成色（纯青渐变）不呼应，建议完成态统一 cyan→magenta 的"描边-填充-连线"三元素同一渐变。

**metric**
- `[data-testid="stMetricValue"]`（ui_theme.py 约 349-357）`font-size:30px` + `text-shadow` 对**所有**指标同权（含 loss/置信度），数字越大越闪。建议区分 delta 或 ≤4 个核心卡时保留 glow，histogram/小卡降 shadow 到 `0 0 10px rgba(0,240,255,.15)`。
- 其 `background: var(--bg-glass)`（半透明 0.5）+ blur-weak 正确；但 Streamlit metric 自带 padding 会被外层再包一层，`padding:14px 16px` 与卡片体系不一致 → 建议与 panel 同 padding 1rem 对齐。

**按钮（普通 / 黄色主行动）**
- 普通钮（:224-253）`letter-spacing:0.1em`+`uppercase` 面向中文文案（"选择目录"等）字距过大像散开；CJK 建议字距 0.03-0.05em，保留大写仅对英文有效。主钮 `button[kind="primary"]`（:255-272）注释写"胶囊圆角"但实际 `--radius-btn`=10px，注释与实现矛盾 → 若要胶囊改 `var(--radius-full)`，否则删注释；而黄色实心渐变与玻璃系统刻意反差本身成立，保留。
- 主/副钮高度 46px vs 38px 合理，但两族 `min-height` 差造成表单内横排（SSH 诊断三连钮）基线不齐；统一通过 `align-items:center` 由容器吸收即可。

**输入框**
- 文本/数字/多行输入（:275-303）描边 `rgba(255,255,255,0.14)` 与 button 描边 `rgba(0,240,255,0.4)` 双白/青两套；建议白描边仅用于"可输入区"，聚焦态青色描边逻辑保留，但 hover 白 0.3→0.45 更明确。
- 字体直接套 `--font-mono`，CJK 占位符（"如 data/coco128.yaml"）会回落系统黑体；建议占位符保持 body 字族、值才用 mono。

**selectbox / tabs** ——见 P1-1，当前**规则整体失效**；除重锚定选择器外，额外缺陷：现 `[data-baseweb="tab"]` 内 `border-radius:8px` 与 `--radius-sm:8px` 一致但与按钮 10px 不成阶梯；替换后建议 tab 激活胶囊用 `--radius-btn`。浮层需补 `border:1px solid rgba(0,240,255,0.25)` 与 `box-shadow: var(--shadow-glass-md)`（原 listbox 规则只给背景）。

**expander**
- `[data-testid="stExpander"] details` 背景 `rgba(12,17,30,0.62)` + blur-weak 正确；但 `summary`（ui_theme.py:483 附近）未设 `border-radius`/箭头样式，默认 `▸` 箭头带原生灰色小方块，展开态与卡片语言不一致。最小修复：`summary{border-radius:var(--radius-md)}` 并 `summary::marker{color:var(--cyan)}`。
- details 与面板堆叠时无间距，建议 `details + details{margin-top:0.6rem}`。

**telemetry-log**
- 主规则（:440-455）设计完整；缺陷：`color:#b8f7e0` 是绿系而周边全部青系，与 `border-left` 青不一致；改 `color:#a8d8ff→var(--cyan)` 一级或统一为文本绿仅用于成功。滚动条 thumb 0.35 青在暗底 6px 偏细，`8px` 更易辨识（不破坏预算，非重绘动画）。
- 轮询区内 `max-height` 由内联 style 二次覆盖（app.py:234/425），两处数值 320/340 与 CSS 默认 340 重复定义 → 收敛到 CSS 一个值。

**侧边栏**
- `.stSidebar > div`（:105-109）md blur 常驻，占用重度 blur 额度 1/3；建议降为 blur-weak（`--glass-blur-weak`）或改成半透明实色渐变，预算让给内容卡。
- `.stSidebar p,span{color:var(--text-secondary)}`（:111）会把 caption 也染成 secondary，与正文无差别；建议 caption 单独压到 `--text-muted`。侧边栏"背景天气预览"selectbox 正受 P1-1 波及（无自定义样式）。

**app.py 内联组件（监控横幅/历史行）**
- 白色横幅见 P1-3；历史行（:945-951）每行都是 `.panel` → **glass-blur-md(18px) × 至多 12 行同屏**，突破"重度玻璃≤3 块"预算（tab_monitor 终止态同屏 2 panel + sidebar 已是 3 块极限）。最小修复：历史行改为新 `.panel-row`（`background: rgba(11,16,30,0.72)` 实色半透明、无 backdrop-filter），或复用 `--glass-blur-weak`。

---

### 2）Top 6「高级感」排序（按性价比）

1. **救活 tabs/selectbox/浮层**（P1-1）：整条 tab 栏与所有下拉控件从原生灰皮换成青描边玻璃胶囊——改动集中、视觉覆盖 90% 页面。
2. **处决白色横幅**（P1-3 + P2 内联色收敛）：监控页最常驻的违和元素，改玻璃态后观感直接翻级。
3. **状态色单源 + 补 `--muted/--amber` + 去 emoji**（P1-2/4/5）：一次性消除 9 处无效色引用，历史/监控配色归位。
4. **历史列表降 blur**（上节）：性能预算合规，同时"可点击列表 vs 深色玻璃面板"的材质分层更有设计感。
5. **中文 tracking 与字号收敛**（header/h5/panel-title/cap/button）：`.14em/.12em/.1em` 对中文是过宽的散字距，调 0.04-0.06em 是"高级感"最廉价的 1 行改动。
6. **明暗氛围扩散**（用户核心诉求）：把卡片背景从硬编码 `rgba(9,13,26,0.52)` 改为 `color-mix(in srgb, var(--bg-color) 78%, #1a2238)`（ui_theme.py 三处 panel/floating-card/sidebar），把 `--glow-c/--glow-m`（day_night 已输出但零消费）接入 hover glow，一次注入变量全站呼吸。

---

### 3）可删除的冗余 / 失效规则

- **失效（运行时 0 命中，删除或替换，勿留）**：ui_theme.py:297-303 selectbox/multiselect 两条、listbox 一条；:306-320 tab-list/tab/tab:hover 三条（`aria-selected` 一条先保留到替换完成）。
- **零引用死变量（:root 内仅定义处出现一次）**：`--bg-void/--bg-base/--bg-raised/--bg-surface/--bg-inset`（:15-20）、`--stroke-strong/--stroke-magenta`（:24-25）、`--purple`（:32）、`--glass-blur-strong`（:46）、`--radius-sm/--radius-xl`（:39/43）、`--glow-magenta-sm`（:59）共 12 个。若实施 Top6-6 可复活其中 2-3 个，其余删除。
- **冗余媒体查询**：ui_theme.py:534-535 `@media(max-width:1000px){.telemetry-grid{repeat(2,minmax(0,1fr))}}` 与默认值完全相同，整段可删。
- **注释与实现矛盾**：button[kind=primary] "胶囊圆角"（:254 注释）实为 10px——删注释或改圆角二选一。
- **未被消费的系统输出**：`day_night.css_vars_block` 在 app.py 仅 import 从不调用（app.py:20；测试引用不算运行时）；`weather_tint` 全仓库无调用方（day_night.py:325）。两者正是"氛围未扩散"的代码面证据：建议要么接进主题（Top6-6），要么先标记 dead code 待天气联动方案落地。

---

**Merge verdict：BLOCK**（P1-1 死选择器 + P1-3 白色横幅 + P1-2/4 直接违反硬约束；其中 P1-1/P1-4 修复成本极低，建议先行）。其余 P2 项可随 UI 专家组第一轮小修合并处理。需要运行验证的命令（本审计未执行）：在 Edge 打开 `http://127.0.0.1:8505`，F12 检查 tab/selectbox 实际 DOM 类名以落地 P1-1 新选择器。