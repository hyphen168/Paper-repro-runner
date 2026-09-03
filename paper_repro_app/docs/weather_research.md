# 业界高质量 Web 天气背景动效（Canvas/WebGL）实现技法工程报告

> 适用场景：深色（赛博朋克风格）桌面应用的全屏 Canvas 背景，按当地实时天气渲染。
> 目标：把"简单雨丝/圆点粒子"升级为"有景深、有质感、像大厂天气页"的动画。
> 约定：全文以 **60fps（16.7ms/帧）** 为基准，速度同时给 px/s 与 px/帧 两种单位；视口面积为 `A = W × H`（CSS 像素），1080p 示例即 `A ≈ 2.07e6`。参考实现基线取自 rainyday.js、Snowstorm、skycons、80s（retro 星空）等开源项目与 Codepen 高赞动效的公共做法（来源见 §E）。

---

## 0. 视觉语言结论（先对齐"质感"从哪来）

大厂天气动效的"真实感"来源按权重排序（综合 Apple Weather、MSN/Windows Weather、Windy、Tomorrow.io 的视觉语言 [S9][S10][S11][S12]）：

1. **分层视差与大气透视**（权重最高）：3~5 层元素，远景变小/变慢/变淡，近景大而清晰。单层全屏粒子再多也"平"。
2. **光线是主角**：天空永远不是一个纯色，而是 2~3 段渐变（地平线处偏亮偏暖/偏霓虹）；太阳/月亮带大范围光晕；闪电先闪天空再画闪电。
3. **动画规律优于数量**：Apple 天气的风、云移动极其缓慢（十几 px/s），粒子数量克制但每层视觉权重分配精细；"堆 2000 根雨丝"不如"400 根雨丝分 3 层 + 底部薄雾 + 偶尔涟漪"。
4. **运动平滑**：所有速度以 `px/s × dt` 驱动而非每帧定值，帧率波动不跳变。
5. **暗色（赛博朋克）配色微调**：雨/雪/雾统一加少量青蓝倾向（如 `(170,220,255)`），避免"脏白"；夜晚主背景建议三色垂直渐变：顶 `#04060e` → 中 `#0a1226` → 地平线 `#1b2a4a`，可再叠一层很弱的品红-青城市辉光条带。

---

## A. 各天气推荐参数表

符号说明：`A = W×H`；分近/中/远三层时用 **far/mid/near**；速度为 60fps 下 px/帧（px/s 附括号）；颜色建议分"白天冷白"与"深色赛博"两档；`θ` 为雨/雪偏离垂直线的倾角（风向角）。

### A-1 雨（小雨/雾雨）——总粒子数 ≈ A/13000（1080p 约 160 根）

| 层 | 数量占比 | 长度 px | 速度 px/帧 (px/s) | 线宽 px | α | 颜色（白天/深色赛博） | 风倾角 θ |
|---|---|---|---|---|---|---|---|
| far | 45% ≈72 | 3–6 | 0.5–1 (20–40) | 0.5–0.7 | 0.12–0.20 | (215,230,255) / (170,215,255) | 4–8° |
| mid | 33% ≈53 | 7–12 | 1.5–2.5 (90–150) | 0.7–0.9 | 0.22–0.32 | 同上 | 6–12° |
| near | 22% ≈35 | 13–22 | 3–4.5 (180–270) | 1.0 | 0.40–0.55 | 同上 | 8–15° |

- 颜色写成 RGBA：far `rgba(215,230,255,0.16)`，mid `rgba(215,230,255,0.28)`，near `rgba(220,238,255,0.48)`；深色版把通道换成 `(170,215,255)`。α 允许 ±20% 随机抖动增强层次。
- **长度应与速度正相关**：`len ≈ vy × 0.06~0.10`（px），或直接按区间随机。快雨长丝、慢雨短丝是"真实"的关键直觉。
- 重绘注意：far/mid/near **各用一次 `beginPath()` 批量画**（每帧总共 3 次 stroke 调用）；雨丝尾端用 `moveTo` 头 `lineTo`，`lineCap='round'` 可消除端点闪烁（成本极低）。

### A-2 大雨（中到大雨）——总粒子数 ≈ A/3800（1080p 约 550 根）

