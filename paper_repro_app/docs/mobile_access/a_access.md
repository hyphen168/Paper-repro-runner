# 手机访问架构设计规范 v1.0（专家组 · 访问架构设计师）

范围：局域网 + 公网远程"手机查看与控制"（提交/监控/日志/指标对比/失败诊断与 AI 分析/重跑，与桌面一致或核心子集）。约束锚点：零新锁定依赖、中文 UI、无 emoji、不写密码明文、v2.0.0 打包行为不变（默认 127.0.0.1 免防火墙弹窗）、复用 AutoDL SSH 凭据体系。

## 决策

### D1 场景矩阵与终裁

| 场景 | 方案 | 新增依赖 | 定位 |
|---|---|---|---|
| 同 WiFi 局域网 | 侧栏开关 → 0.0.0.0 + 防火墙放行 + 控制台打印 URL | 无 | 主（必做、无风险） |
| 异地公网 | SSH 反向隧道经 AutoDL 云机 + 官方「自定义服务」公网映射 | 无（paramiko 已锁定） | 主（训练进行时云机必开机，时间窗吻合） |
| 异地公网（更鲁棒） | Tailscale 异地组网 | 两端装官方客户端 | 备选/逃生通道 |
| —— | frp / 花生壳 / ngrok / Cloudflare | 公网 VPS、账号、国内不稳 | 否决（详见 D6） |

**局域网是第一交付物**：v2.0.0 已按发布规范默认绑 127.0.0.1，手机访问只差一个显式开关。开关写配置、重启生效，桌面/手机 UI 天然全功能可达（Streamlit 响应式 + 已有 620px 断点），无需另做移动子集页。

**公网终裁：SSH 反向隧道（-R）为主方案**。理由：① 用户 AutoDL 云机公网可达且已有完整 SSH 凭据面（`ssh_utils` 解析/连接、`RemoteRunner` 多候选、公钥注入），隧道可纯 paramiko 实现——`paramiko` 已在 requirements.txt 锁定，`ssh` 命令行与手机 SSH 客户端均不需要；② 手机侧只开浏览器；③ "想看训练进度"这一最高频需求发生时 AutoDL 实例必然在跑（开机），隧道天然可用。**备选 Tailscale**：无需云机常开、设备级身份鉴权、PC 睡眠恢复更稳，用于"云机已关机但想看历史/AutoDL 自定义服务不可用"时段。两条路径共用同一个应用层访问口令（D2），可随时切换。

### D2 访问控制：无内置登录的分层信任

Streamlit 无登录。方案：
- **局域网**：信任家庭 WiFi，开关默认关；可选设置访问口令（应用层会话门）。家庭访客 WiFi/AP 隔离风险在文档注明。
- **公网**：**强制口令**。`tunnel_remote.py` 启动自检——`cloud_config.json`（`LocalConfigStore`，已 chmod 600）中无口令哈希即拒绝启动并打印中文原因，杜绝裸奔。
- **口令落盘**：`sha256(salt + pin)`，salt 随实例生成同目录存放，绝不明文；输入走 `st.text_input(type="password")` / `getpass`，不落 argv（避免进程列表泄漏）；日志沿用 `ssh_utils.sanitize` 脱敏。
- **会话门实现**：`render_app()` 顶部（`set_page_config` 后）检查 `st.session_state["access_ok"]`；未过门且服务端开启了访问开关时，全页仅渲染口令框。本机桌面端同一会话只需输一次（Streamlit 无 cookie API，不追 localStorage hack）。
- **链路安全说明**：PC↔AutoDL 隧道段全程 SSH 加密；手机↔AutoDL 公网段由官方映射承载，若自定义服务提供 https/访问凭据选项则优先开启，应用口令兜底。

### D3 二维码显示取舍：仅文字 URL 为 v1 默认

裁定（三选一）：**仅文字 URL（默认）** > **外部 QR API（可选按钮）** > **qrcode 库（否决）**。
- `qrcode` 库：为一次扫码引入新锁定依赖并连带 Pillow，违背"零新依赖"，否决。
- 外部 API（`st.image("https://api.qrserver.com/v1/create-qr-code/?data=…")`）：零代码依赖但依赖 PC 公网可达、URL 出网、服务可用性不可控。
- **结论**：局域网面板默认渲染文字 URL + 复制按钮（手机就在 PC 旁，输短 URL/拍照存文本成本低）；"显示二维码"做成可选小按钮，请求失败或离线自动隐藏并回退文字。远程场景**不提供二维码**（URL 含主机与口令语义，扫码传播面大、价值低）。

### D4 断线 / 重连 / 常驻 / 睡眠

