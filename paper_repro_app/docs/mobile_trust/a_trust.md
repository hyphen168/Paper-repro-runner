简报已写入权威输出路径（4248 字节，约 2400 中文字符目标内）。以下为交付摘要。

# Research: 受信设备机制设计（Streamlit 本地控制端 + 移动远程访问）

## Summary
经研读 `access_gate.py`、`app.py::_access_gate`、`ai_config.py`（DPAPI+Lock 先例）、`storage_utils.py`（内存态先例），并核对 Streamlit 平台约束后终裁：采用 **URL 设备 token（st.query_params 直达链接）** 作为唯一受信通道；Cookie（服务端 Set-Cookie）与 iframe-localStorage 两路因 Streamlit 无法写响应头、组件 iframe 沙箱隔离（opaque origin）、以及零新依赖约束而否决。设计要点：口令通过后签发 `secrets.token_urlsafe(32)`，本机 `access.json` 仅存 sha256+元数据+epoch，默认 180 天过期、逐条/整体可吊销，仅 lan/tunnel 模式启用。

## Findings
1. **终裁方案 a（URL token）可行且最优** — 口令门是单入口守卫（`_access_gate` 置 `auth_ok` 否则 `st.stop()`），在其口令成功分支后签发 token、用 `st.query_params["tk"]=raw` 改写地址栏，书签/主屏天然携带参数，后续每次访问守卫顶部验 tk 即放行，全链路无电脑介入。这是 Streamlit 唯一零依赖的浏览器侧持久通道。
2. **Cookie 方案否决** — Streamlit Python 侧无法设 Set-Cookie（Tornado 服务层未开放），社区组件方案违背零新依赖且 lan http 下 Secure 受限。
3. **iframe-localStorage 方案否决** — `st.components.v1` iframe 与父文档跨源隔离（sandbox 无 allow-same-origin → opaque origin），读写均不可行，且 localStorage 语义上无法被本机吊销。
4. **安全设计** — 只存 sha256 哈希（256bit 高熵免盐）、`hmac.compare_digest` 常数时间比较、`epoch` 全局作废 + 逐 id 吊销、TTL 由 env `PAPER_REPRO_TRUST_TTL_DAYS` 配置、口令重置自动吊销全部、验证失败与口令失败同文案不落日志；风险声明（LAN http 嗅探/转发即授权）与缓解写入 UI 与文档。
5. **不依赖 Host 头** — 自动改写当前地址栏 URL（所见即所得），规避 tunnel 下 X-Forwarded-Proto/公网 URL 未实测的不确定性。

## Sources
- Kept: `paper_repro_app/access_gate.py`（现有口令门全貌：ACCESS_FILE、PBKDF2、0600、不落日志）；`app.py` `_access_gate`/`render_app`（守卫位置、expose 语义、侧栏插入点）；`ai_config.py`（DPAPI、threading.Lock、0600 文件惯例）；`storage_utils.py`（内存态/后台线程先例）。
- Dropped: 无外部网页来源——本环境未提供 `web_search` 工具，未检索第三方文档。

## Gaps
- Streamlit 平台限制（无服务端 Set-Cookie、组件 iframe 沙箱隔离）为本框架公认事实，但本环境无法联网实测；建议实现前以目标 Streamlit 版本实测 `st.query_params` 写回地址栏（含旧版 `experimental_get_query_params` 回落路径）各一次。
- 「添加到主屏」保留 query 参数在 iOS Safari/Android Chrome 的行为未实测（属标准行为，风险低）。

## Supervisor coordination
无需协调。已按任务指定格式（## 决策 / ## 可执行变更，中文、无 emoji、无密码明文、零新依赖）产出完整变更清单，交付物已落盘权威路径 `a_trust.md`；实现细节待「实现工程师」接单执行。