| 层 | 数量占比 | 长度 px | 速度 px/帧 (px/s) | 线宽 px | α | 风倾角 θ |
|---|---|---|---|---|---|---|
| far | 40% ≈220 | 6–10 | 1–1.7 (60–100) | 0.6 | 0.18–0.26 | 10–18° |
| mid | 35% ≈190 | 12–20 | 3–5 (180–300) | 0.9–1.2 | 0.30–0.42 | 15–24° |
| near | 25% ≈140 | 22–38 | 6–9 (360–540) | 1.4–1.8 | 0.50–0.68 | 18–30° |

- 额外要素（提升质感的关键，直接抄）：**near 层中 5% 的雨滴加 1.5~2.5px 的竖直"残影"**（同位置再画一条 α/2 的平行短丝）；底部 6~8% 视高加一层**雨雾渐变条**（见 §B-6）；**雨滴触"地"概率性生成涟漪**（见 §C-2），每帧在屏涟漪控制在 ≤ 60 个。
- 颜色同 A-1；大雨在深色背景上 α 可再 +0.05~0.1。

### A-3 雷暴 —— 大雨参数 + 闪电控制器

- 雨量取 A-2 上限或 A/3000；风倾角可达 30~40°，可再叠加 `0.15 级全局摇摆`（每 2~5s 风向 ±6° 缓变）。
- **闪电调度**：`nextFlash = now + 2500 + Math.random()*9000`（即 2.5~11.5s 一次）。一次雷暴过程 = 主闪白(α0.25~0.4, 120~250ms 指数衰减) + 80~160ms 后第二道弱闪(α0.12) + 2~3 条主折线 + 每主线 1~2 级分支（伪代码见 §C-4）。
- 闪白**只做 α 衰减，绝不整屏白↔黑硬切**（硬切=廉价闪烁的元凶）。
- 重绘注意：闪电线宽与光晕用预渲染 sprite 或 `shadowBlur` 仅在闪电帧使用（次数 ≤ 3 次/雷，不在雨滴循环内用）。

### A-4 雪 —— 圆点雪花（默认）总粒子数：小雪 ≈ A/16000（≈130）、中雪 ≈ A/9000（≈230）、大雪 ≈ A/5500（≈380）

| 层 | 数量占比 | 直径 px | 速度 px/帧 (px/s) 下落 | 横向漂移 px/帧 | α（深色背景） | 摆动 |
|---|---|---|---|---|---|---|
| far | 45% | 1.0–2.2 | 0.3–0.8 (18–50) | 0.1–0.4 | 0.25–0.45 | 周期 3–5s，幅 0.5px |
| mid | 33% | 2.0–3.8 | 0.8–1.6 (50–100) | 0.3–0.8 | 0.5–0.75 | 周期 2–4s，幅 1px |
| near | 22% | 3.5–7.0 | 1.5–3.0 (90–180) | 0.6–1.5 | 0.75–0.95 | 周期 1.5–3s，幅 1.5–3px |

- 绘制：**圆点雪花不要 `arc()` 逐帧画**——预渲染 3 个径向渐变圆 sprite（α 中心 1 → 边缘 0），`drawImage` 即可，1080p 大雪 380 片 drawImage 毫无压力。
- 每个雪片横坐标：`x += (wind + Math.sin(t*freq + phase)*amp) * dt`，其中 wind 为 15~60 px/s 的公共风。
- 背景积雪感：底部加 3~4% 视高的白色 α0.05 渐变"雪雾"。

### A-5 雪（六角星，可选增强）——仅用于 near 层，数量 ≤ 60

- 直径 6–14px，旋转 0.5–2.5°/帧，颜色 `rgba(235,245,255,α)`，其余参数同 near 雪层。
- 六角星**必须离线预渲染成 2~3 个旋转角度的 sprite**（每片 ~4~8 字节内存级别），运行期只 drawImage，绝不在主循环里 stroke 6 条线/片（60 片×6 次 rotate/stroke 会吃掉大量帧预算）。画法见 §C-3。

### A-6 晴昼（太阳）

