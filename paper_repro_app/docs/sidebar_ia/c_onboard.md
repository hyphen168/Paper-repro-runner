# 引导与发现设计 · onboard（c_onboard）

依据：app.py 实读（tab_submit/侧栏/`_render_failure_card`/`_render_success_result`）、ui_theme.py（`CAROUSEL_CARDS`/`build_carousel_html`/CSS 动画）、config_store.py（save=load+update 合并写，不覆盖云端字段）、ai_config.py（Key 独立 DPAPI 存储，meta 无 Key）、GUIDE.md 结构。

## 决策

1. **首启引导：提交页顶部一次性三步卡（不采用全局弹层/侧栏置顶横幅）。** 理由：用户唯一任务流入口是"提交任务"tab；侧栏是"配置区"心智，新用户在配置区找功能入口正是本次失败场景。卡片置于 tab_submit 顶部（"本地输出目录"折叠之前），用 `st.container(border=True)` 静态渲染，不挡提交按钮、不预填任何表单字段（保住空白默认）。内容 3 步编号：① 卡片一填云服务器地址（整行粘贴控制台登录指令即可）；② 填论文/仓库→提交复现任务；③ 失败后进任务详情：先看失败卡结论与建议，再点"AI 分析失败原因"（未配 Key 时该按钮位自动换成去配置引导）。**session 一次性逻辑**：`session_state` 记 `onboard_seen`，展示即标记、本会话不再出现；卡片自带"关闭"按钮（关闭=本会话静默）。跨会话建议加一层版本化持久标记：写 `config_store.save({"ui": {"onboard_hint_v": n}})`（save 为合并写，已核实不会冲掉云端字段），仅当"提示版本号 < 当前功能版本号"才再显示一次——这样存量老用户（看不到侧栏新功能的抱怨者）随升级被自然引导一次，而不是永久弹窗。分支内容：无历史任务→基础三步；有失败任务且未配 AI Key→第 3 步高亮 AI 分析并写全路径（侧栏→AI 助手→填 Key→测试保存）；已有成功任务→第 3 步改指历史记录对比表与档案秒配，避免把老用户当新手。

2. **轮播卡裁决：改造为"功能发现条"，保留无缝滚动机制。** 现有 `CAROUSEL_CARDS` 是营销文案（云端执行/数据安全等），与头部副标题重复、零发现价值；而轮播正处于首屏目光落点。但**不**做可点击卡（纯文本"位置+动作"提示比假按钮诚实），保留无缝循环、hover 暂停与 reduced-motion 兜底（ui_theme.py 已有）。新 6 卡（无 emoji、不含 URL/令牌，口令门语义不破）：① 失败就点 AI 分析（任务详情页一键，侧栏 AI 助手先配 Key）；② 同仓库秒配（再次提交自动提示"填入上次成功配置"）；③ 复现 vs 论文对比表（任务监控/历史记录）；④ 思考强度 快速/标准/深度（侧栏 AI 助手）；⑤ 微调训练参数面板（运行方式选"微调训练"）；⑥ 手机直达与受信设备（条件卡，仅 `PAPER_REPRO_EXPOSE in (lan,tunnel)` 出现）。`build_carousel_html()` 内部按 os.environ 过滤第 6 卡、签名不变，桌面默认环境输出稳定（防测试断言破坏）。最高价值卡排前两张，保证首帧可见、不必等 32s 滚动。

3. **失败/成功页"下一步"：失败卡强化为闭环按钮，成功页只补 caption、不加成功态 AI 复盘。** 现有无 Key 失败卡 caption（"配置 AI 助手（侧栏→AI 助手→…）后…"）指路准确但被动——用户仍需在 5+ 个折叠区里自己翻。强化方案：该 caption 升级为按钮"去配置 AI（自动定位侧栏）"，点击置 `st.session_state["ai_panel_open"]=True` 并 `st.rerun()`；侧栏 AI 助手 expander 的 `expanded` 参数改读该 flag（render 后 pop 复位）。实现在失败现场"一键展开 AI 助手配置面板"的闭环，零新增组件、不写明文。成功页裁决：AI 复盘成功结果边际价值低（成功后无待解问题），故仅在未配 Key 时于成功横幅下补一行 caption："如后续任务失败，可在任务详情页让 AI 一键分析原因——侧栏『AI 助手（失败自动调试）』填 Key 测试保存即可启用。"已配 Key 不显示。

4. **不打扰原则（结论）**：一切引导每会话至多出现一次、可一键关闭；只给"路径+动作"，绝不预填表单、不改写口令门/受信设备安全语义、不渲染 tk 链接与密钥；失败热路径上 AI 按钮永远排在诊断信息之后；纯静态元素（不新增动画/框架）；文案不用"新手教程"，用"从这里开始/新功能"两态，避免老用户被降级对待。

## 可执行变更

E1. **app.py · tab_submit 顶部**新增私有函数 `_render_onboard_card()`（置于 render_app 上方）：入参判定分支用 `config_store.load().get("ui", {})`、`store.list_tasks(limit=1)`、`ai_load()`；固定 widget key（如 `onboard_close`），展示后置 seen 标记；关闭按钮写 `ui.onboard_hint_v`。禁 `st.stop()`、禁异常路径，保证 AppTest 零异常。

E2. **ui_theme.py**：替换 `CAROUSEL_CARDS` 为新 6 条（决策 2 文案），`build_carousel_html()` 内按 `os.environ.get("PAPER_REPRO_EXPOSE")` 过滤第 6 卡；外层调用 `st.markdown(build_carousel_html())` 不变。

E3. **app.py · 侧栏 AI 助手 expander**：`expanded` 改 `st.session_state.pop("ai_panel_open", False)`（注意 render 时序：pop 后本次展开、下次 rerun 复位）。同文件 `_render_failure_card` 无 Key 分支：原 caption 前插入按钮（key 固定 `goto_ai_panel`）→ 置 flag + `st.rerun()`；原 caption 降为按钮下方说明行。

E4. **app.py · `_render_success_result`**：`st.success` 横幅后按"未配 Key"条件渲染决策 3 的 caption（不引按钮/容器，避免指标断言顺序漂移）。

E5. **回归**：改动集中在新增条件渲染 + 单 flag 控制 expanded，不触碰 `_access_gate`、表单空值、密码/凭据读写路径；跑 104 全量测试 + AppTest 零异常。风险点两处需自查：① 若测试按位置索引失败卡按钮（新增 `goto_ai_panel` 会使其后按钮序号后移），须同步为 key 断言；② 若测试断言轮播卡数量，桌面默认输出为 5 张（第 6 张仅 lan/tunnel 环境出现），文案换新但卡数可预测。

---

执行顺序建议：E2（独立、最低风险）→ E3（解决核心"找不到 AI 助手"）→ E1（首启引导）→ E4。全部落地后再由"信息架构"角色复查侧栏分组是否需重组（本报告不做架构改组，避免与 104 基线冲突）。
