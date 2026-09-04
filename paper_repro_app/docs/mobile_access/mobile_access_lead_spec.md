# 手机控制访问规范 v1.0（主导裁决版）

四份报告（a 访问架构 / b 安全 / c 移动 UI / d 运维）已通读，代码事实已交叉复核（start_app 绑定与端口检测、app.py 侧栏与 2s fragment、storage_utils 进程级 _EXEC_STATE 与 task_passwords、ssh_utils sanitize/ensure_ssh_key_file、ui_theme 620px 断点、config_store cloud_config.json）。冲突裁定：局域网口令按 b 一律强制（否决 a 的可选）；隧道主路径按 a/b 取 SSH -R 回环 + 系统 ssh 命令实现（弃 paramiko 自实现与第三方中继首选）；移动表单堆叠修复按 c 升 P0（375px 现不可输入属阻断）；轮询降频按 d 以显式开关为主、UA 自动检测为辅。本规范为实施唯一依据。

## 一、总纲

目标一句：任何人在任意有网处用手机浏览器即可查看与控制复现任务，安全默认、桌面体验零回归。

设计原则：
1. 默认闭环不回归：无 expose 参数时行为与 v2.0.0 一致（绑定 127.0.0.1、免口令、桌面 2s 轮询、现有 UI）。
2. 暴露即门禁：凡非回环监听（lan 或 tunnel）一律启用应用层口令门；进程级执行态（storage_utils._EXEC_STATE）是凭据代理面，网络层加密不构成控制面安全。
3. 凭据红线不变并收严：云端密码仅进程内存；私钥正文入库/入配置前必须经 ensure_ssh_key_file 转 0600 文件路径；任何发送到浏览器页面的凭据只输不显。
4. 破坏性动作双步：结束任务与重新执行需二次确认，防手机误触造成计费资损。
5. 零新框架优先；手机体验以原生响应式 CSS 修复达成；无 emoji、中文文案、数值化验收。

## 二、访问架构终版

### 档位总览
| 档位 | 绑定 | 口令门 | 典型场景 |
|---|---|---|---|
| 桌面默认（无参） | 127.0.0.1 | 关 | 本机使用（现行为，零变化） |
| lan（显式开关） | 0.0.0.0 | 开 | 手机同一 WiFi 直连电脑 |
| tunnel（显式开关） | 127.0.0.1（本地回环）+ 云机 127.0.0.1:18505 | 开 | 不在家经用户 AutoDL 云机中转 |

### P0-1 局域网档（start_app.py）
- start_app.py 新增参数 --expose lan|tunnel（默认无）；lan 时绑定 0.0.0.0 并把 PAPER_REPRO_EXPOSE=lan 写入进程环境；tunnel 时仍绑 127.0.0.1 并写 PAPER_REPRO_EXPOSE=tunnel。
- 新增 start_app_remote.bat：等价 `python start_app.py --expose lan`（供双击）。
- 启动成功日志在 lan 档额外打印：本机 http://127.0.0.1:<port> 与局域网地址清单（复用 task_utils.get_local_ips，每条一行 http://<ip>:<port>）。
- 防火墙：新增 open_firewall.bat（netsh advfirewall firewall add rule name="Paper Repro LAN" dir=in action=allow protocol=TCP localport=<port>），需以管理员运行；netsh 失败时打印手动放行指引（Windows 安全中心-防火墙-允许应用）。放行为一次性，脚本幂等。

### P0-6 公网档（tunnel）
- 主路径：本机系统 ssh（Windows OpenSSH，无则引导启用 Windows 可选功能）执行只回环反向隧道：
  ssh -N -R 127.0.0.1:18505:127.0.0.1:<本地port> -o BatchMode=yes -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 <user>@<云机host> -p <云机port> -i <私钥路径>
  - 复用 ssh_utils 现有连接档案解析与多候选：隧道脚本从 cloud_config.json 读 host/user/port 与已注入私钥路径；无可用免密 key 时提示先在本机完成一次公钥注入（既有「注入公钥」能力）。
  - 仅绑定云机回环 127.0.0.1:18505，不绑 0.0.0.0（杜绝明文 HTTP 上公网）。
  - 新增 start_tunnel.bat / tunnel_keepalive.py：子进程方式运行上述 ssh；退出码非 0 时 sleep 5 自动重启；打印状态行（已建立/重连第 N 次/失败原因截断）。
