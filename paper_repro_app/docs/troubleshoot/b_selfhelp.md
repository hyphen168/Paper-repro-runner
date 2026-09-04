# 自助排障入口设计规范（失败→下一步按钮）

专家组：自助排障入口设计师。目标用户：拿到 zip 即用的非专家。设计原则一句话：**每个失败都给出"结论行 + 下一步按钮 + 技术详情"，用户不需要读懂技术栈，只需要点按钮。**
已读素材：app.py（监控页/历史页失败展示）、storage_utils.py（result 结构）、ui_theme.py（status-dot/pr-pill/telemetry-metric/meta-pill 等类）、remote_runner.py（十步流水线与失败分支）、ssh_utils.py（连接档案引擎）、LogAnalyzer、docs/ssh_expert/ssh_lead_spec.md（L0-L3 与文案模板）、docs/dataset_url_research/dataset_lead_spec.md（reason_code）、docs/acceptance_test/c_universal.md（P0-P2 缺口）、docs/ui_expert/ui_lead_spec.md。真机八案例 ①-⑧ 已纳入模板表。硬约束已核查：无 emoji、不写密码明文、不引新框架（剪贴板用现有 st.components 内联 JS，零依赖）、pytest 88 基线不动、AppTest 0 异常。

## 决策

**D0 渲染契约（单点收口）**。失败永远三区：一区结论行（一句话人话+错误码胶囊），二区建议动作（1-3 个真实 st.button 或复制项，按场景动态生成），三区技术详情（默认折叠：类别/触发步骤/关键片段/根因）。收口到唯一渲染函数 `render_diag_card`，监控页 failed 分支与历史页共用；错误码与结论文案由纯函数推导（不改 storage result 结构，仅 optional 追加 error_code），保证历史 payload 向后兼容。

**D1 错误码与结论模板（13 条，覆盖八案例+既有分类）**。渲染时按"日志锚 + 步骤 + metric_verdict + dataset.reason_code"推导；模板即文案源，内置离线可用。

| 错误码 | 触发证据 | 结论行（人话） | 默认动作按钮 |
|---|---|---|---|
| E_CONNECT_AUTH | Authentication failed 族 | 服务器没认出你的钥匙或密码，卡在连接一步 | 注入公钥到服务器 / 重填密码后重新执行 |
| E_CONNECT_UNREACH | refused/timeout/dns | 连不上服务器：多半没开机或地址端口不是最新 | 回提交页核对 SSH / 测试 SSH 连接 |
| E_ENV_BOOTSTRAP | conda/python not found | 云端是全新系统，正在自动装 Python 基础环境 | 重新执行（等待自动安装，勿关窗） |
| E_ENV_PYVER | Python 版本冲突 | 云端 Python 与仓库要求对不上（案例⑥） | 改环境方式后重跑 |
| E_TORCH_CPU | Torch not compiled with CUDA | 训练引擎装成了没 GPU 的版本，一跑就崩（案例②） | 重新执行（自动改国内 CUDA 源并禁 CPU 回退） |
| E_DEPS_MISSING | ModuleNotFoundError | 仓库少装了一个依赖包，运行中断（案例③） | 重新执行（自动补装）/ 查看缺失包名 |
| E_MODEL_ENTRY | 入口识别 miss / run 无法推断 | 没找到该仓库的训练入口，入口命名差异（案例④） | 切"自定义命令"并粘贴 README 训练命令 |
| E_DATA_UNAVAIL | degrade / degrade-fatal | 数据集没就位，所以没真训练 | 填数据集 YAML 或直链后重跑 |
| E_DATA_BLOCKED | 官方源下载超时 | 官方数据源在你网络下不通（如 MNIST 官网，案例⑤） | 重新执行（已自动切镜像）/ 填镜像直链 |
| E_CREDENTIAL_LOST | 重执行缺内存密码 | 密码只存在本机内存，重启/换会话就丢了（案例⑦） | 带密码重新执行（现场补输） |
| E_THREAD_LOST | 线程已死但状态 running | 任务被打断：关控制台会连带停掉后台执行（案例⑧） | 重新执行，执行期间保持窗口开启 |
| E_STEP_FAILED | 步骤退出码非 0 | 卡在第 N 步「步骤名」，原因见详情 | 复制诊断摘要发给懂行的人或 AI 助手 |
| E_NO_METRICS | metric_verdict=no_metrics_output | 任务结束但没产出指标 | 展开"指标为什么是空"三分类指引 |

**D2 诊断卡三区与 HTML 骨架**。复用现有样式类（.panel/.panel-title/.status-dot/.meta-pill/.telemetry-metric/.panel-row），不新增 CSS 框架，仅补少量 .diag-* 修饰类。骨架：

