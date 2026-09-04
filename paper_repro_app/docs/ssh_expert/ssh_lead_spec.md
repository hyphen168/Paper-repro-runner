# SSH 自动连接与一键运行规范（主导裁决版 v1.0）

五份报告（a 解析 / b 检测 / c 审计 / d 执行 / e UI）已通读；关键代码事实已复核：R1（候选串二次解析把 host 解析成含空格假名）与 R2（3 秒纯 TCP 探测误杀）已实测坐实，R1 是用户"信息正确却报不可达"的最可能直接根因：parse_ssh_candidates(["root@connect.cqa1.seetacloud.com -p 38662"]) 实测返回 host="connect.cqa1.seetacloud.com -p 38662"，DNS 必失败。冲突裁决：解析统一采 a 的"引擎化+兼容壳"而非 c 的全量删除（保测试全绿且迁移风险最低）；检测层级采 b 的 L0-L3；执行状态机采 d 的 connecting 阶段；UI 采 e 的三步收敛但**不做离线排队勾选**。本规范为实施唯一依据。

## 一、总纲

目标观感：一条 SSH 连接串（或候选列表）+ 密钥/密码，本机自动解析、以真实凭据连接、直接把复现流水线跑起来；检测从不说谎——能连就绿，不能连就精确告诉你卡在哪一步、该做什么。

设计原则：
1. 检测与执行同一把钥匙：TCP 探测只做可达性分类、绝不单独否决；能不能用，以 paramiko 真实凭据握手为准（ssh_connect 全链路唯一入口）。
2. 解析单源权威：一个解析引擎消化所有输入形态（完整 ssh 命令 / user@host[:port] / alias / host / 多行候选）；旧解析函数全部降级为委托壳，杜绝"表单看着对、执行走错路"的双解析漂移。
3. ssh_config 别名与 Windows OpenSSH 参与仲裁：ssh -G 是字段权威展开（含 Include/别名），ssh -T 是凭据复核；二者缺失自动回退纯解析/paramiko，不设硬依赖。
4. 凭据铁律：密码与私钥全文只存活于进程内存与内存 state 表，任何落库/落盘前统一 sanitize（仅记 key basename 与公钥前 40 字符）；默认值单源：用户 root、密钥 id_ed25519。
5. 提交零多余操作：提交按钮只做 L0 本地把关（小于等于 0.5s，即时放行或报可操作错误）；L1/L2/L3 在后台线程完成，监控三态呈现（连接云端、执行中、结束），无需用户先点测试。

## 二、连接档案统一结构

### ConnectionProfile 字段与来源
| 字段 | 类型 | 说明 |
|---|---|---|
| host | str | 最终主机名/IP（别名已展开） |
| user | str | 默认 root |
| port | int | 默认 22；AutoDL 多为 4xxxx |
| key_path | str | 私钥文件绝对路径（PEM 粘贴已落盘）；可为空走密码/agent |
| password | str | 仅进程内存；非空时优先密码认证 |
| alias | str | 原始别名（若有），仅用于诊断展示 |
| source | str | 该档案来自哪个输入行（诊断/日志用） |

### 解析优先级（从高到低合并，后项只补缺）
1. 行内显式参数：-p 38662（含紧贴式 -p38662）、-i C:\...\key、user@host；
2. parse_ssh_target 富解析结果（兼容现有 ssh_target 语义）；
3. ssh_config 别名展开：本机有 OpenSSH 时 ssh -G <alias> 权威输出 HostName/User/Port/IdentityFile；无 OpenSSH 时用增强 parse_ssh_config（补 ProxyJump 摘要：仅展示不执行）；
4. UI 上下文兜底（表单 user/port/key 输入值）；
5. 全局默认：user=root、port=22、key=~/.ssh/id_ed25519。

### 新增函数签名（落在 paper_repro_app/ssh_utils.py）
def parse_connection_profile(raw_line, ctx=None) -> dict
    返回 host/user/port/key/alias 全补默认；解析失败返回 {"error": 原因}。
    词法要点：shlex.split(posix=False)（保 Windows 路径反斜杠）；"@"后先按空白截断再就地解析尾部 -p/-i；行首 ssh 命令支持 -p/-i 任意顺序与紧贴式。