- 手机接入两条路径（文档写明，均端到端加密）：
  1. 首选体验：AutoDL 控制台「自定义服务」把云机 127.0.0.1:18505 映射为公网 URL（形态与门槛以官方控制台实测为准，标注核对点）；成功后手机直接浏览器打开该 URL 并过口令门。
  2. 零服务端依赖兜底：手机安装任一 SSH 客户端（如 Termius），执行 ssh -L 8505:127.0.0.1:8505 <user>@<云机host> -p <云机port>，随后浏览器访问 http://127.0.0.1:8505 并过口令门。
- 第三方（Tailscale/ZeroTier/frp/ngrok/花生壳）列备选仅作文档比较表，不作为实施项：需要双端客户端/公共中继或账号，国内可用性不可控。
- 二维码与 PWA 裁定（a）：默认仅提供文字 URL 与复制按钮；不引入 qrcode 库；外部 QR API 按钮可选（失败自动隐藏）列 P2；PWA 不实现（http 非安全上下文无法注册 SW），仅提供「添加到主屏幕」文字指南（P1）。

## 三、安全终版（b 裁定 + 收严）

1. 口令门（P0-2，expose 档强制）：
   - 存储：~/.paper_repro_app/access.json（0600），字段 salt（os.urandom(16) 十六进制）与 hash（pbkdf2_hmac sha256 200000 迭代）。
   - 流程：app.py 顶部（render_app 首行）读取环境 PAPER_REPRO_EXPOSE；为空=桌面模式跳过；非空且 st.session_state 无 auth_ok 时渲染口令页：无 access.json 则引导设置新口令（两次输入一致、长度 6 起），有则校验（hmac.compare_digest），通过置 st.session_state["auth_ok"]=True 并继续；否则固定文案提示（不区分不存在/错误），st.stop()。
   - 口令不进日志；失败连续 5 次后同会话退避 30s（仅内存计数）；不做长效 cookie（浏览器密码管理器自动填充即手机"记忆"）。
2. 私钥正文持久化修复（P0-3）：提交块在 config_store.save 与 create_task 前统一 resolved_ssh_key = ensure_ssh_key_file(原始值)；含 PEM 全文的输入框提交后回显改为已落盘路径摘要（basename），不再回填正文。DB/配置只存路径。
3. 执行确认（P0-5/P0-7）：
   - 「结束当前任务」「重新执行流水线」改为双步：首击按钮文案变为「再点一次确认（5 秒内）」，session 置 pending 并 5s 倒计时或再次点击才执行；桌面与手机一致（防误触）。
   - AI 修复执行（在途 AI 规范合并约束）：任何由 LLM 生成并可能执行的命令，先以只读 code 块渲染供审阅，配显式确认按钮后才允许执行；无静默自动执行路径。
   - 提交按钮保持单步（档案秒配价值优先），新增 st.dialog 提交摘要确认列 P2。
4. 日志与元数据：实时日志窗口 sanitize 维持；expose 模式历史页「后台系统日志文件」尾窗隐藏或截断（仅剩最近 10 行且标注"远程模式已截断"）列 P1；host/port/任务元数据不构成凭据，可展示。
5. 隧道白名单（P1 增强）：authorized_keys 建议给专用子钥加 restrict 前缀与 no-port-forwarding=false（反向允许）约束说明写入文档；BatchMode=yes 保证隧道不落密码。
6. 打包泄漏扫描扩展：make_dist 泄漏模式表追加 access.json、BEGIN .*PRIVATE KEY 排除断言（P0-8）；顺手清理 c_ui 遗留的 __dir_listing_probe.txt。

## 四、移动端 UI 终版（c 裁定）

1. 表单可输入（P0-4，阻断项）：ui_theme 追加 ≤620px 媒体规则——stColumn 强制单列堆叠（对 Streamlit 1.62 data-testid 同时命两套选择器兜底，如 [data-testid="stColumn"] 与横排容器父级 flex:1 1 100%）；提交卡 4 列主机/端口/用户名/密码输入在 375px 实测宽度 ≥95% 视口。
2. 触控与缩放（P0-4 同批）：≤620px 内输入控件 min-height 44px；font-size ≥16px（防 iOS 聚焦自动放大）；radio 运行方式四长标签 ≤1000px 改竖排；按钮 min-height 44px。
3. 对比表：容器 overflow-x auto + 内表 min-width 520px，页面本体不横向滚动（P1 附同批 CSS）。
4. 轮询降频（P1 主案=省流量开关）：侧栏新增「省流量模式（移动网络）」checkbox 存 session：勾选后监控 2s fragment 改为 run_every 5s 且日志窗口 22 行收为 8 行；UA 自动检测（st.context.headers 读 User-Agent，try/except 守卫，命中 Android|iPhone|Mobile）作为同开关的自动预置，用户仍可手改；桌面不勾选保持 2s。
5. 动效降级（P1）：_weather_engine.js 初始化探测 pointer:coarse / touch（matchMedia），触屏窄屏 skip 起始 2、DPR 上限 1.5、粒子密度 ×0.5；ui_theme ≤620px 关闭 backdrop-filter（实色兜底已有 @supports 之外的规则追加）；侧栏「关闭背景粒子」checkbox 作彻底旁路。
6. 验收清单 8 条以 375×667 + 真机（iOS Safari/Android Chrome 各一）覆盖：口令页渲染、错口令拒绝、表单可输入、按钮可达、轮询开关生效、对比表可横滑、任务页按钮双步、桌面 1366px 无回归。

