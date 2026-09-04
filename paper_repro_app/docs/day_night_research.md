# Research: 桌面应用实时白天黑夜系统（Day/Night Cycle）工程规范

> 摘要：本规范给出不依赖外部库的太阳位置纯数学算法（NOAA 简化法，误差约 ±0.2°；备用两档回退模型），把一天划成 9 个阶段并数值化给出每个阶段的天空三色渐变、日月屏幕坐标、霓虹 glow、玻璃卡透明度与参考钟面；过渡采用“事件锚点 + 时间轴 smoothstep 混合”，60 秒 tick 足够，仅写 CSS 变量不动 DOM。所有规则给出可复制代码/伪代码，并附带对比度红线与降级策略。

---

## A. 天文与昼夜判定模型（纯数学）

### A.0 约定与输入

| 符号 | 含义 | 单位/约定 |
|---|---|---|
| φ (lat) | 纬度 | 北纬为正，度 |
| λ (lon) | 经度 | 东经为正，度 |
| N | 年内天数 | 1 月 1 日 = 1 |
| UTC_hours | 当日 UTC 小时 | 含分钟小数，如 2.25 = 02:15 |
| δ | 太阳赤纬 | 弧度（对外输出转度） |
| H | 时角 | 弧度，正午 = 0，下午为正 |
| h | 太阳高度角 | 度，地平线以上为正（本规范白昼判据用 h>0） |

推荐：内部统一以 **UTC 时刻 + 经纬度** 计算（不依赖系统时区，避免时区/夏令时坑）；屏幕展示再转本地钟面。若只给本地时间，需同时给时区偏移 tz_off 小时（UTC = local − tz_off）。

### A.1 太阳赤纬 / 时角 → 高度角（推荐实现，NOAA 简化法）

年角 γ（含小数小时，供日内连续插值）：

```text
γ = 2π/365 × (N − 1 + (UTC_hours − 12)/24)          # 弧度

均时差 EoT（分钟）：
EoT = 229.18 × (0.000075
       + 0.001868·cos γ − 0.032077·sin γ
       − 0.014615·cos 2γ − 0.040849·sin 2γ)

赤纬 δ（弧度）：
δ = 0.006918 − 0.399912·cos γ + 0.070257·sin γ
  − 0.006758·cos 2γ + 0.000907·sin 2γ
  − 0.002697·cos 3γ + 0.00148·sin 3γ

真太阳时（小时）：
TST = UTC_hours + λ/15 + EoT/60

时角：H = 15° × (TST − 12)        # 度

高度角：
sin h = sin φ·sin δ + cos φ·cos δ·cos H
h     = asin(上式)，clamp 到 [−90°, 90°]
```

- 白昼判据：`h > 0°`（几何日心在地平线上）。
- **日出/日没视觉时刻**用 `h = −0.833°`（太阳半径 0.2666° + 大气折射约 0.5667°，NOAA 约定）。做阶段锚点建议用 −0.833°，做“白天/黑夜”布尔开关按任务要求用 0°（两者相差约 3–5 分钟，可忽略）。
- 精度说明：本式未计岁差/章动/光行差，高度角误差约 ±0.2°，对 UI 显示绰绰有余；如需更高精度（<0.01°）用 NREL SPA 算法（见 F 参考 [4]）。

方位角（自北顺时针，下午镜像修正——最易写错的一步）：

```text
cos A = (sin δ − sin h·sin φ) / (cos h·cos φ)      # h≠±90°
A     = acos(clamp(上式,−1,1))                       # 0..180°
if H > 0: A = 360° − A                              # 下午取西侧镜像
```

自检例（φ=40°N、δ=0、正午）：h=50°，A=180°（正南）✓；上午 A≈147°（东南）✓。

Python 直抄版：

```python
from math import sin, cos, asin, acos, radians, degrees, pi

def clamp(x, lo=-1.0, hi=1.0):
    return max(lo, min(hi, x))

def solar_elevation_azimuth(day_of_year, utc_hours, lat, lon):
    g = 2*pi/365 * (day_of_year - 1 + (utc_hours - 12)/24)
    eot = 229.18*(0.000075 + 0.001868*cos(g) - 0.032077*sin(g)
                  - 0.014615*cos(2*g) - 0.040849*sin(2*g))          # min
    dec = (0.006918 - 0.399912*cos(g) + 0.070257*sin(g)
           - 0.006758*cos(2*g) + 0.000907*sin(2*g)
           - 0.002697*cos(3*g) + 0.00148*sin(3*g))                   # rad
    tst = utc_hours + lon/15.0 + eot/60.0                            # 真太阳时
    H   = radians(15.0*(tst - 12.0))
    phi = radians(lat)
    s_alt = clamp(sin(phi)*sin(dec) + cos(phi)*cos(dec)*cos(H))
    alt   = degrees(asin(s_alt))
    denom = cos(alt*pi/180)*cos(phi)
    az    = 0.0
    if abs(denom) > 1e-9 and abs(alt) < 89.9:
        az = degrees(acos(clamp((sin(dec) - sin(alt*pi/180)*sin(phi))/denom)))
        if H > 0: az = 360.0 - az
    return alt, az
```

