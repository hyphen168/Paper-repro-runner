# 录入体验与 UI 规范：云服务器（SSH）三步就绪

结论：录入区压缩为「主输入框 + 凭据二选一 + 检测按钮」三段式，用真凭据全连接判定替代纯 TCP 探测作为「就绪」依据，绿色即代表提交后可自动连上并执行；失败给出四级分级诊断与对应动作。无新增依赖，无 emoji，不回归既有能力。

## 决策

### 1. 录入区终版布局（三步走，一屏收口）

卡片「云服务器（SSH）」内自上而下四层，视觉上依次推进，禁用分屏多表单：

- 第一步提示行（html，青色数字小圆点 + 短句）：「三步就绪：1 粘贴连接信息 → 2 填凭据 → 3 点「检测连接」；亮绿后提交即自动连接并运行复现。」放卡片标题下，初次无检测记录时显示，绿/红后转为状态条。
- 第二步主输入框（st.text_area，高度 3 行，key=ssh_conn_lines）：label 逐字稿「SSH 连接信息（必填，可多行，每行一台）」；placeholder 逐字稿（逐行）：
  `ssh -p 38662 root@connect.cqa1.seetacloud.com`
  `root@192.168.1.15:22`
  `my-alias（~/.ssh/config 已有别名）`
  help 逐字稿：「支持四种写法：完整 ssh 命令、user@host[:port]、纯地址（端口用户名取下方手动值）、config 别名。AutoDL 控制台“自定义服务”的登录命令可整行粘贴，每次开机地址变化只需替换该行。」解析 caption：单机「已识别：root@connect.cqa1.seetacloud.com:38662」；多机「共 2 台候选，检测与执行按填写顺序取第一台认证通过者。」候选与用户名、端口仅作进程内解析，不落库。
- 第三步凭据区（radio 二选一，key=ssh_auth_mode）：选项逐字稿「使用密码」/「使用私钥（路径或粘贴 PEM）」。默认按已保存配置回显（有可用私钥引用则私钥，否则密码）。
  - 密码输入（type=password）：label「实例密码」，caption「仅存于本次进程内存，关闭即失效，绝不写入磁盘」；AutoDL 场景 help「初始密码在控制台“重置密码”处设置」。
  - 私钥输入（text_area，key=ssh_key_path，保留原键）：label「SSH 私钥路径或粘贴 PEM 全文」，placeholder「C:\Users\你的账号\.ssh\id_ed25519（或粘贴 -----BEGIN 开头全文）」。粘贴时经 ensure_ssh_key_file 落盘 0600；下方 st.code 展示本机公钥全文，caption「未授权时粘贴到 AutoDL 控制台密钥管理，或点“注入公钥到服务器”用密码登录一次自动完成」。
- 检测按钮「检测连接」（普通按钮样式，青色描边，非黄色主按钮，整宽）。点击后：对候选逐个执行 阶段一 TCP 探测（probe_host，2 秒）→ 阶段二 带凭据全连接（test_ssh_connection，password 走 paramiko、私钥走 Windows OpenSSH `ssh -T`，别名直接 `ssh -T alias` 终裁），任一认证成功即终止并绿。检测期间按钮下方显示逐行进度「正在检测：TCP 连接 A… → 认证 A…」。

原四列（cloud_host/ssh_port/cloud_user/cloud_password）整体收进折叠区「手动指定（可选）：主机 / 端口 / 用户名 / 别名」，保留全部 widget key、默认 root 与保存键名，作为主输入为纯地址或空时的回退数据源；解析优先级不变（主输入富解析优先，手动值兜底）。原独立「测试 SSH 连接」按钮并入「检测连接」，「注入公钥到服务器」按钮移入凭据区侧（私钥模式与认证失败诊断处均可见），「生成 SSH 配置」移入手动区（负责把成功连接固化为 ~/.ssh/config 别名块）。删除旧展开器内与凭据区重复的私钥粘贴框。

### 2. 检测结果呈现（就绪绿 / 失败红）

结果条复用 status-dot 与胶囊体系，新增整宽状态条：左侧发光圆点（绿 var(--green)/红 var(--red)/检测中 cyan）+ 主文案 + 次行明细。
- 绿：「就绪 · root@connect.cqa1.seetacloud.com:38662 认证通过。提交任务将自动使用该主机，无需再次填表。」同帧写入会话：检测通过主机置候选首位（提交时多机 probe 依此优先，消除「填对了却报不可达」）。
- 红（headline）：「连接失败 · N 台候选均未通过认证」。其下为四级分级诊断（编号列表，逐级只显示首次命中的层级及其动作，而非堆栈原文）：
  1 输入缺失/格式错 → 建议：凭据区补齐密码或私钥；连接信息对照占位符改写。
  2 主机不可达（TCP 超时或拒绝）→ 建议：到 AutoDL 控制台确认实例已开机（关机时端口不通）；重新复制控制台最新 SSH 登录命令整体替换本页；公司网络是否放行 4xxxx 端口。
  3 端口可达但认证被拒 → 建议：核对密码（控制台「重置密码」）；或改用私钥并先执行一次「注入公钥到服务器」。
  4 私钥无效/被拒 → 建议：确认粘贴的是私钥而非公钥、路径无引号且文件存在；Windows 无需 chmod，但私钥目录勿多用户共享。
  5 别名未定义 → 建议：改用完整 ssh 命令，或在手动区点「生成 SSH 配置」。
  层 3/4/5 附动作按钮行：「重新检测」「注入公钥到服务器」，公钥以 st.code 呈现供复制。失败文案逐字稿为「原因与动作」，拒绝把 paramiko 原始异常直接上屏。