## 五、常驻运维终版（d 裁定）

1. 状态显示（P1）：app 内置守护线程（30s tick）写进程心跳文件 ~/.paper_repro_app/heartbeat（含 pid/时间戳）；监控页头部胶囊显示「运行时长 · 最后刷新 mm:ss」；页面轮询命中且心跳超过 90s 转「疑似离线（电脑睡眠或崩溃）」提示；心跳文件在 2s/5s 轮询代码路径同时打点（避免守护线程被桌面 GC 误判）。
2. 断线矩阵（P1 文档+实现）：
   - 电脑睡眠唤醒：心跳恢复即自动正常（Streamlit 重连由浏览器自动）；隧道子进程由 tunnel_keepalive 重启。
   - 隧道断线：ssh 退出 → sleep 5 重试（无限，退避封顶 60s）。
   - app 崩溃：start_app_remote.bat 重双击自检（端口占用检测已实现）。
   - 手机断线：重新打开浏览器即可；任务执行在云端不受手机断线影响。
3. 养机指引（G-1 升级，文案纳入 GUIDE「手机访问」节）：电源计划建议「接电源 + 合盖不睡眠 + 不关机」；开机自启说明（shell:startup 放置 start_app_remote.bat 快捷方式）；明确「关窗即断云端会话（远端训练进程终止）」与「任务运行时勿关控制台窗口」。
4. 多开命中分支（P1）：默认端口被占用且为 expose 启动时，打印已有实例地址清单并退出，不弹第二个浏览器。

## 六、实施顺序与不做清单

P0（一次提交，先打通手机可用的最小闭环）：
- P0-1 start_app --expose lan + start_app_remote.bat + 地址清单打印
- P0-2 口令门模块（access.json/pbkdf2/compare_digest/环境变量守卫）与首访设置页
- P0-3 私钥正文持久化走 ensure_ssh_key_file（提交块单点收口）
- P0-4 移动表单堆叠 + 触控/字号 CSS（620px 媒体）
- P0-5 结束/重跑双步确认
- P0-6 隧道文档 + start_tunnel.bat + tunnel_keepalive.py（ssh -R 回环 18505）与两种手机接入说明（AutoDL 自定义服务 / Termius -L）
- P0-7 AI 修复执行先审后行门禁（与在途 AI 规范对齐）
- P0-8 泄漏扫描扩展 + 清理 __dir_listing_probe.txt
验收：pytest 92+（新增口令散列/校验、UA 判定、双步状态单元测试）全绿；AppTest 0 异常；桌面无参启动 netstat 仅回环且免口令；--expose lan 后同 WiFi 手机见口令页、错口令拒、正确口令通过、375px 表单可输入、结束/重跑双步；make_dist 泄漏扫描零命中。

P1：省流量开关与 UA 自动降频、粒子/backdrop 移动降级、app.log 远程截断、心跳与「疑似离线」胶囊、防火墙一键脚本、restrict 专用子钥文档、浏览器添加到主屏幕指南、多开命中地址清单、口令重试退避、st.dialog 提交摘要确认。
P2：AutoDL 自定义服务 URL 自动展示与探测、局域网二维码面板（外部 QR API 可选）、PWA（仅文档说明不实现）。

不做清单（明示）：不引入登录框架/HTTPS 反代（应用层口令足够且零依赖）；不自研隧道协议（复用系统 ssh）；隧道不绑云机 0.0.0.0（明文 HTTP 不上公网）；不做长效口令 cookie；不改桌面默认绑定与桌面 2s 轮询；不动天气/昼夜/粒子视觉子系统本体（仅降级阈值）；无 emoji、不引新依赖。

参考出处（实施期核实点，均标注）：Windows OpenSSH 客户端可选功能开启路径（设置-可选功能）；AutoDL「自定义服务」映射形态与门槛（官方控制台，实施时实测）；Streamlit st.context.headers 可用性（1.62 文档，try/except 守卫）。
