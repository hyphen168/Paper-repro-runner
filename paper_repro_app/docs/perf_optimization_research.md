# Streamlit 桌面应用「页面卡顿」性能优化工程报告

> 场景：Windows 桌面浏览器（Chrome/Edge）中运行的 Streamlit 深色应用（赛博 + 玻璃圆润 UI）。
> 已知热点堆栈：全屏 Canvas 天气粒子（雨三层 100–550 滴 / 雪 400+ drawImage / 云朵大图平移 / 星星 420 fillRect / 雾带渐变 / 雷暴 shadowBlur）+ 同屏 >6 块 `backdrop-filter: blur(18px)` 玻璃卡片 + 监控 tab 每 2s `st.fragment(run_every=2)` 重渲染大日志 + body 双层伪元素（网格 mask + 扫描线 mix-blend）。
>
> **数值约定**：凡标注「估算」的数值来自公开资料的量级区间（GPU 型号/驱动相关波动大），必须先跑第 A 章探针实测校准后再定稿；"p50/p95" 为帧间隔毫秒数。文中所有 Chrome 特性（Layer borders、Frame Rendering Stats、Long Task）均以 Windows Chrome/Edge 现行版为准。
>
> 报告中“本仓库代码需确认”处，是指优化前必须先 grep 定位现有实现，避免假设性改动。

---

## A. 定位与度量

### A.1 工具与关键指标总表

| 目的 | 工具位置 | 关键指标 / 读数 | 目标值（1080p 前台） |
|---|---|---|---|
| 帧率 | DevTools → Rendering → **Frame Rendering Stats**（旧版叫 FPS meter） | 实时 FPS 曲线 | 静雨 ≥58；风暴 ≥50（降级后）；验收口径 ≥55 |
| 主线程忙碌 | DevTools → Performance 录制 | Summary 四色：Scripting / Rendering / Painting / System；红条 = Long Task | 空闲无长任务；2s tick 阻塞 <30ms |
| 帧节奏 | 自研 rAF 探针（见 A.3） | p50/p95/max 帧间隔 | p50 ≤12ms，p95 ≤20ms，max <50ms |
| 长任务 | PerformanceObserver('longtask') | duration/次数 | 空闲 0 次/10s；交互单次 <50ms |
| 合成层数 | Rendering → **Layer borders**（绿/蓝边框块计数） | 静态页边框块数 | ≤15；glass 降级后 ≤10 |
| 像素/GPU 路径 | 地址栏 `chrome://gpu` | Graphics Feature Status 是否 Hardware accelerated；是否 SwiftShader | 必须 Hardware accelerated |
| 内存 | Chrome 菜单 → 任务管理器（Shift+Esc） | GPU 进程 + 页面进程内存 | 稳态运行 1h 增量 <50MB |
| DOM 规模 | Console：`document.querySelectorAll('*').length` | 节点数及 1h 净增长 | <3000 且无净增长 |
| 2s tick 负载 | DevTools → Network → WS 帧 | 每 2s 的 payload 字节 | ≤12KB（纯摘要 ≤3KB） |

### A.2 Chrome DevTools Performance 关键操作

1. 录制 **30s 静置**（不碰鼠标）+ 一段 **10s 交互**（滚动/hover/点击 stepper），分开录。
2. 判读顺序：
   - 主线程时间轴里找 **红色长任务块（>50ms）**，点开看堆栈：是 `Animation Frame Fired`（canvas 绘制）→ 指向 H1；是样式/布局/WS 消息回包 → 指向 H3；是 `Composite Layers` → 检查 H2。
   - Summary 面板看 **Rendering/Painting 占比**：>40% 基本是绘制（canvas/backdrop）问题，>30% Scripting 且集中在 rAF 是粒子逻辑问题。
   - 勾选 Rendering → **Layer borders** 数一遍带边框的元素：每块 `backdrop-filter` 卡片、`will-change` 元素、canvas、滚动容器各占一层。
   - 内存：Performance Monitor 盯 **JS heap** 与 **DOM nodes**；任务管理器盯 GPU 进程（glass + 全屏 canvas 主要吃 GPU 进程内存）。
3. 录制前先把「监控 tab 每 2s 轮询」保留为独立变量（临时把 `run_every` 调成 60s 做对照录制）。

### A.3 自定义 30s 帧耗时探针（可直抄）

> 控制台粘贴，30s 后自动打印。rAF 回调同帧排队，因此本探针能捕捉到 canvas rAF 吃满主线程导致的帧间隔拉长。

```js
(() => {
  const MS = 30000;                 // 记录 30s
  const BUCKETS = [8, 16, 20, 25, 33, 50, 100];
  const gaps = [];
  const t0 = performance.now();
  let last = t0;

  function report() {
    const n = gaps.length;
    const s = [...gaps].sort((a, b) => a - b);
    const p = q => s[Math.min(n - 1, Math.floor(n * q))].toFixed(2);
    const hist = BUCKETS.map(b => {
      const c = gaps.filter(v => v <= b).length;
      return `≤${b}ms:${((c / n) * 100).toFixed(0)}%`;
    }).join(' ');
    const long = gaps.filter(v => v > 50).length;
    const avg = gaps.reduce((a, b) => a + b, 0) / n;
    console.log(`[帧探针] 采样=${n} 帧 | avg=${avg.toFixed(2)}ms | p50=${p(0.5)} | p95=${p(0.95)} | max=${Math.max(...gaps).toFixed(1)}ms`);
    console.log(`[帧探针] 累计分布: ${hist}`);
    console.log(`[帧探针] >50ms 长帧=${long} (${((long / n) * 100).toFixed(1)}%) → ${avg > 16.7 ? '判定：主线程满载，需降 Canvas/合成负载' : '判定：帧节奏健康'}`);
  }
  function tick(now) {
    gaps.push(now - last); last = now;
    if (performance.now() - t0 < MS) requestAnimationFrame(tick);
    else report();
  }
  requestAnimationFrame(tick);
})();
```

长任务独立观察（可与上面并行跑）：

```js
const lt = [];
new PerformanceObserver(list => {
  for (const e of list.getEntries()) lt.push({ ms: Math.round(e.duration), at: Math.round(e.startTime) });
}).observe({ type: 'longtask', buffered: true });
setTimeout(() => console.table(lt.slice(-50)), 35000); // 35s 后查看最近 50 条
```