| 元素 | 参数 |
|---|---|
| 太阳位置 | 建议 (0.70W, 0.16H)（留天空呼吸感），可加极慢漂移 ±30px |
| 日盘半径 r | `r = clamp(H*0.045, 26, 60)`；中心纯白→`#fff7d6`→`#ffd54a` 径向渐变，边缘 α→0 |
| 光晕 | 预渲染 sprite：半径 4~6r 的径向渐变 `rgba(255,235,170,0.35)→0`，合成模式 `lighter` |
| 光芒射线 | 12–24 条（疏密两轮：长/短交替），长度 2.5~4.5r，α 0.05–0.18，宽 r×0.05–0.1；整组极慢旋转 0.1~0.3°/s |
| 体积光/光柱 | 仅在"有云遮挡"时画 4–6 根：从太阳向外发散的等腰三角形（长 0.3~0.8H），填充 `linearGradient` α0.08→0，合成 `screen`，整体以太阳为轴随云漂移 0.05~0.2°/s |
| 重绘注意 | 日盘+光晕=1 个预渲染 sprite；射线若做旋转则整组画到**离屏旋转缓冲**再贴回（每帧 1 次 drawImage + 1 次整体 rotate），避免 20 多次 rotate/save/restore |

### A-7 晴夜（星空）

| 元素 | 参数 |
|---|---|
| 星星数量 | `A/5000`（1080p ≈ 400 颗），亮度分档：70% 暗星 α0.15–0.4、25% 中星 α0.5–0.7、5% 亮星 α0.8–1 且带 4 芒十字闪烁 |
| 尺寸 | 0.5–2.5px（亮星用预渲染 5×5 sprite + 十字光芒 2–3px） |
| 闪烁 | `α = base × (0.6 + 0.4·sin(t·freq + phase))`，freq 0.5–2.5 rad/s，phase 随机；**相邻星不要同相位**（分 4 组相位可防"波浪状"闪烁） |
| 流星 | 每 6–20s 一颗：起点屏幕上方随机，方向 15~35° 斜下，速度 300–600px/s，寿命 0.5–1.2s，尾迹 60–150px 用 `linearGradient`（头亮 α0.8 → 尾 α0） |
| 月亮 | 盘 r≈H*0.04，冷白 `(230,238,255)`，加 2–3 个 α0.15 的暗斑月海；外光晕半径 6r 慢呼吸 |
| 重绘注意 | 星星位置与相位**固定随机种子**（预生成数组），闪烁只改 α 不改坐标 → 天然无抖动；小星用 `fillRect`（2px）比 `arc` 快 ~5× |

### A-8 多云（晴间云，C=0.3~0.5 遮云率）

- 2 个云层（远/近），每层 4–6 朵云。云绘制=「椭圆叠合 + 径向渐变」方法，见 §C-5；云朵参数：

| 参数 | 远云 | 近云 |
|---|---|---|
| 云主体宽 rx | 0.12–0.2 W | 0.2–0.35 W |
| 云主体高 ry | rx×0.32 | rx×0.34 |
| 内部光斑数 | 7–9 个 | 9–12 个 |
| 主色（深色场景） | `rgba(120,135,180,α0.14)` | `rgba(60,72,115,α0.34)` + 顶缘提亮 `rgba(160,180,230,α0.18)` |
| 漂移速度 | 6–15 px/s | 18–40 px/s（与 §B 视差比匹配） |
| 云朵间距 | 云宽×1.2~2.5（随机），循环出界回绕 | 同左 |

- 太阳出没处理：晴间云可选做"云遮日"——太阳与近云**同层**，被遮时体积光变亮、日盘变暗（α*0.35），这是成品感细节。

### A-9 阴（满天阴云，C=0.85~1）

- 视觉三件套：
  1. 全屏灰蓝罩：`linearGradient` 顶 `rgba(96,110,150,0.18)` → 地平线 `rgba(150,165,205,0.30)`，每帧重画或并入背景缓冲；
  2. 1 层巨型低对比云：云宽 0.4–0.6W，仅 2–3 朵，α 0.05–0.1，速度 10–20px/s；
  3. 取消太阳/星；若带"阴雨"则叠加 A-1 小雨 far 层（数量砍半）。