```html
<div class='panel' style='padding:0.9rem 1rem;'>
  <div class='panel-title'>问题定位</div>
  <div class='diag-row'>
    <span class='status-dot' style='background:var(--red);'></span>
    <span class='diag-verdict'>服务器没认出你的钥匙或密码，卡在连接一步</span>
    <span class='meta-pill'>E_CONNECT_AUTH</span>
  </div>
  <div class='telemetry-grid'>
    <div class='telemetry-metric'><span class='telemetry-label'>触发步骤</span><strong>connect</strong></div>
    <div class='telemetry-metric'><span class='telemetry-label'>发生时间</span><strong>13:42:07</strong></div>
  </div>
</div>
<!-- 动作区：真实 st.button 一行（重新执行/复制诊断摘要/注入公钥） -->
<!-- 详情区：st.expander('技术详情（给想看原因的人）') 折叠 现有 LogAnalyzer 五字段 -->
```

动作按钮由模板表自动映射：rerun（复用现"重新执行流水线"缺密码补输逻辑）、inject_key（跳转并触发 SSH 私钥折叠区）、go_submit（切 tab 到提交页并展开对应卡片）、copy_diag（触发剪贴板摘要）、help_faq（展开侧栏"遇到问题？"）。每条失败只保留 ≤3 个按钮，主动作排第一且文案以动词开头（"点这里：重新执行"）。

**D3 "遇到问题？"帮助入口（侧栏顶部折叠，默认收起）**。侧栏最上方加 `st.expander("遇到问题？先看这里")`，内含七问，每问 1-2 句人话 + 所在 UI 位置（提交页/监控页/历史页）；错误卡 E_* 的动作 help_faq 直接展开到对应问答。文案全部内嵌常量，离线可用，无跳外链。七问：连不上服务器 / 认证失败要密码 / 提交后没跑训练 / 指标是空的 / 报告在哪 / 想重跑一次 / 关窗后任务断了。顶部仪表条不加按钮（避免与天气/状态胶囊抢层级，低风险优先）。

**D4 三段式改造集中化**。旧文案为"长段中文列表/裸 stdout/未归类兜底"三类，统一改造成三区输出，但底层 message 与 result 字段保持不变、只追加 `error_code` 与可选的 `verdict`（供日志/摘要复用），渲染差异收敛在 render_diag_card，杜绝逐处拼接再次分叉。

**D5 quiet 防线（两个检查点）**。运行前检查点：run 步骤执行前打印一行预期配置摘要（数据路径/epoch/batch/imgsz/device/cuda 可用性），让"没跑/跑错参数"在日志第一屏就暴露。运行后检查点：collect 结束后零指标时输出原因分类三选一：no_train_output（没真训练）/ metric_files_missing（缺 results.csv 等标准文件）/ format_unrecognized（有文件但指标键名不在识别词典），并把分类写进 metric_verdict 派生字段供 UI 三分类渲染。

**D6 一键诊断摘要**。诊断卡动作区提供"复制诊断摘要"：纯文本拼装（标题+时间+任务+环境+错误码+结论+建议+关键日志片段≤12 行），经 sanitize 脱敏后经剪贴板复制；给用户"贴给朋友或 AI 助手"的最低成本求助通道。内容模板见 C5。

**D7 不做清单与边界**。不引入新框架/图标/在线客服；不动轮询数据模型与十步流水线结构；不新增 DB 列（error_code 仅内存/result 可选字段）；不存密码明文；不改状态色单源与主题规范；帮助文案不得含具体密码与私钥内容；不在轮询区挂动画（诊断卡静态）。

## 可执行变更

**C1 新增纯逻辑模块 paper_repro_app/troubleshoot.py + app.py 渲染接入**。
- `troubleshoot.py`（零 streamlit 依赖，可单测）：`build_verdict(task, payload) -> dict(code, conclusion, actions)`（查 D1 模板表，按优先级：ssh 类别→数据集 reason_code→metric_verdict→日志锚→步骤映射）；`build_diagnostic_text(...)`（D6/C5）；`FAQ_ITEMS` 常量（C2 文案）；`config_summary_echo(...)`（C4 摘要行生成，纯函数好测）。
- app.py 接入点：`_render_monitor_content` 的 failed 分支（现 `st.error(f"任务执行失败：{fail_message}")`）→ `render_diag_card(...)`（st.markdown 骨架 + 动作列 st.button + 详情 expander，技术详情复用现有 LogAnalyzer 五字段不删）；历史页 failed 行同步复用，行内保留原 panel-row + expander 位置不动（低风险）。
- 验收：AppTest 打开含 failed 种子任务页 0 异常；Edge 截图三区齐全。

