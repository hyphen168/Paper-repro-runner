# AI 自动调试闭环设计（内嵌 LLM 专家诊断）

## 决策

**D1 触发与上下文包**：在 `_render_failure_card`（任务监控失败卡）与历史记录失败行内新增「AI 分析」按钮，点击后组装上下文包发往 LLM。组装函数 `build_debug_context(task, diag, e_code)` 以 JSON 生成（不依赖 streamlit，便于测试）。字段与预算：

| 字段 | 来源 | 预算 |
|---|---|---|
| meta(task_id/status/step/运行方式/环境方式/时间) | DB tasks 行 | ≤600 字符 |
| e_code + 结论 + 动作 + 手册锚点 | `_classify_failure` 三段式 | ≤800 |
| diag(error_category/failed_step/cause/suggestion) | `LogAnalyzer().analyze_log()` | 各 ≤400 |
| 失败 message 前 1500 字 | DB log 字段 JSON payload 的 message | ≤1500 |
| 日志尾 60 行（去重时间戳） | DB log + `read_log_tail` 本地兜底 | ≤4000 |
| 仓库档案 | `get_for_repo`：run_command/data_config/task_family/fail_reason_tags/success_count | ≤800 |
| 已装依赖摘要 | 任务日志最近一次 install/deps 步 echo | ≤600 |
| README 片段 | 本地校验目录或爬虫缓存（缺省放空并注明"无"） | ≤2048 |

合计 ≤11KB，发送前统一过 `sanitize()`（ssh_utils 已有：PEM 私钥、password/pwd= 值置红），并对 message/log 追加正则擦除 `token=|key=|sig=`、http 直链 query、IP 与主机名做可配置遮蔽（默认只留仓库 owner/name 段）。Key/密码绝不入包。

**D2 提示词 v1**（system + user 完整模板，置于 ai_assistant.py 常量）：

system：`你是"论文复现助手"的专家诊断 AI。下方 context 来自一次云端论文复现任务的失败诊断，已脱敏。你的任务：定位根因并给出最小、可直接执行的修复步骤。规则：1) 只依据 context，证据不足时在 fix_steps 给 type=manual 并说明需人工查证什么；2) 目标仓库目录在云端 {remote_workdir}/repo，Python 包已在 conda/venv 环境内安装；3) 依赖安装类只给包名（可带版本约束），禁止自造 --index-url，执行器会自动走多源回退；4) 禁止建议修改 SSH 配置、上传密钥、下载任意脚本执行、rm -rf 仓库外路径；5) 涉及删文件、改系统目录、sudo、apt、重启服务、改代码文件内容时，一律 type=edit（只给 diff 文本，不直接改）或 type=manual；6) 一律用简体中文解释原因；7) 只输出一个 JSON 对象，不要 markdown 代码块、不要额外文字。`

user：`context={context_json}\n请输出 JSON：{"root_cause": "根因一句话", "fix_steps": [{"type": "command|pip_install|edit|manual", "target": "local|cloud", "cmd": "命令原样/包名或约束/diff 文本/空", "reason": "为何这样修、解决什么问题"}], "verify_hint": "修复后应如何验证（可空）"}。command 类云端命令在仓库目录执行，超时 300 秒，先于任何自动批准逐条展示待用户确认；pip_install 由执行器套用云端既有候选源回退。`

**D3 修复执行器与安全边界（专家组裁决）**：云端 `type=command` 属高风险（任意 shell），逐条需用户确认后方执行，复用 `ssh_connect` 开独立短会话在 `remote_workdir/repo` 执行单条命令（timeout 300s、捕获 rc + 输出尾 200 行）。云端与本地自动执行仅白名单：`pip_install`（本地执行前校验包名 `^[A-Za-z0-9._-]+(\[.*\])?(\s*[<>=!~]=?\s*[0-9A-Za-z.*]+)?$`，禁空格/管道/分号；云端经 `install_with_fallback` 语义多源重试）；本地另放行「写入 .env 环境变量键值」类低危操作。`edit` 只生成并展示 diff 文本，绝不自动改文件；`manual` 展示人工步骤，用户勾选"已完成"后才继续。目标主机凭据仅从内存 `task_passwords` 取或现场补输，不落盘不发给模型。

