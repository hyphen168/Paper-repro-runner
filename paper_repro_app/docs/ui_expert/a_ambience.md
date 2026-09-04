# 天气 × 昼夜 → 全主题氛围架构规范

根因判断：现状 app.py 每 60s 只注入 `--bg-color` 单变量；而 day_night.py 已产出 `glow-c/m/y、card-alpha、card-bright` 等整套语义量却未被 ui_theme.py 的 APP_CSS 消费（死输出）。本规范即打通"天气系数 × 昼夜因子 → ~10 个氛围 token → 全元素消费"这条已存在一半的管线，注入频率不变（首帧 + 每 60s），不触碰 2s 轮询区与粒子层。

## 决策

### D1｜明暗氛围作用的 UI 维度清单（逐条给理由）

| # | 维度 | 作用方式 | 理由 |
|---|---|---|---|
| 1 | 页面底色 `--bg-color` | 调变最弱，混色上限从 0.9 收至 0.6 | 底色大部分被天气 canvas 天空盖住，提底是浪费对比预算；晴昼的"亮"应由高光与描边承担 |
| 2 | 玻璃填充不透明度 `--glass-a` | 主轴，全天候跟随 | 雨夜画布与世界皆暗，卡片须"更沉更实"（α↑）才像暗夜里的安稳仪表舱；晴昼画布亮，α 取中高并用高光造"通透"而非靠低 α 漏光 |
| 3 | 顶部内高光 `--sheen-a` | 晴昼升、雨夜收敛 | 高光是"面朝光源"的物理语义：有太阳才有亮边；雨夜无直射光，去高光留沉 |
| 4 | 描边双层 | 中性白描边 `--edge-w` 随环境亮增；accent 描边 `--edge-acc` 随 `glow-c` 夜增 | 描边功能是锚定轮廓：亮背景下轮廓必须加深才立得住；暗背景下细亮发丝线更赛博 |
| 5 | 文字对比层级 | primary/strong 恒定近白；secondary/muted 由 Python 生成微抬色值（抬升 ≤0.1 亮度，经上级批准） | 文字是信息主轴：宁可背板迁就文字，不可文字迁就背板 |
| 6 | accent 霓虹强度 | 白天收敛（青 ~0.30）、夜全开（~0.85×天气系数） | 霓虹是暗环境才成立的发光语言；白天强霓虹刺眼且与天空抢亮度；夜雨保留霓虹＝"雨夜霓虹灯"情绪，不应随天气削光 |
| 7 | 阴影深度 `--shadow-k` | 白天浅、夜雨最深 | 影子语义＝光源高度：太阳高挂影短浅；夜雨无环境光，深影定义层距，防卡片在黑底上"漂" |
| 8 | 侧边栏明度 | 玻璃 α 与主区联动 +0.04 常驻偏移 | 侧栏是常驻导航，须与主区同呼吸但更稳定，避免反差过大 |
| 9 | 输入凹区/下拉/stepper 节点 `--well-a` | 夜雨加深凹感 | 凹区是"可操作"隐喻：夜雨时操作区需更明确的触觉暗示，晴昼可稍平 |
| 10 | 终端日志/代码块 | 刻意恒定（近黑+青边不变） | 终端是"事实层"，变色会暗示数据在变；恒定也保证 2s 轮询区零视觉噪音 |
| 11 | 卡片顶部渐变亮线（panel::before） | 青→品 alpha × `glow-c` | 它是环境光反射条，应随昼夜呼吸 |
| 12 | 天空/粒子层 | 不重复接管（weather_fx 自持 kind/day）；`--star-alpha` 已注入，继续消费 | 单一职责，避免两套系统争画布 |

### D2｜变量架构：注入"成品 token 块"，否决单变量 --ui-light

理由：单一 `--ui-light` 迫使所有色值在 CSS 内做乘法推导链，"可读性"与"美观"耦合进同一条表达式；而本主题有刻意例外（终端恒定、hover 恒定、muted 上限），每个例外都要覆盖写，失控且难调。改为 **Python 每 60s 算完、整块注入成品 token**（复用并扩展 `css_vars_block`；app.py 的两处单变量注入替换为整块注入）。CSS 内只允许 `var()` 与 `rgba()` 内 `calc(乘法)`，**不用 color-mix**（Edge 兼容面最小）。hover/active/首帧态一律用绝对高亮常量，不随氛围变——交互反馈必须稳定可预期。

最终注入变量表（默认值＝ui_theme.py `:root` 中写死的兜底常量＝深夜色）：