**C2 帮助入口接入**：app.py 侧栏最上方（"云端配置"之前）插入 FAQ expander，逐条 `st.markdown("**连不上服务器** · 先确认实例开机，端口用控制台最新 SSH 登录信息（AutoDL 多为 4xxxx 不是 22）。位置：提交任务页·云服务器卡·测试 SSH 连接")`；诊断卡 help_faq 动作展开同一组件（session_state 锚点）。验收：提交/监控/历史三页均可见、不遮挡表单。

**C3 三段式文案改造清单（文件/函数/旧→新，5 条）**。

| 文件/函数 | 旧文案（问题） | 新三段结构 |
|---|---|---|
| remote_runner.execute 认证失败分支 | 长段 1)2)3)4) 列表塞 message | message=结论行一句；error_code=E_CONNECT_AUTH；修复步骤移入诊断卡动作与详情 suggestion（原列表保留在 cause 字段） |
| remote_runner.execute 兜底 | "远程执行失败：{last_error}" 裸抛 | message="卡在第 N 步「步骤名」，原因见详情"；error_code=E_STEP_FAILED+failed_step；原始异常入详情片段 |
| remote_runner dataset 分支 | degrade-fatal 中文长段 | 结论行=E_DATA_UNAVAIL；reason_code/candidates_tried/suggested_actions（数据集规范字段）直接入卡 |
| app.py 监控 failed 分支 | `st.error` 整段红字+大 expander | 诊断卡三区；红条只留结论行一句，动作独立成钮 |
| LogAnalyzer 未归类兜底 | "任务中途异常中断…检查配置" 无指向 | 按步骤表给动作：install/deps 步→"重新执行自动补装"；run 步→"复制摘要求助/核对自定义命令"；collect 步→三分类指引 |

**C4 运行前后检查点（quiet 防线改造点）**：remote_runner.run_step 在 `timeout ... bash -c` 前追加一段：从数据集 env 读数据路径、从 run_command/tune_args 正则提取 epochs/batch/imgsz/device，打印 `[paper-repro-config] mode=... data=... epochs=... batch=... device=... cuda=True/False`；collection_script 末段加三分类判定（stdout 有训练字样但零指标→no_train_output；无标准四文件→metric_files_missing；有文件但键全不在 map/precision/recall/f1/accuracy/loss 词典→format_unrecognized 并列出前 5 个实际键名），打印 `[指标分类] reason=...`；storage_utils.merge_stdout_metrics 已产出 metric_verdict，追加 no_metrics_reason 透传。UI：指标为空提示区（现 degraded/info 两分支）下方按分类渲染一句人话+建议（如 metric_files_missing → "仓库没写标准指标文件；可把指标另存为 results.csv/metrics.json 后重跑"）。验收：真机 auto 模式日志首屏见 config 摘要、collect 尾部见 [指标分类]。

**C5 一键诊断摘要（内容模板与复制）**。文本模板：
```
【论文复现助手诊断摘要】
时间 / 任务ID / 状态
任务：论文链接 / 仓库 / 运行方式(safe|auto|run|tune)
云端：host:port(user)（脱敏：密钥仅记文件名） / 环境方式 / 远程目录
错误：E_TORCH_CPU · 结论：训练引擎装成了没 GPU 的版本
建议：重新执行（自动重装 CUDA 版）
关键日志（尾部 12 行）：
...
```
复制实现：st.button("复制诊断摘要") → 将文本写入 session_state → `components.html`（app 已 import，允许）内联 JS 填 textarea 后 document.execCommand('copy')，失败降级为展示 st.code 提示手动复制（try/except 包裹，AppTest 无异常）。全程不落库、经 sanitize（密码/PEM/私钥路径只留 basename）。

**C6 文案与 FAQ 全量内嵌 + 落盘 docs/troubleshoot/faq.md**：D1 表与 FAQ 文案以常量形式进入 troubleshoot.py（单源），docs 侧生成镜像 md 便于人工维护；验收 grep 全仓无 emoji、无密码明文。

**验收与回归**：pytest 88 基线保持全绿（新增 troubleshoot 纯函数单测约 8 条，总数上升不下降）；AppTest 三页 0 异常；真机失败样本复验三区渲染与 [指标分类]；重启场景验证 E_CREDENTIAL_LOST/E_THREAD_LOST 文案；脱敏复查日志无密码/私钥泄漏。

参考素材（已读，未重复调研）：app.py、storage_utils.py、remote_runner.py、ssh_utils.py、ui_theme.py、log_analyzer.py、docs/acceptance_test/c_universal.md、docs/ssh_expert/ssh_lead_spec.md、docs/dataset_url_research/dataset_lead_spec.md、docs/ui_expert/ui_lead_spec.md、README.md。
