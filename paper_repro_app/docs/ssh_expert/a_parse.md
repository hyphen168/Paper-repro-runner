# 连接信息解析架构规范（SSH Connection Profile）

依据实读代码：ssh_utils.py（parse_ssh_target/parse_ssh_config/resolve_ssh_profile/ensure_ssh_key_file/write_ssh_profile/test_ssh_connection）、remote_runner.py（probe_host/parse_ssh_candidates/RemoteRunner.execute/detect_ssh_auth_sources）、app.py 提交流、storage_utils.py（password 与 hosts 均走内存态不落库）复核。全篇中文、无 emoji，新增文案沿用现有中文风格。

## 决策

### D0 根因与总纲
"自动连接检测失败"的机理已定位：execute() 在凭据检查**之前**只用 probe_host 做 3 秒纯 TCP 探测选机，别名/配置/密钥不参与判定，且全部不可达即返回 failed。决策：引入一等公民"连接档案 ConnectionProfile"，检测与执行共用同一解析引擎与同一 `ssh_connect(profile, password)` 连接器；TCP 探测降级为快速预筛，最终以"完整 SSH 认证握手"定机，失败按不可达/认证/代理/配置分类回传，不再由裸 TCP 一票否决。解析只产出结构，密码永不进入档案，仅在提交时刻以内存参数注入。

### D1 输入形态矩阵与优先级
优先级：**完整 ssh 命令 > user@host[:port] > ssh 别名 > host[:port]**（同框混合时逐行各自定级后去重保序）。