def build_connection_profiles(lines, ctx=None) -> list
    逐行 parse_connection_profile；error 行单独返回供 UI 提示；去重键 (host, port, user)；别名行先 expand_ssh_config 再入档。
def expand_ssh_config(alias_or_host) -> dict
    优先 subprocess ssh -G（1.5s 超时）解析 HostName/User/Port/IdentityFile（含 Include）；失败回退 parse_ssh_config；均失败返回 {}。
def classify_conn_error(exc) -> str
    类别：auth / refused / timeout / dns / net_unreachable / proxy / other；依据 paramiko AuthenticationException 族 / socket errno / DNS 异常。
def ssh_connect(profile, timeout=12) -> paramiko.SSHClient
    统一连接入口：hostname/user/port/key_filename/password/allow_agent/look_for_keys；AutoAddPolicy；认证类异常原样上抛（永不重试），其它异常带分类信息上抛。
def sanitize(text) -> str
    替换密码原文、BEGIN...PRIVATE KEY 全文、私钥路径（保留 basename）为 <redacted>；供 StepLogger、TaskStore 写 log、失败 message 落库前统一调用。

### 旧函数兼容壳（保持签名与 message 前缀不变，内部委托新引擎）
- parse_ssh_target(raw_target)：parse_connection_profile 的子集映射；
- parse_ssh_candidates(lines, default_user, default_port)：build_connection_profiles；
- resolve_ssh_profile(raw_target, fallback_host, fallback_user, fallback_key)：组合解析（行为与现版一致）；
- probe_host(host, port, timeout=6.0) 保留但降级为 L1 分类探测部件，返回值保持 bool（内部 2 次重试）；
- ensure_ssh_key_file 提升为唯一 PEM 落盘实现（remote_runner 三份拷贝删除改 import）；文件名 paper_repro_<sha1(value)[:12]>.key（替换 abs(hash(value))，杜绝跨进程随机文件名垃圾累积）。

## 三、检测规范终版（L0-L3）

### L0 本地解析（小于等于 0.5s，提交门禁与测试按钮共用）
检查项：候选行可解析出真实 host（无 error）；至少存在一种认证源（密码非空 / key 文件校验通过 / ssh-agent 有密钥 / config IdentityFile 存在）。失败立即返回分级文案，不建任务。无任何凭据时优先报"缺凭据"而非"不可达"（顺序前置修正）。

### L1 可达分类（只记录，不否决）
每台 TCP connect：单次超时 6s，失败重试 1 次（共 2 次）；多台并行（ThreadPoolExecutor，max_workers=min(8, n)），总预算小于等于 12s。结果五态：ok/refused/timeout/dns/net_unreachable，写入执行日志（host 经 sanitize）。判定规则：L1 仅用于排序（ok 台优先）与诊断文案，不单独判死任何台。

### L2 凭据真连（决定性，后台线程）
顺序尝试候选（L1 ok 台优先）；单台预算 12s（connect+banner+auth）。命中：paramiko 握手成功即中选进入流水线；auth 类失败立即短路判"凭据级错误"（同组内不再试下一台）并给修复指引；refused/timeout/net 类自动转下一台。总预算 min(60, n*16) 秒；每台尝试前查 cancel_event。全部失败：分段明细落库（每台类别+单行原因+下一步动作），保持既有 failed 结构（attempts/message）兼容历史 UI。

### L3 环境预检（连接成功后，只告警不阻断）
一条组合命令（小于等于 20s）：whoami / uname -m / GPU nvidia-smi 摘要 / python3 -V / 磁盘 df；结果作为 connect 阶段日志输出，异常仅提示不断言失败。

### 失败分级与用户文案模板（逐字，无 emoji）
| 类别 | 模板 |
|---|---|
| 缺凭据 | 未找到可用 SSH 认证源：请填写密码，或提供有效私钥（路径或粘贴 PEM 全文），或在 ssh-agent 中加载密钥。 |
| 解析失败 | 第 N 条候选无法解析（原文：行）：原因。支持格式示例：ssh -p 38662 root@connect.xxx.seetacloud.com / root@host:38662 / host |
| 不可达 | 自动识别 N 台候选均无法连接：host1:port1 类别; host2:port2 类别。请确认实例已开机，且地址端口为控制台最新 SSH 登录信息。 |
| 认证失败 | SSH 认证失败（异常类）：user@host:port 拒绝了当前凭据。排查：1) 密码是否正确；2) 私钥是否与公钥配对且公钥已加入 authorized_keys（可点注入公钥）；3) AutoDL 密码在控制台设置。 |
| 兼容受限 | 凭据校验通过（ssh 命令可连），但 paramiko 直连受限：原因。不影响使用：程序将改用系统 ssh 命令执行。（仅 P2 仲裁后展示） |

