# 动效与微交互规范 v1（交互动效专家意见）

适用范围：ui_theme.py 的 APP_CSS + app.py 少量结构类。核心纪律：**交互有反馈、反馈有分寸、轮询区零回放、可访问性优先**。全篇无 emoji（现状 `⛔ 执行失败 / ⏹ 已结束` 文案属越界，须改为纯文字 + status-dot 配色）。

## 决策

**1. 时间分层与果冻克制区间。** 动效分三层时标：按压/变色 80–150ms；hover/焦点/状态 150–220ms（`--dur-1/--dur-2`）；入场/终态确认 350–500ms（新增 `--dur-3:.35s; --dur-4:.45s`）。果冻（spring，带回弹）只允许出现在三个时刻：① 按压释放回弹；② 元素首次挂载的 pop；③ 终态确认的一次性 pop。**hover 一律不超调**（位移 ≤3px、scale ≤1.02，用 ease-out 或现有 `--ease-spring-soft`），否则卡片 hover 全部弹跳会显得油滑。spring 用硬 `--ease-spring`（0.34,1.56）时超调 ≤6%、单元素、同屏并发 ≤1；页面大段落出现/日志滚动/昼夜变色**禁用 spring**。只动 transform/opacity/纯色，禁止动 left/top/width/height 触发布局。

**2. 时钟分区制。** 页面存在四类重绘时钟，动画政策各不相同：
- **首帧区**（header/carousel/weather-chip）：允许一次性挂载动画，节点跨 rerun 复用故不会反复回放；
- **交互区**（hover/press/focus）：事件驱动，允许，但 2s 轮询内的子树例外（见禁区清单）；
- **轮询区**（`@st.fragment(run_every=2.0)` 渲染的子树）：**禁 keyframes、禁 transition、禁重放**——DOM 每 2s 重建，无限动画会不断从 0% 重启造成节点跳动/闪烁（现 `.fx-step.active .node` 的 nodePulse 与 `.live-dot` badgePulse 正属此病）；
- **昼夜区**（60s 注入 `--bg-color`）：色值随 day_factor 限幅渐变，逐 tick 增量极小；允许对「纯 var 底色」属性挂 0.8–1.5s ease-out 过渡做平滑，渐变/半透明组合色不逐帧过渡（靠小增量自然平滑）。

**3. 明暗作用于全主题（动效侧接线）。** day_night 已输出 `--glow-c/m/y、--card-alpha/bright`，但 APP_CSS 目前硬编码了 rgba 辉光、未消费这些变量——这是“只变背景”的根因。动效规范要求：**所有 hover 辉光/呼吸/光扫的颜色强度一律用 `color-mix(in srgb, 霓虹色, transparent calc((1 - var(--glow-c)) * 100%))` 表达**（Edge≥111 支持），夜间/雨雪自动收敛光效，白天自动增强，氛围整体联动；不再新增硬编码 alpha。夜晚振幅可另乘 `calc(0.75 + 0.25*var(--day-factor))` 收窄位移。

**4. prefers-reduced-motion 是一等公民。** 系统级“减弱动态”下动效全灭，但状态对比保留（hover 变色、焦点环**即时**呈现，无过渡），滚动不动画。与 2s 轮询禁区别：reduce 是全站兜底，轮询禁令是性能纪律，二者叠加不冲突。

**5. 无限动画白名单（全站仅此两处）。** ① `.fx-track` 轮播走马灯（hover/focus 暂停）；② weather-chip 呼吸辉光（新增，见下）。其余任何 `infinite` 一律移除或改为静态样式。轮询区内的“运行中”信号一律静态化（圆环/点 + 颜色），不以动画表达。

## 可执行变更

**A. 动效配方表**（属性/时长/缓动/位移；★=现状保留，◆=本次修正/新增）

