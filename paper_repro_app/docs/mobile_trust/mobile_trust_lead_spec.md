# 手机受信访问与思考强度规范 v1.0（主导裁决版）

四份报告（a 受信设备 / b 自主入口 / c 思考强度 / d 打包形态）已通读；关键代码事实复核：access_gate.py 口令门单守卫（_access_gate 置 auth_ok 否则 st.stop）、ai_client chat_once/chat_stream 现仅传 model+max_tokens、start_app 支持 --expose lan/tunnel 且已含 is_port_in_use 单实例语义、监控轮询实际 run_every=3.0、98 测试绿、v2.0.0。本规范为实施唯一依据，冲突处以本文件为准。

## 一、总纲

设计原则：
1. 手机端不做原生打包：活页控制台（WebSocket 轮询 + 云端执行）离线价值为零，真卖点是"免口令一键直达"，不是 App 图标壳。
2. 一切暴露都过口令门：lan/tunnel 任何新通道不绕过 access_gate；令牌只是"第二条口令"，可吊销、可过期、可整体作废。
3. 唯一持久通道是 URL（st.query_params）：Streamlit 无服务端 Set-Cookie、组件 iframe 为 opaque origin 隔离；cookie 与 localStorage 两路否决。
4. 受信与自主都要"电脑零操作"：常开自启（lan）服务闭环 + 主屏书签入口闭环 + 令牌接管口令。
5. 思考强度是"单次请求级"临时参数：只改本次发送的模型与 body 字段，不回写已保存 model；reasoning 专用字段可剥离降级，服务端不支持的请求自动长输出重试，绝不打断用户。

目标一句：手机在主屏点一下图标即可免口令进入并完整控制应用，AI 助手可按 快速/标准/深度 三档思考，全程零新依赖、可吊销、可回退。

## 二、受信设备终版

机制选型：URL 设备令牌（采纳 a）。Cookie 与 iframe-localStorage 否决（平台限制 + 无法本机吊销）。

1. 签发与存储（access_gate.py 向后兼容扩展，schema v2）：
   - access.json 结构：{"salt","hash","epoch":1,"tokens":[{id,name,hash,created_at,expires_at,last_used_at}]}；0600 + threading.Lock；旧文件无 tokens/epoch 字段按默认读，98 测试零回归。
   - issue_device_token(name) -> raw：secrets.token_urlsafe(32)，本机只存 sha256(raw)；明文仅签发当次经 URL 传输，不落日志/DB/云机。
   - verify_device_token(raw) -> bool：hmac.compare_digest 常数时间；比对 epoch 与 expires_at；命中更新 last_used_at（写频按分钟节流）；验证失败与口令失败同文案、不落日志。
   - TTL：默认 180 天；PAPER_REPRO_TRUST_TTL_DAYS 环境变量可配（显式 0 不过期）；过期条目惰性删除。
   - 吊销：revoke_device_token(id) 逐条；revoke_all_tokens()=epoch+1 并清表；set_access_code/reset 一律 epoch+1（改口令即全部作废）；clear_access_code 同步升 epoch。吊销即时生效（每次请求实时校验）。
2. 守卫改造（app.py::_access_gate，仅 expose=lan/tunnel）：
   - 未置 auth_ok 时先读 st.query_params["tk"]（无则回落 experimental_get_query_params）→ verify_device_token 命中置 auth_ok；不剥离 URL 参数以保书签持续有效。
   - 口令成功分支：勾选「信任此设备」→ 签发 → 写 st.query_params["tk"]=raw → rerun；老版本不可写时降级为展示直达链接 code 块。
   - 进入后顶栏横幅「受信设备模式 · 免口令已生效」。
3. UI 与风险缓解：
   - 认证页口令下加「信任此设备（此设备下次免口令）」勾选，默认不勾。
   - 侧栏「安全 · 受信设备」expander：设备表（备注/签发时间/最近使用/剩余有效期）+ 逐条/全部吊销（二次确认）+ 风险声明（"此链接等同口令，请勿转发"）+ access.json 路径；本机模式追加口令重置入口。
   - 文案无 emoji、中文；风险经明文 http 可嗅探与转发即授权，由"仅入口凭证 + 可吊销 + 口令门仍在"对冲，写入卡片与文档。

