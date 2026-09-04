核对完毕。已实读：`start_app.py`（绑定/端口）、`config_store.py`、`storage_utils.py`（内存态 `_EXEC_STATE`/sanitize 调用）、`app.py` 全文（会话与控件用法）、`ssh_utils.py`（`sanitize`/`ensure_ssh_key_file`）、`remote_runner.py`、`database.py`、`repo_profiles.py`、`logging_config/logger_utils`、`.streamlit/config.toml`、`docs/release` 与 `docs/.../c_legal.md` 既有安全裁定。未发现任何现有 auth/口令代码（全仓 grep 零命中）。下为安全模型评审终稿（报告落盘 `docs/mobile_access/` 需写盘能力，本文全文即交付物）。

---

## 风险与裁定

**暴露面分析与裁定（问题 1）**
- **现状正确项**：`start_app.py:296-301` 硬绑 `--server.address 127.0.0.1`（P0-3 已落地，默认关、免防火墙弹窗）；Streamlit 无内置登录（`.streamlit/config.toml` 仅主题）；全功能页零守卫。
- **风险定性**：LAN 开 0.0.0.0 后，同网段者可视日志/历史/档案、可提交新任务、可点"结束当前任务/重新执行"。其中隐蔽升级点是 `storage_utils.py:161-172` 的 `_EXEC_STATE` 为**进程级全局**——任何会话点"重新执行流水线"都会静默复用 `task_passwords[task_id]`（`app.py` rerun 分支 `_mem_pwd`），即攻击者**无需知道云端密码**即可借主人内存凭据触发云端执行；且 `ssh_key_path` 默认已预填主人私钥路径，新任务可借钥对云端跑任意仓库命令。结论：控制面≈"凭据代理+计费代付"，网络层加密（隧道）只保传输、不保控制。
- **终裁**：**默认关闭；凡开启非回环监听（LAN 或隧道）一律启用应用层"首次访问口令"**。"简单只读开关"否决——当前无只读视图可复用（监控/历史同一渲染路径、按钮与数据同页），做每会话角色裁剪比一次口令门改动面更大；"纯网络层安全"仅限本人可信 WiFi 且建议仍开。
- **实现要点**：① 口令只存散列：`os.urandom(16)` 盐 + `hashlib.pbkdf2_hmac("sha256", …, 200_000)`（或 scrypt），存 `~/.paper_repro_app/access.json`（0600）；`hmac.compare_digest` 校验；通过后置 `st.session_state["auth_ok"]`，在 `render_app()` 顶部守卫 `st.stop()`。② 门**只在 expose 模式开启**：`start_app.py` 新增 `--expose lan|tunnel` 参数，以环境变量传给 `app.py` 决定是否守卫——桌面本机体验零变化。③ 口令不进任何日志、失败提示固定文案、可加次数退避；手机"记忆"=浏览器密码管理器自动填充 + 标签页级 session（零新依赖、不做长效 cookie）。④ 开启时侧栏同步展示 `http://<PC 局域网 IP>:端口` 与访问 URL 二维码可选。

**凭据面裁定（问题 2）**
- **正确项（维持）**：密码仅进程内存——DB 无 password 列（`database.py` schema）、`config_store.save` 无密码字段、重启/换会话即失效（rerun 需补输）；实时日志窗口回写前过 `sanitize`（`ssh_utils.py:377-385`、`storage_utils.py:195`）；repo_profiles 红线不写凭据。**裁定：云端密码/私钥对手机只输不显**——现有 `type="password"` 空默认保持，不新增"明文查看"项。
- **P1 发现**：`app.py` "SSH 私钥路径（或粘贴私钥全文）"是普通文本框；提交块 `config_store.save` 与 `create_task` 把 `resolved_ssh_key` **原文**写入 `cloud_config.json` 与 `tasks.db.ssh_key_path`。用户若粘 PEM 全文，私钥正文明文落两个本地文件（仅 0600 弱防），且同会话页面/手机渲染往返。最小修复：保存前统一走 `ensure_ssh_key_file` 转 0600 文件路径再落库落配置，DB/档案永不存私钥正文；含 PEM 的输入框改为摘要/遮蔽显示。
- **P2**：历史页"后台系统日志文件"尾 40 行直出 `app.log`（含完整远端命令/连接诊断），远程模式建议隐藏或截断；远端 stdout/直链 token 残余风险维持 `c_legal.md` 既有声明。host/user/端口等元数据可接受（非凭据）。