### A.4 CSS containment 建议（度量时先加，排除无关重排干扰）

```css
/* 度量用临时层：把侧边栏/滚动区从全局布局里隔离，减少 2s tick 触发全页 relayout 的假象 */
[data-testid="stSidebar"] { contain: layout style; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { contain: layout style; }
```

注意：`contain: paint` 会裁剪元素外阴影与 backdrop 采样范围，玻璃卡片上先不要用 paint，只对侧边栏/日志容器用 `layout style`（A/B 测完可保留）。

### A.5 首屏 vs 滚动 vs 交互 vs 后台 卡顿区分清单

| 现象 | 可能的根因（本栈） | 验证操作 |
|---|---|---|
| **首屏慢/打开卡 1–2s** | 多张大云 PNG decode + 首帧全屏绘制 + 6+ 块 backdrop 首次光栅 | Performance 录首 5s；Network 看图片 decode；Rendering→Layer borders 首次建立时间 |
| **不操作也卡（静置掉帧）** | canvas 每帧重绘成本（H1）或 2s tick 撞帧（H3） | A.3 探针静置 30s；对比 WS 2s 边界是否有帧间隔尖刺 |
| **滚动卡** | 玻璃卡/大 box-shadow/will-change 图层随滚动重光栅；backdrop 卡片在滚动容器内 | Rendering 勾 **Scrolling Performance Issues**（滚动时出问题的区域闪烁红/绿）；把卡片移出滚动容器或用玻璃降级类复测 |
| **hover/点击卡** | hover 大面积 box-shadow 过渡重绘；点击 stepper 恰逢 2s tick 重渲染 | 交互 10s 录制，查点击后 200ms 内 paint 面积；见 E.3 |
| **切回标签页瞬间卡** | 后台 rAF 被节流，恢复时 dt 未钳制导致粒子瞬移/大重绘 | 见 B.3 `visibilitychange` 与 dt 钳制 |
| **远程桌面/集显全局都卡** | GPU 合成走软件路径（SwiftShader），backdrop + 全屏 canvas 双重放大 | 见 C.3 检测开关 |

### A.6 三大瓶颈假设的验证方案（先验证后优化）

**H1：Canvas 天气粒子每帧重绘成本过高**
- 方法：静置录 30s（风暴模式为最坏工况），再在 Console 执行 `document.querySelectorAll('canvas').forEach(c => c.style.display='none')` 复测 30s（rAF 仍跑但绘制为 0）。
- 判据：隐藏 canvas 后 p95 帧间隔改善 **>8ms** 或 FPS 提升 **>15%** → H1 成立；若仍卡则转 H2/H3。
- 记录：隐藏前后 p50/p95/GPU 进程内存两组数字。

**H2：backdrop-filter 卡片过多导致合成压力**
- 方法：Layer borders 数边框块 → 记 N；Console 执行 `document.documentElement.classList.add('glass-off')`（类定义见 C.2），复测 Layer borders 与帧探针。
- 判据：边框块 **减少 ≥5**，且 p95 改善 ≥4ms 或 GPU 进程内存下降 >50MB → H2 成立。
- 补充：滚动录制时观察 glass-off 前后滚动画面的 paint 事件数量。

**H3：2s 大日志区重渲染（Streamlit 侧 + 浏览器侧）**
- 方法：Network → WS 面板观察每 2s 的 message 大小（记字节）；Performance 静置 30s，检查是否 **每 2s 出现一组 Recalculate Style + Layout + 长任务**；临时把 `st.code(...)` 那行注释或 `run_every=2 → 60` 复测。
- 判据：WS 帧 **>20KB** 或 tick 引起主线程阻塞 **>30ms** 或出现 >50ms 长任务 → H3 成立。

> 三个假设互不排斥，按 H1 → H2 → H3 顺序各做一次开/关实验，即可量化每块可释放的毫秒数，作为 F 章预算表依据。

---

## B. Canvas 天气粒子优化

### B.0 画布像素预算公式（所有优化之前先算这个）

全屏背景 canvas 的 fill/blit 成本 ≈ 后备缓冲像素数。减像素是第一性价比手段。

| 逻辑尺寸 | dpr=1 | dpr=1.25 | dpr=1.5 | dpr=2 |
|---|---|---|---|---|
| 1080p 浏览器区 ≈1920×1000 | 1.9M | 3.0M | 4.3M | **7.7M** |
| 4K@150% ≈2560×1300 | 3.3M | 5.2M | **7.5M** | —（少见） |
| 相对 dpr2 成本 | 25% | 39% | 56% | 100% |

```js
// 主初始化：resize 防抖回调里调用一次（已有防抖，仅把 width/height 赋值替换为此函数）
function pickDPR(W, H, quality = 'medium') {
  const PRESET = {
    high:   { maxDPR: 2,   maxPx: 6.0e6 },   // 强独显 / 交互型画布才用
    medium: { maxDPR: 1.5, maxPx: 3.9e6 },   // 本应用默认（背景氛围画布）
    low:    { maxDPR: 1.25, maxPx: 2.4e6 },  // 集显 / 远程桌面
  }[quality];
  const d = Math.min(window.devicePixelRatio || 1, PRESET.maxDPR, Math.sqrt(PRESET.maxPx / (W * H)));
  return Math.max(1, d);
}
function resizeCanvas(canvas, quality) {
  const W = window.innerWidth, H = window.innerHeight;
  const dpr = pickDPR(W, H, quality);
  canvas.width = Math.round(W * dpr);
  canvas.height = Math.round(H * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);   // 之后统一用 CSS 像素坐标绘图
}
```

**B.1 结论：默认上限 dpr=1.5 + 按面积动态封顶（medium=3.9M 像素）。**
- 1080p 下 `min(dpr2, 1.5, √(3.9M/1.9M)=1.43)` → 实际 1.43：后备缓冲 3.9M，相对现 dpr2 的 7.7M **像素/填充量减半**，观感差异在背景氛围层几乎不可见（小雨丝/星光本来就是亚像素柔光）。
- 4K@150%（逻辑 2560×1300，dpr 1.5）下公式自动压到 ≈1.08（3.9M 封顶），避免 7.5M 灾难。
- 1.5 与 2 的取舍：仅当卡片/图表区不透明盖住画布时 2 才有意义；本栈画布 90% 面积被玻璃（半透明）盖住，模糊底下 1.43 与 2 无肉眼差。

