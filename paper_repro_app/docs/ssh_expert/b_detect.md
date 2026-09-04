# 连接检测与诊断架构设计（b_detect）

现状复核定论：RemoteRunner.execute 的选机只做 TCP 3 秒探测且不读 ssh_config、凭据不参与判定，任一候选超时即被归入"不可达"并整批失败——这是用户"自动连接检测失败"误报的主因。修复方向是把"探测"从一句话退化成一个有层级的、可解释、可执行的检测器。

## 决策

D1 检测分层 L0-L3，与现有函数一一对应。

- L0 解析层（本地、毫秒级、无网络）：resolve_ssh_profile 已覆盖 ssh 命令富解析 + ~/.ssh/config 别名。新增两类子检查：DNS（socket.getaddrinfo，单主机 2 秒上限，失败单独归因 dns_fail，不并入"不可达"）；别名核对（候选行首 token 若在 config 中无 Host 匹配且不是 IP/域名，则报 alias_error 而不是继续探测）。别名内容正确性由 ssh -G 仲裁（见 D4）。
- L1 TCP 可达层：probe_host 语义升级为"分类探测"，返回 ok / refused / timeout / dns / net_unreachable 五类而非布尔。超时策略：单台 6 秒（AutoDL 跨境链路握手常在 0.2-0.8 秒，冷开机 sshd 尚未就绪时 SYN 可能被丢，3 秒确实会误杀）；多台并行（ThreadPoolExecutor，stdlib，并发上限 min(N,8)），总预算 10 秒而非 N*6；ConnectionRefused 是确定态（主机活着但端口未开/开错），立即短路该候选不做第二次等待；timeout 才允许第二轮重试。
- L2 真实 SSH 层：paramiko 全量连接，凭据按"显式 key 文件 → ssh-agent/默认 key → 密码"依序组合（沿用 detect_ssh_auth_sources 的结论；password 仅与 key 并传，不单独降级）。成功判定 = 认证通过 + transport 存活 + exec_command 一条探针命令退出码 0。认证异常（_is_auth_exception）即刻短路，复用现有精准诊断。探针命令只读不回写：echo PAPER_REPRO_PROBE_OK。
- L3 环境预检层：认证成功后只发 1 条组合命令收集 uname -srm、python3 --version、df -h / 尾行、（可选）nvidia-smi -L 首行；结果落任务日志头，异常只告警不阻断。结论进入诊断卡，供流水线启动前给用户"环境就绪 / 环境注意"信号。

D2 失败分级与话术模板（分级错误码 + 最终 UI 文案，全部纯文本无 emoji）。

- dns_fail："域名解析失败：{host} 无法解析。请核对地址拼写；AutoDL 实例若已释放需在控制台复制最新登录域名，或把控制台 ssh 命令整行粘贴到'SSH 连接串'。" 按钮：定位到"SSH 连接串"输入框。
- refused："端口拒绝连接：{user}@{host}:{port} 主机在线但该端口未开放。AutoDL 每次开机端口变化，请到控制台复制最新登录命令整行粘贴；自有服务器请检查 sshd 是否启动、防火墙是否放行。" 按钮：同上。
- unreachable_timeout："连接超时：{host}:{port} 6 秒无响应。常见原因：实例未开机/正在开机（可稍候重试）、跨境网络波动、实例地域网络被限制。已自动对可达候选降级尝试。" 按钮：重新提交；提示把多台候选分行填入主机框。
- net_unreachable："本机网络不可达（网卡/代理问题），非服务器故障。请检查本机网络后重试。"
- alias_error："别名 {alias} 未在 ~/.ssh/config 中找到，或该行不是有效主机。请在'SSH 配置别名'留空，或点击'生成 SSH 配置'写入后重试。"
- auth_failed_key："SSH 认证失败：{user}@{host}:{port} 拒绝了当前私钥。① 私钥应为 -----BEGIN 开头的真实私钥全文或真实文件路径（粘贴内容自动写入应用密钥目录）；② 公钥未加入云端 ~/.ssh/authorized_keys，点'注入公钥到服务器'一键添加；③ 用 Windows OpenSSH 在命令行 ssh -i <私钥> -p <端口> <user>@<host> 复核。" 复用现有长诊断结构。
- auth_failed_pwd："SSH 认证失败：密码被拒绝（或该实例仅支持密钥登录）。请核对实例控制台的 root 密码；AutoDL 需在控制台/创建时设置密码后生效。"
- key_format："私钥格式不可用：{path} 不是 OpenSSH/PEM 私钥。Putty 生成的 .ppk 请用 puttygen 导出为 OpenSSH 格式；文件路径请用正斜杠或 ~ 开头，避免反斜杠转义问题。"
- 成功模板（测试按钮）："连接通过（{host}:{port}，{user}，{耗时}ms）：解析 OK → TCP 可达 → SSH 认证通过 → 环境就绪。可直接提交任务。"
- 单候选特殊场景：候选唯一但 probe 未过的老任务（重跑路径）保留原回落逻辑，不因门禁改变历史任务行为。