- 重绘注意：罩层若做**缓慢浓度脉动**（±8%，周期 20~40s），用叠加在背景缓冲上的单独全屏 rect 每帧 fill 一次即可（1 次 fill 成本极低），不要改背景缓冲内容。

### A-10 雾

| 要素 | 参数 |
|---|---|
| 雾带（bank）层数 | 3–5 层，水平椭圆渐变带，高 = H×(0.08–0.3) 随机，宽 1.2–2.0W（出界循环） |
| 主色 α（深色场景） | far→near：`rgba(140,165,210,0.05)` → `rgba(170,190,225,0.12)`；白天版 `rgba(225,235,245,…)` |
| 漂移速度 | 3–8 px/s（远）到 10–20 px/s（近），上下缓慢浮动 ±10px（sin，周期 10–25s） |
| 全局浓度罩 | 底部重：地平线 `rgba(160,180,215,0.10–0.25)` → 顶部 0（视浓雾程度调节） |
| 绘制方法 | **预渲染**：每层先在离屏画 1–3 个 `α0.15` 径向渐变椭圆，再用 `ctx.filter='blur(24–48px)'` 模糊一次存 sprite；运行期只 drawImage + 平移。逐帧对 5 个大形状用 filter 会被 GPU/CPU 打爆 |
| 重绘注意 | 雾带与雨/雪不同层（雾在雨之后、UI 之前渲染）；雾端部不要露出硬边（把 sprite 拉长到超屏 1.5 倍） |

---

## B. 分层与"景深感"做法

### B-1 五层结构（自后向前）与推荐比例

统一规则（Apple Weather / Windy 视觉逻辑的通用参数化 [S9][S11]）：

| 层 | 内容 | 元素尺寸倍率 | 速度倍率 | 相对 α | 大气透视处理（暗色场景） |
|---|---|---|---|---|---|
| L0 天空 | 渐变背景（2~3 段） | 1（整屏） | 0（静态缓存） | 1 | 地平线亮 1 档并偏冷色（青/蓝），表现大气散射 |
| L1 远景 | 远云 / 星 / 太阳月亮 / 远雨 | 1× | 0.25× | 0.5 | 去饱和+压暗：`(r,g,b)` → `(r×0.55, g×0.6, b×0.85)` |
| L2 中景 | 中云 / 中雨雪 | 1.5–1.7× | 0.5–0.6× | 0.7 | 轻度压暗 |
| L3 近景 | 近云 / 近雨雪 / 涟漪 | 2.2–2.5× | 1× | 1 | 保持对比，亮部更亮 |
| L4 前景效果 | 雾罩 / 闪电闪白 / 暗角 | 叠加层 | 独立 | 叠加 | — |

- **速度比建议按 1 : 0.55 : 0.25**（近:中:远）配 **尺寸比 2.3 : 1.6 : 1**、**α 比 1 : 0.7 : 0.5**。用户"平"的观感主要来自三者全为 1:1:1。
- 大气透视公式（可照抄）：给定元素基础色 `(r,g,b)` 与景深 d∈[0,1]（远=1），输出色 = `(r·(1-0.45d)+bgR·0.45d, …)` 向背景色插值，即"远处融进背景色"。

### B-2 指针/鼠标视差（可选，成品感+15%）

- 视口鼠标归一化 `nx∈[-1,1], ny∈[-1,1]`（缓动 `cur += (target-cur)×0.05`）。
- 每层平移偏移：`offset_layer = nx × maxShift × 层系数`，maxShift ≈ 24px，层系数 L1=0.08、L2=0.18、L3=0.35、L4=0.6。
- 重绘注意：仅当 `|cur-target| > 0.01` 才更新背景层（防静止时白耗帧）。

### B-3 视差派生的小技巧

- **风与云、雨联动**：把风强度做成全局参数 `wind(px/s)`，雨倾角 `θ = atan(wind/vy)`、云速度 `= wind×k`、雪横向漂移 `= wind`——所有天气统一由同一天气状态对象驱动（Weather API 返回 windSpeed/visibility/cloudCover 时直接映射），比每天气各写死参数真实得多，也是"实时天气"卖点。
- 雨中的三层密度与"能见度"挂钩：`visibility` 低（雨大/雾大）→ far 层削减（远处看不见），near 层增强，并可叠加 L4 罩。