- **隧道进程化 + 自动重连循环**（paramiko，Windows 原生，替代非 Windows 的 autossh）：`set_keepalive(30)` 保活；检测 `transport.is_active()` 为假或连接异常即按 2/5/10/30s 退避重连并打印中文原因（实例关机显示"实例未开机（E_CONN_UNREACH 类），60s 后重试"）。
- **电脑睡眠**：睡眠会冻结 PC 上调度/落库线程与隧道——任务若在云端跑，唤醒后 app 会提示"后台线程不在运行"，按既有"重新执行流水线"恢复。文档明确：**远程监控期间电源策略设为合盖不睡眠**（这是本方案唯一硬约束）。
- **手机端 2s 轮询**：`live_monitor`/`_auto_refresh_monitor` 仅在监控页可见时建 fragment（现状已满足）；浏览器后台标签节流（iOS Safari 挂起 JS）属预期，回到前台自动续刷；锁屏/切走不产生轮询流量。不做推送（零基础设施），文档给"完成任务后回看"心智模型。

### D5 PWA / 添加到主屏幕：不加

局域网 IP 为 http 非安全上下文，Service Worker 与 Web App Manifest 均不可注册 → 非真 PWA、无离线无推送。结论：只给"添加到主屏幕"文本指南（iOS 全屏书签体验尚可；Android 为普通书签）。远程 URL（自定义服务公网地址/Tailscale IP）稳定不变，值得存主屏；局域网 URL 随 DHCP 漂移，建议路由器对 PC 做 IP 保留。

### D6 候选淘汰与 AutoDL 公网可达性判定

- AutoDL 实例默认**无独立公网 IP**：对外仅两个入口——控制台暴露的 SSH 映射端口（`connect.xxx.seetacloud.com:随机端口`）与官方「自定义服务」映射。因此"`-R` 绑 0.0.0.0 后手机直连"**不成立**（公网无路由到该端口）；手机 SSH 客户端二次转发 UX 不可行，否决。手机访问云机端口的正解只有：**云机 127.0.0.1 绑隧道端口 → 控制台「自定义服务」把该端口映射为公网 URL**。绑定地址默认 127.0.0.1（防 AutoDL 邻实例嗅探）；若自定义服务要求监听全接口，脚本提供 `--remote-bind 0.0.0.0` 并在 AutoDL 实例 sshd 开 `GatewayPorts clientspecified`。功能与 URL 形态以官方控制台为准，文档标注"需实名/工单/实例运行中"等官方限制并给出人工核对点。
- Tailscale：免服务器、免费额度足够、身份鉴权内建；代价是手机/PC 装客户端 + 登录账号（微软/GitHub/邮箱），国内控制面与中继需实测（必要时后续自建 DERP，不在 v1）。
- frp/花生壳/ngrok/Cloudflare：分别需要额外公网 VPS、客户端/路由器改造+实名、账号+随机域名、国内边缘不稳——相对既有 AutoDL 通道均无优势，否决。

## 可执行变更

**C-1 `start_app.py`（局域网核心）**
- 新增读配置：`cfg = json.loads((Path.home()/".paper_repro_app"/"cloud_config.json").read_text(...))`（复用 `LocalConfigStore` 路径，stdlib 即可，不引 streamlit）；`allow_lan = str(cfg.get("allow_lan")) == "1"`。
- `start_app()` 启动参数 `--server.address` 由固定 `127.0.0.1` 改为 `"0.0.0.0" if allow_lan else "127.0.0.1"`（P0-3 默认行为不变）；`is_port_in_use` 早退分支若检测到配置与旧实例不符，打印"访问设置已变更：请关闭旧窗口后重新双击 start_app.bat"。
- 控制台打印手机访问块（复用 `get_local_ips()`）：`手机访问（同一 WiFi）：http://192.168.x.x:<实际端口>`（多 IP 全列；过滤虚拟网卡提示以 192.168/10./172.16 开头者优先）。
- 防火墙两步文案：① 首次以 0.0.0.0 启动会弹 Windows 安全中心警报 → 勾选"专用网络"并允许（若 WiFi 显示"公用网络"先改专用）；② 无弹窗或曾误拒 → 管理员运行 `netsh advfirewall firewall add rule name="Paper Repro App <port>" dir=in action=allow protocol=TCP localport=<port> profile=private`，删除用 `delete rule name=...`。附 `scripts/firewall_open.bat`：自提权（`powershell Start-Process -Verb RunAs`）执行 netsh，免手输。

**C-2 `app.py` 侧栏"手机访问"面板 + 会话门**
- 侧栏新增 expander（置于"云端配置"与天气区之间，`render_app()` 内）：
  - `st.checkbox("允许局域网访问（重启生效）", value=cfg.allow_lan)` → `config_store.save({"allow_lan": …})`，保存后 `st.info("已写入配置：关闭本窗口后重新双击 start_app.bat 生效")` + 预显示 URL（`get_local_ips()` 已在 app import 面）。
  - 访问口令设置：`type="password"` 输入 + "设置/清除"，落盘 `salt+sha256`；文案说明"开公网远程必须设置"。
  - 远程区：显示 `tunnel_remote.py` 启动命令（一键复制）与 `tunnel.state` 状态（隧道存活/断开，Launcher 与隧道脚本各写此文件于 `~/.paper_repro_app/`）。