### 手动"测试连接"按钮（L0-L3 全量，上限 40s）
输出四条胶囊状态行（L0 解析 / L1 可达 / L2 认证通过 / L3 环境摘要），最终绿条"连接就绪"或红条（分级文案）。

## 四、执行链路终版

### 状态机
queued 到 running（current_step="connect"，标题"连接云端"）到 running（流水线各步）到 success/failed/cancelled。不新增 DB 列：current_step 复用现有字段；connect 阶段结束后进入 build_pipeline 第一步。监控页可辨：日志首行"自动识别：N 台候选，选用 host（可达 M 台）"；connect 失败消息含分段明细。

### RemoteRunner.execute 流程（改动后最终顺序）
1. 读候选：task["hosts"]（内存注入）逐条 parse_connection_profile + expand_ssh_config；为空回落 task 单机字段构造单档。
2. 凭据前置：detect_ssh_auth_sources() 先跑；无任何认证源返回"缺凭据"分类失败（不再先探测）。
3. L1 分类（并行小于等于 12s）排序候选。
4. L2 顺序真连（每台 12s，尝试前查 cancel_event）：成功则 self.host/user/port/key 更新为该档并记"自动识别：已连接 user@host:port"，进入第 5 步；auth 失败返回认证失败分类（带修复指引）；其它失败转下一台；全败返回分段明细失败。
5. 流水线主循环：完全保留现有 build_pipeline 步骤逻辑（connect 成功后才进入）。
6. 连接中途断开：保持现有 attempts 小于等于 max_retries 同台重连逻辑（不引入跨台热迁移）。
7. 取消：cancel_event 贯穿 L1/L2 每台尝试与主循环（主循环已支持，补探测段检查）。

### 历史重跑（无内存候选）
回落 task 单机 + 现有 key/agent 链；UI 提示"该任务创建时的候选列表未保留（密码与多机清单不落库），本次按原主机直连"。原因写进日志：AutoDL 地址动态变化，旧清单本身是误导源。

### 脱敏
sanitize 应用于：StepLogger 每行、TaskStore.update_task_status 的 log 参数、失败 message、异常文本（全部 return failed 前过一遍）。key 字段日志只记 basename；public key 只记前 40 字符。

### 提交链修正（app.py）
候选解析后 host_candidates[0] 直接作为任务 host/user/port（与 resolved_* 合并取同一来源，禁止二次覆盖产生垃圾 host，R1 修复后二者天然一致）。resolved_cloud_user 兜底 ubuntu 改为 root（与 UI 默认、config 渲染、候选默认四方单源）。占位默认 my-server.example.com 改为空字符串（避免假主机混入候选）。test_ssh_connection 与执行共用同一 profile：测试按钮不再在"有 alias 时无条件 ssh -T alias"；仅当用户显式启用别名时才走 alias，否则按解析后 host/user/port/key/password 直连。

## 五、录入 UI 终版（app.py 云服务器卡片 + 折叠）

1. 主输入框（服务器地址/候选）：多行，placeholder="ssh -p 38662 root@connect.xxx.seetacloud.com"，help="支持每行一条：完整 ssh 命令 / user@host[:端口] / 别名；可填多台，程序自动选用可用者。AutoDL 换机只需更新这里。" 保留 widget key cloud_host，无值时默认空。
2. 凭据区（radio，key ssh_auth_mode，值 password/key）：
   - 密码：text_input type=password（key cloud_password）；
   - SSH 私钥：text_input（key ssh_key_path，路径或粘贴 PEM 全文，从现有 expander 提升到该区，保留原 key 兼容）。