| 元素 | 触发 | 属性 | 时长·缓动 | 位移/振幅 |
|---|---|---|---|---|
| .panel / .floating-card / [stMetric] | hover★ | transform+box-shadow+border | .22s spring-soft | -3px·scale1.012 / -2px |
| .fx-card | hover★ | 同上 | .22s spring-soft | -2px·scale1.02 |
| .weather-chip | hover★ | transform+glow | .22s spring-soft / ease-out | -2px |
| button / primary | hover★ | transform+bg+glow | .22s spring | -2px |
| button / primary | press★ | scale | .1s ease-in 后 .3s spring 回弹 | 0.93/0.94 |
| 所有按钮 | focus-visible◆ | outline+offset | 0（即时） | 2px 环 |
| 输入框 | hover/focus★ | border-color / ring | .15s/.22s ease-out | 0 位移 |
| stTabs tab | hover/选中★+active◆ | color/bg/glow + scale | .15s ease-out | active scale.97 |
| .fx-step .bar::after | 状态迁移◆ | scaleX（仅终态渲染，轮询内静态） | .5s ease-out | 0→1 |
| .fx-step.done 节点 | 终态挂载◆ | jellyPop 单次 | .45s spring | 峰 1.04 |
| header/carousel/chip | 首帧挂载◆ | opacity+translateY | .45s ease-out | 4px，错峰 0/60/120ms |
| 新日志行 | 轮询更新 | **无动画**；末行静态高亮 | — | — |

克制判定口诀：**点按用 spring、悬停用 ease、出现用一次、轮询用静态。**

**B. 六个低风险微交互**（≤6，全部纯 CSS，触发与频率边界见括号）：
1. **标题光扫**（首帧类，仅全页 rerun 重挂载 header 时回放；2s/60s fragment 不触及 header）：`.fresh-header h1{position:relative}.fresh-header h1::after{content:"";position:absolute;left:0;bottom:-2px;width:0;height:2px;background:linear-gradient(90deg,transparent,var(--cyan),var(--magenta));animation:titleSweep .8s var(--ease-out) .1s both}` + `@keyframes titleSweep{to{width:min(420px,100%)}}`。
2. **卡片角部光带**（hover-in 触发、每次 hover 一次、0.25s）：`.panel::after{content:"";position:absolute;right:12px;top:12px;width:16px;height:16px;border-top:2px solid transparent;border-right:2px solid transparent;transition:border-color .25s ease-out}`、`.panel:hover::after{border-color:var(--cyan)}`——只动纯色，零布局。
3. **weather-chip 呼吸**（无限白名单#2，仅 box-shadow 换成伪元素 opacity 省绘制；reduce 下停）：`.weather-chip::after{content:"";position:absolute;inset:-3px;border-radius:inherit;box-shadow:0 0 0 0 color-mix(in srgb,var(--cyan) 30%,transparent);opacity:0;animation:chipBreath 3.2s ease-in-out 1.2s infinite}`、`@keyframes chipBreath{0%,100%{opacity:0}50%{opacity:1}}`；chip 需 `position:relative`。频率：3.2s 周期、振幅仅一层辉光、不位移。
4. **首帧轻量出现**（mount-only，不挂 fragment；回放容忍：仅 header 重注入时）：`.fresh-header,.fx-carousel,.weather-chip{animation:riseIn .45s var(--ease-out) both}`、`@keyframes riseIn{from{opacity:0;transform:translateY(4px)}}`，三者 animation-delay 0/.06s/.12s 错峰。
5. **终态确认 pop**（终态渲染不在 2s fragment 内，单次；离开再进可重放 1 次可接受）：monitor 终态外层 panel 追加结构类 `boot-pop`，`.boot-pop{animation:jellyPop .45s var(--ease-spring) both}`（jellyPop 已有）。
6. **日志末行静态高亮 + 活动节点静态环**（0 动画，替代现重放脉冲）：末行渲染为 `<span class='tail-line'>`：`.tail-line{display:block;background:rgba(0,240,255,.07);border-left:2px solid var(--cyan);padding:0 .4rem}`；`.fx-live .fx-step.active .node{animation:none;box-shadow:0 0 0 5px rgba(255,206,0,.14),0 0 18px rgba(255,206,0,.3)}`。