日出/日没时刻 = 在 0..24h 上对 `h(now)=−0.833°` 做二分查找（20 次迭代即达秒级精度），每天 00:00 缓存一次即可：

```python
def find_crossing(day, lat, lon, lo_h=0.0, hi_h=24.0):
    for _ in range(30):
        mid = (lo_h + hi_h)/2
        if solar_elevation_azimuth(day, mid, lat, lon)[0] > -0.833:
            hi_h = mid          # 已在地平线上 → 收缩上限（找日出）
        else:
            lo_h = mid
    return (lo_h + hi_h)/2      # 返回当日日出/日没的 UTC 小时
```

### A.2 晨昏（Twilight）阈值表

以太阳中心高度角为准（负值 = 地平线下）：

| 术语 | 太阳高度角阈值 | 现象（建议映射到 UI 的锚点） |
|---|---|---|
| 民用曙暮光 Civil | h = **−6°** | 地平线清晰可辨、大字可读；UI 上“天边第一抹光带” |
| 航海曙暮光 Nautical | h = **−12°** | 海天线不可辨但可辨轮廓；UI 上“深蓝渐浓，月亮全亮” |
| 天文曙暮光 Astronomical | h = **−18°** | 天空全黑（天文上“夜”开始）；UI 上“深宵”色调起点 |
| 日出/日没（视觉） | h = **−0.833°** | 太阳上缘贴地平线，作为阶段调色锚点 |
| 白昼（本规范布尔） | h > **0°** | 太阳几何中心在地平线上 |

### A.3 无位置回退：两档模型（都必须可运行）

**档位① 有经纬度（精确）**：用 A.1 全式 + 事件锚点（日出/日没/正午），下文 B/C 全部基于它。

**档位② 仅系统本地时间（简化）**——没有 lat/lon 时，取“名义纬度”`φ_nom = 32°`（约全球人口加权纬度，视觉效果对大多数中低纬地区合理），季节由赤纬近似给出：

```text
δ ≈ 23.44° × sin(360° × (284 + N) / 365)      # Cooper 近似，误差 < ±0.5°
时角（忽略 EoT 与经度，正午=12:00 本地）：
H = 15° × (local_hour − 12)
sin h = sin 32°·sin δ + cos 32°·cos δ·cos H
日出/日没角：ω0 = acos(−tan 32°·tan δ)
日出 = 12 − ω0/15 小时；日没 = 12 + ω0/15 小时（本地钟面）
```

示例核对（φ=32°N）：春/秋分 δ=0 → 日出 06:00、日没 18:00、昼长 12h；夏至 δ=+23.44° → ω0≈105.7° → 昼长 ≈14.1h、日出 ≈04:57、日没 ≈19:03；冬至 → 昼长 ≈9.9h、日出 ≈07:03、日没 ≈16:57。档位② 的定时误差来源 = 忽略 EoT（±16 min）与经度/时区偏移，UI 上可接受；如 app 能拿到 `time.timezone` 标准子午线 λ_std，则用 `H=15°×(local+4·(λ_std−0)/60 …)` 无意义（无本地经度），故推荐直接忽略并在设置页提示“未定位 → 约 ±15 分钟误差”。

**极昼/极夜（两档都要兜底）**：若当日 `max(h) < 0` → 全天按“夜晚”调色（可叠加月光底）；若当日 `min(h) > 0` → 全天按“白天”调色、把太阳高度归一化到 [0, h_max] 模拟低角“午夜太阳”；两态都取消阶段切换、只做慢速亮度呼吸（周期 24h）。

---

## B. 昼夜阶段与时间线色板（核心）

### B.0 设计总则（深色主题下的“暗色白天”）

1. 画面基座永远是深色（#05070f 量级），白天不“变亮到接近浅色”，而是**让天空色相转青蓝、粒子/亮度因子抬升、霓虹收窄**——UI 文字永不失去对比（见 D.4 红线）。
2. 用一个 0..1 的全局 `--day-factor` 驱动亮度：粒子层亮度 = `lerp(0.85, 1.18, day_factor)` 乘原值；任何天空渐变色的 sRGB 相对亮度建议 `≤0.20`（只有黄金/日间地平线高光条可到 0.20–0.35，且只出现在画面下缘 15–20% 高度、通常被玻璃卡覆盖的区域）。
3. 天空用三段线性渐变（顶→55%→地平线），各段给独立 HEX，便于 CSS 变量逐帧混合。

### B.1 九阶段定义（太阳高度 h 为主键，事件偏移为参考）

边界（°）：`−18 / −6 / +6 / +25 / +25(降) / +6 / −4 / −8 / −18`