### B.2 雨滴批量绘制

**现状（每层一次 beginPath）已经是正确做法，别拆回逐滴 stroke。** 每层单 path + 单次 stroke：颜色/宽度统一，路径点连续，CPU 侧调用开销最小；逐滴 `beginPath()+stroke()` ×550 是主要浪费。

进一步优化（按收益排序）：

1. **按层合并可行，但收益已不大**：把远层 100 滴并入中层 path 一次 stroke 只省 1 次调用，可忽略；**不要跨层合并**——雨丝长度/透明度不同，合并后无法分层控制 alpha，还会在路径相交处产生 AA 叠加亮斑。
2. **远层 + 中层走离屏雨幕纹理**（收益最大）：
   - 建半分辨率离屏（`W/2 × H/2`，约 1/4 像素），在离屏上按 0.5 比例画远/中层雨丝（数量×0.5、长度×0.6、`globalAlpha×0.5`），每帧仅 1 次 `drawImage(rainSheet, 0, 0, W, H)` 全屏拉伸。
   - 拉伸后雨丝变粗变柔——正好符合“远雨=虚影”的视觉语义；注意把 `ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality='medium'`。
   - 近层（最强那层）保留全分辨率 CSS 像素单 path 绘制，数量建议 ≤180。
3. **雨按帧率分帧**（30fps 观感止损，见 B.7）：近层每帧画，中层每 2 帧画，远层每 3 帧画（配合离屏雨幕更省）。

```js
// 初始化一次
const RS = Math.max(1, Math.floor(0.5 * W));      // 雨幕宽
rainSheet = mkCanvas(RS, Math.floor(0.5 * H));
function drawRainLayers(frame) {
  // 近层：全分辨率，单 path（保持现实现）
  ctx.beginPath();
  for (const d of rainNear) { ctx.moveTo(d.x, d.y); ctx.lineTo(d.x - d.vx * d.len, d.y - d.len); }
  ctx.strokeStyle = 'rgba(180,215,255,0.55)';
  ctx.lineWidth = 1;
  ctx.stroke();

  // 远/中层：半分辨率雨幕，帧率分帧后整张 blit
  if (frame % 3 === 0) drawFarRainToSheet();        // 20fps 更新远层
  ctx.drawImage(rainSheet, 0, 0, W, H);             // 1 次全屏拉伸替代数百次 stroke
}
```

### B.3 雪 sprite：动态数量降级 + visibilitychange（直抄）

```js
// —— 配置与状态 ——
const SNOW_CAP = { high: 420, mid: 290, low: 200 }; // 三级上限(片)
let level = 0;                  // 0=high, 1=mid, 2=low
let snowBudget = 420;
let emaMs = 16;                 // 帧耗时滑动平均
let lastDown = -1e9, lastUp = -1e9;
const DOWN_WAIT = 2000, UP_WAIT = 12000;   // 降级确认窗 / 恢复窗（防抖动）

function adapt(drawMs, now = performance.now()) {
  emaMs = emaMs * 0.9 + drawMs * 0.1;        // 指数滑动平均 ≈ 最近10帧
  if (emaMs > 17.0 && level < 2 && now - lastDown > DOWN_WAIT) {
    level++;
    snowBudget = Math.max(80, Math.round(snowBudget * 0.7));  // 420→294→206
    lastDown = now; lastUp = -1e9;
    console.log(`[降级] L${level} 雪=${snowBudget} ema=${emaMs.toFixed(1)}ms`);
  } else if (emaMs < 9.5 && level > 0 && now - lastUp > UP_WAIT) {
    level--;
    snowBudget = Math.min(420, Math.round(snowBudget / 0.7));
    lastUp = now; lastDown = -1e9;
    console.log(`[恢复] L${level} 雪=${snowBudget}`);
  }
}
// 主循环：用实际绘制耗时喂 adapt，而不是 rAF 间隔
function frame(now) {
  const t0 = performance.now();
  updateAndDraw();                 // 雪只取前 snowBudget 片
  adapt(performance.now() - t0);
  requestAnimationFrame(frame);
}
// 切后台：显式停（浏览器会自动停 rAF，但显式停可省 CPU 并避免恢复跳变）
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { stopRAF(); }
  else { lastNow = performance.now(); startRAF(); }   // dt 清零，防瞬移
});
// 恢复首帧 dt 钳制：任何 dt > 50ms 一律按 50ms 计算（防 sleep/后台恢复跳变）
const dt = Math.min(50, now - lastNow);
```

雪片少到 80 片仍不达标 → 触发 B.7 的 30fps 限频，而不是继续砍数量。

### B.4 星星 420 fillRect：两级结构（静态纹理 + 少量动画层）

420 个独立 `fillRect` 每帧的成本大头不在填充而在 **每颗星的 globalAlpha 状态切换**（420 次状态机抖动）。

- **静态星层**：全部 420 颗星按固定坐标+固定低 alpha（烘焙进像素）画进**半分辨率离屏**一次；仅在 resize 与昼夜调色板变化时重画（重画一次 3–6ms，非每帧）。每帧只 1 次 `drawImage`。
- **闪烁层**：真实闪烁只需要“亮/暗交替”。保留 **≤60 颗**动态星每帧用 `globalAlpha = base + amp*sin(t*speed+phase)` 画（风暴/低配时降到 24 颗或暂停）。
- 不要试图在 canvas 上给 420 颗星做 CSS 闪烁——canvas 像素不受 CSS 动画影响；两级 canvas 是正确解。

```js
// 一次性/变化时重建静态星场
function bakeStars() {
  const s = mkCanvas(Math.ceil(W * 0.5), Math.ceil(H * 0.5)); // 半分辨率
  sCtx.fillStyle = '#cfe4ff';
  for (const st of stars) {          // 420 颗：位置/亮度预生成
    sCtx.globalAlpha = st.base;      // 0.15~0.7，烘焙进纹理
    sCtx.fillRect(st.x * 0.5, st.y * 0.5, st.size, st.size);
  }
  return s;
}
// 每帧：静态 1 blit + 动态 ≤60 fillRect
ctx.drawImage(starSheet, 0, 0, W, H);
const tw = twinkles;                 // 60 颗，含 phase/speed/amp
for (const t of tw) {
  ctx.globalAlpha = t.base + t.amp * (0.5 + 0.5 * Math.sin(nowMs * 0.001 * t.speed + t.phase));
  ctx.fillRect(t.x, t.y, t.size, t.size);
}
ctx.globalAlpha = 1;
```

