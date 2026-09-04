# UI 主题升级最终规范（主导裁决版 v1.0）

五位报告（a 氛围 / b 布局 / c 审计 / d 动效 / e 舒适）已通读，关键事实已对本仓库源码抽查复核（9 处未定义色引用、emoji 违例、白色横幅、data-baseweb 死选择器、_day_night_tick except 分支 pop、css_vars_block 全量变量未注入均属实）。本规范为实施唯一依据；冲突处以本文为准。

## 一、总纲

设计原则：
1. 氛围 = 变量面联动，不是背景微调。明暗必须扩散到卡片玻璃、描边、霓虹、输入凹区、文字辅助色 12 个维度。
2. 玻璃克制。同屏 backdrop-filter 大 blur 恒 ≤3 块（监控页主面板 2 块为限），其余一律 no-blur 半透明实色或 blur-weak；材质靠"重卡 / 轻卡"分级建立层次，不靠堆 blur。
3. 文本永远清晰。正文对比 ≥7:1、标签 ≥4.5:1、muted ≥3:1（暗/亮双锚动态令牌，不做纯静态值）；中文最小字号 11px。
4. 轮询区（2s fragment 重建 DOM）零重放动画：animation 类一律不进轮询 DOM；transition 可保留（DOM 重建不触发过渡回放，状态变化可播一次）。
5. 无 emoji、状态色单源、中文 tracking ≤0.06em、accent 仅作点缀（≤3 处同屏）。

目标观感一句话：深色玻璃仪表舱随真实天气与时间呼吸——晴昼通透高光、深夜霓虹全开、雨夜玻璃沉淀，但文字与信息层级始终锐利稳定。

## 二、明暗氛围联动最终架构

裁决：采用 a 的"多变量整块注入"（上级已裁定 A），弃用 color-mix 单变量推导（公式难维护、旧浏览器风险）；采纳 e 的双锚文本令牌与白天 accent 提亮降饱和；采纳 a 的降级三级链。

### 注入链路（app.py 改造）
- 每 60s tick 与首帧均注入完整变量块（约 18 token），不再只写 --bg-color。
- `_day_night_tick` 的 except 分支删除 `pop("dn_prev")`：异常时保留上一组注入值，静默返回（保降级第 1 级）。
- day_night.py 新增派生函数 `ambient_vars(v, kind, df)` 在 css_vars_block 前把 v 补全 6 个 amb token（见下表）；css_vars_block 保留为纯渲染函数。
- 2s 轮询 fragment 不注入任何变量（只消费）。

### CSS 变量表（默认值 = 深宵档兜底，公式在 Python 侧一次算好）
| token | 默认 | 驱动公式（Python） | 应用元素 |
|---|---|---|---|
| --bg-color | #0A1120 | 沿用 bg_color_for(kind, df) | body 底色 |
| --amb-card | 0.50 | 玻璃 α 锚点表 × smooth(df)：晴昼0.56 阴昼0.60 晴夜0.50 雨夜0.70，clamp[0.46,0.74] | .panel/.floating-card/.panel-row/stSidebar 底 rgba(9,13,26,α) |
| --amb-line | 0.08 | 描边 α = 0.10×glow_c | 卡边框 rgba(255,255,255,α)、分隔线 |
| --amb-hi | 0.045 | 顶高光 α = 0.05×(1.6−df) 晴昼弱化防泛白 | 卡顶部 1px 高光 gradient 段 |
| --amb-glow | 1.00 | 直通 day_night glow_c | hover 光晕/盒阴影半径 calc(10px×var) 与 alpha |
| --amb-acc | #00f0ff | 白天锚提亮降饱和：df>0.6 用 #7ce8ee，夜用原色 | 青 accent 系（按钮描边/tab 激活/聚焦环） |
| --txt-2 | #8fa3c7 | 双锚 secondary：亮档 #a9bcdb | 次级文本 |
| --txt-3 | #5c6f96 | 双锚 muted：亮档 #8b9fbe | 弱文本/caption（≥3:1） |
| --sky-* / --sun-* / --moon-* / --star-* / --particle-bright | （已有） | 原样保留在块内供粒子预留 | 粒子引擎（当前未消费，保留不注入消耗可忽略） |

锚点表只用四种组合（晴昼/阴昼/晴夜/雨夜），其它天气按 kind 系数插值；R 语言禁止：CSS 内不得出现 color-mix 推导氛围。