| 阶段 | 名称（id） | h 范围（°） | 参考钟面（日出06:00/日没18:00，φ≈35°N 春秋分近似） |
|---|---|---|---|
| P1 | 深宵 DeepNight | h < −18 | 00:00–04:30 与 19:30–24:00 |
| P2 | 黎明前 PreDawn | −18 ≤ h < −6（上升） | ≈04:30–05:30 |
| P3 | 日出黎明 SunriseDawn | −6 ≤ h < +6（上升，含 06:00 日出） | ≈05:30–06:30 |
| P4 | 清晨 Morning | +6 ≤ h < +25（上升） | ≈06:30–08:05 |
| P5 | 正午白天 Midday | h ≥ +25（上升段与下降段合并） | ≈08:05–15:55 |
| P6 | 午后 Afternoon | +25 ≥ h > +6（下降） | ≈15:55–17:30 |
| P7 | 日落黄金 GoldenDusk | +6 ≥ h > −4（下降，含 18:00 日没） | ≈17:30–18:20 |
| P8 | 蓝调黄昏 BlueHour | −4 ≥ h > −8（下降） | ≈18:20–18:40 |
| P9 | 夜晚 Nightfall | −8 ≥ h ≥ −18（下降） | ≈18:40–19:30，之后回到 P1 |

> 参考钟面只是“示意”，勿硬编码：真实边界一律由 A.1 事件锚点算出（P3 起点 = 日出−30min、P7 终点 = 日没+20min 等偏移见 C.1 事件表）。高纬冬夏偏移会显著伸缩，算法自适应；高纬冬季正午 h_max<25° 时，P5 窗口收缩为 `h ≥ h_max − 8°`。

### B.2 天空渐变三色表（顶 / 中55% / 地平线），全部符合“暗色调和”

| 阶段 | 顶 Top | 中 Mid (55%) | 地平线 Horizon | day_factor | 星 alpha | 说明 |
|---|---|---|---|---|---|---|
| P1 深宵 | `#03050D` | `#070C1D` | `#0D1530` | 0.00 | 1.0 | 深蓝黑，青味极淡 |
| P2 黎明前 | `#060B1C` | `#0E1D3E` | `#1E3F6E` | 0.08 | 0.85 | 地平线透出青蓝 |
| P3 日出黎明 | `#0A1128` | `#22375F` | `#D79B4E` | 0.30 | 0.5 | 暖金破晓带（黄金晨） |
| P4 清晨 | `#16294C` | `#2C4770` | `#5A7394` | 0.60 | 0.15 | 天转青蓝但压暗 |
| P5 正午白天 | `#24406B` | `#33547F` | `#5F7BA0` | 1.00 | 0 | 全天最亮（仍深） |
| P6 午后 | `#1A2C4E` | `#2B4260` | `#CF9A5A` | 0.60 | 0.15 | 地平线开始暖化 |
| P7 日落黄金 | `#0C1230` | `#33305C` | `#FF9E4F` | 0.35 | 0.4 | 橙金+品红折射，最强暖带 |
| P8 蓝调黄昏 | `#070E2C` | `#123464` | `#3D5F9E` | 0.12 | 0.75 | 深宝蓝，含青 #00f0ff 余晖（可选地平线叠加 `rgba(0,240,255,.10)`） |
| P9 夜晚 | `#050A1E` | `#0B1736` | `#1E3258` | 0.04 | 0.95 | 蓝调退去、夜色复浓 |

颜色审计：以上顶色 sRGB 相对亮度 L≈0.01–0.05、中色 L≈0.03–0.09、地平线 L≤0.16（除 P3/P7 暖带 L≈0.25–0.35 且仅在画面下缘 15%），全部满足 D.4 红线前提（正文永远浮在玻璃卡上，不直接压在天色上）。

### B.3 太阳 / 月亮屏幕位置与 alpha

太阳与月亮对象（现有粒子层）用两个 div/对象各自独立控制，属性 = `--sun-x/--sun-y/--sun-a`、`--moon-x/--moon-y/--moon-a`（百分比，相对窗口或画布）。

太阳（屏幕弧线 = 真实方位角 + 高度角的映射，北半球示例）：

```text
A_noon = 180°（φ>0 正南）；φ<0 用 A_noon=0°（正北）
x% = 50 + 50·sin(radians(A − A_noon))        # 东(左) → 中(正午) → 西(右)
h_max = 90 − |φ − δ|                          # 当日正午最大高度
y% = 72 − 64·clamp(sin(radians(max(h,0))) / sin(radians(max(h_max,5))), 0, 1)
# 72% = 地平线高度、8% = 天顶，可换算任意画布：y = HOR_Y − (HOR_Y−TOP_Y)·ratio
--sun-a：h ≥ −0.833 时 = 1；−0.833 > h ≥ −6 时按 (h+6)/5.167 淡出到 0
--sun-r：建议 4–6 vmin（黄昏可加大 1.3×）
```

月亮（无月相星历时的视觉近似——够用、可抄；有天气缓存月相数据则直接替换）：

```text
月亮方位 ≈ 太阳方位 + 180°（太阳西沉→月亮东升的自然观感）
月亮高度角 ≈ min(50°, 20 + 20·cos(radians(月龄相位角)))   # 满月高、新月低；无相位数据取固定 40°
--moon-a：day_factor < 0.15 时 = 1；0.15–0.30 线性淡出；> 0.30 → 0（太阳同现则月亮隐藏）
--moon-r：建议 2.5–3.5 vmin
```

联动铁律（对应需求“深夜太阳消失/月亮出现”）：**太阳与月亮 alpha 之和在黄昏/黎明交叉带做 10–30 分钟双向渐变（CSS transition 2000ms 只负责帧间平滑），任何时刻两者可短暂同框但不会硬切。**