### B.5 云朵大 drawImage 的开销真相

- `drawImage` 的成本 ∝ **目标像素数 + 采样带宽**，与源图分辨率关系不大；同尺寸离屏贴图逐帧 blit 确实便宜。真正贵的是：**目标太大**（整屏云）、**每帧对云图做缩放插值**、以及**在云上叠加 ctx.filter / shadowBlur**。
- 建议：① 初始化时把每朵云预缩放到「目标显示宽 ×0.5」的离屏（一次性成本），逐帧 drawImage 时目标尺寸同步减半或维持、但只做二次幂友好缩放；② **云数量上限 ≤5 朵**，单朵目标宽 ≤ 视口宽 40%；③ 逐帧禁止 `ctx.filter` 与阴影，云自身若需柔边在烘焙时用一次 `shadowBlur` 或预乘 alpha PNG 解决。
- 降半分辨率离屏的真正收益：显存占用与采样带宽减 4 倍（对集显/远程桌面有效）；若云图本身就是小图，此步可跳过。

### B.6 雷暴闪电：离屏发光 sprite 替代逐帧 shadowBlur

`shadowBlur` 是 canvas 2D 最贵的光栅化路径之一（逐帧使用可把单帧成本抬高 2–10 倍，GPU/CPU 双侧都放大）。**任何 shadowBlur 只允许在初始化/事件触发时用一次，画进离屏后永久弃用。**

```js
// 闪电触发时一次性烘焙（含 glow 与锯齿闪电形状），此后逐帧零 shadow
function bakeBolt() {
  const b = mkCanvas(96, 320);
  const b2 = b.getContext('2d');
  b2.shadowColor = 'rgba(150,200,255,0.9)';
  b2.shadowBlur = 18;                 // 仅此处一次
  b2.strokeStyle = '#e8f4ff';
  b2.lineWidth = 3;
  b2.beginPath();
  // ... 闪电折线 moveTo/lineTo ...
  b2.stroke();
  return b;
}
// 每帧（闪存期 200–600ms）：'lighter' 合成 + 一次 drawImage
ctx.globalCompositeOperation = 'lighter';
ctx.globalAlpha = flashAlpha;         // 0→1→0 的包络，程序算
ctx.drawImage(boltSprite, x, y);      // 逐帧无 shadowBlur
ctx.globalCompositeOperation = 'source-over';
ctx.globalAlpha = 1;
```

### B.7 空闲降帧率 / 30fps 取舍

- **后台 tab**：浏览器对隐藏页自动停 rAF（≈0fps），无需自己做节流；但**必须**处理 `visibilitychange` 恢复后的 dt 跳变（B.3 已给）。注意 Streamlit 的 2s `run_every` 是**服务端定时**，切后台仍在跑——见 D 章控制 payload。
- **前台 30fps 限频**（适用：非风暴 + 无指标动画 + 降级已达 L2）：

```js
let rafId = null, lastTs = 0;
const FPS = 30;                       // 或 60
function loop(now) {
  rafId = requestAnimationFrame(loop);
  if (now - lastTs < 1000 / FPS) return;   // 跳过本帧
  lastTs = now;
  updateAndDraw();
}
function setFPS(v) { FPS = v; lastTs = 0; } // 风暴/前台交互时切回 60
```

- **雨在 30fps 的观感**：雨丝是高速线性运动，30fps 下每帧位移若 >10px 会出现明显步进/闪烁感。取舍方案：
  - 近层雨保留 60fps（每帧只画 ≤180 滴近雨，成本低）；
  - 远/中层（雨幕纹理）降 20–30fps —— 远雨本来就是虚影，肉眼无感；
  - 若整层必须 30fps：同时把雨速 ×0.6（每帧位移控制在 <8px），视觉可接受。
  - 雪（慢速）与云（极慢）在 30fps 下观感无损，放心限频。

### B.8 每帧对象/渐变创建审计（先 grep 后改）

| 审计点（本栈常见雷区） | 每帧创建 ⇒ 触发 GC + 状态重建 | 处理 |
|---|---|---|
| `ctx.createRadialGradient()`（雾/雪残迹/星光光晕处） | 每帧新建渐变对象 + 重置 paint | **只允许 resize/昼夜切换时创建**，存入变量复用 |
| `ctx.createLinearGradient()`（昼夜天空色、雨幕色调） | 同上 | 缓存为 `skyGrad`，昼夜切换时重建一次 |
| `ctx.createPattern()` | 极贵 | 缓存，禁止每帧 |
| `{x,y,vx,vy}` 对象数组 push/splice | 每帧 GC 压力 | 预分配数组 + 游标/交换删除（对象池） |
| 循环内 `String`/模板字符串、`JSON.stringify` | 小对象潮 | 移到帧外 |
| 循环内 `getComputedStyle(...)` 读 CSS 变量 | 强制样式/布局 | 昼夜系统把变量值**只读一次**、事件驱动更新，不要在 rAF 内读 |

**建议把以下画面从 canvas 逐帧绘制移到“一次性离屏 + 每帧 blit”或 CSS 层：**

| 元素 | 现实现 | 改法 |
|---|---|---|
| 底部雾带 | 每帧 fill 渐变 | 改 CSS `position:fixed` 底部渐变层（0 帧成本），或缓存 gradient 对象每帧只 fill |
| 雾/雪残迹光晕 | 每帧 radial gradient | 预烘焙 64×64 光晕 sprite，drawImage 复用 |
| 闪电 | 逐帧 shadowBlur | B.6 离屏 sprite |
| 天空基色/远山剪影 | 每帧渐变 fill | 缓存 gradient 或静态离屏层，仅昼夜切换重画 |

---

## C. 毛玻璃预算与降级

### C.1 同屏 backdrop-filter 面积/数量预算规则

`backdrop-filter: blur(18px)` 的成本 = 被采样背景面积 × 模糊半径 × 该元素是否在动 × 数量（每块独立采样再合成，**不共享**）。经验预算（需实测校准）：