**执行面裁定（问题 3）**
- **裁定：需要二次确认，且分两级**：`结束任务/重新执行/提交任务`→P1，双步确认（首击置"再点一次确认（5s）"态或 `st.dialog`），防手机误触与预填档案一键提交的资费误触发；**LLM AI 修复执行（在途）→P0 门禁**：须先渲染待执行命令只读 `code` 供审阅 + 显式确认按钮，不做静默自动执行。

**隧道方案结论（问题 4）**
- **采用 SSH -R 反向隧道**（零新依赖、复用 AutoDL 既有 SSH 凭据与 ssh_utils/RemoteRunner）：`ssh -N -R 127.0.0.1:<port>:127.0.0.1:8505 user@cloud -i <key>`——**仅远端回环转发**（不开 GatewayPorts、不绑 0.0.0.0，杜绝明文 HTTP 上公网），手机**二次访问**：SSH 登 AutoDL 后用 `-L` 本地转发进浏览器（两跳均 SSH 加密端到端）。key 认证专用独立 ed25519 子钥、`authorized_keys` 加 `restrict` 前缀、隧道命令带 `-o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30`、禁密码转发。隧道模式**口令门同样开启**（云机被共用/攻破时仍挡最后一层）。第三方（Tailscale 备选但需双端客户端+账号+国内 DERP 质量；frp/ngrok/花生壳需公共中继且存明文段）不作首选。

## 兜底规则清单

1. **默认闭环**：无 `--expose` 参数时行为不变（127.0.0.1）；验收 `netstat` 无 0.0.0.0 监听。
2. **口令门**：expose 模式 `render_app` 顶部守卫 + `st.stop()`；散列 0600 落盘、`compare_digest`、不落日志、错误提示固定；回环模式不启门。
3. **凭据红线**：密码类控件一律 `type="password"`；私钥正文入库/入配置前转 0600 文件路径；打包泄漏扫描（make_dist P0-1 规则）扩展 `BEGIN .*PRIVATE KEY`、`access.json` 排除项。
4. **执行确认**：结束/重跑双步确认；提交对话框确认；AI 修复"先看命令、再点执行"门禁。
5. **隧道白名单**：远端仅回环绑定、专用 restrict 子钥、BatchMode、口令门常开。
6. **日志脱敏**：live 窗口 sanitize 保持；远程模式隐藏/截断 app.log 尾窗；GUIDE 声明 stdout 直链 token 残余风险。
7. **移动端基线**：触控目标 ≥44px、表单宽度适配、2s 轮询仅限 queued/running 状态（现 `@st.fragment(run_every=2.0)` 已满足，勿扩到空闲态）、不引新框架、无 emoji、中文。
8. **验收判据**：`--expose lan` 手机同 WiFi 见口令页→错口令拒→口令通过→结束/重跑需二次点按→桌面无参启动免口令→92+新用例 pytest 全绿→zip 泄漏扫描零命中。

**合并裁定：OK with notes（有条件通过）**——方案可行且贴合现状；放量前置条件为 P0 级口令门与 AI 修复执行门禁，P1 项为私钥正文落库路径修复与执行双步确认。评审全程未改任何文件。

## Review（English summary）
- Correct: default 127.0.0.1 bind (start_app.py:298); password memory-only (no DB/config column); live-log sanitize (ssh_utils.py:377, storage_utils.py:195); repo_profiles no-secret policy.
- P0 (gate): zero access control on any non-loopback expose + process-global `_EXEC_STATE` lets any remote session rerun with the owner's in-memory cloud password (storage_utils.py:161-268, app.py rerun path); no read-only safe subset exists → app-layer first-visit passphrase mandatory for LAN/tunnel modes.
- P1: pasted PEM private key stored verbatim to cloud_config.json/tasks.db via `resolved_ssh_key` (app.py submit block); route through `ensure_ssh_key_file` before persistence.
- P1: destructive actions (cancel/rerun/submit) need two-step confirm; upcoming AI fix-execution needs explicit command-review gate (P0).
- P2: app.log tail rendered in history tab; sanitize does not cover final stdout JSON/app.log.
- Tunnel verdict: SSH -R loopback-only + second-hop SSH access + dedicated restricted key + passphrase; third-party relay options deprioritized.
- Merge verdict: OK with notes (P0 passphrase gate and AI-fix-execution gate required before release).