| 变量 | 默认(兜底) | 推导公式（Python 60s 算一次） | 应用元素 |
|---|---|---|---|
| `--bg-color` | `#0A1120` | 现 `bg_color_for` 混色上限改 0.6 | body 底色 |
| `--glow-c` | `0.80` | `clamp(相位glow_c × (1+0.12n−0.10g), 0.2, 1.0)` | 青 glow、标题辉光、panel::before、step.done、live-dot |
| `--glow-m` | `1.00` | 同上（品红版） | 品红 glow、panel::before 尾段 |
| `--glow-y` | `0.40` | 同上 | 黄 glow、step.active 光晕 |
| `--glass-a` | `0.52` | 分段锚点表（见 D3）× smooth(df) 插值，clamp `[0.46,0.74]` | .panel/.floating-card/.fx-card/stMetric/.telemetry-metric/expander/meta-pill 填充 alpha |
| `--sheen-a` | `0.045` | `0.025 + 0.045·amb·(is_day?1:0)`，clamp `[0.02,0.07]` | 卡片顶部白渐变、weather-chip inset |
| `--edge-w` | `0.09` | `0.05 + 0.10·amb`，clamp `[0.05,0.17]` | 中性白描边（panel/.telemetry-metric/.fx-card 等） |
| `--edge-acc` | `0.50` | `0.35 + 0.25·glow_c` | accent 描边基础态（青/品 border） |
| `--shadow-k` | `1.0` | `0.50 + 0.55·n`，clamp `[0.5,1.1]` | 全部阴影 token 的 rgba alpha 乘子 |
| `--well-a` | `0.05` | `0.04 + 0.05·g + 0.02·n`，clamp `[0.04,0.12]` | 输入框/textarea/selectbox/stepper 节点底色 |
| `--tx-sec` | `#8fa3c7` | `mix(#8fa3c7, #bcd0ec, 0.45·amb)`（hex 成品） | 标签、label、secondary 文本 |
| `--tx-muted` | `#5c6f96` | `mix(#5c6f96, #a6b8d8, min(0.35·amb+0.15·n, 0.45))` | caption、mini-title、弱标注（抬升封顶保住层级） |

驱动量：`df`＝day_factor（现有）；`n=1−clamp(df,0,1)`；`g`＝天气灰沉系数 `GLOOM`（晴0/多云.06/阴.14/雾.20/雨.32/大雨.45/雷.55/雪.15，新增表）；`amb=clamp(_WEATHER_LIFT[kind]·df, 0, 1)`。现有 `card_alpha/card_bright` 输出保留不删（兼容测试），但改注"弃用"。

### D3｜换算配方（四档锚点 + smooth(df) 插值）

`glass-a` 锚点按 kind×昼/夜取值（夜锚×昼锚之间以 smooth(df) 过黎明/黄昏）：

| kind | 昼锚 | 夜锚 |
|---|---|---|
| 晴/大部晴 | .58 | .50 |
| 多云 | .56 | .52 |
| 阴 | .57 | .54 |
| 雨 | .60 | .66 |
| 大雨 | .62 | .70 |
| 雷 | .64 | .74 |
| 雪/雾 | .58/.58 | .58/.62 |

四档观感与全 token 值：

| token | 白天晴 | 阴天(昼) | 晴夜 | 雨夜(大雨) |
|---|---|---|---|---|
| 驱动(df,g) | .95, 0 | .60, .14 | .03, 0 | .03, .45 |
| --glass-a | .58 | .57 | .50 | .70 |
| --sheen-a | .07 | .05 | .03 | .03 |
| --edge-w | .15 | .10 | .05 | .05 |
| --glow-c | .30 | .52 | .95 | .92 |
| --shadow-k | .53 | .72 | 1.03 | 1.09 |
| --well-a | .04 | .06 | .06 | .08 |
| --tx-sec | 抬升大 | 抬升中 | 近基准 | 近基准 |
| --tx-muted | 抬升 .35 | 抬升 .20 | 抬升 .15 | 抬升 .16 |

- 白天晴：青蓝底叠金日天空，卡面 α.58 + 顶部 .07 高光 + 白描边 .15，青 glow 收至 .30，影浅，副文本微抬——整页"阳光通透、清爽克制"，通透感由高光与亮边表达，不靠低 α。
- 阴天：中性玻璃 α.57、高光 .05、描边 .10、glow 中位——灰调匀净无锋芒，沉浸工作态。
- 晴夜：墨蓝底 + 星月，α.50 通透玻璃 + 发丝亮边 + 青 glow .95，影深——冷峻高对比。
- 雨夜（大雨/雷）：α.70~.74 厚实玻璃、高光收敛 .03、中性边低调、霓虹 .92 如雨夜灯、影子最深、凹区加深、背景近黑——沉静安稳的"雨夜仪表舱"。

### D4｜玻璃明度安全域（防对比跌破）