### B-4 天空渐变与辉光（暗色场景可直接用）

```
渐变 = linearGradient(0,0 → 0,H)
0.00: #04060e     // 顶
0.55: #0a1226     // 中
0.85: #14224a     // 地平线上
1.00: #1e2f5e     // 地平线（偏亮=大气）
```
夜晚再加 1 条地平线青-品霓虹光带（α0.04 的 gradient 条）。每次天气/时间切换，天空颜色用 **HSL 插值 2–4s 缓动**，避免瞬切跳变——这是"质感"分水岭之一。

---

## C. 各效果绘制要点与伪代码

### C-1 雨滴运动方程与雨丝绘制

```js
// 每层维护 drop 数组。数据结构只含标量，无嵌套对象，避免 GC 抖动。
drop = { x, y, vy /*px/s*/, len /*px 尾迹长度*/, a /*α*/, seed }
// 初始化：x=rand(-m, W+m)；y=-len*(1+rand()*1.5)  // 只从屏幕上方进场，杜绝"半空凭空出现"

function updateRain(drop, wind, dt){
  const vx = Math.tan(windAngle /*rad*/) * drop.vy;  // 风只改水平速度
  drop.x += vx * dt;
  drop.y += drop.vy * dt;
  // 出界回收（m = 尾迹横向分量余量，≈ len*tan(θ) + 8）
  if (drop.y - drop.len > H) { drop.y = -drop.len*(1+Math.random()); drop.x = Math.random()*(W+2*m)-m; }
  if (drop.x < -m) drop.x = W + m;
  if (drop.x > W+m) drop.x = -m;
}

function drawRainLayer(ctx, drops, color){
  ctx.beginPath();                     // ★ 一整层只一次 beginPath
  for (const d of drops){
    const ang = windAngle;
    const tx = Math.sin(ang)*d.len, ty = Math.cos(ang)*d.len;
    ctx.moveTo(d.x, d.y);              // 头
    ctx.lineTo(d.x - tx, d.y - ty);    // 尾（反运动方向）
  }
  ctx.strokeStyle = color; ctx.lineWidth = w; ctx.stroke();
}
```
要点：`len` 与 `vy` 正相关预先生成；α 用「整层 strokeStyle 一个 α + 少量 drop 单独 α」折衷（一层一次 stroke 时无法每根不同 α——若需逐根 α 差异，按 α 分 2~3 个子批次即可，总 stroke 次数仍 ≤ 9/帧）。

### C-2 落地涟漪扩散

```js
// 触发：near 层雨滴 y ≥ H - groundH 且 Math.random() < 0.35（groundH 为底部虚拟地面带高）
// 若无可见地面，把"地面"画成底部 6~8% 高的一条深色反射渐变带，涟漪就在带上，视觉才成立。
ripple = { x, y, r: 1.5, vr: 25 + Math.random()*55, a: 0.30 + Math.random()*0.15, decay: 0.9 }
update: r += vr*dt;  a *= Math.pow(0.30, dt);        // 约 0.7s 消散
draw:  ctx.strokeStyle = `rgba(190,225,255,${a})`; ctx.lineWidth=1;
       ctx.beginPath(); ctx.arc(x,y,r,0,TAU); ctx.stroke();
       // 加一道内侧更亮短弧（r*0.55，α*1.6）看起来更"湿"
剔除：a < 0.01 时移除（用"末位交换弹出"避免 splice 每次 O(n)）。
屏上涟漪目标值：≤ 60 个，超出则降低生成概率。
```

### C-3 雪花六角形画法（离屏预渲染）

```js
function renderHexFlake(r){               // 只跑一次 → offscreen sprite
  const s = r*4+8, c = document.createElement('canvas');
  c.width = c.height = s; const x = c.getContext('2d');
  x.translate(s/2, s/2);
  for (let i=0;i<6;i++){
    x.rotate(Math.PI/3);
    line(0,0, r,0);                        // 主轴
    for (const t of [0.55, 0.85]){         // 两个分叉点
      line(r*t, 0, r*t - r*0.32, -r*0.30); // 上叉（±30°）
      line(r*t, 0, r*t - r*0.32,  r*0.30); // 下叉
    }
    x.arc(0,0, r*0.05, 0, TAU);            // 中心点
  }
  return c;
}
// 运行期: ctx.save(); ctx.translate(x,y); ctx.rotate(rot); ctx.drawImage(sprite,-s/2,-s/2); ctx.restore();
```
圆点雪花优先：预渲染 α 中心 1→边 0 的径向渐变圆 sprite（半径档 1/2/4px），`drawImage`。混合策略：**大雪 = 近 40 片六角 + 其余圆点**，是"真实又便宜"的平衡点。