- 会话门：`render_app()` 在 `st.markdown(APP_CSS)` 之后插入守卫——当 `(allow_lan or 远程开) and 已设口令 and not session_state.access_ok` → 渲染口令框即 return；校验通过写 `session_state["access_ok"]=True`。

**C-3 `scripts/tunnel_remote.py`（公网主方案，纯 paramiko）**
- 参数：`--ssh-target "<AutoDL 控制台整行 ssh 指令>"`（复用 `parse_connection_profile` 解析 host/user/port/key，天然支持多候选形态）、`--local-port 8505`、`--remote-port 18505`、`--remote-bind 127.0.0.1`、`--key`（缺省走 profile/config）、密码走 getpass 交互（或 `--password-stdin`），**不进 argv**。
- 启动自检：`cloud_config.json` 无 `access_pin_hash` → 打印"公网暴露必须先设置访问口令"并退出码 2。
- 主循环伪码：`ssh = ssh_connect(profile); t = ssh.get_transport(); t.set_keepalive(30); t.request_port_forward(bind, remote_port)` → 每 5s 查 `is_active()`，异常按 D4 退避重连；每次状态变更写 `tunnel.state`（pid/status/时间/远端端口）并打印中文行。
- 密码登录的 AutoDL 用户：先在该 app 内"注入公钥到服务器"，隧道即可无密码常驻（推荐路径）；纯密码用户手动跑脚本交互输密码即可。

**C-4 AutoDL 侧与手机操作步骤文案（进文档）**
1. 桌面开 `start_app.bat`，侧栏"手机访问"设访问口令。
2. AutoDL 控制台确认实例开机，复制整行 SSH 登录指令。
3. 桌面双击/运行：`.venv\Scripts\python scripts\tunnel_remote.py --ssh-target "<整行指令>"`（Windows OpenSSH/paramiko 均可）。
4. AutoDL 控制台添加「自定义服务」，服务端口填 18505（隧道远端端口），获得公网 URL；若要求监听全接口，用 `--remote-bind 0.0.0.0` 并在实例 sshd 开 `GatewayPorts clientspecified`。官方限制/URL 形态以控制台实际为准。
5. 手机浏览器打开该 URL → 输入口令 → 与桌面一致的提交/监控/诊断/重跑。用完 Ctrl+C 停隧道并在控制台删自定义服务。
6. 逃生通道：装 Tailscale（PC/手机同账号）→ 手机开 `http://<PC 的 100.x 地址>:8505` → 口令。

**C-5 `ui_theme.py` 移动端细节（在既有 620px 断点内追加）**
- `@media (max-width:620px)`：`[data-testid="stColumn"]{min-width:100% !important}` 强制 st.columns 纵向堆叠（解决 SSH 四列/微调三列在窄屏挤压，需在 1.62 DOM 下回归确认）；按钮 `min-height:44px`（触控达标，现 38 偏小）；`[data-testid="stMetricValue"]{font-size:22px}`；日志 `font-size:12px;max-height:260px`；`body{background-attachment:scroll}`（iOS fixed 背景性能）；stepper 节点 34→28px。提交 radio 已 `horizontal=True`，窄屏自动换行，保持。

**C-6 手机 URL 记忆指南（文档，非代码）**
- iOS：Safari 分享→添加到主屏幕（类全屏书签）；Android：Chrome 菜单→添加到主屏幕。远程 URL 稳定值得存；局域网 URL 先给 PC 做路由器 IP 保留/DHCP 绑定再存主屏。

**C-7 测试与验收清单**
- 92 pytest 保持全绿（新增 `config_store`/`tunnel 参数解析`/PIN 哈希纯逻辑测试，不涉 GUI）。
- 手工验收：开关关→默认 127.0.0.1 无弹窗（回归 P0-3）；开→重启后手机同 WiFi 可开、桌面照常；口令门：局域网本机/手机均一次输入；隧道：AutoDL 自定义服务 URL 手机可开、拔网线重连自动恢复、实例关机给出中文提示；睡眠唤醒后隧道自动重连、监控页按"重新执行"可恢复。

**C-8 文档落盘**：`docs/mobile_access/ACCESS_PLAN.md`（本规范全文）、`scripts/start_tunnel.bat`（调 C-3 并保活窗口）、`scripts/firewall_open.bat`（C-1）。侧栏面板内嵌精简版操作步骤。

## 附：风险与未决项
- AutoDL「自定义服务」的可用性/URL 形态/是否需实名或工单以官方控制台为准——文档给核对点，实现不依赖其细节。
- Tailscale 国内连通性需用户实测；失败即回退 SSH 隧道主路径。
- 手机端 st.columns 强制堆叠的 CSS 需在 1.62 真实 DOM 回归，未验证前不合并发布。