3. 折叠"高级（端口/用户名/连接串/别名）"（expanded=False）：ssh_port（默认 22）、cloud_user（默认 root）、ssh_target（富连接串自动解析）、ssh_alias（默认 papercloud，仅勾选使用）。
4. 行动条：按钮"检测连接"（key btn_ssh_test）全量 L0-L3，胶囊状态条（复用 .pr-pill/.status-dot，新增 .conn-ok/.conn-fail）；就绪状态条（key ssh_health_bar）三态：绿"连接就绪，可提交"/黄"本地校验通过，执行时将自动连接"/红"分类失败文案"。
5. 提交按钮逻辑：仅 L0 校验通过即可提交（不强制先检测）；健康条为绿时按钮旁 caption"已检测：user@host:port 可用"。
6. 仪表盘"最近任务"胶囊已就绪复用，无需新控件。
文案风格：全中文、无 emoji、错误首句结论次句行动。

## 六、实施顺序（P0/P1/P2）与不做清单

### P0（止血，一次提交；目标：消除"信息正确却不可达"两类误报）
- P0-1 remote_runner.parse_ssh_candidates @ 分支修复：host 先按空白截断，再就地解析尾部 -p N / -pN（R1）。验收：新增单测 user@host -p 38662、-p38662 紧贴式、别名行均解析正确且与 parse_ssh_target 一致。
- P0-2 probe 增强：timeout 默认 6.0s + 每台重试 1 次；新增 classify_conn_error；execute 探测段改为分类记录+排序，不再单凭 TCP 判死（L1 语义）。
- P0-3 凭据前置：execute 中 login_methods 判断提到探测段之前；无凭据返回"缺凭据"分类。验收：单测（mock 可达主机+无凭据，返回缺凭据文案）。
- P0-4 app.py：resolved_cloud_user 兜底 ubuntu 改 root；cloud_host 占位默认改空；候选与 resolved 单源（防二次覆盖）。
- P0-5 去 emoji：remote_runner.py:1060 注入成功消息去除；全仓扫 emoji 清零。
验收：pytest 85+ 全绿；AppTest 0 异常；人工复现 R1 场景 host 不再含空格。

### P1（主链路统一；目标：解析/检测/执行单源，认证失败可转移）
- P1-1 ssh_utils 新增：ProfileContext / parse_connection_profile / build_connection_profiles / expand_ssh_config / classify_conn_error / ssh_connect / sanitize；旧四函数委托壳；ensure_ssh_key_file 唯一化+sha1 命名（三份拷贝删除）。
- P1-2 词法：shlex.split(posix=False)；-i/-p 任意顺序与紧贴式；Windows 路径原样保留。
- P1-3 RemoteRunner.execute 探测段替换为：L1 并行分类到 L2 ssh_connect 顺序真连（auth 短路、其它转台、每台 12s、总预算 min(60, n*16)）；connect 阶段 current_step="connect" 标题"连接云端"，日志输出自动识别摘要。
- P1-4 test_ssh_connection 与提交共用 profile（alias 仅显式启用时优先）。
- P1-5 sanitize 接入 StepLogger / TaskStore 写 log / 失败 message（密码与 PEM 全文脱敏）。
验收：pytest 90+；新增 mock 单测大于等于 6（解析一致性、auth 转台、缺凭据前置、sha1 幂等、sanitize 不泄密、Windows 路径）。

### P2（体验打磨；目标：环境预检与诊断精度）
- P2-1 L3 组合命令预检步骤化，connect 日志输出环境摘要（GPU/Python/磁盘），异常仅提示。
- P2-2 手动测试按钮 L0-L3 胶囊状态条（.conn-ok/.conn-fail）与健康条；文案按第三节模板。
- P2-3 ssh -T 仲裁：paramiko 非认证失败且本机 OpenSSH 可用时用 ssh -T 复核，给出"凭据有效但 paramiko 受限"提示（不改执行引擎）。
验收：全绿；真机 e2e（用户 AutoDL 机 connect.cqa1.seetacloud.com:34367，root，密码仅内存注入）：提交 safe 模式到连接、克隆、conda 环境自举、依赖、入口识别、安全检查通过，日志脱敏复查（无密码泄漏）；监控 2s 刷新与取消链路抽查。

### 不做清单
不做离线排队/勾选机制（交互复杂且用户未要求）；不引入新库/新框架（paramiko+标准库+本机 OpenSSH 已够）；密码与私钥全文不落 DB/配置文件（延续内存通道）；不改天气/昼夜/手动城市/粒子行为；不把 ssh -G/-T 设为硬依赖（缺失自动回退）；不做跨台任务热迁移（连接中断仅同台重连）。