### CSS 消费清单（ui_theme.py，全部 token 化）
背景 body；卡底色三处 .panel/.floating-card/.panel-row + stMetric + stExpander details + weather-chip + fx-card；描边 stroke 系（rgba 尾数换 var(--amb-line)）；顶高光 .panel::before 与 .floating-card::before；hover 光晕 box-shadow 乘 var(--amb-glow)；text 辅助色换 --txt-2/--txt-3（正文 strong/primary 恒用现值不变——微调收益低、风险高，否决 a 的 text 微调项）；按钮聚焦环与 tab 激活用 var(--amb-acc) 或原色（原色已可读，白天档用提亮锚）。

## 三、视觉与布局规范

采纳 b 的密度/字阶/头部骨架，修正：头部三区仪表条降为 P2（P0 先止血），本节只落 P1 内可直接生效项。

- 密度：.block-container padding-top 20px；面板 padding 统一 1rem；同屏卡片列 gap 16px；expander 与 panel 间距 12px；列表行 gap 8px。
- 字阶（size / weight / 用途）：
  - kicker 11px mono / 600 / 0.28em 青（西文专用，中文不落此规则）
  - h1 页面主标题 22px / 700 / display 字族，西文数字走 Bahnschrift，中文整段回落雅黑 700（禁止混排细体西文在中文标题上）
  - panel-title 12px / 600 / tracking 0.06em（原 0.14em 对中文过散，砍半）
  - 正文 15px / 400 / body 字族，行高 1.7
  - 表单 label 13px / 600 / secondary
  - micro（telemetry-label/mini-title/fx-step cap）≥0.68rem / tracking ≤0.12em，中文可读下限 11px
  - metric 主值 28px（原 30px），副指标 24px
  - 日志 13px / mono / 行高 1.6
- h5/h6 硬标题：加 1px 左青条提层级，去全局辉光（辉光仅 h1）。
- 头部骨架（P2 落地，HTML 先行在文档记录）：brand（kicker+名称）| 分隔刻度 | weather-chip + 运行状态胶囊 + 时钟文本（时钟复用 60s tick 注入文本，不引 JS 定时器）。
- 监控区：历史列表行改 .panel-row（见 P1-1）；终止态同屏 panel ≤2 块。

## 四、交互动效规范

采纳 d 克制区间（spring 仅按压/首帧/终态，hover 一律 ease 150-220ms，超调 ≤6%，只动 transform/opacity/纯色；单元素并发动画 ≤1）。

首批微交互（4 个，全部位于非轮询 DOM）：
1. 按钮/胶囊按压 scale(0.93)，transition 0.1s，回弹 cubic-bezier(0.34,1.56,0.64,1)。
2. 卡片 hover：translateY(-2px) + 角部光带（::after 渐变，opacity 0→1 220ms ease）；hover 位移改用 ease 而非 spring（原 --ease-spring-soft 与 2s 重建叠加会显跳）。
3. weather-chip hover 辉光 + active 按压缩放（同按钮语言），呼吸动画仅首屏非轮询页可加，周期 3.2s。
4. 首帧 rise-in（fragment 区外元素入场 opacity+translateY 8px → 0，400ms ease，delay ≤80ms 按 index 递增，最多 5 元素）。

轮询区禁区（硬性，直接写进 CSS）：.fx-live 包装类内 禁止 animation 属性（nodePulse/live-dot/badgePulse 全改静态光晕：`box-shadow: 0 0 0 5px rgba(255,206,0,0.14)`）；允许 transition（状态变化播一次、DOM 重建不重放）。
reduced-motion：现规则保留，白名单追加：聚焦环、静态状态点、日志末行静态高亮（均为非动画态）。
补 focus-visible 专属态：select 触发框、radio/checkbox、summary 补 2px 青环（现仅 text input 有）。

## 五、组件修复清单

P0（一步 commit，先止血）：
- P0-1 死选择器重锚：删除 .stSelectbox/.stMultiSelect/.stTabs 下 5 条 data-baseweb 规则；改为 1.62 data-testid 锚定：[data-testid="stTabs"] button[role="tab"]（激活 [aria-selected="true"]）、[data-testid="stSelectbox"]（含 input[role="combobox"]）、[data-testid="stSelectboxPortal"]。数值沿用现 CSS：radius var(--radius-btn)=10px、bg rgba(255,255,255,0.045)、border 1px rgba(255,255,255,0.14)、浮层补 border cyan 0.25 + box-shadow var(--shadow-glass-md)。实施前 Edge F12 复核实际类名一次。
- P0-2 :root 补两行：--amber:#ffce00; --muted:#5c6f96;（app.py 9 处引用立即生效，替代逐处替换）。
- P0-3 去 emoji：app.py:203-204 改为 "执行失败"+"已结束"，配色行内 status-dot（failed=var(--red)/cancelled=var(--muted)），删 emoji 字符。
- P0-4 白横幅玻璃化：rgba(255,255,255,0.85) → background: linear-gradient(180deg, rgba(255,255,255,0.05), rgba(9,13,26,0.55)); backdrop-filter blur-weak; border 1px rgba(0,240,255,0.25); 文字 #bfe8dd。
- P0-5 状态色单源：label_map 文案行配色全部改调 get_status_color(status)；history 行内 <b> 色改 var(--text-strong)（id 的 #2b6e5c 删除）。
- P0-6 氛围全主题注入：第二节架构落地（含 except pop 修复 + ambient_vars + CSS 消费清单 12 处）。