- **主内容区 blur 卡片 ≤3 块**，侧边栏单独算 1 块，全屏合计 **blur 总面积 ≤ 视口 35%**；
- 单卡片面积 > 视口 15% 的，blur 半径 18 → **10px**；
- 单卡片面积 > 视口 40%（全屏弹层/大面板）**禁止 backdrop-filter**，走玻璃模拟类（C.2）；
- 禁止 backdrop-filter 嵌套（卡片套卡片）——内层卡片会强制重复采样；
- 禁止在 backdrop-filter 元素上做 transform/box-shadow 连续动画（每帧触发整块背景重采样 + 重光栅）。

### C.2 降级 CSS 类 + 自动启用逻辑（直抄）

```css
/* 基础玻璃（现状） */
.glass {
  background: rgba(16, 20, 34, 0.55);
  -webkit-backdrop-filter: blur(18px) saturate(140%);
  backdrop-filter: blur(18px) saturate(140%);
  border: 1px solid rgba(255, 255, 255, 0.14);
  border-radius: 16px;
}
/* 浏览器不支持 backdrop-filter 时：提高不透明度保底 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .glass { background: rgba(16, 20, 34, 0.85); }
}
/* 档位1：大屏降半径（blur 18→10） */
html.glass-lite .glass { -webkit-backdrop-filter: blur(10px) saturate(120%); backdrop-filter: blur(10px) saturate(120%); background: rgba(16, 20, 34, 0.62); }
/* 档位2：面积>40%视口的卡片 / 低端环境：彻底去掉 blur，用高光+描边模拟玻璃 */
html.glass-off .glass {
  -webkit-backdrop-filter: none; backdrop-filter: none;
  background: linear-gradient(155deg, rgba(255,255,255,0.09), rgba(255,255,255,0.02) 38%, rgba(0,0,0,0.14));
  border-color: rgba(255, 255, 255, 0.17);
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.14), 0 10px 28px rgba(0,0,0,0.28);
}
```

```js
// 自动分档：auto（按面积/数量）| lite | off；优先级 localStorage > 自动
function glassTier() {
  const saved = localStorage.getItem('glassTier');
  if (saved === 'lite' || saved === 'off' || saved === 'auto') return saved;
  let n = 0, area = 0, sidebarArea = 0;
  for (const el of document.querySelectorAll('.glass')) {
    const r = el.getBoundingClientRect();
    const isSB = el.closest('[data-testid="stSidebar"]');
    (isSB ? (sidebarArea += 0) : (area += r.width * r.height)); // 侧边栏只计块数
    n++;
  }
  const mainArea = area / (innerWidth * innerHeight);
  if (mainArea > 0.60 || (n - (sidebarArea ? 0 : 0)) > 6) return 'off';
  if (mainArea > 0.35 || n > 4) return 'lite';   // 侧边栏 1 块 + 主区 3 块 ≈ 4 为界
  return 'auto';
}
function applyGlass() {
  const tier = glassTier();
  document.documentElement.classList.toggle('glass-lite', tier === 'lite' || tier === 'off');
  document.documentElement.classList.toggle('glass-off', tier === 'off');
  console.log(`[glass] tier=${tier}`);
}
window.addEventListener('resize', () => clearTimeout(window.__gt) || (window.__gt = setTimeout(applyGlass, 400)));
applyGlass();
```

> 侧边栏规则建议单独：sidebar 允许保留 1 块 blur（人眼主视觉锚点），主区卡 3 块；上代码已按「n>4 或主区面积 >35% → lite」处理，按本仓库实际 DOM 微调计数选择器。

### C.3 Windows 远程桌面 / 集显开关

- **检测软件渲染（启发式，非 100%）**：

```js
const gl = document.createElement('canvas').getContext('webgl');
const renderer = (gl && gl.getParameter(gl.RENDERER)) || '';
if (/swiftshader|llvmpipe|software/i.test(renderer)) {
  localStorage.setItem('glassTier', 'off');   // 远程桌面/无独显：默认关玻璃
  document.documentElement.classList.add('glass-off');
  console.log('[glass] 检测到软件渲染 → 自动 off', renderer);
}
```

- 同时人工确认 `chrome://gpu` 的 Graphics Feature Status；远程桌面（RDP）下 GPU 合成常退回软件路径，此时 **C.2 的 off 档 + B.0 的 low 档（maxDPR 1.25）+ 扫描线去 blend（E.2）** 三者一起开。
- 提供 UI 开关持久化到 `localStorage.glassTier`（auto/lite/off），默认 auto；可在应用设置里加「玻璃效果：自动/轻量/关闭」。

### C.4 测量法 + 观感 A/B

- **合成层计数（chrome://tracing 已废弃，用其简化替代）**：Rendering → Layer borders 数边框块；期望：静态页 ≤15 块。逐块验证：hover/滚动时哪几块边框在动/在重建。
- GPU 内存：任务管理器（Shift+Esc）看 **GPU 进程**；glass-off 前后应降 >50MB（6 块 18px blur + 全屏 canvas 时常见 100MB+）。
- **观感 A/B 判据**：同一风暴/夜景画面，glass-lite 与 glass-off 各截图，静止对比 + 5 秒动态对比。若 tester 无法在 2 米距离 3 秒内指出差异，接受降级档。量化底线：`glass-lite`（18→10px）在深色 UI 上通常**无感知**；`glass-off`（高光模拟）与真 blur 的差异集中在“卡片背后的文字/粒子是否可辨”，深色半透明底 + 细描边下大多数卡片场景可接受。

---

## D. Streamlit 2s 轮询区优化

### D.1 结构拆分：2s tick 只更新“摘要”，日志降频/降量

`st.fragment(run_every=2)` 只重跑 fragment 体（不重跑整页脚本）——**前提是监控内容都包在 `@st.fragment` 里**，且把日志与状态拆成**两个不同频率的 fragment**：

```python
from collections import deque
import streamlit as st

LOG_LINES = 150          # 尾 N 行（D.2 给预算表）
LOG_CHARS = 120          # 单行截断字符
_tail: deque[str] = deque(maxlen=LOG_LINES)

def _drain_log():
    # 只取新增行，做一次截断；读取源可 @st.cache_data(ttl=1)
    for line in log_source.read_new(timeout=0):   # 你的实际日志源
        line = line.rstrip("\n")
        _tail.append(line if len(line) <= LOG_CHARS else line[:LOG_CHARS] + "…")

@st.fragment(run_every=2)
def ticker():            # 2s tick：只放 stepper/状态数字，payload 极小
    _drain_log()         # 日志数据可在此累计，但渲染不放这里
    st.metric("吞吐", f"{metrics.rate():.1f}/s")     # 示例：轻量数字
    st.progress(metrics.progress())

@st.fragment(run_every=15)
def log_pane():          # 15s 或按钮手动刷新；大文本不跟 2s 走
    text = "\n".join(_tail) or "…"
    with st.container(height=280, border=False):
        st.code(text, language=None, key="log-tail")  # language=None 关闭高亮
```