### B.4 霓虹 glow 系数表（青 #00f0ff / 品红 #ff2a6d / 黄 #ffce00 的发光强度 0..1）

含义：`--glow-*` 作为 UI 中 `text-shadow`、边框光晕、扫描线等霓虹层的整体乘数（每 60s 更新一次；发光用 `filter: drop-shadow` 或 `box-shadow` 已现成样式乘数即可，不做每帧动画）。

| 阶段 | 青 glow | 品红 glow | 黄 glow | 设计意图 |
|---|---|---|---|---|
| P1 深宵 | 0.85 | 1.00 | 0.40 | 夜晚赛博感最强，品红主导 |
| P2 黎明前 | 0.70 | 0.80 | 0.35 | 仍暗，青蓝微醒 |
| P3 日出黎明 | 0.50 | 0.45 | 0.75 | 暖色初升，黄抬头 |
| P4 清晨 | 0.35 | 0.25 | 0.55 | 光强增、霓虹收 |
| P5 正午白天 | 0.30 | 0.20 | 0.45 | 全天霓虹最弱（靠清晰度而非光晕） |
| P6 午后 | 0.35 | 0.30 | 0.60 | 暖意回归 |
| P7 日落黄金 | 0.45 | 0.55 | 1.00 | 黄金时刻黄到顶、品红折射 |
| P8 蓝调黄昏 | 0.75 | 0.80 | 0.30 | 蓝调时刻青品回涌 |
| P9 夜晚 | 0.80 | 0.95 | 0.35 | 夜色霓虹复苏 |

### B.5 玻璃卡底色 alpha 与提亮系数

规则：`--card-alpha`（卡片底色不透明度）与 `--card-bright`（内容提亮百分比）随 phase 表线性取值：

| 阶段 | card-alpha | card-bright | 备注 |
|---|---|---|---|
| P1/P9 夜晚段 | 0.50 | 0% | 保持通透感看星星 |
| P2/P8 | 0.50–0.52 | +2% | |
| P3/P7（金/黄昏） | 0.52 | +4% | 透一点暖光 |
| P4/P6 | 0.55–0.56 | +6% | |
| P5 正午 | **0.60** | **+8%** | 白昼最实，遮蔽亮地平线 |

实现建议：卡片样式 `background: rgba(9,13,26,var(--card-alpha)); backdrop-filter: blur(14px) saturate(1.2) brightness(calc(1 + var(--card-bright)*0.01)); border: 1px solid rgba(0,240,255,calc(0.10 + 0.06*var(--day-factor)))`。注意卡片底色本身保持暗色不变（只动 alpha），文字色恒为 `#E8F4FF` 体系——这正是可读性红线的结构保证。

### B.6 九阶段一览（直接复制进实现的“示意表”）

| 阶段 | 时间窗 | 天空(顶/中/地) | 太阳 | 月亮 | 玻璃α | dayF |
|---|---|---|---|---|---|---|
| P1 深宵 | 00:00–04:30, 19:30–24:00 | #03050D/#070C1D/#0D1530 | 无 | 高亮 1.0 | .50 | 0.00 |
| P2 黎明前 | 04:30–05:30 | #060B1C/#0E1D3E/#1E3F6E | 无 | .85 | .50 | 0.08 |
| P3 日出黎明 | 05:30–06:30 | #0A1128/#22375F/#D79B4E | 地平线渐显 | .50 | .52 | 0.30 |
| P4 清晨 | 06:30–08:05 | #16294C/#2C4770/#5A7394 | 东侧低空 | 淡 | .55 | 0.60 |
| P5 正午白天 | 08:05–15:55 | #24406B/#33547F/#5F7BA0 | 天顶偏南 | 无 | .60 | 1.00 |
| P6 午后 | 15:55–17:30 | #1A2C4E/#2B4260/#CF9A5A | 西侧中低空 | 淡 | .55 | 0.60 |
| P7 日落黄金 | 17:30–18:20 | #0C1230/#33305C/#FF9E4F | 西地平线 | .40 | .52 | 0.35 |
| P8 蓝调黄昏 | 18:20–18:40 | #070E2C/#123464/#3D5F9E | 已没、余晖 | .75 | .50 | 0.12 |
| P9 夜晚 | 18:40–19:30 | #050A1E/#0B1736/#1E3258 | 无 | .95 | .50 | 0.04 |

---

## C. 平滑过渡算法

### C.1 时间轴模型：事件锚点 + 相邻相位 keyframe 混合

不做“到点切阶段”，而是把一天建成 **12 个边界事件**（分钟制，来自 A.1 算出的真实日出 RS / 日没 SS，并缓存），白天黑夜每 60s 求一次 `(当前相位, u∈[0,1])` 并对相邻两相位调色板做平滑混合：