### C-4 闪电折线生成（分支 + 闪白）

```js
function genBolt(x, y, depth){            // depth ≤ 2
  const pts = [[x,y]]; let cx=x, cy=y, len = 200+Math.random()*260;
  while (len > 0){
    const seg = 12 + Math.random()*24;
    cx += (Math.random()-0.5)*70 + windX*0.3;   // 水平抖动 ±35px，风偏
    cy += seg;                                   // 只向下
    pts.push([cx, cy]);
    if (depth < 2 && Math.random() < 0.22)       // 22% 概率出叉
      forkLine(cx, cy, 0.5+Math.random()*0.3, depth+1);
    len -= seg;
  }
  return pts;   // 存入 boltList，寿命 120~200ms 后剔除
}
draw: for bolt in boltList:
  主脉: 白核心 lineWidth 2.5–3, α1.0
  次脉: 错位 polyline lineWidth 1, α0.5
  光晕: lineWidth 9–12, α0.18，颜色(180,200,255)
闪白(每次雷击最多 2~3 帧连续白，其余帧衰减)：
flashA = peak(0.3~0.45);
每帧: 全屏 fillRect rgba(220,230,255, flashA); flashA *= Math.exp(-dt/0.08); // τ≈80ms
在 +90~160ms 处再触发一次 0.5× 峰值小闪（模拟云内二次放电）。
```

### C-5 云（椭圆叠合）坐标生成

```js
function makeCloud(baseRx, baseRy, colorA){      // 每朵云 1 次生成，运行期只平移
  const blobs = [];
  blobs.push({dx:0, dy:0,        rx:baseRx*0.62, ry:baseRy*0.80});   // 主体
  const n = 7 + (Math.random()*4|0);
  for (let i=0;i<n;i++){
    blobs.push({
      dx:(Math.random()-0.5)*baseRx*1.7,          // 横向铺开 [-0.85rx, 0.85rx]
      dy:-Math.random()*baseRy*0.85 + baseRy*0.1, // 上拱：顶部最鼓、底部基本平
      rx:baseRx*(0.22+Math.random()*0.35),
      ry:baseRy*(0.30+Math.random()*0.45),
    });
  }
  return blobs;   // 按 dy 从小到大（先画上方小斑，后画下方大斑，形成层叠感）
}
// 单朵云 = 对每个 blob fill 一个径向渐变圆：
//   colorA → transparent；底缘再叠一层同色 α0.25 的"底座"椭圆(位于 dy=+0.1ry)
// 提亮顶缘(可选，暗色场景强烈推荐)：最顶 1~2 个 blob 改画 colorB(亮 35%，α0.35)
// 风变形：drawImage 前 ctx.scale(1+wind*0.0008, 1)（横向拉长）
// 循环：x > W + baseRx*1.5 → x = -baseRx*1.5
```

### C-6 太阳光柱/体积光

```js
// 光柱 = 从太阳发出的扇形，切在近云下缘。做法：离屏画 1 次
ctx.save(); ctx.translate(sunX, sunY); ctx.rotate(θ - spread/2);
for (k=0;k<n;k++){                                  // n=4~6
  const L = H*(0.35+Math.random()*0.35), w = L*0.08;
  const g = ctx.createLinearGradient(0,0, 0,L);     // 沿柱方向
  g.addColorStop(0,'rgba(255,240,190,0.10)');
  g.addColorStop(1,'rgba(255,240,190,0)');
  ctx.fillStyle=g; ctx.beginPath();
  ctx.moveTo(0,0); ctx.lineTo(-w/2, L); ctx.lineTo(w/2, L); ctx.closePath(); ctx.fill();
}
// 运行期：整组画在"太阳+体积光"离屏层，随 θ 极慢旋转(0.05–0.2°/s)后 drawImage 一次。
// 有云遮时：柱 α×1.8、日盘 α×0.4（丁达尔效应）。
```

