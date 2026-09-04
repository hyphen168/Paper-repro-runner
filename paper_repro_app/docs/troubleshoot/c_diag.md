# 健康检查（体检）设计规范 v1.0 —— 专家组·健康检查设计师

依据：app.py（侧边栏/提交区/SSH 诊断折叠/health 条）、config_store.py、storage_utils.py（_EXEC_STATE 内存密码、后台线程、detect_ssh_auth_sources 门）、ssh_utils.py（test_ssh_connection/ensure_default_ssh_keypair/sanitize/连接档案引擎）、remote_runner.py（L1 probe_host、L2 ssh_connect、conda 自举、CUDA torch 保护、依赖扫描）、weather_fx.py 30 分钟缓存范式、start_app.py、database.py、c_universal.md P0 清单、ui_lead_spec.md（胶囊/status-dot/无 emoji/状态色单源）。

设计原则裁决：体检只做"预防性发现"，不做修复执行（修复动作沿用现有按钮）；本地项全静态零网络、单次 <1 秒；云端项一律可选且结果 30 分钟缓存；密码永不落盘、永不入缓存键、永不入导出包；全部复用现有纯逻辑模块，不引新框架。

## 决策

D1 分层防线。用户 8 个真机失败案例按"能提前抓到就提前抓"分层：① 无 python/conda、② CUDA torch 装成 CPU 版、③ requirements 安装被吞、④ 模型入口 miss、⑤ 数据集源不可达、⑥ python 版本不匹配、⑦ 密码重启失效、⑧ 关控制台即断。前六类多发生在云端且流水线已有自愈（env 自举、CUDA 保护、依赖扫描、多源克隆），但都是"提交后才花 20 分钟才知道"——体检把它们前置到"提交前可见"：②③⑥ 归云端体检的环境摘要（torch.cuda 验证、requirements 与 python 版本、源可达性 HEAD），⑤ 归环境摘要源可达性，① 归环境摘要的"需自举"预提示；④ 归本地模型入口预期提示；⑦⑧ 归本地凭据项（密码仅内存=警告）与侧边栏常驻警示。结论：体检是"望远镜"，不是"第二套执行器"。

D2 本地体检必跑且阻断分级。8 项本地检查在每次页面 rerun 与每次提交点击时自动执行，只允许 <1s 的纯本地 I/O（sqlite quick_check、文件 stat、shutil.disk_usage、ssh-add -L 限时 1s、无任何 socket）。fail 级项阻断提交并展开明细（与现有"凭据无效 st.stop"风格一致）；warn 级不阻断，仅提示。云端体检（L0-L3+环境摘要）是独立可选按钮，绝不自动触发（需 15-40s 网络），提交链路不依赖它。

D3 与"测试 SSH 连接"按钮合并策略：不删除、不替换。现有按钮是轻量 L2 探测，保留用于"注入公钥后快速复验"的高频场景；新增"云端体检"按钮 = L2 真实连接 + L3 环境摘要（python/GPU/磁盘/源可达），结果写入 session_state 并复用现有 ssh-health 条样式 + 缓存时间戳。二者是"体检快照"与"单点复验"的分工。

D4 体检胶囊放侧边栏（"云端配置"区正下方），明细折叠。状态取值 pass/warn/fail 用现有 status-dot 彩色圆点表达（绿/黄/红），文案零 emoji、状态色单源映射新增 `HEALTH_COLOR`。明细每行 = 检查名 + 结论 + 建议（一句话可执行动作，指回现有按钮/字段）。

D5 诊断导出为"纯文本、内存态、脱敏"：不落盘、st.download_button 直接下发 .txt，硬预算 ≤256KB，任何截断只发生在"最近任务条数、日志行数"两个维度，绝不含密码（构造上不含 + sanitize 兜底）。

## 可执行变更

### E1 新纯逻辑模块 paper_repro_app/preflight.py（零 streamlit 依赖，可单测，pytest 88 基线只增不减）

统一结果类型：`HealthItem = {"id": str, "label": str, "status": "pass"|"warn"|"fail", "message": str, "suggestion": str}`；统一汇总 `{"items": [...], "fail": n, "warn": n}`。

