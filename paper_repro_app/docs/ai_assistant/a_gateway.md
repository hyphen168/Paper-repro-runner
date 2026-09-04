# 专家组 · LLM 网关架构规范（a_gateway）

> 范围：零新依赖、OpenAI 兼容流式网关（`paper_repro_app/llm_gate.py`）。已核对代码事实：requirements 仅 `requests==2.34.2` 可用且足够；`ssh_utils.sanitize()` 已存在（PEM/`password=` 键值脱敏）；`LocalConfigStore` 与 `repo_profiles._save_atomic` 均以 0600 明文 JSON 落 `~/.paper_repro_app/`，为本设计先例；`storage_utils._get_exec_state()["task_passwords"]` 为内存密码源；任务 `log` 字段既存滚动文本又存最终 JSON 载荷（含 `message/failed_step/logs/metrics/report`）。

## 决策

**1) 服务商预设表（≥6，全部 OpenAI 兼容；每项含 base_url、推荐模型、注意点，另设「自定义」兜底）**

| 服务商 | base_url | 推荐模型（备选） | 已知注意点 |
|---|---|---|---|
| DeepSeek | `https://api.deepseek.com`（官网注明亦可附 `/v1`） | `deepseek-chat`（备 `deepseek-reasoner`） | 推理模型输出长，诊断场景默认 chat；Key 形如 `sk-` 开头 |
| Moonshot Kimi | `https://api.moonshot.cn/v1` | `kimi-k2-0711-preview`（备 `kimi-latest`；旧档 `moonshot-v1-8k/32k/128k` 表示上下文档位而非版本） | 短上下文报超限时提示换 32k/128k 档 |
| 通义 Qwen（百炼） | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus`（备 `qwen-max`/`qwen-turbo`） | 仅 compatible-mode 端点走 OpenAI 协议；Key 用百炼 API-Key |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-plus`（备 `glm-4-flash`） | v4 为 OpenAI 兼容版；老 key 需在 bigmodel.cn 换新 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | 大陆网络受限，失败中文提示改用国产服务商 |
| OpenRouter | `https://openrouter.ai/api/v1` | `deepseek/deepseek-chat`（备 `qwen/qwen-2.5-72b-instruct` 免费档） | 模型名必须带 `厂商/模型`；免费模型 429 频繁，命中后提示换付费档 |
| 自定义 | 用户手填 | 手填 | 用「探测模型」按钮验证，不保证兼容则自动回退非流式 |

模型名会随厂商下线过期：UI「保存」时自动调 `list_models` 刷新下拉可选项，失败仅提示、不阻断（沿用预设表）。

**2) 模块与调用契约**（`llm_gate.py` 零 streamlit、零新依赖，纯 requests + 标准库）

- `LLMConfig`（provider/base_url/api_key/model）+ `save_config/load_config`：独立文件 `~/.paper_repro_app/llm_config.json`，沿用 repo_profiles 的 tmp+`os.replace` 原子写并 `chmod 0600`。**加密结论**：明文 0600 与 cloud_config 同构、零新依赖，已足够；不强上加密（引入口令/依赖得不偿失），文档留 TODO 备注可选 `cryptography`。
- `chat_stream(messages, on_delta, cfg, max_tokens=1500) -> str`：`POST {base}/chat/completions`，`stream=True`，`timeout=(15, 120)`（15s 建连、120s 读超时=两帧间隔上限）；逐行手解析 SSE：`data: ` 前缀行、`[DONE]` 结束、空行/心跳注释跳过、多行 JSON 累积到可解析；返回值为拼好的完整文本。
- `chat_once(messages, cfg, max_tokens=1500) -> str`：内部关闭 stream 复用同解析路径。
- 非 OpenAI 兼容回退：Content-Type 非 `text/event-stream` 或 body 是完整 JSON（`choices[0].message.content`）时按非流式一次返回；服务商拒绝 stream 参数（400）时自动重发一次非流式请求。
- `list_models(cfg) -> list[str]`：`GET {base}/models`（Bearer 鉴权）探测，失败返回预设表并标注不可用。
- `validate_key(cfg) -> (bool, str)`：优先 `/models`，个别端点不支持则发 `max_tokens=1` 的极短 chat。
- 重试策略：仅 1 次、幂等前置（收到任何增量后绝不再试，避免重复正文），覆盖 429（尊重 `Retry-After`，封顶 15s）/连接错误/5xx；401/403/400 不重试。
- 错误分类→中文：401「API Key 无效或已失效」；403「账号/区域受限（OpenAI 需代理）」；429「限流或余额不足，稍后重试/换服务商」；超时「网络连接超时（15s/120s），检查网络或服务商状态」；DNS/连接「无法连接服务商端点」。统一抛 `LLMGateError(kind, 中文信息)`，UI 只展示。
- 上下文估算与截断：`estimate_tokens = len(chars) × 1.6`（保守上取整）。诊断上下文装配顺序＝系统提示→任务元信息→E_* 诊断卡 diag_text→日志窗口→repo_profiles 档案摘要（≤2KB）→用户问题；超预算按「日志中部 → 历史轮次 → 系统提示」从中间向外裁剪，**保头保尾**（错误尾部必保）。