```text
事件表（分钟，一天 0..1440）：
  e0  = 0          （P1 深宵起点）
  e1  = RS − 90    （P1→P2，h=−18°）
  e2  = RS − 30    （P2→P3，h=−6°）
  e3  = RS + 30    （P3→P4，h=+6°）
  e4  = RS + 125   （P4→P5，h=+25°）
  e5  = SS − 125   （P5→P6，h=+25° 下降）
  e6  = SS − 30    （P6→P7，h=+6°）
  e7  = SS + 20    （P7→P8，h=−4°）
  e8  = SS + 40    （P8→P9，h=−8°）
  e9  = SS + 90    （P9→P1，h=−18°）
  e10 = 1440
# RS=日出、SS=日没（h=−0.833° 二分求出）。极昼/极夜走 A.3 兜底。
```

> 偏移分钟数是按 φ≈35°、|dh/dt|≈0.2°/min 的典型值标定；若想完全精确，直接以 h 落入 B.1 的区间为唯一判据（主键），事件表只用于取“相位内进度 u”与 keyframe 参考钟面——推荐后者（h 判据天然连续、无地理失效）。

插值与防跳变（伪代码）：

```python
def sample_sky(now_min, events, palettes):
    i = 上一个边界索引            # events[i] ≤ now < events[i+1]
    u = (now - events[i]) / (events[i+1] - events[i])
    u = clamp01(u)
    s = smoothstep(u)            # s = u*u*(3-2u)，见下
    A = palettes[phase_of(i)]    # 当前相位 keyframe
    B = palettes[phase_of(i+1)]  # 下一相位 keyframe
    return {
      "top":  mix_color(A.top,  B.top,  s),   # 建议在 sRGB→线性→Oklab 域混色
      "mid":  mix_color(A.mid,  B.mid,  s),
      "hor":  mix_color(A.hor,  B.hor,  s),
      "day_factor": A.day_factor + (B.day_factor-A.day_factor)*s,
      ...   # glow / card-alpha 同法
    }

def smoothstep(x): return x*x*(3-2*x)
```

防跳变硬规则：
1. 任何输出变量单 tick 变化量限幅：`Δday_factor ≤ 0.02/60s`、颜色通道 Δ ≤ 6/255/60s（超限则夹取）——从根上杜绝“亮度突变”。
2. 相位回卷（跨 1440↔0）只允许在 P1 内部发生；若 h 抖动穿越边界，用 ±0.25° 迟滞带 + 相位标签 30s 去抖（只影响图标/文案，不影响颜色——颜色本就是连续混的）。
3. 颜色在 **线性 RGB 或 Oklab** 里做 lerp，再转回 sRGB HEX（避免 HSL 的色相环绕与暗部发灰）。纯 HEX 表 → 每 60s 预计算一次线性分量缓存，运行时只做加权。

### C.2 计算频率

| 项 | 结论 |
|---|---|
| 基础 tick | **60 秒足够**。太阳高度在晨昏最快也仅 ~0.2–0.3°/min，对应天空色每 60s 变化 < 1–2 ΔE，肉眼不可察觉 |
| 晨昏高频 | 在日出/日没 ±45 min 窗口内建议提到 **10–20s**（此时相变最显著；可用 `e1..e7` 事件表判断是否在窗内） |
| 服务端 vs 前端 | 这是**本地桌面** app：优先**前端本地时钟**（无网络往返、无时区歧义）。但 Streamlit 的 `st.markdown` 会剥离 `<script>`，直接 JS 注入不可行（见下）。可行方案：**(a) Python 兜底默认**：60s 更新一次 CSS 变量（推荐用 `@st.fragment(run_every="60s")` 只重跑片段，不整页 rerun）；**(b) JS 精确时钟**：用自定义组件（`components`）把窗口改成同源可访问 `window.parent.document.documentElement.style.setProperty(...)`（组件 iframe 默认 sandbox 无 allow-same-origin 时会被拦，需要 `streamlit.components.v1.html(..., scrolling=False)` 测试同源可达性——不可达则退回 (a)） |
| 结论 | 交付物内默认 Python 线程/片段每 60s 推 CSS 变量；JS 版作为可选的“本地体验增强”，两者共用同一 `sample_sky()` 数学内核 |

### C.3 过渡时长与动画性能

- 因为颜色是“每 60s 直接写新值”，本身即连续渐变，**不需要**再叠加 20–40 分钟的阶段切换动画；真正需要 CSS transition 的只有三类快速属性：日月 alpha 淡入淡出（`transition: 2000ms ease`）、星星 alpha（`3000ms`）、霓虹 glow（`4000ms`）。
- 性能红线：**禁止每帧改全屏背景/重绘整个 Canvas**。天空渐变用**一个** `position:fixed; inset:0; z-index:-2` 的 div，其 `background-image` 由三个独立色层合成：`.sky-stop`（顶/中/地平）三层各 100% 高的 div 叠放 + `mix-blend` 或直接 `linear-gradient` 双份背景 + CSS `background` 更新——最省做法是**直接写三层不透明度层**：每层纯色、`height` 由变量控制（顶 30%、中 30–55%、地平 55–100%），只改 `background-color`（可被 CSS transition 平滑），不触发合成之外的开销。
- 天气粒子 Canvas 照常逐帧渲染，与昼夜系统解耦：昼夜只改 **CSS 变量 + 一个 sky 层颜色 + 粒子亮度乘数变量**（粒子 shader/ctx 里每帧读 `--day-factor` 的低频缓存值即可，不要每帧去读 DOM）。
- 增加一层“呼吸”：`--day-factor` 变化本身不做逐帧 JS，直接由 60s tick 驱动；帧循环只负责已有天气动画。