**C. 2s 轮询禁区清单与审计**。禁区选择器（`_auto_refresh_monitor` / `live_monitor` fragment 内出现的全部）：`.fx-stepper .fx-step`、`.fx-step .node/.bar::after`、`.fx-stepper-meta .meta-pill`、`.live-dot`、`.telemetry-log`、fragment 内 `.panel` 及其 `::before`、fragment 内 `[data-testid="stButton"] button`（结束/重新执行按钮）。落实方式：app.py 每个 `run_every` fragment 的最外层渲染包 `<div class="fx-live">`（唯一结构改动），CSS 尾部追加覆盖块：
```css
.fx-live, .fx-live * , .fx-live *::before, .fx-live *::after { animation:none !important; transition:none !important; }
```
审计四步：① 结构核对——运行中 DevTools 数 `main .fx-live` 与 fragment 声明数相等；② `getAnimations()` 抽查：轮询容器上隔 1.5s 采样两次，断言无 `playState==='running'`；③ Performance 录 6s——只应有 2s 整数倍的轻量重绘，无逐帧动画帧与 layout 抖动；④ hover 体检：运行中鼠标停驻轮询卡片/按钮 4s 无跳动，终态后再 hover 恢复弹性为正常基线。

**D. prefers-reduced-motion 完整处理**（替换现仅 1 行的写法）：
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation:none !important; transition:none !important; scroll-behavior:auto !important; }
  .fx-track { animation:none !important; }
  .fx-step.active .node, .live-dot, .weather-chip::after { animation:none !important; }
  .fx-step.active .node { box-shadow:0 0 0 5px rgba(255,206,0,.12); }
  [data-testid="stTabs"] { overflow-x:auto; } /* 灭掉标签滑动过渡后保可滚 */
}
```
注意 reduce 下 focus 环仍**即时**显示（outline 不是动画），hover 变色仍即时——状态可见性不动画化即可达标。APP_CSS 里 `:focus-visible` 全局规则保留。

**E. hover/focus-visible/active 三态完整度检查**。
- **已完整**：stButton、primary（hover/press 有，focus 需补：`:focus-visible` 环用 offset 外圈以免与 glow 混淆）。
- **缺失 active**：stTabs tab（补 `[role=tab]:active{transform:scale(.97)}`）；expander summary（补 hover 变色 `summary:hover{color:var(--cyan)}`）。
- **缺失 focus-visible 专属**：所有按钮、tab、checkbox/radio、expander summary。统一补组件级规则（避免只靠全局兜底 outline 被 Streamlit 容器裁剪）：
```css
.stButton>button:focus-visible, [role=tab]:focus-visible,
summary:focus-visible { outline:2px solid var(--cyan); outline-offset:2px; }
button[kind="primary"]:focus-visible { outline:2px solid var(--yellow); outline-offset:3px; box-shadow:0 0 0 5px rgba(255,206,0,.18); }
button:active:focus-visible { outline:none; } /* 按压时不双重描边 */
```
- **缺状态样式**：selectbox 的 focus-within（baseweb 用焦点容器而非原生 focus-visible）：`.stSelectbox:focus-within [data-baseweb="select"]>div, .stMultiSelect:focus-within [data-baseweb="select"]>div{border-color:rgba(0,240,255,.7);box-shadow:0 0 0 3px rgba(0,240,255,.14)}`；下拉 `[role="option"]:hover,[role="option"][aria-selected="true"]{background:rgba(0,240,255,.12)}`；radio/checkbox label 补 `label:hover{opacity:.9} input:focus-visible+*{outline:...}`；st.code 复制按钮补 hover 背景。**结论**：当前实质缺口集中在「focus 专属态」与「select/option、radio、checkbox、summary」四类；改动集中于 ui_theme.py 一处，不触碰业务逻辑。
