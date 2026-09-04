# AI 助手（内置大模型调试）· UI 与存储设计

面向"论文复现助手"（app.py 单文件控制端 + ~/.paper_repro_app 数据层 + 云端 SSH 执行）的 AI 助手体验与存储方案。定位：非专家用户在侧栏填一次 Key，即可在任务失败卡一键让 AI 读日志给原因与修复、在问答区自由提问；一切"修复命令"需人工确认后执行。

## 决策

### 1. 架构：新增 3 个本地模块，保持零新依赖
- ai_client.py：OpenAI 兼容 REST（Chat Completions + GET /models 模型列表），全部基于现有 requests；SSE 用 response.iter_lines 手解析 `data:` 行、遇 `[DONE]` 结束、finally 关闭连接，约百行内。不引入 openai/httpx：所需仅为单轮补全+流式+模型列表，requests 全覆盖；少两个大依赖保住 v2.0.0 打包冻结与国内镜像安装。评估强需（如工具调用编排）再引入。
- ai_config.py：仿 LocalConfigStore 的独立 Key 存储。
- ai_ui.py：渲染 + 会话 + 执行编排（设置折叠、失败分析、问答、动作执行）。app.py 只加 3 个调用点（侧栏、失败卡、新 Tab），改动面最小。

### 2. 存储与 Key 安全
- 独立文件 ~/.paper_repro_app/ai_config.json（不复用 cloud_config.json：提交任务时 config_store.save 会整体合并写云配置、clear() 一键全清，混存会把 Key 覆盖丢失或误删）。字段 {provider, base_url, api_key, model, tested_at, models_cache}；保存后 os.chmod 0o600，与现有 cloud_config 一致。
- Key 明文只允许存在两处：type=password 输入框、ai_config.json（0600）。禁入日志/DB/task.log/命令行/云机；云端无 Key。组装诊断与问答上下文时按字段白名单取值，任何"执行"动作不携带 Key。
- 回显规则：密码框 value 恒空，placeholder「Key 已保存，留空保持不变」；保存成功 caption「Key 已保存（尾号 xxxx，不显示明文）」；另设「移除已保存 Key」按钮。

### 3. 侧栏"AI 助手"设置折叠（服务商联动 + 常用模型）
- 位置：侧栏「云端配置」分隔线之后、"当地定位与天气"之前；expander 标题前带状态点（未配置灰 / 已就绪绿），沿用 .status-dot 语义色。
- 服务商 selectbox：DeepSeek / Moonshot Kimi / 通义 Qwen / 智谱 GLM / OpenAI / 自定义。选中即联动填充 base_url 与常用模型建议（可改）：
  - DeepSeek https://api.deepseek.com/v1：deepseek-chat、deepseek-reasoner
  - Kimi https://api.moonshot.cn/v1：moonshot-v1-8k / 32k / 128k
  - 通义 https://dashscope.aliyuncs.com/compatible-mode/v1：qwen-plus、qwen-turbo、qwen-max
  - 智谱 https://open.bigmodel.cn/api/paas/v4：glm-4-plus、glm-4-air、glm-4-flash
  - OpenAI https://api.openai.com/v1：gpt-4o-mini、gpt-4o
  caption：国内直连 OpenAI 官方通常不通，建议国内服务商；模型名以服务商控制台为准，均可手改。
- 模型输入：text_input 为唯一真值，上方 selectbox 为"常用建议"（选中即填入文本框），避免硬下拉被新模型淘汰。
- 「测试并保存」按钮：GET {base_url}/models（Bearer 头）；成功自动保存表单并回显返回的模型 id 列表；/models 404 时降级一次 max_tokens=1 的 chat 探活。结果条复用 .ssh-health ok/fail 样式与文案（连接就绪/失败原因），不新增 CSS。

### 4. 失败卡「AI 分析」按钮与结果呈现
- 位置：_render_failure_card 内诊断摘要 code 块之后追加分隔线与 AI 区块。未配置时渲染一行引导 caption（「左侧展开 AI 助手，选择服务商并填入 API Key 即可一键分析」），按钮 disabled。
- 点击后：spinner + 阶段文案（「正在读取任务日志与诊断…」「正在请求模型生成修复方案，约 10–30 秒…」），SSE 流式累积渲染。
- 上下文（字段白名单、只读、上限约 5000 字）：错误码 E_*、三段式结论与建议、diag 的 cause/suggestion/error_snippet、failed_step、任务日志尾部约 3000 字、repo_url、run_command 摘要。不含密码、Key、私钥。
- 输出协议：system 约束「你是论文复现排障助手，只输出严格 JSON：{原因, 证据, 动作:[{命令, 目标:本机|云端, 说明, 风险:低|中|高}]}」，temperature 0.2、max_tokens ≤1200。JSON 解析失败回退 markdown 全文展示，不崩溃。
- 结果卡：原因+证据 markdown；动作列表逐行呈现 代码块 + 风险徽章（低=绿/中=黄/高=红，沿用现有语义色）+「执行」「跳过」按钮组；底部附「重新执行流水线」与「预填参数重新提交」（沿用 rp_fill 跳提交页），修复后一键回到现有流程。