D3 预检时机与成本，两档执行。

- UI"测试 SSH 连接"按钮 = 全量 L0-L3 同步检测（预算 40 秒内给结论），结果按层逐行展示"检查项 / 结果 / 耗时"，任一 L2 以下失败即停在该层并给 D2 模板。此按钮只读不写、密码只进 paramiko 不落库不落命令行。
- 提交任务 = 同步快速门禁 L0+L1（预算 5 秒；候选超 1 台时并行、只等首台确定态），通过即 create_task 放行；L2/L3 移到后台线程与流水线衔接，不改动 step 序列（不新增 step id，避免步进器与 get_step_order 回归）。状态消息设计：后台线程首次 on_step 沿用 prepare 壳，内容依次为"正在连接 {host}:{port}…"→ 认证通过后由 execute 内回调 on_step 追加"SSH 认证通过，{user}@{host} 已登录"→ L3 完成追加"环境就绪，开始执行流水线"。监控页因此无需新轮询即可看到三态推进。
- 门禁不过不创建任务：提交处 st.error 输出分级模板并 st.stop，避免再出现"全部不可达"的裸失败任务记录。

D4 探测与 ssh 命令仲裁。

- Windows OpenSSH 存在性检测：shutil.which("ssh") 且 subprocess ["ssh","-V"] 返回 0（存在性一次性缓存到模块级）。
- ssh -G 仲裁规则：当候选来自别名或存在"表单字段 vs 连接串 vs config"分歧时，调用 ssh -G <host>（4 秒上限），解析 HostName/Port/User/IdentityFile 首值，以其覆盖 resolve 结果中的空值与端口默认 22——解决"用户以为 config 端口生效但实际走了 22"类隐形错配。
- ssh -T 仲裁规则：仅当 paramiko 已失败且错误不是认证类（如密钥格式不兼容、算法协商失败、paramiko 解析不了 OPENSSH 新格式私钥）时执行 ssh -o BatchMode=yes -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new -T -p <port> -i <key> <user>@<host> echo OK（10 秒上限）。若 ssh 成功而 paramiko 失败，判定为"凭据真实有效、paramiko 兼容性受限"，诊断文案给出两种选择：改用密码认证，或把私钥转换为 PEM/ed25519 格式；执行引擎不切换传输通道（避免大面积回归），仅在诊断与候选排序中生效。私钥格式预校验优先用 ssh-keygen -y -f <path>（Windows OpenSSH 自带），成功即格式可用。
- 权限语义：Windows 无 chmod 语义，paramiko 不校验 0600，故"权限问题"在 Windows 收敛为"路径/格式问题"（key_format、alias_error、key 不存在），不再提示 chmod。

D5 超时与重试预算总表（结论逐条）：

| 层 | 操作 | 单次超时 | 重试 | 并发/总预算 | 重试条件 |
| --- | --- | --- | --- | --- | --- |
| L0 | getaddrinfo | 2s | 0 | 每候选 | 无（dns 不重试） |
| L0 | ssh -G | 4s | 0 | 1 次全局 | 无 |
| L1 | TCP 单台 | 6s | 1 轮（间隔 2s） | 并行 N 台总预算 10s | 仅 timeout |
| L2 | paramiko connect | 12s / banner 15s / auth 15s | 沿用 execute 内 3 连（间隔 2s） | 每候选顺序 | 认证类永不重试 |
| L2 | 探针 echo | 8s | 0 | — | — |
| L3 | 环境命令 | 12s | 0 | — | — |
| 全链路 | 测试按钮 | 40s 上限 | — | — | — |
| 门禁 | 提交前 L0+L1 | 5s | 0 | — | — |

关键结论：timeout/refused 语义不同——refused 多半端口错（实例已换端口），timeout 多半实例未就绪或网络，二者后台阶段都可再试但给不同话术；dns 与认证永不重试，避免把用户等待浪费在必败路径上。

## 可执行变更

E1 remote_runner.py：新增分类探测与选机。