### 3. 与已保存配置的关系

保存：ssh_target 存主输入全文（多行原样，支持历史单行）；cloud_host 存首候选 host、ssh_port/cloud_user 存解析终值（兼容旧读取与 DB host 字段）；ssh_key_path/ssh_alias 照旧。密码永不进 config_store。
回显：有 ssh_target 则整块回填主输入（多行逐字回显）；历史版本仅存 cloud_host 时，拼成单行 host 回填，另以 caption「已载入旧版保存的主机，可继续编辑」。别名块与配置只增不删。
清除：手动区尾部「清除已保存的云端配置」小按钮，确认文案「仅清空本页连接信息、凭据引用与回显，不删除 ~/.ssh 下任何文件或别名块」；执行 config_store.clear 相关键并 rerun，密码随会话内存即刻丢弃。

### 4. 仪表盘右侧状态胶囊

头部右侧集群按「天气、连接、最近任务」排序新增 .conn-pill（复用 pr-pill 圆角胶囊与 status-dot 发光点）。数据源：执行态取后台实际连上主机（RemoteRunner 成功 connect 后经回调写入执行态与任务记录），空闲取最近一次成功/远程失败任务的 host/user/port（DB 已有字段）。文案（无 emoji）：
- 空闲灰：「未连接云端」；
- 本次就绪绿：「已就绪 root@host:port」；
- 运行中 cyan：「执行中 · root@host:port」；
- 最近成功绿：「上次成功 root@host:port · HH:MM」。
胶囊 hover 展开 title 含完整连接串；不挂 2 秒轮询动画，随 rerun 刷新。

### 5. 文案与风格

专业、中文短句、无 emoji（含后台返回消息——现有 inject_public_key 成功文案前缀的「✅」符号必须去除，改为「公钥已成功注入 user@host：~/.ssh/authorized_keys …」）。数字与层级用「①②③/1 2 3」，统一成 1 2 3 编号。一律“就绪/失败/检测中”，不出现英文裸状态与 traceback。示例域名只进 placeholder，绝不作为可提交的默认值；默认用户统一 root。

## 可执行变更

1. 去假默认值，堵误报源（app.py）：cloud_host 无保存值时置空而非 "my-server.example.com"；resolved_cloud_user 兜底链统一 root（删除提交分支内 "ubuntu"），与主输入及手动区默认一致。此为「填对了却说不可达」的首因修复合入本规范。
2. 新增纯逻辑 `detect_ssh_ready(candidates, password, key, alias)`（remote_runner.py，零 streamlit）：逐候选 probe_host(2s) → test_ssh_connection 全连接，返回 {ready, host, user, port, tier, message, detail}；tier 映射 1 输入/2 TCP/3 认证/4 私钥/5 别名。配套单测覆盖「候选可达但凭据错」「多候选首台认证失败次台成功」。
3. 提交门禁改判（app.py submitted 段）：先取会话最近一次检测结果（输入未变直接复用；否则同步跑一次，超时上限首台 12s）。非就绪时阻止建任务，红条展示分级诊断，不再落入后台 TCP-only probe 才报「自动识别均不可达」；仅当用户勾选「实例尚未开机，后台稍后重试」才放行。运行期 execute 的 probe 多选逻辑保留（多机轮换能力不回归），但候选顺序以检测通过主机置顶，且其全失败 message 改写为「按本页『检测连接』结果核实后重试」并回链诊断。
4. execute 成功 connect 后回调 `on_connected(host,user,port)`（storage_utils 写入执行态与任务记录 chosen_host），支撑胶囊第 4 点；同时把 task 创建处的 host 落库值改为检测通过主机，保证「谁在执行」一致。
5. UI 组件与骨架：app.py 提交卡内按第 1 节段落重排，主输入用 text_area；关键文案全部按上文逐字稿替换。ui_theme.py 的 APP_CSS 末尾追加：.ssh-bar（整宽圆角状态条）、.ssh-ok/.ssh-bad/.ssh-busy（文字与描边取 var(--green)/var(--red)/var(--cyan)）、.hint-3step（步骤提示行）、.diag-ol（分级诊断编号列）与 .conn-pill；均无动画、无新字体、无新库。
6. 文案侧代码修改：remote_runner.inject_public_key 成功串去除「✅」前缀；test_ssh_connection 各 return 文案对齐第 2 节措辞（口令、动作化）。
7. 回归与验收清单：保留手动城市、天气粒子、昼夜主题与侧栏定位控件不动；AppTest 断言涉及的原 widget key（cloud_host/ssh_port/cloud_user/ssh_key_path/ssh_target/ssh_alias）全部存活（仅移入折叠区）；pytest 81 全绿前提下为 detect_ssh_ready 与门禁新分支补测；手工走查 AutoDL 全链路（粘贴登录命令→密码→检测绿→提交→任务监控 running 日志出现已连接主机串）。本规范未决点：Windows 下 alias 依赖 OpenSSH 客户端是否存在，检测失败层 5 的提示文案已兜底。