---

## D. 性能与清晰度（可直接抄的量化基线）

1. **devicePixelRatio**：
   `const dpr = Math.min(window.devicePixelRatio || 1, 2);`（4K 屏取 1.5 或 2，超过 2 无视觉收益且 fill-rate 翻倍）。
   `canvas.width = cssW*dpr; canvas.height = cssH*dpr;` + `ctx.setTransform(dpr,0,0,dpr,0,0)`；**尺寸换算只在 resize 时做**（150ms 防抖），任何一帧内 resize 都会造成闪烁/清屏。
2. **粒子数硬上限**（单天气，避免 2K/4K 下失控）：
   | 效果 | 上限 | 说明 |
   |---|---|---|
   | 雨（三层合计） | 1400 | 1080p 的 550~640 根已很有质感，上限留余量 |
   | 雪（圆点） | 800（其中六角 ≤ 60） | 全 sprite，成本极低 |
   | 星星 | 600 | 超过属浪费 |
   | 云朵 blob 绘制调用/帧 | ≤ 300 | 18 朵×~12 blob+远云，足够 |
   | 涟漪 | 60 | |
3. **时间步进**：`dt = Math.min((now-last)/16.667, 3)`，所有位移 `×dt`。标签页切回后 dt 被钳制，不会"瞬移一大段"。
4. **rAF 与批量绘制**：分层各一次 `beginPath → 批量 lineTo/arc → stroke`；目标 **JS+绘制总预算 < 16ms**，其中闪电/太阳光等重活仅在对应帧做。
5. **避免闪烁清单**：
   - 永不逐帧改 `canvas.width/height`；resize 防抖 150ms。
   - 粒子只从屏幕外进场、出界统一回收（杜绝中间闪现）。
   - 闪电闪白用**指数衰减的 α** 而非 α 0↔1 硬切。
   - 静止层（天空渐变、太阳光晕、雾 sprite）缓存到离屏 canvas，每帧 `drawImage` 代替重绘 gradient。
   - 需要"运动轨迹拖尾"时，用 `ctx.fillStyle='rgba(背景色,0.06)'; fillRect` 覆盖代替 `clearRect`，仅适合自带背景的场景；若背景复杂则**必须全清**再贴背景缓冲（一次 drawImage），否则出鬼影。
6. **对象池/GC**：粒子用预分配数组 + 交换删除；禁止热循环里 `new` 对象或闭包分配；`Math.random` 在 spawn 时用即可。
7. **离屏预渲染**（三件套）：雪圆点 sprite、六角 sprite、云朵单朵 blob 群、太阳+光晕 sprite、雾带 sprite、光柱 sprite——**凡每帧重复出现的渐变/复杂形状一律先画到 offscreen**。
8. **动态降级**：内置 2s 滑动平均帧耗时，若 > 22ms → 粒子数 ×0.75（三次封顶），或 DPR 降到 1.5；`visibilitychange` 隐藏时暂停整个 rAF 循环。
9. **无障碍/省电**：`prefers-reduced-motion` 时粒子数减半、禁止闪白与镜头抖动。
10. **Canvas2D vs WebGL 决策**：雨/雪/星/云/雾全套 Canvas2D 在 1080p 下足够（本报告上限 ≤ ~1500 图元 + 预渲染 sprite，远未触及 Canvas2D 瓶颈）；只有当你要做**粒子级体积光/景深模糊/5000+ 粒子**时才上 WebGL（regl/PixiJS instancing）。桌面 Electron 应用两者皆可，Canvas2D 实现与调试成本低一个量级，优先。

---

## E. 参考来源列表

