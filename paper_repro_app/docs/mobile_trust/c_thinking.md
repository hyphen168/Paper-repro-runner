# 思考强度设计规范（专家组 · 思考强度设计师）

## 决策

**档位语义**：采用三段制 **快速(fast)/标准(standard)/深度(deep)**，默认 **标准**。档位是"单次请求级"参数：只改变本次发送的模型、body 字段与超时，**不回写已保存的 model**（避免深度模型被永久写进配置）。语义一句话：快速=快而省、求定位；标准=日常默认（即现状）；深度=更慢更贵更细致（reasoner/thinking 或长输出）。UI 文案统一写"深度更慢、更贵、更细致"。

**档位→模型/参数映射**（max_tokens=输出上限，temperature 仅快速档发 0.3；reasoner 类模型一律不传 temperature）：

| 档位 | DeepSeek | Moonshot Kimi | 通义 Qwen | 智谱 GLM | OpenAI |
|---|---|---|---|---|---|
| 快速 | 当前模型 + mt800 + temp0.3 | 同左 | 同左 | 同左 | 同左 |
| 标准 | 当前模型 + mt1400（现状不变） | 同左 | 同左 | 同左 | 同左 |
| 深度 | model_override=deepseek-reasoner，mt2400，无 temp | 保持模型，mt2400，提示可填 kimi-k2-thinking | model_override=qwen3-max（建议），body enable_thinking=true，mt2400 | model_override=glm-4.5（或可用新号），body thinking=true（字段以智谱文档核对），mt2400 | 模型须为 o1/o3/o4/gpt-5 系：body reasoning_effort=high + 用 max_completion_tokens=2400（不用 max_tokens）；若当前模型是 gpt-4o 系则仅 mt2400 并提示用户改填 o 系模型 |

**模型自动切换规则**：深度档只在"已选服务商是预置商 + 当前模型是该商 chat 系"时做 `model_override`（发送期临时替换，请求前在 caption 提示"已临时切换为 X（仅本次）"）；若用户当前模型本身就是 reasoning/thinking 系（按前缀/名单识别），不重复切换、只注入参数。**自定义 base_url/模型**：深度档只把 max_tokens 提到 2400、快速档加 temp0.3，并提示"自定义模型无法自动选思考模型，想深度请填写支持思考的模型名"。另补规则：快速档若检测当前模型为 reasoning 系，同样不传 temperature（该类模型不支持）。

**兼容性与容错**（reasoning_effort/enable_thinking/thinking 均为 body 顶层字段；各厂差异）：
- OpenAI：chat 接口对未知顶层参数返回 400 "Unrecognized request argument"，且 reasoning 模型不接受 max_tokens 与 max_completion_tokens 并存 → 深度档按上表二选一。
- DeepSeek：deepseek-reasoner 不支持 temperature/top_p 等，设置会 400；reasoner 流式时 content 迟迟为空、只有 delta.reasoning_content。
- DashScope/智谱/多数国产网关：对未知字段有的忽略、有的 400，行为不一。
- **统一降级策略**：构造请求时把"推理专用字段（reasoning_effort/enable_thinking/thinking）+ temperature"作为可剥离组；HTTP 400 且错误文案含 parameter/param/argument/not supported/unrecognized 时，剥掉该组字段用长输出模式重试一次，成功则把"已按深度档请求，服务商不支持思考参数，已自动降级为长输出"作为提示回传 UI，不打断用户。实现上新增内部 `_post_chat(...)→(ok,text,info)`，`info={degraded,model_used}`。

**超时与成本**：timeout 现行 `(15,150)`；深度档 reasoner 首 token 常需 20-60s、总时长可能 60-120s+，映射为：快速 `(15,90)`、标准 `(15,150)`（现状）、深度 `(30,420)`，chat_stream 同步放宽读超时。spinner 文案分档：标准维持"约 10-40 秒"，深度改为"深度思考中：Reasoner 模型可能需要 1-2 分钟，请勿关闭页面"。成本提示：reasoning 过程 token 也计费，深度档通常为数倍于普通回答的费用，侧栏帮助文案写明"仅在对复杂失败根因/长命令排障时需要深度"。