- 恒等式：有效面亮度 `L_eff = L_card·α + L_sky·(1−α)`（L_card≈0.007）。sky 亮度估表（内容区均值）：晴昼 .12 / 阴昼 .08 / 雨昼 .06 / 各夜 ≈.012。
- 保证线：primary(L≈.66)≥7:1 无需担心；**secondary(L≈.37) 需 ≥4.5:1** → 反解 `L_eff ≤ (L_t+.05)/4.5 − .05 ≈ .043` → 晴昼 α≥.60、夜 α≥.46；**muted 不承诺 4.5**，只承诺 ≥3:1（感知不跌破），因此 muted 永远只用于 caption 级辅助文字，此条写入 CSS 注释与规范。
- 安全带结论：α 全局 clamp `[0.46, 0.74]`（配方内置）；卡片承载正文/标签时走夜锚或昼锚高值，轻容器（chip/pill/stepper node）可低于此带——但它们的文字是强色/大号，不受 4.5 约束。
- L_sky 若偏离估表：不推 α 补偿逻辑（避免叠床架屋），改依赖 tx-sec/tx-muted 抬升兜底（上限 0.1 内）。

### D5｜失效兜底（三级）

1. 单次 tick 异常：**保留 `session_state["dn_prev"]` 不清除**（现 `_day_night_tick` 的 `except` 里 `pop` 是缺陷），跳过本次沿用上轮变量。
2. 首帧/网络全挂、什么都不注入：APP_CSS `:root` 的字面默认值＝今日静态深蓝主题（bg #0A1120、glass .52、霓虹常量）——即当前可用视觉，天然高对比，自动降级为"深夜模式"，不破版。
3. 浏览器能力缺失：全程不用 color-mix；`rgba()+calc()+var()` 为 Edge 106+ 稳定能力；既有 `@supports not (backdrop-filter)` 实色兜底保留。无其它能力分支。

## 可执行变更

按序落地 6 步（每步独立可回滚，第 1~2 步完成后即获得"全主题呼吸"）：

1. **day_night.py**：新增 `GLOOM` 表与 `ambience_vars(kind, v: dict) -> dict`：读取 `_WEATHER_LIFT`/`GLOOM`/传入的 day_factor，产出 D2 表全部 12 token（`bg_color_for` 混色上限改 0.6，α 走 D3 锚点表 + smooth(df)）。`css_vars_block` 在既有输出后追加新 token（保留旧键兼容测试断言）。
2. **ui_theme.py（APP_CSS）**：把所有氛围常量替换为 token 引用——.panel/.floating-card/.fx-card/[data-testid="stMetric"]/.telemetry-metric/[data-testid="stExpander"] details 的填充尾色改 `rgba(9,13,26,var(--glass-a,0.52))`；侧边栏渐变改 `var(--glass-a,0.52)` 基值 +0.04；三类描边写 `rgba(255,255,255,var(--edge-w,0.09))` 与 `rgba(0,240,255,var(--edge-acc,0.5))`；阴影/glow token 的 alpha 改 `calc(基值 × var(--glow-c,0.8))`、`calc(基值 × var(--shadow-k,1.0))`；输入凹区改 `rgba(255,255,255,var(--well-a,0.05))`；`--text-secondary/--text-muted` 改 `var(--tx-sec,…)/var(--tx-muted,…)`。**不动**：telemetry-log、stCodeBlock（事实层恒定）、全部 hover/active/首帧常量、模糊半径与张数（性能预算不变）、emoji 禁令。
3. **app.py**：`_day_night_tick` 与 `dn_boot` 两处注入由单变量 `--bg-color` 换成 `css_vars_block(ambience_vars(kind, _vars0))` 全块（kind 取自 `describe(get_weather())`）；删除 except 中的 `dn_prev` pop。注入仍只在首帧与 60s tick fragment，不进 2s 轮询区。
4. **过渡策略（防"变脸"）**：.panel 等保留 box-shadow/border-color 的既有 0.15~0.22s transition——每 60s 一次的 token 变化产生的是平滑渐变而非 2s 循环重放动画，属氛围品质允许；监控轮询区（stepper/telemetry-log）不新增任何动画与注入。
5. **文本层兜底**：`--tx-muted` 抬升封顶 0.45 插值且永不上移为可承载正文的层级；CSS 注释写明"muted 仅限 caption 级"。若后续发现晴昼某标签对比存疑，优先调 D3 昼锚 α 而非破文字常量。
6. **验收清单**：用侧栏预览覆盖四档（晴昼=clear:1、阴=cloudy:1、晴夜=clear:0、雨夜=heavy_rain:1），检查①三 Tab 卡片/输入/侧栏/stepper 同步呼吸 ②终端与 hover 反馈稳定 ③对比抽检：卡片正文 ≥7:1、标签 ≥4.5:1、α 落在 [0.46,0.74] ④无 2s 闪烁、无新增 blur 张数 ⑤拔网/停天气后回到静态深蓝不破版。

落地后量级：Python 净增 ~60 行（GLOOM + 派生函数 + 注入改造），CSS 净改 ~25 处常量引用，0 个新依赖、0 个新框架。