关键点：
- **不要**把 150 行日志放进 2s fragment——每次 tick 都要全量重建 DOM 节点（D.2 量化）。
- 若产品要求日志也要 2s 刷新：则 ticker 与 log_pane 合并为 `run_every=2`，但 **LOG_LINES 必须 ≤120、单行 ≤100 字符**（payload 上限见 D.2 表），并接受滚动条位置被重置（全量替换语义，Streamlit 无 diff 保留滚动）。

### D.2 大文本截断策略（>20KB 判定线）

Streamlit 前端收到整块 markdown/code 文本 → 解析 + DOM 重建。**建议阈值：单次 payload ≤12KB；超过 20KB 必须截断。**

| 尾行数 | 平均行长 | 最坏 payload(UTF-8 近似) | 结论 |
|---|---|---|---|
| 200 | 100 | ≈20KB+ | 超阈值，交互点击会撞上重建 |
| 150 | 120 | ≈18KB | 临界，仅在纯日志场景接受 |
| 150 | 80 | ≈12KB | **默认推荐** |
| 120 | 100 | ≈12KB | 日志+stepper 混合 2s tick 推荐 |
| 60 | 120 | ≈7KB | 摘要/事件流 |

- 实现上按 D.1 的 deque `maxlen=LOG_LINES` + 单行截断，即“虚拟滚动不可行时只渲染尾 N 行并保留滚动条”的服务端等价物。滚动条由固定高度容器承担：

```css
/* 日志区样式：限高 + 滚动条（挂到 st.code 输出容器） */
[data-testid="stCode"] pre { max-height: 280px; overflow-y: auto; font-size: 12px; line-height: 1.5; }
```

- **滚动位置提醒**：每 2s 整块替换会重置滚动到顶。若必须“粘底”，Streamlit 原生做不到（`components.html` 的 iframe 沙箱无法操作父 DOM）；工程取舍：
  - 方案 A（推荐）：2s 摘要 ≤30 行常驻 + 全量日志 15s/手动展开（D.1 拆分）；
  - 方案 B：接受 2s 尾部 120 行 + 滚动条，牺牲粘底；
  - 方案 C：日志改自绘 custom component（postMessage 增量更新文本、不重建节点）——工程量最大，仅在日志是产品核心时做。

### D.3 fragment 内避免大 HTML 拼接

- 不要每 2s 用 f-string 拼 20KB 字符串再 `st.markdown(..., unsafe_allow_html=True)`。markdown 解析器（react-markdown）+ HTML 白名单渲染都是纯浪费。
- 用**预构建模板 + 替换值**，且用 `st.code(language=None)`（等宽 pre，不解析 markdown、不高亮）：

```python
_TEMPLATE = "{ts:%H:%M:%S}  {level:5s}  {msg}"     # 模块级预构建一次
lines = [_TEMPLATE.format(ts=t, level=lvl, msg=msg) for t, lvl, msg in new_rows]  # 只格式化增量
```

- 增量 append 到 deque、全量 join 一次（join 150 行 ≈ 微秒级），避免逐行 `st.markdown`（150 次 element 创建 = 150 个 DOM 节点 + 150 次 diff）。

### D.4 2s 重绘区内 CSS 动画禁用清单 + 审计方法

2s 整块替换会**重建 fragment 子树的所有 DOM 节点**——任何挂在日志区/stepper 区的 CSS 动画都会每 2s 重启一次（闪烁、光标跳动、进度条回卷）。

审计方法（Elements 面板选中 2s 刷新容器后 Console）：

```js
const root = $0;                 // 选中 monitor fragment 根节点
const bad = [];
root.querySelectorAll('*').forEach(el => {
  const s = getComputedStyle(el);
  if (s.animationName && s.animationName !== 'none') bad.push([el.tagName, String(el.className).slice(0, 40), 'animation: ' + s.animationName]);
});
console.table(bad);
```

- 若结果只有 hover 类（`transition-property` 且 `animationName=none`）：确认 transition 是否只在 `:hover` 触发——2s 重建不影响 hover 过渡，可保留；
- **禁用清单**（放进全局 CSS 但只作用于 2s 区，用 `[data-testid="stVerticalBlock"]` 内的精确容器选择器）：

```css
/* 只作用于 2s 刷新子树：任何自动动画一律禁 */
[data-testid="stCode"] *, [data-testid="stCode"] { animation: none !important; }
/* stepper/指标卡如有入场动画，从 fragment 子树移除或改为 JS 控制的 class 切换 */
```

- 额外提醒：`st.fragment(run_every=2)` 是服务端定时器，**浏览器切后台仍在每 2s 重渲染**。后台无感知 → 用 `st.fragment(run_every=2)` 的替代方案：切后台时 Streamlit 前端仍收 delta。控制手段只有把 payload 做小（D.2），无法用 JS visibilitychange 停服务端 timer（需要时可对 fragment 逻辑加「页面可见才累积日志」的服务端 flag，配合前端 heartbeat，属 P2）。

---

## E. CSS 层优化

### E.1 body::before 网格 + mask 的成本与替代

- 静态的 44px 平铺网格本身很便宜（一次光栅）；**贵的是**：① 全屏 mask 让该层在视口/尺寸变化时整层重光栅；② 如果该伪元素叠在**每帧更新的 canvas 之上**且有 `opacity<1`/blend/mask，浏览器可能每帧重合成整屏。
- 性能友好替代（**无 mask、低透明度、细线**，观感接近）：

```css
body::before {
  content: ""; position: fixed; inset: 0; z-index: 0; pointer-events: none;
  background:
    linear-gradient(rgba(0, 229, 255, 0.05) 1px, transparent 1px) 0 0 / 44px 44px,
    linear-gradient(90deg, rgba(0, 229, 255, 0.05) 1px, transparent 1px) 0 0 / 44px 44px;
  /* 原 mask 的径向淡出效果改由底部雾带层(CSS)自然遮罩，或把网格 opacity 降到 0.35~0.5 */
  opacity: 0.5;
}
```