### C.4 时钟源与两套注入

JS 建议骨架（组件内自包含计算，同源时可选写父窗口）：

```js
function tick(){
  const now = new Date();
  const localH = now.getHours() + now.getMinutes()/60;
  const [alt, az] = solarNow(now, LAT, LON);      // 移植 A.1 的 ~20 行公式
  const sky = sampleSky(dayEvents(now), alt, localH);  // 与 Python 同表同函数
  const root = document.documentElement;
  for (const [k,v] of Object.entries(sky)) root.style.setProperty(`--${k}`, v);
}
setInterval(tick, (isNearSunEvent()? 15000 : 60000));  // 晨昏加速
tick();
```

Python 注入骨架（默认实现）：

```python
def render_css_vars(v):
    st.markdown(f"""
    <style>
    :root{{
      --day-factor:{v.day_factor:.3f};
      --sky-top:{v.top}; --sky-mid:{v.mid}; --sky-hor:{v.hor};
      --sun-x:{v.sun_x:.0f}%; --sun-y:{v.sun_y:.0f}%; --sun-a:{v.sun_a:.2f};
      --moon-x:{v.moon_x:.0f}%; --moon-y:{v.moon_y:.0f}%; --moon-a:{v.moon_a:.2f};
      --glow-c:{v.glow_c:.2f}; --glow-m:{v.glow_m:.2f}; --glow-y:{v.glow_y:.2f};
      --card-alpha:{v.card_a:.2f}; --card-bright:{v.card_b:.0f}%;
      --star-alpha:{v.star_a:.2f};
    }}
    </style>""", unsafe_allow_html=True)

# 主线程每 60s（或晨昏窗 15s）取一次采样并调用 render_css_vars
```

---

## D. 与天气 / UI 协同规则

### D.1 晴空联动
- 白昼（day_factor ≥ 0.5）：太阳对象位置 = `(--sun-x,--sun-y)`，从日出东侧(≈8%,72%)沿弧线到正午(50%,8–20%)再到西侧(≈92%,72%)，尺寸午间略小、晨昏放大约 1.3 倍加光晕。
- 夜间（day_factor < 0.2）：太阳隐藏（alpha→0），月亮+星星 alpha 按 `--star-alpha`；月相若无数据按满月视觉近似（B.3）。
- 星星只在 P1/P2/P9/P8(低) 全亮；P3/P7 减半；P4/P6 仅个别亮星；P5 全关。

### D.2 阴雨/雪/云：只调亮度色温，不改粒子类型
- 云/雨/雪粒子类型**与昼夜无关**，由既有天气状态决定。
- 昼夜只叠加：粒子亮度乘数 = `0.55 + 0.45·day_factor`（阴天 max 额外 ×0.85）；云底光 tint：白天乘 `rgba(255,220,190,0.08)`，夜晚乘 `rgba(0,240,255,0.06)`（用 `globalCompositeOperation` 或 shader uniform 每帧读一次即可）；雨滴/雪片在 P1/P9 降低对比度（×0.8）。
- 闪电（若有）：只与天气有关，夜晚出现时把 `--day-factor` 临时抬到 0.15 并 1.5s 回弹（单次覆盖，不影响相位状态机）。

### D.3 UI 注入契约（CSS 变量总表）

| 变量 | 含义 | 单位/类型 | 更新频率 |
|---|---|---|---|
| `--dn-t` | 日进度 0..1（秒/86400） | float | 60s |
| `--day-factor` | 0 夜 → 1 午 | float | 60s |
| `--sky-top / --sky-mid / --sky-hor` | 天空三色 | HEX | 60s |
| `--sun-x / --sun-y / --sun-a` | 太阳屏幕坐标与透明度 | % / % / 0..1 | 60s（晨昏 15s） |
| `--moon-x / --moon-y / --moon-a` | 月亮同上 | % / % / 0..1 | 60s |
| `--star-alpha` | 星空不透明度 | 0..1 | 60s |
| `--glow-c / --glow-m / --glow-y` | 青/品红/黄霓虹乘数 | 0..1 | 60s |
| `--card-alpha / --card-bright` | 玻璃卡透明度 / 提亮% | 0..1 / % | 60s |
| `--particle-bright` | 天气粒子亮度乘数 | float | 60s |

用法示例：正文霓虹 `color:#E8F4FF; text-shadow: 0 0 calc(6px*var(--glow-c)) rgba(0,240,255,calc(.55*var(--glow-c)))`；扫描线/装饰可再乘 `calc(0.2 + 0.8*var(--glow-m))`。

### D.4 可读性红线（任何时候正文对比度 ≥ 4.5:1 的近似实现）

WCAG 1.4.3 AA：正文 ≥ 4.5:1、大字号/粗体 ≥ 3:1、纯装饰豁免。快速公式：

