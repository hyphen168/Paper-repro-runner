# 移动端 UI 审计报告（专家级 · 手机查看/控制达标方案）

审计对象：`app.py` 主流程（提交表单 c1–c4 列、监控 2s fragment、诊断卡、结果对比表）、`paper_repro_app/ui_theme.py`（APP_CSS 全部 @media 规则）、`.streamlit/config.toml`、`weather_fx.py` 粒子引擎、`start_app.py`。Streamlit 固定 1.62.0。基线视口 375×667。

## 决策

总体结论：手机浏览器**可用性门槛目前未达标**，但全部问题是一次性 CSS/小结构修复，零新框架、零新依赖。四项硬伤按优先级排序：

1. **多列 `st.columns` 在 375px 下不堆叠（最严重）**。Streamlit 列是 flex 行（`[data-testid="stHorizontalBlock"]` > `[data-testid="column"]`），没有响应式自动换行。提交表单 `c1,c2,c3,c4 = st.columns([3,1,1.4,1.6])` 在 343px 可用宽度下：主机框约 137px、密码框约 73px——无法输入，且无横向溢出提示，是"看不到的坏"。同类受影响：`ssh_target` 下方 `tf1–tf3`/`tf4–tf6`、`sc1–sc3` 分割比例、`storage [5,1.6]` 行、`_pwd_col/_go_col [3,1]`、成功结果指标 `st.columns(min(4,len(keys)))`。决策：**≤620px 断点内对所有 stHorizontalBlock 子列强制 `flex:1 1 100%` 堆叠**（指标卡随之变单列长列表，可接受；若想两列可用 50% 变体，但 44px 触控高度优先，建议全宽）。
2. **触控尺寸与 iOS 自动缩放**。桌面按钮 min-height 38px（primary 46px），输入框约 38px，低于 44px 触控推荐值；页面 `font-size:15px` 让输入框在 iOS Safari 聚焦时触发**自动放大**（<16px 即触发），体验极差。决策：≤620px 内按钮/输入/radio 项 min-height:44px，所有输入控件强制 `font-size:16px`（顺带治自动缩放）；radio 四项长中文标签在横向布局会挤压/溢出，**≤1000px 改竖排**（点按目标变大）。
3. **监控 2s 轮询流量与手机资源**。每 tick 经 WebSocket 推送该 fragment 全部增量：日志窗口 22 行约 2.5–4KB 文本 + HTML 转义/JSON/协议开销 ≈ **6–10KB/次**。2s 频率 = 30 次/分 ≈ 180–300KB/分 ≈ **10–18MB/小时**（活跃前台）。浏览器侧 tab 隐藏会自动暂停 fragment 定时，但亮屏监控期持续消耗流量与电量。决策：**不全局降频**（PC 主控保持 2s），仅对移动 UA 降频——用 `st.context.headers["User-Agent"]`（1.62 原生支持）判定，`run_every` 由 2.0 动态改为 5.0，并把移动端日志窗口从 22/14 行收到 8 行 → 约 **2–4MB/小时**，流量降 4–5 倍且监控延迟仍可接受（训练分钟级变化）。检测 UA 优于统一降频：桌面端是主控入口，不能牺牲它的实时性。
4. **表格横向滚动缺口**。论文对比表（五列 markdown table）在 375px 必然撑破或压扁，现有 CSS 无任何 table 规则。决策：容器级方案——≤620px 给 markdown 容器开 `overflow-x:auto`、表 `min-width:520px` 触发内部横滑（保语义、保 `-webkit-overflow-scrolling:touch` 惯性），页面本体不横向滚动。

特殊处理（纯装饰降级）决策：粒子 canvas **不整段删除**。实测代码已有面积自适应（雨密度 W×H/13000、星 /5000 上限 420、DPR 像素上限 3.9M、帧耗时自动 skip≤3、visibilitychange 停帧），手机上的真正成本是**60fps 全屏重绘 + 多个 panel/stSidebar 的 backdrop-filter blur**。因此：① ≤620px CSS 关闭全部 backdrop-filter 改近实色背景（低端安卓 GPU 收益最大）；② JS 顶部加粗粒度指针探测（`maxTouchPoints>1` 且窄屏），命中则初始 skip=2（≈30fps）、DPR≤1.5、雨/雪/星密度 ×0.5、涟漪上限减半——保留"停雨幕但留氛围"的观感，参数化一行可调到彻底关停。

访问与网络定位：应用无内建鉴权。局域网暴露（0.0.0.0）依赖 Windows 防火墙白名单限定网段即可；公网远程走 SSH 反向隧道时远端端口是明文 HTTP，**不可裸开公网端口**，需应用层口令页或 `--server.address 127.0.0.1`+隧道本机回环（归属网络/访问控制专家组，本报告不展开，UI 侧不新增鉴权代码）。`.streamlit/config.toml` 无需为移动端改动。

## 可执行变更

### A. ui_theme.py —— APP_CSS 末尾追加移动端块（CSS，全部含断点值）