- 若必须保留“中心亮、边缘暗”：把 mask 换成一张**预生成全屏淡出 PNG** 作为 `mask-image` 或直接把整层 opacity 压低；不要在网格层上叠 blend。

### E.2 扫描线 mix-blend-mode: overlay 的成本与替代

- 全屏 `mix-blend-mode: overlay` 叠在**每帧变化的 canvas** 上 = 每帧全屏逐像素混合 + 破坏层提升。1080p 硬件合成一次全屏混合约 0.5–2ms GPU（软件渲染 5–20ms）；且它使下方所有层无法独立缓存 → **把 canvas 动画的合成优势全部抵消**。
- 替代（无 blend，肉眼几乎一致）：

```css
body::after {
  content: ""; position: fixed; inset: 0; z-index: 1; pointer-events: none;
  background: repeating-linear-gradient(
    to bottom,
    rgba(255, 255, 255, 0.035) 0 1px,
    transparent 1px 3px
  );
  /* 删除 mix-blend-mode: overlay；3.5% 白色覆盖 ≈ overlay 扫描线观感，成本≈一次静态合成 */
}
```

- 取舍：overlay 在“黑底亮扫描线”上更有 CRT 感；用 alpha 覆盖后把线宽/间距调到 1px/3px、alpha 3–5%，深色主题下差异难辨。**本栈建议直接删 blend。**

### E.3 backdrop 卡片 hover 大面积 box-shadow 的重绘成本

- 大 `box-shadow` 过渡（0.2–0.3s 动画）期间每帧重绘区域 = 卡片包围盒 + 模糊外扩（如 spread 24px + blur 34px ⇒ 约 2–4 倍卡片面积），6 张卡 + 玻璃 backdrop 会让 hover 抖动。
- 处理：**transition 只保留 transform/opacity，box-shadow 直接跳变**（一次静态重绘，无逐帧成本）：

```css
.glass-card {
  transition: transform 0.18s ease;               /* 连续动画只允许 transform */
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
}
.glass-card:hover {
  transform: translateY(-2px);                    /* 视觉反馈主力 */
  box-shadow: 0 12px 34px rgba(0, 0, 0, 0.32), 0 0 0 1px rgba(120, 220, 255, 0.25);
  /* 阴影不参与 transition，hover 时一次性重绘 */
}
```

### E.4 will-change 滥用检查

- 给静态卡片/非持续动画元素加 `will-change: transform` = 每块一个合成层（内存 + 合成负担），正是本栈图层爆炸的来源之一。审计：

```js
const wc = [];
document.querySelectorAll('*').forEach(el => {
  const w = getComputedStyle(el).willChange;
  if (w && w !== 'auto') wc.push([el.tagName, String(el.className).slice(0, 50), w]);
});
console.table(wc);
```

- 应加的（白名单，≤3 处）：正在做连续 transform/opacity 动画的元素（如云层平移 wrapper、入场动画容器）；**不加**：canvas 本身（浏览器已为其建层）、hover 目标、backdrop-filter 元素（叠 will-change 会强制整块玻璃每帧重采样）、静态卡片。

### E.5 contain 与其余小项

- 日志 pre、侧边栏可加 `contain: layout style`（防 2s tick relayout 波及整页）；**慎用 paint**（会裁掉玻璃卡外阴影与 blur 采样，若加需回归视觉）。
- 昼夜系统每 60s 注入 CSS 变量属于轻操作，但注意：① 变量变化会让引用它的样式全部 recalc（一次，可接受）；② **禁止 rAF 循环内 `getComputedStyle` 读变量**（见 B.8）；③ 若 canvas 配色跟随时，用事件把新值一次性 push 进引擎，别让 canvas 每帧解析 CSS。

---

## F. 性能预算总表与验收

### F.1 1080p 前台验收目标（风暴为最坏工况）

| 指标 | 预算目标 | 测量 | 超限动作 |
|---|---|---|---|
| 帧间隔 p50 | ≤12ms | A.3 探针 | 触发粒子降级（B.3） |
| 帧间隔 p95 | ≤20ms（≈50fps 底线） | A.3 探针 | 风暴模式自动降级 |
| Long Task | 空闲 0 次/10s；交互单次 <50ms | longtask observer | 定位到 H1/H3 |
| 2s tick 主线程阻塞 | <30ms/次 | Performance | D 章拆分/截断 |
| WS payload（2s tick） | ≤12KB（摘要 ≤3KB） | Network→WS | D.2 截断 |
| 合成层数 | 静态 ≤15；glass 降级后 ≤10 | Layer borders | C.2 降级 |
| GPU 进程内存 | 1h 增量 <50MB | 任务管理器 | 排查纹理/层泄漏 |
| JS heap | 1h 增量 <20MB；稳态 <60MB | Performance Monitor | 对象池/缓存审计 |
| DOM 节点 | <3000，1h 无净增长 | Console 计数 | 检查 fragment 是否累积节点 |
| FPS（静雨前台） | ≥58 | Frame Rendering Stats | — |

内存口径（估算，需实测）：全屏 dpr1.43 canvas 后备 ≈ 15MB + 离屏雨幕/星场/云纹理 ≈ 20–40MB；6 块 18px blur 每块一层 ≈ 数十 MB；glass-off 后应下降 >50MB。

### F.2 每项优化前后验证方法（自带 30s 帧耗时记录脚本）

固定剧本，每改一项跑一遍，只改一个变量：

1. 打开监控 tab（2s tick 运行中），切**风暴模式**，A.3 探针跑 30s → 记 `p50/p95/max/long帧数` + WS 峰值 KB；
2. 切换**静雨白天**复测一轮；
3. 手动滚动 10s + hover 每张卡 1s，录交互段；
4. 填表（示例模板）：

| 变更 | 场景 | 前 p95 | 后 p95 | 前 max | 后 max | 层数前→后 | GPU 内存 Δ | 结论 |
|---|---|---|---|---|---|---|---|---|
| DPR cap 1.43 | 风暴 | 38ms | 22ms | 120ms | 60ms | 12→12 | −80MB | ✅ |
| … | … | | | | | | | |

脚本输出建议直接 `console.table` 便于复制进表。

### F.3 实施优先级清单

**P0（必做，先止血）**