- 形态一：完整 ssh 命令（`ssh [-p/-P N][-i 路径][-J 跳板][-l 用户][-o k=v]… [user@]host`）。判定：首 token（引号剥离、小写）恰为 `ssh`。
  - 词法不用 `shlex.split`（其 posix=True 会把 `C:\Users` 的反斜杠当转义吞成 `C:Users`）；改 `_split_ssh_words(text)`：只按空白切分、支持单双引号成组、Windows 下反斜杠一律当字面量，切完剥掉包裹引号。
  - 选项规则：`-p/-P/-i/-J/-l/-o` 可跟值也可粘连（`-p38662`、`-iC:\key`）；`-o` 值为 `k=v` 单 token；`-i`/`-o IdentityFile`/`ProxyCommand` 类路径字段做 `\`→`/` 归一（forward slash 在 Windows OpenSSH 与 paramiko 均可用），其余字段禁止含反斜杠。目标主机取最后一个裸 token（去掉已消费的选项参数后），剥 `user@` 前缀即 host。
  - 边界：`-i` 值含空格时必须带引号；盘符冒号形如 `^[A-Za-z]:[\\/]` 只可能在键路径字段出现，绝不参与 host:port 判定；IPv6 仅接受 `[addr]:port` 方括号形态，裸 IPv6 直接报"不支持，请加方括号"（避免 v6 冒号误拆）。
  - **ProxyJump 必须保留**为档案 `proxy_jump` 字段（原样字符串，含多级逗号列表），不得丢弃；执行层经 paramiko `ProxyCommand(['ssh','-W',target,jump…])` 或 `ssh -W` 子进程开隧道（等价 `-J`，只消耗本机 OpenSSH+paramiko，不加依赖）。
- 形态二：`user@host[:port]`。整行恰含一个 `@` 且 `@` 左段无空白即为用户字段；host 右段再按形态四规则拆 `:port`。
- 形态三：ssh 别名（见 D2）。
- 形态四：`host[:port]`。拆端口仅当：token 不含 `\`、非盘符开头、冒号右段全数字且 1–65535；否则整体作 host（域名允许含点与连字符）。`[v6]:port` 走独立分支。
- 判定顺序细节：形态判定不看字面猜测，一律"先试解析、后验证据"：含 `ssh` 首 token→形态一；含 `@`→形态二；单 token 且能命中 config 的 Host 项→形态三；余下按形态四。每行产出独立档案并记录 `source`，无法解析的行返回显式错误串（不静默吞行），UI 逐行 caption 展示。

### D2 ssh 别名一等公民
- 何时视为别名：**非 IP、非域名、无 `@`/`:`/`/` 的单 token（或空格分隔的 token 组中单 token），且大小写不敏感精确命中 ~/.ssh/config 某 `Host` 项** → 走别名档案，source=alias，保留原始别名供溯源。若单 token 未命中任何 Host 项，判定其为"疑似别名未定义"，但**不阻断**：作为直连主机名继续（兼容内网短主机名），仅在连接失败时提示。
- 展开以本机 OpenSSH 为最终仲裁：`ssh -G <alias>` 取 stdout 的 `hostname/user/port/identityfile/proxyjump/proxycommand` 键（一次性本地进程、零网络，天然覆盖 Include/通配 `Host *`/大小写规则，这正是现有 parse_ssh_config 手写解析的盲区）；`ssh` 不可用时回退现有 parse_ssh_config 并补读 `ProxyJump`/`ProxyCommand` 两键。配置缺失或展开后仍无 HostName 时，报错指引（中文无 emoji）：“别名 xxx 未在 ~/.ssh/config 定义或缺少 HostName：请直接在“服务器地址”填 IP/域名，或在 SSH 配置区点“生成 SSH 配置”写入别名块”。
- 别名解析出的 `IdentityFile` 只进入档案 `key_file`；`IdentitiesOnly yes` 语义由连接器以"仅尝试档案 key+公共凭据"近似实现（不扫 agent 全量试探）。

### D3 统一解析结果与旧函数差异
统一结构 ConnectionProfile（同时是检测与执行的输入，密码除外）：

| 字段 | 类型/默认 | 说明 |
|---|---|---|
| host | str | 展开后最终连接地址（唯一可入 socket） |
| port | int=22 | 行内 > config > 公共默认 |
| user | str | 行内 > config > 公共默认 |
| key_file | str="" | 行内 -i > config IdentityFile > 公共 key > 空（空=交 agent/默认） |
| alias | str="" | 原始别名（溯源、测试按钮复用） |
| proxy_jump | str="" | 原样保留，连接器负责隧道化 |
| source | str | ssh_cmd / user_host / alias / host_port / config / ui / default |
| errors | list[str] | 该行解析告警（不阻断时） |

`password` 不在档案内：只在提交与运行时作为 `ssh_connect(profile, password)` 的独立内存参数，绝不进 task 字典/JSON/库（沿用 storage_utils 现有内存密码表通道）。

与现函数差异与合并：现有四个函数是"扁平猜词 + 只认四键"的早期实现（parse_ssh_target 不处理 Windows 反斜杠与 -J；parse_ssh_config 不认 ProxyJump/ProxyCommand/Include；parse_ssh_candidates 对 ssh 命令只取 -p 与 user@host、丢掉 -i/-J；resolve_ssh_profile 手写 config 且不与 ssh -G 对齐）。合并方案为**引擎化 + 旧名兼容壳**：新增引擎函数（签名见可执行变更），UI 提交与 RemoteRunner 全部改走新引擎；`parse_ssh_target/parse_ssh_config/resolve_ssh_profile/parse_ssh_candidates` 函数名与签名原样保留为薄包装（保证 pytest 81 全绿与 AppTest 0 异常不回归），新增用例覆盖新边界后逐步让旧实现只做兼容断言、不再被调用。

### D4 候选与档案、凭据合并、检测执行共用
逐条结论：
1. 多候选输入（ssh_target 一行 + cloud_host 每行）**每行独立成档**：host/port/user/key_file/proxy_jump/source 各自独立，去重键 (host,port,user)。
2. 公共密码属于"会话凭据层"：提交时一次读取，逐档合并进内存连接参数，不写回任何档案字段，不落库。
3. 公共私钥属于"档案 fallback 层"：仅当该行无 -i/config IdentityFile 时才用 UI 的 ssh_key_path（或粘贴 PEM 落盘路径）填充 key_file；行内 -i 优先于公共 key。
4. 公共 user/port 只填空缺、不覆盖行内值；别名字段的 User/Port 高于公共值（config 显式声明优先于表单默认）。
5. 合并时机固定在"UI 提交→构造档案列表"一步完成，之后检测与执行读同一份列表；探测结果只用于排序与诊断，**永不回写档案**。
6. 档案列表随 start_pipeline_execution 以内存态传递（task_hosts），与现有 storage_utils 通道一致；任务表仅落库"首选档案"展开的扁平 host/user/port/key 以兼容历史展示与重跑。
7. 选机算法（检测=执行同路径）：按候选顺序对每档执行 `ssh_connect(profile, password)`：先 4 秒 TCP 快速预筛（有 proxy_jump 则探测跳板机），预筛不过标记 unreachable 继续；预筛过则完整 paramiko 认证握手（单档上限约 12–15 秒，多档总预算上限，防止整机休眠拖死任务）；认证失败（AuthenticationException 族）判定为 auth_failed 并**换下一候选**（现有实现恰恰在首台拒钥处整体终止并误报）；分类枚举 unreachable/auth_failed/proxy/config/timeout/other 全量汇入失败消息与 log。
8. 每档至少具备一个认证源（档案 key_file 或公共 key 或公共密码或 agent）才进入握手；否则该档跳过并记"无认证源"原因，避免"先报不可达、后报没密钥"的两段式误导。

## 可执行变更

1. `ssh_utils.py` 增补（旧函数不动，行为零变化）：
   - `_split_ssh_words(text: str) -> list[str]`：Windows 字面量反斜杠、引号成组剥离、盘符不吞。
   - `parse_connection_profile(line: str) -> dict`：单行→ConnectionProfile（含 errors/source；内部实现 D1 形态矩阵与 D2 别名判定入口）。
   - `expand_ssh_config(target: str) -> dict`：`ssh -G` 优先（hostname/user/port/identityfile/proxyjump/proxycommand），缺失时回退 parse_ssh_config 扩展版；无 HostName 返回可读指引。
   - `build_connection_profiles(lines, shared: dict | None = None) -> list[dict]`：逐行 parse_connection_profile 后按 D4 规则合并 shared（user/port/key fallback、password 除外），去重保序。
   - `write_ssh_profile(..., proxy_jump: str = "", force=True)`：可选写入 `ProxyJump` 行（仅当非空），config 块与现有测试断言字段保持兼容。
   - 兼容壳：`parse_ssh_target = 旧实现`（先不动），`resolve_ssh_profile` 改为内部调 build_connection_profiles 首档展开结果（对旧输入输出逐键一致，保证既有断言不变）。
2. `remote_runner.py`：
   - `ssh_connect(profile: dict, password: str = "", timeout: int = 15) -> tuple[paramiko.SSHClient | None, str]`：唯一建连入口；proxy_jump 时经 `paramiko.ProxyCommand(["ssh","-W",f"{host}:{port}",*jump_args])` 作 sock；异常映射为上文分类串。
   - `probe_host` 保留但仅作预筛；`execute()` 选机段改调 D4-7 算法：逐档 ssh_connect 取首个成功者，全部失败返回含"逐档诊断表"的 failed（各档 classification+原因），文案中文无 emoji；认证失败不再整体终止而是轮换下一档。
   - `detect_ssh_auth_sources` 保持不变（仍作为诊断素材）。
3. `app.py`：
   - 提交段把"resolve_ssh_profile+parse_ssh_candidates 手工拼接"替换为 `build_connection_profiles(行集合, shared={user: 表单默认 root 优先、port、key: ensure_ssh_key_file(ssh_key_path) 结果})`；caption 展示每档摘要（host/user/port/alias/proxy_jump/errors）。
   - 修正遗留默认值：`resolved_cloud_user` 的 "ubuntu" 兜底改为 "root"（与输入框默认一致，避免 key 对应用户错配）。
   - 测试/注入/生成按钮一律改经 `parse_connection_profile`+`ssh_connect` 或 `ssh -G` 校验；列表页错误文案同步 D2/D4 指引。
4. `storage_utils.py`：`start_pipeline_execution` 透传 profiles（内存态 task_hosts 已在用），无接口破坏。
5. 测试（保证 81 全绿前提下的增量）：新增 Windows `-i "C:\Users\My Name\id_rsa"` 反斜杠/引号用例；`C:\key` 盘符不误拆端口；`ssh -p38662 -J u@j:22 root@host` 的 proxy_jump 保真；单 token 命中 config Host 走别名、未命中回落直连；盘符/端口/认证分类枚举；AppTest 全程零异常。
6. 约束核对：全程仅 paramiko+标准库（隧道经本机 ssh -W，无新依赖）；密码仅内存注入；新增 UI/报错全中文且无 emoji；Windows 下 chmod 全部静默容错（现 ensure_ssh_key_file 已具备），不引入 unix 语义。
