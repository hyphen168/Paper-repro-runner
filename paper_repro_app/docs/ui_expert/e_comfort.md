# 舒适性 / 可读性审计与规范（UI 专家组 · E-舒适）

审计对象：`ui_theme.py` 的 `APP_CSS`、`app.py` 运行时注入（day_night 60s tick、live_monitor 2s fragment、头部/遥测/日志 HTML）。方法：WCAG 相对亮度/对比度实算（sRGB 线性化），按两档实测底色——暗档 `#0E1524`（L≈0.008）、亮档 `#374769`（L≈0.063，仍属"深钢蓝灰"而非真亮底，整站保持深底浅字策略成立）。

## 1) 对比度审计（4 级文字 × 2 档底色）

| 令牌 | 色值 | 暗档对比 | 亮档对比 | 结论 |
|---|---|---|---|---|
| text-strong | #eaf6ff | 16.6:1 | 8.4:1 | 全达标（AAA） |
| text-primary | #c9d8ee | 12.6:1 | 6.4:1 | 达标；亮档未及 AAA，可接受 |
| text-secondary | #8fa3c7 | 7.1:1 | **3.6:1** | 亮档跌破 4.5，仅够大字号 |
| text-muted | #5c6f96 | 3.6:1 | **1.8:1** | 暗档仅装饰级；**亮档不及格** |

**结论与微调**：两级底色均为深底，文字体系方向不动（勿引入深色文字——亮档底色 L=0.063 上限决定了黑字对比最高只有 2.3:1，不可行）。需把 secondary/muted 做成**双锚动态令牌**（与 --bg-color 同用 mix_hex 的 p 值插值，一行注入即可）：secondary 亮端 `#a9bcdb`（亮档 4.8:1）；muted 亮端 `#8b9fbe`（亮档 3.4:1，作弱化/辅助文字可接受，正文信息一律禁用 muted）。另发现事实性 bug：live_monitor 横幅引用 `var(--muted)`/`var(--amber)`，`:root` 未定义 → 解析失败；且横幅内联底色 `rgba(255,255,255,0.85)` + 深青 `#3e9d89` 字样，是**全页最刺眼的光斑**（见 §3）。

## 2) 字号与行高（中文场景）

正文中文建议 ≥15px、行高 1.7（`body` 现为默认 14px/1.6，段落偏挤；单行控件 1.5 即可）。问题集中在**过小的微标签**（中文 10px 基本不可读）：
- `.telemetry-label` 0.64rem(10.2px)+0.16em 字距 → **升 0.72rem、字距降 0.08em**；
- `.mini-title` 0.66rem、`.fx-step .cap` 0.6rem(9.6px) → 升 0.72rem / 0.68rem，中文最小字号锁 **11px**；
- `.panel-title` 0.75rem → 0.8rem（12.8px）；
- 日志 12px 等宽 → 13px、行高 1.6；遥测数值 0.9rem 维持。
- 大标题 h1 clamp 1.9–2.6rem 与 h 行高 1.2 合理；metric 30px 数字偏大，见 §3。中文字距：正文/小标签字距 0.012–0.05em 即可，**0.1em 以上只留给拉丁大写短语**，避免中文拆散感。

## 3) 降噪（长时间盯屏疲劳）

- **纯青成片刺眼（头号问题）**：#00f0ff 亮度极高（L≈0.70），metric 大数字 30px 全青 + 双重 text-shadow、panel-title/stepper meta 的青值、目录绿 code、hover 边框全青，信息密度上"青色≈所有强调"会失焦。规范：**青只作 ≤3 处强调位**（激活态/边框/小值），大数字与卡片标题正文改为 text-strong 白 #eaf6ff + 青色 1px 下描边或青色仅用于单位/状态小字。
- **霓虹 glow 过量**：text-shadow 挂满 h1/kicker/panel-title/metric/weather-chip/stepper 已达标节点。规范：**夜间默认 glow 半径 ≤10px、alpha ≤0.35，且仅边框发光（box-shadow 环）不叠加文字辉光**；hover 外发光半径 ≤16px。修改集中在 `:root` 的 `--glow-*` 变量，改一处全站生效。
- **扫描线/网格密度应再降**：44px 青色网格(0.02)+3px 周期扫描线(0.014)叠加粒子，大屏近距离易产生莫尔与闪烁感。规范：网格 56–64px 且只留单向微光、alpha 降 0.012；扫描线周期改 5px、alpha 降 0.008，**亮档（白天晴）时 opacity 再砍半**（可用注入的 --day-factor 控制）。
- **白底状态横幅**（live_monitor）在深色玻璃里是强眩光源，2s 重绘区还贴着重启横幅 → 改为玻璃暗底（`--bg-glass` + 1px 边框），内文状态色换浅青绿 #bfe8dd；同时修复 `var(--muted/--amber)` 未定义。此区除 hover transition 外不加任何动画（已合规，勿新增）。
- 背景顶部青 radial 0.11 在亮档下轻微抬亮，建议随 --bg-color 明度自动降到 0.05–0.07。