```python
def lin(c):              # c ∈ 0..255
    c = c/255
    return c/12.92 if c <= 0.04045 else ((c+0.055)/1.055)**2.4
def L(rgb): return 0.2126*lin(rgb[0]) + 0.7152*lin(rgb[1]) + 0.0722*lin(rgb[2])
def contrast(a, b): return (max(L(a),L(b)) + 0.05) / (min(L(a),L(b)) + 0.05)
```

工程上三条保证（不必逐帧计算）：
1. **正文永不直接压在天色上**：一律落在玻璃卡上；玻璃合成后相对亮度 ≤0.05（含最亮天空透射的最坏情形）时，`#E8F4FF`（L≈0.89）对比度恒 ≥ (0.89+0.05)/(0.05+0.05) ≈ 9.4:1，远超 4.5:1。
2. 白天天空不“亮到浅于文字”：全天空色 L≤0.20，地平线高光带只在 y>78%（玻璃覆盖区）出现；`--card-bright ≤ +8%` 只提亮卡片内部浅色（文字保持 #E8F4FF 不变暗）。
3. 验收自检：拿上述 `contrast()` 扫一遍“天空最亮色 × 玻璃 α=0.60”合成色 vs 正文色 ≥ 4.5；用 `st.markdown` 灰度+色觉模拟截图检查一次即可。

---

## E. 实现清单与伪代码

### E.1 模块与函数清单

| # | 模块 | 内容 |
|---|---|---|
| 1 | `astro.py` | `solar_elevation_azimuth()`、`find_crossing()`、`day_length()`, δ/EoT/二档回退函数 |
| 2 | `schedule.py` | 事件表 `build_events(day, lat, lon)`（RS/SS 缓存）、极昼极夜兜底 |
| 3 | `palettes.py` | 9 相位 keyframe 常量表（B.2/B.4/B.5/B.6 全部数值） |
| 4 | `mixer.py` | `sample_sky(now) -> vars`；smoothstep + 线性域混色 + 限幅 |
| 5 | `inject.py` | `render_css_vars()`（st.markdown）与 CSS 模板 |
| 6 | `clock.py` | 主循环/`@st.fragment(run_every="60s")`；晨昏窗 15s |
| 7 | `ui.css` | 消费变量的全部现有样式（天空层、玻璃卡、霓虹） |
| 8 | `particles.js/canvas` | 读取低频缓存 `--particle-bright` 等，不逐帧读 DOM |

### E.2 昼夜状态机（含阶段查找，直接抄）

```python
PHASE_IDS = ["P1_DeepNight","P2_PreDawn","P3_SunriseDawn","P4_Morning",
             "P5_Midday","P6_Afternoon","P7_GoldenDusk","P8_BlueHour","P9_Nightfall"]

def phase_of_alt(alt):            # 主判据：h 区间（顺序重要，勿调整）
    if alt < -18: return "P1_DeepNight"
    if alt < -6:  return "P2_PreDawn"       # 上升期；下降期由同一区间得 P9？——
    # ——见下方说明：区间只判“视觉带”，上升/下降方向用 alt 差分决定取哪一侧相位
```

> 修正提示（重要）：同一 h 区间在上升与下降对应不同命名相位（P2 vs P9、P3 vs P7…），因此阶段查找必须携带方向：`rising = (现在 h − 60s 前 h) > 0`。推荐查表实现：

```python
def phase_of(alt, rising):
    if alt < -18: return "P1_DeepNight"                       # 深宵（不分方向）
    if alt < -6:  return "P2_PreDawn" if rising else "P9_Nightfall"
    if alt <  0:  return "P3_SunriseDawn" if rising else "P7_GoldenDusk"  # −6..0
    if alt < +6:  return "P3_SunriseDawn" if rising else "P7_GoldenDusk"  # 0..+6
    if alt < +25: return "P4_Morning" if rising else "P6_Afternoon"
    return "P5_Midday"                                          # h ≥ 25 双向合并
```

阶段序号按需做整数索引（P1=0 … P9=8），P9→P1 循环。

### E.3 主循环伪代码

```python
def main_loop():
    loc = load_ip_location_cache()          # 有 lat/lon → 档位①；无 → 档位②
    while True:
        now = local_now()
        if loc:
            ev = build_events(day, loc.lat, loc.lon)   # 每天 00:00 缓存
        else:
            ev = fallback_events(day)                  # φ=32° Cooper 近似
        alt, az = solar_elevation_azimuth(...)
        s = sample_sky(now_minute, ev, alt, az)        # mixer.py
        clamp_all_outputs(s)                           # 限幅防跳变
        render_css_vars(s)                             # inject.py
        sleep(15 if near_sun_event(ev, now) else 60)
```

### E.4 降级与无障碍

1. **无 JS**（Python 兜底即为默认实现）：全部逻辑在 Python 主循环，浏览器只负责渲染 CSS 变量。
2. **无定位**：档位②自动生效（B/C 全表照常跑）。
3. **极昼/极夜**：A.3 兜底，禁掉 RS/SS 事件二分（无交点时返回 None 处理）。
4. **`prefers-reduced-motion: reduce`**：星星闪烁、扫描线、霓虹呼吸全部停用或降为静态；日月 alpha 过渡缩为 1s；天空仍 60s 渐变（低频，属“非动画”信息变化，可保留）。
5. **性能**：天空只改背景色（不每帧重绘全屏）、粒子每帧只读低频缓存变量；60s tick 中任何一次渲染耗时目标 < 5ms（CSS 变量写入毫秒级）。
6. **时钟漂移**：本地时钟仅作显示源；如后续要精确同步可换成 NTP，架构已隔离（clock.py 单点替换）。
7. **测试口**：暴露调试参数 `--day-factor-override`/`--freeze-phase P7`，可手动冻结任意相位做截图回归。