## 可执行变更

**1) ai_config.py（存储层，最小改动）**：save_credentials/load_credentials 增加可选字段 `thinking`（"fast"|"standard"|"deep"，默认 "standard"）。沿用现有合并逻辑：不传时保留旧值，load 缺省补 "standard"（兼容旧 meta 文件）；继续只写 llm_meta.json，Key 仍走 DPAPI 单独文件，不加新依赖。

**2) ai_client.py（纯逻辑层，向后兼容）**：
- 新增档位规格常量与解析器：`TIER_SPEC = {fast:{max_tokens:800,temperature:0.3,timeout:(15,90)}, standard:{max_tokens:1400,timeout:(15,150)}, deep:{max_tokens:2400,timeout:(30,420)}}`；`REASON_EXTRA` 每商映射（DeepSeek→无 body 仅切模型；Qwen→enable_thinking；GLM→thinking；OpenAI o 系→reasoning_effort:"high" 且输出参数字段切 max_completion_tokens）；`is_reasoning_model(provider, model)` 前缀名单 o1/o3/o4/gpt-5、deepseek-reasoner、qwen3、glm-4.5/glm-4.6、kimi-k2-thinking。
- `resolve_request(provider, model, tier) -> (final_model, extra_body, max_tokens, param_name, temperature, timeout)`：实现"切模型/注入参数/自定义只加长"与"剥离重试"逻辑的单一入口。
- `chat_once`/`chat_stream` 签名各追加可选 kwarg：`model_override=None, extra_body=None, temperature=None, timeout=None, max_tokens_field="max_tokens"`，缺省 None 即走现值，**所有旧调用与 98 条测试零回归**；内部改调 `_post_chat`（携带 info 用于降级提示）。chat_stream 补一句：deep 档 reasoner 的 SSE 若只来 delta.reasoning_content 则累计到 info["reasoning"]（供未来问答区"思考中…"占位），content 照常拼接。

**3) app.py（UI 与调用点）**：
- 侧栏 AI 助手 expander 内、服务商下方加 `radio("思考强度", ["fast","standard","deep"], format_func=快速/标准/深度, key="ai_thinking")`，caption 文案"快速：省时省钱，适合简单问答；深度：自动切换 reasoner/thinking 模型，更慢更贵更细致"。默认取 `ai_load().get("thinking","standard")`。点"测试并保存"时把 thinking 一并写入 `ai_save`。
- 失败卡 AI 分析按钮：`_ai_cfg_now.get("thinking","standard")` → 用新入口发请求；spinner 文案按档位；deep 时 caption 展示 model_override/降级提示。
- 未来问答区（chat_stream）默认沿用当前档位，档位 radio 全应用共享一个 session 值，不另设。
- 预置模型建议表微调：DeepSeek 已含 deepseek-reasoner；Qwen 建议列表补 "qwen3-max"；GLM 补 "glm-4.5"；OpenAI 补 "o3-mini"/"o4-mini"（以官方列表为准，仅 help 提示不强校验）；Kimi help 提示 kimi-k2-thinking（未实测，作文字建议）。

**4) 测试与文档**：补 ai_client 单测：档位解析表、reasoner 不传 temperature、400 剥离重试后 info.degraded=True、chat_once 旧签名兼容、ai_config thinking 缺省/往返。文档落 docs/mobile_trust/，注明"思考强度不写密码、不落盘 model override、零新依赖"。

**结论**：用"配置存档位 + 发送期解析注入 + 剥离重试容错"的架构，即可在零新依赖、不动现有签名与测试的前提下交付三档思考强度；深度档真正的风险点是超时与费用，已用分档 timeout、spinner 文案与"仅临时切模型"对冲。