```css
/* ===== 移动端适配（375px 基线；追加于文件末尾保证级联优先） ===== */
@media (max-width: 1000px) {
  [data-testid="stRadio"] [role="radiogroup"] { flex-direction: column; align-items: stretch; gap: 0.2rem; }
}
@media (max-width: 620px) {
  /* ① 列堆叠：1.62 子列为 data-testid="column"（旧版 stColumn 双写兜底） */
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap; row-gap: 0.6rem; }
  [data-testid="stHorizontalBlock"] > [data-testid="column"],
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 100% !important; width: 100% !important; max-width: none !important;
  }
  /* ② 触控尺寸与 iOS 自动缩放 */
  .stButton > button, div[data-testid="stFormSubmitButton"] button,
  button[kind="primary"] { min-height: 44px !important; }
  [data-testid="stTabs"] button[role="tab"] { min-height: 44px; }
  .stTextInput input, .stTextArea textarea, .stNumberInput input,
  [data-testid="stSelectbox"] > div, [data-testid="stMultiSelect"] > div {
    font-size: 16px !important; min-height: 44px;
  }
  [data-testid="stRadio"] [role="radio"] { min-height: 44px; padding: 0.4rem 0; }
  /* ③ 五列对比表内部横滑（容器方案，不撑宽页面） */
  [data-testid="stMarkdownContainer"] { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  [data-testid="stMarkdownContainer"] table { min-width: 520px; }
  /* ④ 装饰降级：关毛玻璃（GPU），粒子 JS 另行处理 */
  .panel, .floating-card, .fx-card, .panel-row, .meta-pill, .pr-pill, .weather-chip,
  [data-testid="stMetric"], [data-testid="stExpander"] details,
  [data-testid="stSidebar"] > div, .telemetry-metric, .telemetry-subpanel {
    -webkit-backdrop-filter: none !important; backdrop-filter: none !important;
    background: rgba(11, 16, 30, 0.97) !important;
  }
  body::after { display: none; }            /* 扫描线叠层手机不需要 */
  .telemetry-log { font-size: 12px !important; max-height: 220px; }
}
```

### B. weather_fx.py —— `_WEATHER_JS` 两处小改（JS，触屏窄屏降载）

```js
// 顶部（CFG 解析后）：LITE 探测 + 初始降帧
var LITE = (navigator.maxTouchPoints || 0) > 1 && (P.innerWidth || 900) <= 900;
if (LITE) { skip = 2; }          /* 起步≈30fps，不等帧耗时判定 */
// doResize() 内：DPR = Math.max(0.7, Math.min(want, LITE ? 1.5 : 2));
// 密度三处：星 n = /(LITE ? 10000 : 5000)；雨 density = /(LITE ? 26000 : 13000)（heavy 同理 ×2）；
// 雪 density = /(LITE ? 12000 : 6000)；雨最低值 LITE 时 Math.max(40, …)；ripples 上限 60→24。
```
彻底关闭的旁路（可选）：侧栏「背景天气预览」上方加 1 个 checkbox 写 `st.session_state["wx_off"]`，`render_particle_background()` 首行 `if st.session_state.get("wx_off"): return`。

### C. app.py —— 轮询降频与日志瘦身（结构，改动 ≤15 行）

1. 新工具（放 app.py 顶部）：`is_mobile_browser()` = `st.context.headers.get("User-Agent")` 含 mobile/android/iphone/ipad 关键字，异常回落 `False`（桌面 2s 不变，测试断言不受影响）。
2. `_auto_refresh_monitor` 与 `render_pipeline_steps` 内 `live_monitor` 改为工厂式，使 `run_every` 可随 UA 取 `5.0 if is_mobile_browser() else 2.0`（每次 run 内定义并立即调用一次，与现状 live_monitor 的写法同构，fragment 按代码位置识别、无副作用）：
   ```python
   def _auto_refresh_monitor_factory(interval: float):
       @st.fragment(run_every=interval)
       def _inner(task_id: str):
           _render_monitor_content(task_id)
           # …原逻辑原样…
       return _inner
   # 调用点：_auto_refresh_monitor_factory(5.0 if is_mobile_browser() else 2.0)(task_id)
   ```
3. `_render_monitor_content` 与 `render_pipeline_steps` 的日志窗口按同一判定收窄：`max_entries=8` / `lines[-10:]`（桌面维持 14/22）。

### D. 验收清单（375×667，Chrome 设备工具栏 + 真机各一遍）

- 提交页：c1–c4 四输入**各占一整行**自上而下排列，无横向页面滚动；主机框可贴多行、密码框宽度正常。
- 触控：主按钮/普通按钮/radio 项实测点按区 ≥44×44（DevTools 逐层检查）；点输入框**不发生 iOS 页面放大**。
- 运行方式 radio 已竖排，四项长中文完整显示。
- 监控页：任务运行中 Network 面板每约 5s 一条 WS 消息；模拟 4G 限速（Fast 3G）下日志与步进器仍流畅刷新；切后台 tab 自动停更、切回恢复。
- 结果对比表：在卡片内可**惯性横滑**查看全部五列，页面本身不横向滚动。
- 成功结果指标卡为单列堆叠、数值不截断；失败诊断卡文字无溢出、折叠面板正常展开。
- 粒子背景：真机（触屏）滚动/输入不卡顿；GPU 面板无持续 60fps 满载；锁屏后无后台绘制。
- 功能回归（手机端执行一遍主流程）：提交任务 → 监控到 running → 结束后看失败诊断卡或成功对比 → 点击「重新执行」→「结束当前任务」，全程无元素错位/遮挡。
- 桌面端回归：2s 轮询不变、列布局不变、毛玻璃效果保留——确认无全局副作用。

验收标准一句话：375px 上"核心子集 = 全功能"，唯一允许的横滑区域是对比表与日志/代码块。