---

## F. 参考来源 URL 列表（需人工复核）

> 重要声明：本次运行环境无网络检索工具，下列 URL 为依据长期稳定知名来源给出，**内容正确性均需人工复核**（尤其 NOAA 链接页面常有迁移）。核对方法：打开页面、比对 A.1 公式与文中阈值。

| # | 来源 | URL | 用途 | 复核点 |
|---|---|---|---|---|
| 1 | NOAA GML 太阳计算器（Solar Calculator）与公式文档 | https://gml.noaa.gov/grad/solcalc/ ；方程文档 https://gml.noaa.gov/grad/solcalc/solareqns.pdf | A.1 主公式、−0.833°、EoT/δ 系数 | URL 是否迁移；系数与本文一致 |
| 2 | NREL/SPA 论文（Reda & Andreas, 2004, NREL/TP-560-34302） | https://www.nrel.gov/docs/fy04osti/34302.pdf | 高精度算法备选（±0.0003°） | 如需高精度才采纳 |
| 3 | Wikipedia: Twilight | https://en.wikipedia.org/wiki/Twilight | −6/−12/−18 阈值与命名 | 阈值表与 A.2 一致 |
| 4 | Wikipedia: Blue hour / Golden hour (photography) | https://en.wikipedia.org/wiki/Blue_hour ；https://en.wikipedia.org/wiki/Golden_hour_(photography) | P7/P8 相位边界（−4/−8 等） | 相位窗口口径（各源 ±1–2° 差异） |
| 5 | Wikipedia: Solar elevation angle / Sun path | https://en.wikipedia.org/wiki/Solar_elevation_angle ；https://en.wikipedia.org/wiki/Sun_path | 方位角公式与半球翻转 | A_noon 半球约定 |
| 6 | WCAG 2.1/2.2 1.4.3 对比度 | https://www.w3.org/TR/WCAG22/#contrast-minimum | 4.5:1 红线 | 大字号 3:1 豁免口径 |
| 7 | MDN: CSS 自定义属性 / prefers-reduced-motion | https://developer.mozilla.org/en-US/docs/Web/CSS/Using_CSS_custom_properties ；https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion | CSS 变量注入与降级 | — |
| 8 | MDN / caniuse：background 渐变可动画性 | https://caniuse.com/css-gradients ；linear-gradient 兼容性页 | C.3“三层 div 代替渐变动画” | 各浏览器行为 |
| 9 | Streamlit 文档：fragments / components / markdown | https://docs.streamlit.io/develop/concepts/architecture/fragments ；https://docs.streamlit.io/develop/api-reference/components | E 的 st.fragment 60s 注入与组件同源限制 | run_every 语法版本 ≥1.33 |
| 10 | SunCalc（mounerr/suncalc，MIT） | https://github.com/mourner/suncalc | JS 端太阳位置移植参考（同 NOAA 简化法） | 许可与公式核对 |
| 11 | Easings.net | https://easings.net/ | smoothstep / easeInOut 曲线参考 | — |
| 12 | 色彩空间：Oklab 论文（Björn Ottosson） | https://bottosson.github.io/posts/oklab/ | 白天→黑夜线性域混色建议依据 | 可选，非必需 |

**已排除（Dropped）**：各种 SEO 聚合站点的“golden hour 计算器”与二手博客（数值口径混乱，无权威性）；仅作科普的“日出日落 APP 原理”文章（公式缺镜像修正，含典型 bug）；付费 API 文档（本项目要求纯数学自算，不需要外部服务）。

---

## Gaps（不确定性 & 建议下一步）

1. **未能在线复核**：本会话无网络工具，F 列表 URL 与公式需人工打开核对（重点：#1 NOAA 方程 PDF 的 URL 是否仍有效、A.2 阈值、B.2 色值观感）。
2. **色板是设计初值**：9 阶段 HEX 为“可运行初稿”，建议真机截图校准（尤其 P3/P7 地平线高光带亮度与玻璃卡叠层后的观感）。
3. **参考钟面误差**：B.1 的时间窗按 φ≈35° 与 ≈0.2°/min 竖直速率标定；不同纬度季节会整体伸缩（算法自适应，但表格数字勿直接硬编码）。
4. **月亮无星历**：采用“对跖方位 + 固定高度”视觉近似；如需真实月相/月位，接入天气缓存或简易月球星历（如 26 项低精度月球公式）后再替换 B.3。
5. **下一步建议**：(a) 人工复核 F 来源；(b) 用 `solar_elevation_azimuth` 自检脚本对照 NOAA 网页计算器 3–5 个 (lat,lon,时刻) 抽查；(c) 真机跑 P3/P7 截图验收对比度与过渡顺滑度。