1. Python/依赖版本 `check_python_runtime() -> HealthItem`：sys.version_info >= (3,11) 且 importlib 可载入 streamlit/paramiko/requests；fail=版本过低→"安装 Python 3.11+ 后双击 start_app.bat"（对应案例⑥的本地侧 + 开箱断裂点）。
2. DB 完整性 `check_db_integrity(db_path=DB_PATH) -> HealthItem`：文件存在 + `PRAGMA quick_check` + 查 tasks 表首行；fail=损坏→"把 ~/.paper_repro_app/tasks.db 改名备份后重启应用"。
3. SSH 配置可解析性 `check_ssh_config(alias) -> HealthItem`：调 parse_ssh_config(alias)，alias 为空=pass(用表单字段)；alias 存在但解析不出 host=warn→"检查 ~/.ssh/config 缩进或换行"。
4. 凭据存在性 `check_credentials(has_password, key_path, agent_ok) -> HealthItem`：三方皆无=fail→"填密码，或填私钥路径，或点注入公钥"；仅有密码=warn→"密码只在本进程内存，重启应用或关控制台即失效；建议注入公钥免密"（对应案例⑦⑧，一次命中两个）。
5. 候选主机格式 `check_host_candidates(lines, default_user, default_port) -> HealthItem`：每行走 build_connection_profiles，error 行→fail 并回显该行；最终 host 为空或等于占位串 "my-server.example.com"→fail→"在云控制台复制登录指令整行粘贴"。
6. 公钥存在 `check_public_key_ready() -> HealthItem`：ensure_default_ssh_keypair 或 ~/.ssh/*.pub 存在=pass；无且当前无密码=warn；无且点了注入=该按钮自身已有错误兜底。
7. 磁盘空间 `check_local_disk(local_data_dir) -> HealthItem`：shutil.disk_usage 剩余 <200MB=fail，<1GB=warn→"清理磁盘或换本地输出目录"。
8. 端口可用 `check_remote_port(port, host_hint) -> HealthItem`：非 1-65535 数字=fail；port==22 且 host 含 seetacloud/autodl=warn→"AutoDL 实例端口通常为 4xxxx，以控制台登录指令为准"。

统一入口 `run_local_health(ctx) -> dict`（ctx 收表单现行值），rerun 与提交共用一份结果；侧边栏胶囊与提交阻断都只读它，杜绝逻辑分叉。

### E2 云端体检（可选按钮，L0-L3 复用）

`run_cloud_health(profile) -> {"status", "message", "env": {...}, "checked_at": ts}`：
- L0 本地凭据门：复用 RemoteRunner.detect_ssh_auth_sources + 密码在场判断，无凭据直接短路返回 fail（不发起网络）；
- L1 probe_host 逐候选 TCP（6s×2/台，总预算 ≤12s）分类排序；
- L2 ssh_connect 真实连接（12s，auth 类短路并回显 ssh_utils 既有诊断文案模板）；
- L3 连接后单条有界命令（exec_command，timeout 25s）取环境摘要并解析：`python --version`、conda 位置与 python 版本是否满足仓库要求（案例⑥）、`nvidia-smi --query-gpu=name,memory.total`（有 GPU 时追加 `python -c "import torch;print(torch.cuda.is_available())"`，False=warn"存在 CUDA torch 风险，流水线将走国内源修复"——案例②）、`df -Pk /` 与数据盘剩余（案例①的 <8G 走 /root/autodl-tmp 策略预提示）、对 pypi 清华/阿里、download.pytorch.org、github、ghfast.top 各做 3s HEAD 给出可达表（案例③⑤）。
- 缓存：`APP_HOME/health_cache.json`，键 = user@host:port + 私钥文件 mtime 指纹（不含密码），TTL 30 分钟，沿用 weather_fx 缓存读写范式；UI 显示"检查于 x 分钟前"，提供"重新体检"按钮破缓存。

### E3 结果呈现与按钮合并

侧边栏"云端配置"区下新增分区"本机体检"：一行胶囊（状态色 status-dot + "体检：通过/警告 n 项/失败 n 项"）复用 .pr-pill 风格；其下 st.expander("体检明细") 逐项输出 label + message + suggestion，fail 项建议文本直接给出"点击上方『注入公钥到服务器』/『测试 SSH 连接』"式动作指引。云端体检结果以独立小胶囊显示在 ssh-health 条旁（含缓存龄），颜色同源（pass 绿/warn 黄/fail 红 = 复用 get_status_color 色值映射常量，避免新增色）。提交点击时：run_local_health 存在 fail 项→st.error 列出首条 fail 建议并 st.stop（warn 只 toast 汇总一次）。渲染路径保持 try/except 兜底，任何体检异常只降级为"未体检"灰色，不影响表单与 AppTest 0 异常约束。

### E4 一键诊断导出

`build_diagnostics_export(tasks, log_tail=200) -> str`：纯文本，分四段——本机环境（platform、python、streamlit/paramiko 版本、APP_HOME、config 目录）；最近任务摘要（≤10 条：id/状态/当前步/host/user/port/repo_url/起止时间，不含私钥路径与 remote_workdir 细节）；app.log 尾部（read_log_tail 复用，≤200 行）；体检结果 JSON。整体经 ssh_utils.sanitize 过一遍（密钥/密码形状兜底）。UI：在"历史记录"页系统日志 expander 旁放 st.download_button("下载诊断包")，data 内存生成，file_name=`paper_repro_diagnostics_<时间戳>.txt`，不落盘；大小预算 ≤256KB，超限时按"任务先裁到 5 条、日志再裁到首尾各 100 行"截断并写入截断说明行。密码在构造上不可能出现（DB 无 password 列、_EXEC_STATE 仅内存、导出函数不接收密码参数），满足"无密码无敏感"。

### 验收口径
preflight.py 全纯函数可单测；pytest 88 基线保持全绿；AppTest 全页零异常（体检渲染失败静默降级为灰）；侧边栏与 ssh-health 条截图复核无 emoji、色彩取自既有令牌；诊断导出文件 grep 无 "BEGIN.*PRIVATE KEY"、无表单密码值。