## 三、手机自主入口终版

1. 常开（lan 档 + 开机自启，采纳 b D1，范围仅局域网）：
   - 前置：start_app.py 加 --no-browser（argparse store_true；start_app 增加参；"已在运行"分支同样遵守）。start_app_remote.bat 不透传参数，自启脚本必须直调 start_app.bat --expose lan --no-browser。
   - 新增根级 autostart_install.bat / autostart_uninstall.bat：install 向 %APPDATA%\...\Startup\ 写 paper_repro_lan.cmd（start /min cmd /c "start_app.bat --expose lan --no-browser"）；uninstall 删除之；回显手工路径备选。
   - 防火墙：首次管理员运行 open_firewall.bat（仅专用网络建议）；口令建议 8 位以上（提示不硬改，4 位策略兼容存量）。
   - 公网 tunnel 档维持手动（云机按量/URL 易变）；不做公网常开。单实例语义已由 is_port_in_use 成立；tunnel 可复用常开实例（0.0.0.0 亦监听回环、口令门 env=lan 仍生效），手册写清"无需双开"。
2. 主屏快捷方式 = 唯一推荐入口（不做真 PWA、不做 QR 内置）：
   - PWA 终裁：否决主体。SW/manifest 需 https：lan 档必不合格；tunnel 档 AutoDL URL 未实测。即便实测 https，Streamlit WebSocket 控制台离线收益约零、静态作用域难覆盖、双 origin 维护成本高——不预埋 manifest/sw.js。两步验证法入文档（地址栏无锁即放弃；有锁再做成本评估）。
   - QR：不内置（外网 API/新依赖 + 场景错配），URL 文本 + 复制兜底；文档提外部码工具用法即可。
3. 应用内「手机直达」卡（expose=lan/tunnel 时渲染，替换现侧栏地址 caption）：
   - 可复制地址（全部可达 IP 列表；端口附注"非 8505 见启动日志"）；主屏添加步骤（iOS Safari / Android Chrome）；打不开三分法（电脑是否开机登录 / 手机是否同一 WiFi / 管理员跑一次 open_firewall.bat）；说明"首次打开仍需访问口令（可勾选信任免后续口令）"。
4. GUIDE.md 增补 G-8「手机自主进入」：常开安装/卸载、主屏添加入口、口令强度建议、tunnel 复用常开、关机/断网语义、安全须知。

## 四、思考强度终版（采纳 c）

1. 档位：快速/标准/深度，默认标准；仅作用于单次请求（model_override + body + max_tokens + timeout），不回写已保存 model。
2. 规格常量与解析（ai_client.py 新增，全部可选 kwarg，旧签名/调用零回归）：
   - TIER_SPEC = {fast: mt800 temp0.3 timeout(15,90), standard: mt1400 timeout(15,150), deep: mt2400 timeout(30,420)}。
   - REASON_EXTRA：DeepSeek 深度→model_override=deepseek-reasoner（不传 temperature）；Qwen→qwen3-max + enable_thinking:true；GLM→glm-4.5 + thinking:true；OpenAI（o1/o3/o4/gpt-5 系）→reasoning_effort:"high" 且输出参数字段用 max_completion_tokens（不与 max_tokens 并存）；Kimi→保持模型 + mt2400 + help 提示 kimi-k2-thinking。
   - is_reasoning_model(provider, model)：前缀名单判定；已是 reasoning 系则不重复切换只注入参数；reasoning 系一律不传 temperature（快速档同）。
   - 自定义 base_url/模型：深度只提 mt2400、快速加 temp0.3，caption 提示自行填思考模型。
   - resolve_request(provider, model, tier) -> (final_model, extra_body, max_tokens, field_name, temperature, timeout)：单一入口。