**3) 发送前清洗链**：先 `ssh_utils.sanitize()`（PEM 私钥、`password/passwd/pwd=` 键值），再叠加 `sanitize_for_llm()` 规则：① URL 查询串按 `&` 拆 key，凡命中 `X-Amz-*|Signature|AWSAccessKeyId|X-Signature|token|credential` 的参数整段剥离；② `sk-[A-Za-z0-9]{16,}`、`Bearer …` 替换为占位符；③ 含 `.ssh` 的路径剥成 basename；④ 发送前断言清洗结果不再包含 `cfg.api_key` 与任务密码原文，命中即拒发并在 UI 告警。此链同时用于任何要展示给 LLM 的日志/命令全文。

**4) 成本与调用护栏（结论）**：单次输出 `max_tokens ≤ 1500`；诊断上下文上限 **12KB 字符**（约 2 万估算 token，兼容 32K 窗口模型，超长一律先截断）；每分钟 ≤ 6 次调用（模块内简单时间窗计数器，超限返回中文提示）；全部常量置模块顶部可调。AI 修复单任务最多自动迭代 2 轮，之后只给人工指引。

**5) 安全边界（专家组裁决）**：云端永远不出现 Key（调用仅本机发往 LLM；下发云端的是修复命令，经既有 SSH 链+内存密码，Authorization 头只存在于本机请求）。命令执行分级：
- **自动（白名单，无需确认）**：`python -m pip install <包名…>`（包名须 `^[A-Za-z0-9_.\-]+$`，参数列表由本地构造成数组、逐项 `shlex.quote`，禁止 `; & | > < $() \` *` 与 `-e/--editable`）；一次性 `export NAME=value`（仅当次会话，不带 `>` 写文件）；复用 `start_pipeline_execution` 原样重跑既有流水线。
- **必须人工确认**：一切其余命令——apt/conda 安装、系统库/驱动（`nvidia-*`）、改删文件、git 操作、运行 python/训练脚本。UI 呈现「命令预览 + 执行 / 拒绝」，确认后同样走 RemoteFixer 下发并记录审计。
- 每条动作（自动或确认）落审计 `~/.paper_repro_app/llm_actions.log`（任务 id/时间/命令/级别/退出码，已脱敏），不入任务 log 正文污染展示。

**6) UI（无 emoji）**：侧栏新增「AI 助手设置」折叠区（服务商下拉 + base_url/model/Key 手填 + 测试/保存 + 隐私说明「Key 仅存本机 0600，不上云不进日志」）；各失败诊断卡与历史失败卡加「AI 分析」按钮，问答区放「任务监控/历史记录」页底部（结合当前任务上下文）。报告落盘 `docs/ai_assistant/`（不可写时全文回填会话），QA 报告同时留档 `~/.paper_repro_app/ai_reports/` 备查（可移植性原则）。

## 可执行变更

1. **新增 `paper_repro_app/llm_gate.py`**（约 420 行，纯逻辑）：`LLMConfig/PROVIDERS/save_config/load_config`、`chat_stream/chat_once/list_models/validate_key`、SSE 解析器 `_iter_sse`、`LLMGateError` 分类、`estimate_tokens/trim_to_budget/build_diagnosis_context`（内聚：取 TaskStore 任务 + LogAnalyzer diag + repo_profiles 摘要）、`sanitize_for_llm`、`parse_action_commands`（从模型回复提取代码块命令并逐条 `is_auto_allowed` 分级）、`_rate_limiter`、`run_remote_fix(task_id, cmd, level)`——复用 `ssh_utils.ssh_connect` + `RemoteRunner` 的 conda 激活引导段，在 `remote_workdir/repo` 下执行，密码取自内存 `task_passwords`，退出码回传供下一轮分析。
2. **`app.py`（零逻辑外迁约束不变）**：仅接线 UI——侧栏设置折叠区；`_render_failure_card` 与历史失败 expander 内加「AI 分析」按钮（`on_delta` 用会话态累积后 `st.markdown` 展示流式文本）；问答区；动作确认卡（st.code + 确认/拒绝双按钮，确认调 `run_remote_fix`，结果按钮「继续让 AI 看新日志」最多 2 轮）。新函数保持 app.py 纯编排。
3. **`paper_repro_app/storage_utils.py`**：导出 `ai_fix_runner` 相关小函数（或直接放 llm_gate 内），并在任务 `log` JSON 载荷追加 `"ai_fixes": [...]` 键（不破坏既有读取路径）；`llm_actions.log` 由 llm_gate 落。
4. **`docs/ai_assistant/`**：本方案存档 `ARCHITECTURE.md`；运行时分析报告默认写该目录（失败回退全文回复）。
5. **配置/打包零改动**：requirements、pyproject、make_dist 均不动（新 py 自动入包；`llm_config.json` 在用户家目录，不会被打进 zip）。
6. **新增 `tests/test_llm_gate.py`**（不联网、不碰真 Key）：monkeypatch `requests.post` 注入伪流（模拟 `data:`/`[DONE]`/心跳/完整 JSON/401/429/超时），断言 SSE 拼接、非兼容回退、错误分类中文文案、截断保头保尾、`sanitize_for_llm` 剥离签名 token 与 Key、白名单判定、限频、配置 0600 落盘。与既有 92 例共跑保持全绿。
7. **排序建议**：llm_gate 纯函数 + 测试（1 天）→ app.py UI 接线（0.5 天）→ RemoteFixer 与审计（0.5 天）→ 手册 FAQ 更新（0.5 天）。