| # | 改动 | 预期收益（估算） | 风险 / 备注 | 验证 |
|---|---|---|---|---|
| P0-1 | B.1 DPR 封顶 1.5 + 面积动态（medium 3.9M） | 像素/填充 −50%；p95 预估改善 5–15ms | 背景略柔，近层雨观感几乎不变 | 前后探针 + 截图 |
| P0-2 | B.6 闪电 shadowBlur → 离屏 sprite | 每次闪电帧成本 2–10ms → <0.5ms；消除风暴卡顿主源 | 光晕观感需调 alpha 包络 | 风暴模式探针 |
| P0-3 | D.1/D.2 fragment 拆分 + 日志截断（≤120 行×100 字符） | tick 阻塞 30–80ms → <10ms；payload 20KB+ → ≤12KB | 日志可见行数减少；2s 滚动重置 | WS 帧大小 + longtask |
| P0-4 | B.3/B.7 滑动平均降级 + visibilitychange + dt 钳制 | 满载时自动保 60fps；后台恢复不瞬移 | 粒子减少需阈值校准（17/9.5ms） | 长稳 10 分钟风暴 |

**P1（重点优化）**

| # | 改动 | 预期收益 | 风险 | 验证 |
|---|---|---|---|---|
| P1-5 | B.4 星星两级（静态纹理 + 60 动态） | 420 次状态切换/帧 → 1 blit + 60 fillRect | 闪烁星数减少 | 星空场景探针 |
| P1-6 | B.2 雨远/中层半分辨率雨幕 + 分帧 | 数百次远雨 stroke → 1 次全屏 blit | 远雨变柔（符合预期） | 雨景截图 |
| P1-7 | C.2/C.3 glass-lite 自动降级 + 软件渲染检测 | 层数 15+ → ≤10；GPU 内存 −50MB+ | 需要 UI 手动档兜底 | Layer borders + 任务管理器 |
| P1-8 | E.2 扫描线去 blend；E.1 网格去 mask | 消除每帧全屏混合（0.5–20ms/帧） | 观感微差（alpha 3–5% 兜底） | 风暴探针 + A/B 截图 |
| P1-9 | B.8 渐变缓存 + 雾带改 CSS | 消除每帧 gradient 创建与 GC | — | 探针 + heap 曲线 |

**P2（打磨）**

| # | 改动 | 预期收益 | 风险 |
|---|---|---|---|
| P2-10 | B.5 云半分辨率离屏 + 数量≤5 | 采样带宽 −75%（集显有效） | 大云观感略糊 |
| P2-11 | E.3 hover 阴影去 transition、E.4 will-change 白名单 | 交互帧稳定；减层 | 视觉动效降级需确认 |
| P2-12 | E.5 contain + 昼夜变量事件化 | 隔离 relayout；避免 rAF 读 CSS | contain: paint 慎用 |

---

## 参考来源（需复核）

> 本次运行无实时联网检索工具，以下 URL 均为**需复核**的权威文档入口，落地前请逐条打开确认当前有效版本/路径（尤其 Chrome DevTools 文档改版频繁、Streamlit fragment 版本下限 1.37）。

- Chrome DevTools Performance 录制与分析：https://developer.chrome.com/docs/devtools/performance/ （需复核；含长任务/帧率面板说明）
- Chrome DevTools Performance reference（指标词典）：https://developer.chrome.com/docs/devtools/performance/reference （需复核）
- Chrome DevTools Rendering 面板（Frame Rendering Stats / Layer borders / Scrolling Performance Issues）：https://developer.chrome.com/docs/devtools/rendering/ （需复核，现行版本菜单位置）
- Chrome GPU 状态：`chrome://gpu`（本地，无需 URL）
- web.dev 渲染性能（Rendering Performance，rAF/paint 管线）：https://web.dev/articles/rendering-performance （需复核现状与更名）
- MDN 优化 canvas：https://developer.mozilla.org/en-US/docs/Web/API/Canvas_API/Tutorial/Optimizing_canvas
- MDN OffscreenCanvas：https://developer.mozilla.org/en-US/docs/Web/API/OffscreenCanvas
- MDN backdrop-filter（含 GPU 合成与兼容性说明）：https://developer.mozilla.org/en-US/docs/Web/CSS/backdrop-filter
- MDN mix-blend-mode：https://developer.mozilla.org/en-US/docs/Web/CSS/mix-blend-mode
- MDN will-change：https://developer.mozilla.org/en-US/docs/Web/CSS/will-change
- MDN contain：https://developer.mozilla.org/en-US/docs/Web/CSS/contain
- MDN Long Tasks API（PerformanceLongTaskTiming）：https://developer.mozilla.org/en-US/docs/Web/API/PerformanceLongTaskTiming
- MDN visibilitychange：https://developer.mozilla.org/en-US/docs/Web/API/Document/visibilitychange_event
- MDN mask（网格 mask 成本复核）：https://developer.mozilla.org/en-US/docs/Web/CSS/mask
- MDN imageSmoothingQuality：https://developer.mozilla.org/en-US/docs/Web/API/CanvasRenderingContext2D/imageSmoothingQuality
- Streamlit st.fragment（run_every 参数、限制列表）：https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment （需复核）
- Streamlit 性能架构文档（rerun 与缓存）：https://docs.streamlit.io/develop/concepts/architecture/performance （需复核 slug）
- Streamlit element container（固定高度+滚动）：https://docs.streamlit.io/develop/api-reference/layout/st.container （需复核）
- Can I use — backdrop-filter：https://caniuse.com/css-backdrop-filter （需复核，用于 @supports 与 Windows 版本矩阵）

---

## 缺口与后续

1. 上述全部为量级估算与工程惯例，**关键数字（DPR 封顶像素、blur 面积占比、payload 阈值）必须用 A.3 探针在本机 Chrome + 本仓库代码上实测校准**；GPU 差异（Intel UHD vs NVIDIA vs RDP 软件渲染）可达 10 倍，无法纸面定死。
2. 现有 weather 引擎代码（是否每帧建 gradient、云是否用 shadow、日志 HTML 结构、glass 卡片选择器）需要先做一次 grep 审计再套用本节，报告中已标注“需确认”点。
3. Streamlit 侧“每 2s 全量替换导致滚动位置重置/粘底不可行”是框架语义限制，若产品要求真·增量日志需评估 custom component（额外工程量）。