## 4) 日志区（绿字 terminal）

底色 rgba(2,4,10,.92) 近纯黑、字 #b8f7e0 → 对比 ≈17:1，达标且正确（终端日志就该高对比）。建议：
- 字号 12→13px、行高 1.55→1.6；`font-variant-numeric` 无关紧要但保留 `white-space: pre-wrap`；
- **去掉 `inset 0 0 26px` 暗角内阴影**（文字边缘被压暗，滚动时累眼）；
- 日志区**保持无 backdrop-filter**（2s 重绘区大 blur 最耗 GPU，现 .92 实色正确）；
- 若日志已带 ANSI 色，仅着色于数值/URL/时间戳，通篇 mint 一色时用浅青 #6f8f9a 弱化时间戳前缀。

## 5) 全局舒适化补丁清单（每条一行 CSS，集中贴 APP_CSS 尾部即可）

```css
:root { --text-muted:#6e81a3; --glow-cyan-sm:0 0 8px rgba(0,240,255,.14); --glow-magenta-sm:0 0 8px rgba(255,42,109,.16); }
body { font-size:15px; line-height:1.7; }
.telemetry-label, .mini-title { font-size:.72rem !important; letter-spacing:.08em !important; }
.fx-step .cap { font-size:.68rem !important; line-height:1.35; }
.panel-title { font-size:.8rem !important; text-shadow:none; }
[data-testid="stMetricValue"] { color:var(--text-strong) !important; text-shadow:none !important; font-size:26px !important; }
[data-testid="stMetricValue"]::after { content:" "; border-bottom:2px solid var(--acc-cyan,#00f0ff); }
body::before { background-size:56px 56px; }
body::after { opacity:.3; background:repeating-linear-gradient(0deg,rgba(255,255,255,.008) 0 1px,transparent 1px 5px); }
.telemetry-log { font-size:13px !important; line-height:1.6 !important; box-shadow:none !important; }
.telemetry-log::first-line { color:#6f8f9a; }
div[style*="rgba(255,255,255,0.85)"] { background:rgba(12,17,30,.72) !important; border-color:rgba(77,171,151,.35) !important; }
div[style*="rgba(255,255,255,0.85)"] span { color:#bfe8dd !important; }
h1, .fresh-kicker, .fx-card .t { text-shadow:none; }
.fx-card .t { color:var(--text-strong); }
.panel:hover, .floating-card:hover { box-shadow:var(--shadow-glass-md), 0 0 0 1px rgba(0,240,255,.25); }
code { color:var(--text-primary); background:rgba(0,240,255,.07); }
```

**红线提醒**：以上全部为静态/transition 级，无任何挂载轮询区的新增 `@keyframes` 循环；2s fragment 内保持现状。

## 6) 明暗氛围联动时 accent 的亮度同步

关键计算：两档底色都是深底，accent 主要敌人不是"看不清"而是**眩光**——满饱和青在亮档(6.6:1)与黄(6.2:1)仍可读，但品红 `#ff2a6d` 亮档仅 2.6:1 且高饱和高刺激。同步规则：
- **accent 用双锚插值**：在 `_day_night_tick` 现有注入块里（它已在用 mix_hex，且 day_night 已产出 `glow_c/m/y` 系数但 css_vars_block 当前根本没被注入——先补上），同 p 生成 `--acc-cyan/--acc-magenta/--acc-yellow/--acc-green` 四个令牌：夜间端点保持现有霓虹原色；白昼端点换**同色相提亮降饱和**的安全色——青 `#7ce8ee`、品红 `#ff9ab8`、黄维持 `#ffce00`（文字/细线各保 ≥4.5:1），再 `--text-shadow:none`。CSS 侧把 `var(--cyan)` 等使用点统一改引 `var(--acc-cyan, #00f0ff)`（留默认值防首帧闪变）。
- **glow 随 `glow_c/m/y` 缩放**：定义 `--glow-cyan-sm: 0 0 calc(10px*var(--glow-c,1)) rgba(0,240,255,.2)`，白天系数自动趋 0.3，光晕收敛；品红白天不发光（glow_m 已自动压到 0.2），正好把"暗底高饱和青刺眼"从来源上消除。
- 玻璃卡片底色 `--bg-glass`/面板半透明白高光层在亮档保留即可（明暗层次感来源），但**边框青描边 alpha 白天降一半**：`border-color: color-mix(in srgb, var(--acc-cyan) 55%, transparent)`。

## 结论（给决策）

1. 文字体系成立，唯一硬伤是白天档 muted 1.8:1 —— 双锚动态令牌是正解（成本：一次注入扩展）。
2. 微标签全面 <11px 是中文可读性首害，6 行 CSS 可解决。
3. 眩光大头：30px 纯青大数字、双层文字辉光、白底状态横幅、品红白天裸奔 —— 按 §5 清单一次收敛，视觉基因不变。
4. 建议把 day_night 注入从单 `--bg-color` 升级为 css_vars_block + `--acc-*` + `--day-factor` 的完整块，之后全部"氛围联动"都只改令牌不再改选择器。