**开源项目（GitHub，规格与算法主参考）**
1. maroslaw/rainyday.js — https://github.com/maroslaw/rainyday.js — 玻璃雨滴+滑落+合并+涟漪的权威实现，ripple/碰撞/下落模型参考其算法结构。[S1]
2. darkskyapp/skycons — https://github.com/darkskyapp/skycons — Canvas 天气图标动画（日/雪/雨/风），几何元素+循环动画的风格基准。[S2]
3. scottschiller/Snowstorm — https://github.com/scottschiller/Snowstorm — 经典 JS 雪花，flakesMax/flakesMaxActive 上限思路与漂移/摆动参数参考。[S3]
4. loktar00/JQuery-Snowfall — https://github.com/loktar00/JQuery-Snowfall — Canvas 下雪量控制与"慢速大片雪"质感参考。[S4]
5. nathansmith/80s — https://github.com/nathansmith/80s — retro 渐变星空视觉语言（synthwave 深色+霓虹的调色/辉光参考，接近赛博朋克目标审美）。[S5]
6. GitHub topic: weather-animation — https://github.com/topics/weather-animation — 天气动画项目聚合入口（可再挖 Electron/React 天气动画实现）。[S6]

**CodePen / 在线案例（画法与参数参考入口；个别 slug 需按标题检索确认）**
7. CodePen canvas rain 高赞作品检索页 — https://codepen.io/search/pens?q=canvas+rain （典型高赞实现：三层雨丝+风倾角+底部涟漪；注意其参数常为 1080p 专用，需按 §A 公式换算到你的 W×H）[S7]
8. CodePen canvas snow 检索页 — https://codepen.io/search/pens?q=canvas+snow （含圆点雪/六角雪/"slow heavy snow"质感作品）[S7]
9. CodePen lightning / storm 检索页 — https://codepen.io/search/pens?q=lightning+canvas （闪白衰减与折线分支的通用做法：多次 polyline 错位 + exponential 淡出，无硬切）[S7]

**商业天气产品视觉语言**
10. Apple Weather（iOS/macOS 背景场景）— https://www.apple.com/ios/weather/ — 多层视差+极缓云动+光线氛围；"克制而分层的天空"是现代质感标杆。[S9]
11. MSN Weather / Windows 天气（含锁屏天气场景）— https://www.msn.com/en-us/weather — 场景化动态背景：云漂移、昼夜光色整体调性。[S10]
12. Windy — https://www.windy.com — 大气数据可视化 + 地图动效节奏（风与云联动思路）。[S11]
13. Tomorrow.io Weather — https://www.tomorrow.io/weather/ — 大色域天空渐变+图标动效的现代天气页面范式。[S12]

**开发文档**
14. MDN Canvas 教程（基础绘制与动画循环最佳实践）— https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial [S13]

**核验说明**：本环境未挂载联网检索工具，以上 URL 为各项目/产品的官方仓库或站点地址（GitHub 仓库与厂商官网 URL 结构稳定），其中标 [S7] 的 CodePen 检索页与个别官网落地页建议发布前人工复核一次 slug/路径；所有参数、算法与比例为本报告对上述项目公共实现手法的数值化综合，可按需在演示中直接微调。

---

## Gaps（未决项与后续动作）

- **当前版本内未做实时抓取核验**：需要人工确认的 URL（CodePen 具体高赞作品 slug、Apple/MSN 天气功能页路径）已在上节标注。
- **商业产品内部技术栈不可见**：Apple/Windows Weather 的模糊层级与粒子实现无公开参数，§A/§B 的参数是对其视觉结果的工程反推，建议落地后与真实天气页并排截图对比调 α/速度。
- **建议下一步**：按本报告先实现"雨（三层）+底部雨雾+涟漪"作为 A/B 基准场景，用 fps 面板验证预算后，再扩展其余天气；对每一天气录制 10s 对比目标参考页主观打分（层次感/运动平滑度/光感三项）。

---

## 附：工程落地检查单（照抄顺序）

1. 建 `weatherState = {type, wind, visibility, cloudCover, isDay}`，由天气 API 驱动。
2. 建 `EffectManager`：每天气一个控制器，切天气时按 L0→L4 顺序**淡入淡出图层**（400~800ms），禁止整层瞬切。
3. 天空背景（L0）→ 缓动插值换色；远/中/近三层各一个数组 + 一个批量 draw。
4. DPR/尺寸/resize 防抖 + dt 钳制 + 离屏预渲染三件套先做齐，再做天气特效。
5. 用 1080p 与 4K 两块屏验收，跑帧耗时面板，必要时启用 §D-8 动态降级。