3. 容错降级：reasoning 专用字段 + temperature 为"可剥离组"；内部 _post_chat 遇 HTTP 400 且文案含 parameter/argument/not supported/unrecognized → 剥组重试为长输出，info={degraded:true, model_used} 回传 UI 提示，不打断。
4. 存储与 UI：
   - ai_config：save/load 增可选 thinking（缺省 standard，兼容旧 meta，仍只写 llm_meta.json）。
   - app.py 侧栏 AI 助手加 radio(key=ai_thinking，format 快速/标准/深度)，caption 注明深度更慢更贵更细致 + "仅复杂根因需要深度"；测试并保存时一并写入。
   - 失败卡 AI 分析与未来问答区取当前档位；spinner 分档文案（深度："深度思考中：可能需要 1-2 分钟，请勿关闭页面"）。
   - 预置模型帮助补 qwen3-max / glm-4.5 / o3-mini / o4-mini / kimi-k2-thinking（文字建议不强校验）。
5. 成本说明入 UI help：reasoning 过程 token 计费，深度档通常数倍费用。

## 五、打包形态终裁（采纳 d）

推荐组合 = 主屏快捷方式（通用，零代码）+ lan 常开自启（服务闭环）+ 受信直达链接（免口令闭环）+ 文档「手机使用」节。真 PWA / Android WebView 壳 APK / iOS 壳 / 远程桌面类全部否决（判据：收益约等于书签图标，成本为工具链/审核/地址漂移维护/分发信任恶化数倍）。tunnel https 实测通过后仅做 manifest+图标的 P2 渐进增强（可选，不阻塞）。交付物收敛为：受信令牌功能件 + 直达卡 + autostart 脚本 + 两处文档（FRIEND_GUIDE 常量与 GUIDE.md）新增「手机使用/G-8」，README 同步为次（zip 不含 README）。

## 六、实施顺序 P0/P1 与不做清单

### P0（一次提交，先做受信闭环）
- P0-1 access_gate.py v2：schema/issue/verify/list/revoke/revoke_all/epoch 语义 + TTL 常量 + 单测（签发往返、错误拒、过期拒、epoch 全作废、逐条吊销、旧文件兼容）。
- P0-2 app.py _access_gate：query 校验优先 + 勾选信任签发写 URL + 降级 code 块 + 横幅。
- P0-3 app.py 侧栏「安全 · 受信设备」expander（吊销双步确认 + 风险声明）。
- P0-4 app.py 侧栏「手机直达」卡（地址复制 + 主屏步骤 + 三分法）。
验收：pytest 98+ 全绿、AppTest 0 异常、AppTest 模拟 st.query_params tk 直通（可加单测/mock）、make_dist 打包泄漏扫描零命中、解压副本 AppTest 0 异常。

### P1（次批提交）
- P1-1 start_app.py --no-browser + autostart_install/uninstall.bat；cold start 验证不再抢焦点。
- P1-2 ai_client TIER_SPEC/REASON_EXTRA/resolve_request/_post_chat 与 chat_once/chat_stream 可选 kwarg + 400 剥离重试 + 单测（档位表、reasoner 无 temp、降级 info、旧签名兼容）。
- P1-3 ai_config thinking 字段 + app.py 侧栏 radio 与失败卡/spinner 分档。
- P1-4 GUIDE.md G-8 + FRIEND_GUIDE「手机使用」节 + 手机直达文档 docs/mobile_trust/（含 PWA 两步验证法、QR 外部工具用法）。
验收：98+ 全绿；bash 无关；真机 375px 八步流程（口令页→错口令拒→信任签发→无痕直达免口令→吊销失效→主屏图标直进→桌面无回归）。

### 不做清单
不做原生 App / WebView APK / iOS 壳 / 远程桌面类；不预埋 manifest/sw.js；不内置 QR 生成；不做公网常开；不把 model_override 持久化；不改口令最少位数硬策略；cookie/localStorage 受信通道不启动。

参考轮询口径统一：监控页 run_every=3.0（文案同步为"每 3 秒自动刷新"，避免代码漂移）。