P1（第二批）：
- P1-1 历史行 .panel-row：background rgba(11,16,30,0.72) 实色，无 backdrop-filter，border 现描边，hover 仅提 border；删除历史行对 .panel 的复用（blur 预算释放）。
- P1-2 侧栏降 blur-weak（原 md 常驻）；.stSidebar caption 单独压 --txt-3，其余 p/span 保 secondary。
- P1-3 卡片分级：.floating-card 去 blur 改实色半透明 rgba(11,16,30,0.72)+inset 高光；.panel 保 blur-md（监控大卡）；.panel z-index 1 / hover 2 防同区压叠。
- P1-4 双锚令牌生效（--txt-2/--txt-3 注入随档切换）；micro 字号下限 0.68rem；日志 13px、color 改青系 #b8e6ff（原绿 #b8f7e0 与青描边割裂）、去 inset 26px 暗角、滚动条 8px。
- P1-5 中文 tracking 收敛：.panel-title/.fresh-kicker 中文语境 0.06em；button letter-spacing 0.03em（uppercase 仅对英文自然生效）；.fx-step .cap 0.64rem/tracking 0.03em。
- P1-6 metric 分级：核心卡（≤4）保 28px + glow；副指标 24px + shadow 0 0 10px rgba(0,240,255,0.15)；padding 与 panel 对齐 1rem。
- P1-7 细节：stExpander summary border-radius md + ::marker cyan + details+details margin-top 12px；输入占位符 font-body、值 font-mono；weather-chip hover 文字 var(--text-strong)、active scale(0.94)、font-variant-numeric tabular-nums；primary 主钮注释改"主行动实心黄"（radius 保留 10px 不强改胶囊）。

P2（增量打磨）：
- P2-1 accent 双锚白天提亮（青 #7ce8ee/品红 #ff9ab8 仅 df>0.6 时）；glow 半径 calc(10px×var(--amb-glow)) 随昼夜收敛。
- P2-2 头部三区仪表条骨架 + 监控页 4:8 分栏（先保 P1 效果评估再动结构）。
- P2-3 网格 44→56px、扫描线 alpha 减半（白天再半，amb token --scan 控制）；随 P0-6 一起把 --scan 并入注入面。
- P2-4 清理：:root 12 个零引用死变量（--bg-void/--bg-base/--bg-raised/--bg-surface/--bg-inset/--stroke-strong/--stroke-magenta/--purple/--glass-blur-strong/--radius-sm/--radius-xl/--glow-magenta-sm 保留或删按复活情况）；冗余 @media 1000px 重复段；day_night 死代码 weather_tint 标记或接入。

## 六、实施顺序与不做清单

Step 1（P0 六项 + P2-4 的死变量/失效选择器清理随行）：
验收：pytest 76+ 全绿、AppTest UI 0 异常、Edge 截图（提交/监控/历史）确认无原生灰皮控件、无 emoji、横幅玻璃化、状态色归位、暗/亮两档变量注入生效。
Step 2（P1 全套）：
验收：同屏 blur ≤3（DevTools layer borders 目检）；2s 轮询 getAnimations() 为空；muted 亮档对比 ≥3:1；三页截图审美复检。
Step 3（P2 增量）：
验收：perf 探针 p95 不劣化于优化前基线；截图最终比对；重启 8505 curl 200。

不做清单（明确否决）：不做浅色/白底主题（背离赛博基因与本需求定位）；不做 color-mix 单变量推导；不引任何新框架/组件库/图标字体；不改业务功能与表单逻辑结构（只改视觉层与 DOM 包装类）；不重构天气粒子引擎（性能预算已锁定）；不引入 emoji 或新图标系统（无 emoji 基因，装饰用 CSS 形状）；不动轮询业务数据模型换取视觉。