### 5. 安全边界（专家组裁决）
- 总原则：AI 无自动执行权。每条修复命令均须人工点「执行」后才在本机或云端运行。
- 白名单（低危；代码侧正则+包名校验，不信任 AI 标注）：pip install 具体包名、pip config set/unset、export 环境变量（云端 bash）；不得含管道/重定向/$()/反引号/&&/;/sudo。
- 「全自动白名单修复」开关（默认关）：开启后白名单命令分析完自动逐条执行；非白名单仍逐个确认。
- 硬拒绝清单（任何入口拦截并提示）：rm -rf /、mkfs、dd、shutdown/reboot、curl|sh 下载执行、含密码或 Key 明文的命令。
- 执行通道：本机 subprocess（capture+timeout）；云端复用任务已存 host/port/user/key，另开独立 SSH 连接（与运行中任务互不抢占）；密码用内存缓存（同现有"带密码重执行"）或一次性询问，不回显。执行记录（命令/目标/结果码/日志尾，无密钥）追加 ~/.paper_repro_app/logs/ai_exec.log。

### 6. 轻量问答区（任务页 + 全局）
- 全局：新增第 4 个 Tab「AI 助手」，st.chat_input 自由问答；上下文 = 最近一次失败任务的三段式诊断摘要（若存在）+ 本会话最近若干轮。
- 任务页：任务监控 Tab 底部固定问答输入（上下文 = 当前任务完整诊断，同 §4 白名单字段）；历史页失败卡片内放同款「追问」。
- 实现：st.chat_message 渲染 markdown 回答；会话仅存 st.session_state，按 scope 分键、单 scope 上限 12 条自动滚旧；提供「清空会话」按钮；不落盘（隐私最小化）。未配置 Key 时 chat_input disabled + 引导文案。答题 temperature 0.4、max_tokens 800。

### 7. 状态文案与隐私
- 无 Key / 测试失败 / 配额耗尽统一给"人话 + 下一步"：401/403→「Key 无效或已过期：检查是否复制完整（含 sk- 前缀），或到服务商控制台重新生成」；429/402→「请求太频繁或额度用尽：稍后再试，或到服务商控制台查看限流与余额」；连接超时/无法解析→「无法访问该地址：核对 base_url；国内直连 OpenAI 官方一般不通，可换国内服务商」。
- 隐私提示固定一行，置于设置折叠、失败卡 AI 区、问答输入区上方：「分析内容将发送至所选服务商，仅含任务日志与诊断摘要，不含密码与 API Key；请勿在问题中粘贴任何密码。」
- 全程中文、无 emoji，颜色与交互沿用现有主题语义。

## 可执行变更
1. 新增 paper_repro_app/ai_client.py：DEFAULT_PROVIDERS 表；list_models(base_url,key)→(ok,msg,ids)；chat_stream(...) 生成器（SSE 手解析，超时 连接10s/首token 60s/流空闲 120s）；错误统一映射为 E_AI_* 供 UI 翻译。
2. 新增 paper_repro_app/ai_config.py：AiConfigStore(load/save/clear)，写后 chmod 0o600；save 遇空 api_key 保留旧值（支持"留空不变"语义）。
3. 新增 paper_repro_app/ai_ui.py：render_ai_settings()、render_ai_analysis(task_id, diag, fail_map 三元组)、render_chat(scope, context_builder)、_execute_action(action, task)；widget key 前缀 ai_。app.py 顶部 load 一次注入侧栏；_render_failure_card 末尾调用分析渲染；新增第 4 个 Tab。
4. remote_runner 或 storage_utils 增加公共 run_single_command(conn_spec, cmd, timeout)（复用 paramiko），供测试连接、本地/云端修复执行共用。
5. APP_CSS 增补约 25 行：风险徽章、动作行、结果卡（主体复用 .panel/.floating-card/stCodeBlock）；连接结果复用 .ssh-health。
6. 新增 pytest 约 15 条：白名单放行/拦截表、SSE 解析与 [DONE]、AiConfigStore 0600 与空 Key 保留、上下文组装不含 key/password；确保现有 92 条全绿不回归。
7. 用户文档 docs/ai_assistant/USAGE.md（配置步骤、隐私声明、FAQ），侧栏「遇到问题？先看这里」追加一行链接。