- 保留 probe_host 原签名不动（有测试依赖），新增 probe_host_ext(host, port, timeout=6.0) -> dict，输出 {ok, code, detail, ms}，code ∈ {ok, refused, timeout, dns, net_unreachable}。异常映射：gaierror→dns；ConnectionRefusedError→refused；socket.timeout/TimeoutError→timeout；其余 OSError 按 errno（EHOSTUNREACH/ENETUNREACH/EHOSTDOWN→net_unreachable）。
- 新增 select_candidate_with_report(candidates, per_host=6.0, total_budget=10.0, max_workers=8) -> (picked, report)。用 concurrent.futures.ThreadPoolExecutor 并行探测，报告按原候选顺序排序；picked = 原顺序中第一个 ok，无 ok 时取第一个非 dns 候选返回其 code 供话术使用。
- execute() 的选机段改为调用上述函数；失败分支保持原 message 首句兼容，另在返回 dict 增加 "connection": report（monitor 页读取并渲染分级建议），保证既有 pytest 断言不断。
- 连接成功、build_pipeline 前插入 L3 预检命令（1 条组合命令，12s 超时），输出经 on_step("prepare", ...) 以"SSH 认证通过…/环境就绪…"落库。

E2 ssh_utils.py：新增两类纯函数（零 streamlit 依赖）。

- resolve_ssh_config_via_ssh_g(target: str, timeout: int = 4) -> dict：先判 Windows OpenSSH 存在，否则返回 {}；解析 -G 输出的 HostName/Port/User/IdentityFile 行首 token，Port 无效时回落。
- validate_ssh_key_format(path: str) -> tuple[bool, str]：文件不存在→(False,"文件不存在")；含 BEGIN 私钥头则尝试 ssh-keygen -y -f（存在 ssh 时）校验；不含头→(False, key_format 话术)。不改变 ensure_ssh_key_file / test_ssh_connection 签名。
- test_ssh_connection 内部：密码分支保持 paramiko 原路径；无密码分支在执行 ssh -T 前先做 L0-L1 快速分类，若 DNS/refused/timeout 提前返回对应分级文案而非等 ssh 报错（这是把"测试按钮"从黑盒变分层的核心改动）。

E3 app.py 调整。

- 统一兜底用户名：resolved_cloud_user 的 "ubuntu" 兜底改为 "root"（与表单默认、AutoDL 默认一致，一行改动）。
- 测试按钮分支：替换为调用新 check 汇总函数（L0→L3 顺序执行，任一失败短路），结果用 st.caption/st.error 逐行展示层级清单；文案全部无 emoji。
- 提交门禁：create_task 之前、ensure_ssh_key_file 校验之后插入同步快速门禁（单候选 5s 预算）：L0 解析+dns 检查 → L1 probe；失败则 st.error(分级模板)+ 给出可执行建议（"点击'测试 SSH 连接'查看分层详情"），并 st.stop()；通过则照常提交，L2/L3 留给后台。
- 修文案：现有 inject_public_key 成功文案与模板中含 emoji 的位置统一去 emoji，改纯文本。

E4 storage_utils.py：不改线程模型。仅将后台首条 on_step 文案改为"正在连接 {host}:{port}…"（host 从 task 取，候选未定前用首候选名），后续推进消息由 E1 的 execute 回调写入，形成"连接中→认证通过→环境就绪"三态。

E5 新增纯逻辑模块 conn_detect.py（从 remote_runner 拆出，便于单测）：承载 L0-L3 编排函数 run_connection_check(candidates, profile, password, key, full=True) -> list[dict]，每层输出 {layer, status, ms, detail, advice_code}；advice_code 映射 D2 模板。remote_runner 与 app 均只 import 该模块，不引第三方库。

E6 回归与测试策略：pytest 81 全绿是硬门槛——所有新函数独立成模块补单测（probe_host_ext 分类表驱动、select 顺序语义、ssh -G 解析用临时 config 文本、check 编排用 monkeypatch 假 socket/paramiko）；不改动既有测试依赖的 probe_host、test_ssh_connection 布尔签名与 execute 失败 message 前缀；AppTest 走既有流程（无 SSH 表单交互的页面用例不受影响，新增用例只测按钮存在性与文案渲染）。密码流复核：门禁与测试全走进程内 password 变量，不写入 config_store、不入 create_task 之外的落库路径，hosts/password 沿用 task_passwords/task_hosts 内存表。

E7 验收口径：用户按"控制台 ssh 命令整行粘贴 SSH 连接串→点测试 SSH 连接"应看到 L0-L3 四行全绿；实例未开机时提交任务应给出"正在连接…（6 秒无响应）"的明确超时话术而非笼统"全部不可达"；实例开机后重新提交应自动完成认证并在监控页出现三态状态消息。

## Gaps

- AutoDL 网关域名 connect.cqa1.seetacloud.com 是否随实例释放失效、DNS 缓存 TTL 行为未实测，需真机打点验证（dns_fail 话术按"可能已释放/换区"写）。
- paramiko 对 OPENSSH 新格式/加密私钥的支持随版本波动，仲裁逻辑（D4）需在 3.x 环境补一轮兼容样例。
- 并行探测在 pytest 环境下的线程安全（monkeypatch socket 时并发副作用）需在 E6 落地时以串行降级开关保护。