**D4 闭环流程**：AI 分析 → 展示 root_cause 与步骤卡 → 每步「执行/跳过」→ 按序执行（失败步骤标红可"仅重试此步"）→ 全部完成后自动触发「重新执行任务」（复用现有 `start_pipeline_execution` + 内存密码流，无密码则复用现成补输弹层）→ 新失败可再次 AI 分析。防循环与防重复：同一 task+错误码 30 分钟内最多自动重跑 1 次；建议去重键=sha1(错误码+fix_steps JSON)，命中已执行记录时提示"此方案上次已试过并失败"。执行日志 `~/.paper_repro_app/ai_fix_history.json`（0600）记录：时间、task_id、错误码、prompt_hash、每步(type/target/cmd/批准态/rc/输出尾)、结果；不落 LLM key 与原始提示词全文。轻量问答区置于新「AI 助手」页签，失败卡「AI 分析」可一键带入该任务上下文。

**D5 局限性声明（UI 文案）**：「AI 分析仅作参考：大模型可能给出错误或过时方案，凡涉及改动或执行的步骤均需你逐条确认；云端命令有 300 秒超时与输出截断，超长安装或卡死进程可能判定失败。若 AI 建议与手册/档案冲突，以手册与仓库成功档案为准。」

## 可执行变更

1. 新增 `paper_repro_app/ai_assistant.py`（纯逻辑，零 streamlit、零新依赖；SSE 用 `requests.post(stream=True)` + `iter_lines` 手解析 `data:` 行）：常量 `LLM_PROVIDERS`（DeepSeek `https://api.deepseek.com/v1`、Moonshot `https://api.moonshot.cn/v1`、Qwen `https://dashscope.aliyuncs.com/compatible-mode/v1`、GLM `https://open.bigmodel.cn/api/paas/v4`、OpenAI `https://api.openai.com/v1`、自定义 base_url）；`load/save_llm_settings` → `~/.paper_repro_app/llm_config.json`，沿用 `LocalConfigStore` 同款 0600 明文（与 cloud_config 先例一致；不进日志/DB/不入包）；`stream_chat(messages, settings)`、`build_debug_context(...)`、`parse_fix_json(reply)`（坏 JSON 尝试截取首个 `{...}` 段修复）、`apply_fix_step(step, task, password)`（cloud 走 paramiko 短会话；local 走白名单 subprocess）、`record_fix_history(...)`。
2. `app.py`：侧栏新增「AI 助手」折叠配置区（服务商/自定义 base_url/model/API Key 密码框/测试连接），控件文案全中文无 emoji；任务页签新增「AI 助手」（问答 + 修复历史 + 防重复提示）；`_render_failure_card` 与历史失败行加「AI 分析」按钮，失败后展开诊断卡复用 `st.session_state[f"diag_text_{task_id}"]` 与 `LogAnalyzer` diag。
3. 安全阀模块内集中三函数：`is_whitelisted_pip(pkg)`、`is_whitelisted_local(step)`、`needs_confirmation(step)`；云端白名单另有只读探测（`python -c "import …"`、`nvidia-smi`、`which`、仓库内 grep）可自动执行，其余一律确认。新增对应 pytest：脱敏不泄漏 key、上下文大小上限、白名单拒绝注入、坏 JSON 修复、执行日志结构。
4. 重新执行沿用 `start_pipeline_execution(task_id, password=...)`（密码仅内存）；执行完自动 `st.rerun()` 展示新结果，新失败出现则提示「可再次 AI 分析」。
5. 文档落 `docs/ai_assistant/`（本设计说明 + 提示词版本 + 边界白名单），正式报告路径随实现输出。
