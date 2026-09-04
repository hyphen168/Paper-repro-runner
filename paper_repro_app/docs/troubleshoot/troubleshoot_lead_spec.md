（本环境无写盘工具，规范全文如下，将由运行时落盘到指定输出路径）

# 用户自助排障体系规范 v1.0（主导裁决版）

四份报告已通读：a_fail（31 项失败盘点+静默失败 Top5+事件字段模型）、b_selfhelp（13 条 E_* 码人话模板+三区诊断卡+quiet 防线+FAQ）、c_diag（本地 8 项体检+云端体检+L0-L3 复用+脱敏导出）、d_docs（GUIDE 阶段表+锚点双入口单源+FRIEND_GUIDE 五章+README 增节）。分歧已裁决：消息体系采 b 的轻量路径为骨架、采 a 的字段模型为数据契约、log_analyzer 不重写（后置）；健康检查采 c 全案（保留原"测试 SSH 连接"按钮不复用）；文档采 d 全案（锚点 G-x.y 为唯一步骤源）。本规范为实施唯一依据，冲突处以本文为准。

## 一、总纲

目标一句：任何用户（拿到 zip 即用）在任何一步失败时，都能在 15 秒内读到"发生了什么 + 我该做什么"，成功结果若有打折必有一行"结果说明"——无人指导也能自助解决。

设计原则：
1. 三段式消息（结论一句 / 动作一句 / 细节折叠），技术栈 trace 永不进主消息。
2. 静默失败等于失败：degrade、warn、空指标、CPU 化、降级模式，全部进收尾"结果说明"区与监控顶部警示条。
3. 双入口单源：UI 动作带锚点（G-x.y），步骤细节只维护 GUIDE.md 一份；FRIEND_GUIDE 常量是 zip 使用说明唯一事实源。
4. 体检前置优于排障后置：提交前本地体检（<1s）fail 即阻断；云端体检为可选快照，与"测试 SSH 连接"并存。
5. 中文无 emoji、不写密码明文、零新框架；错误码统一 E_* 短码，历史任务无码可渲染（向后兼容）。

## 二、失败模式 Top 清单收敛（16 项，每项消息模板落地源）

从 a 的 31 项按"用户频次×危害"收敛为 16 项；每项产出一条三段式用户可见消息（结论 / 动作 / 详情锚点），模板落盘 GUIDE 第 0-7 章，代码里出现处替换为 E_* 码渲染。

连接（G-2）：
- E_CONN_UNREACH：无法连接主机：原因分类（DNS/拒连/超时/网络不可达）。动作：确认实例开机且地址端口为控制台最新值（G-2.1）。详情：列出全部尝试主机与分类。
- E_CONN_AUTH：SSH 认证失败。动作：核对密码；或注入公钥；AutoDL 密码在控制台重置（G-2.4）。
- E_CONN_NOCRED：未找到可用认证源。动作：填密码或私钥路径/粘贴 PEM，或在 ssh-agent 加载（G-2.3）。
- E_CONN_AMBI（R1 类已修）：解析后主机名异常。动作：粘贴整行 ssh 登录指令（G-2.1）。

克隆（G-4）：
- E_CLONE_TIMEOUT / E_CLONE_PRIVATE：拉取超时或私有/不存在。动作：换加速源；私有仓库需在候选框填可用地址（G-4.1）。

环境与依赖（G-3）：
- E_PY_BOOTSTRAP：云端无 python/conda，自动安装中失败。动作：按提示手动安装 Miniconda 后重试（G-3.1）。
- E_PY_VERSION：conda 环境 Python 版本与仓库要求不符。动作：重建指定版本环境（G-3.2）。
- E_TORCH_CPU：检测到 CUDA 训练所需 torch 为 CPU 版或缺失。动作：重新执行（自动装 CUDA 版，已禁 CPU 回退）（G-3.3）。
- E_DEP_SWALLOW：依赖安装失败被容忍，运行期才缺包。动作：重新执行（本次失败即中断并列出缺包清单）（G-3.4）。

数据集（G-5）：
- E_DS_DEGRADE：未发现匹配数据集配置，已降级安全检查（未训练）。动作：填数据集 YAML 路径或 ZIP/TAR 直链后重跑（G-5.1）。
- E_DS_SRC：官方下载源不可达。动作：换镜像直链（G-5.2）。

运行（G-4）：
- E_MODEL_ENTRY：自动未识别出训练入口。动作：切"实际运行"粘贴 README 训练命令（G-4.2）。
- E_RUN_TIMEOUT：单步超时。动作：延长超时重跑，或确认是否训练卡死（G-4.3）。
- E_GPU_RES：显存不足/驱动不匹配。动作：改小 batch/imgsz 后重跑（G-4.4）。

结果与重跑（G-6/G-7）：
- E_METRIC_MISS：训练可能已执行但未采到指标。动作：确认输出文件名为 results.csv/metrics.json（或按 G-7.2 格式调整）。
- E_RERUN_CRED：重执行缺密码（进程内存安全设计）。动作：现场补输密码；勿关控制台窗口（G-6.1）。

静默面五类（危险最高）统一处置：auto 降级空指标、依赖被吞假成功、GPU 静默 CPU、指标 miss 误标"安全模式"、取消/关窗残留计费——前四类由 P0 结果声明与 quiet 防线消除，残留计费给"结束前查日志/关窗前知悉"指引（G-6.3）。

## 三、错误消息三段式与诊断卡终版

裁决：采用 b 的轻量事件结构（optional 追加，历史兼容）承载 a 的字段语义，字段最小集：

- err_code：E_* 短码（见上表），无码则省略。
- user_msg：两短句（首句结论、次句动作）。
- category：连接/克隆/环境/依赖/数据集/运行/指标/重跑/内部（降级消息另带 level=degrade）。
- action_text + action_target（锚点 G-x.y）；可复制命令或 URL 放详情。
- trace_tail：技术栈尾部 ≤3 行；全文仅进折叠 code 块。
- silent_flags：result_warnings（聚合 degrade/verdict/无指标）由 storage_utils 落库生成。

触发规则：remote_runner 各失败出口先产出 {err_code, user_msg, trace_tail}，替换现"远程执行失败：<裸错>"的整段主消息；collect 零指标输出分类 `[指标分类] reason=no_train_output|metric_files_missing|format_unrecognized`；run 前输出 `[paper-repro-config]` 摘要（data/epoch/batch/device/cuda）。监控 failed 分支与历史页共用一个 `render_diag_card(result)`（面板结构复用 .panel/.status-dot/.meta-pill）：结论行（err_code+user_msg）→ 动作行（锚点文本）→ 技术详情折叠（st.code ≤120 行）。成功但 result_warnings 非空时，顶部渲染 amber 警示条（复用 ssh-health fail 样式族），文案首句"任务完成但结果打折"。

五条改造示例（文件：旧 -> 新）：
1. app.py 监控 failed 分支：`st.error(payload.message)` -> `render_diag_card(payload)`。
2. app.py 历史页失败 expander：原样 JSON -> 顶部 diag 卡 + JSON 折叠。
3. remote_runner install_step：吞错继续 -> 失败 exit 并打印 `缺包清单：<差集>`（E_DEP_SWALLOW 模板）。
4. remote_runner run_step：`--help` 不看退出码 -> 非 0 即失败并打印尾部（消除 #24 假启动）。
5. remote_runner run_step 头：训练前打印 GPU/CUDA 摘要，CPU 化即 warn（进 result_warnings，E_TORCH_CPU）。

## 四、健康检查终版

采纳 c_diag 全案，分层防线：

本地体检（提交前自动，8 项，纯静态 <1s，fail 阻断）：新模块 `paper_repro_app/preflight.py`，函数签名逐项：1) python 版本 ≥3.11；2) 依赖齐（importlib 检查 streamlit/paramiko/pandas）；3) 配置目录可写（~/.paper_repro_app）；4) 天气缓存可读（异常仅 warn）；5) 主机候选已填且非占位（占位默认已改空，此处兜底）；6) 凭据存在（密码非空或私钥文件有效或 agent 可用）；7) 端口为 1-65535 数字；8) DB 可读写（TaskStore 冒烟）。每项返回 {check, status: pass|warn|fail, action}；fail 汇总阻断并逐条渲染（st.error+建议），warn 放 caption。提交按钮处理器最前调用，全 pass 才继续（对齐现有 st.stop 风格）。

云端体检（可选按钮，E2）：复用 L0 凭据门 -> L1 probe_host（并行 12s 预算）-> L2 ssh_connect（12s）-> L3 单条有界命令（python3 版本 / nvidia-smi 摘要 / 磁盘 / 四数据源 HEAD 可达表）。结果 30 分钟缓存（键不含密码，沿用 weather 缓存范式）。呈现：侧边栏"体检"胶囊（复用 .pr-pill/.status-dot 色系）+ 折叠明细；原"测试 SSH 连接"按钮保留（L2 轻量复验）。

诊断导出（E4）：st.download_button 内存下发脱敏纯文本摘要（DB 任务最近 10 条：状态/步骤/err_code/user_msg/尾日志 12 行 + 本地体检结果 + 环境信息），构造不含密码字段，sanitize 兜底，超 256KB 按任务数/行数两级截断。放侧边栏体检区。

## 五、文档与手册终版

采纳 d_docs 全案：

1. 新建 `docs/troubleshoot/GUIDE.md`：章节轴 = 流水线阶段（0 读日志与总规则 / 1 本地启动 / 2 服务器填写与连接 / 3 云端环境与依赖 / 4 仓库与运行入口 / 5 数据集 / 6 运行中断与重跑 / 7 结果与指标），每章"阶段 | 症状 | 原因 | 动作"四列表 + 锚点 G-x.y。内容源 = 第二节 16 项模板 + ssh/dataset/ui 既有定稿文案 + 八条真机案例改写。
2. `make_dist.py` FRIEND_GUIDE 常量改写为五章：快速开始 5 步 / 服务器填写（AutoDL 三步：整行粘贴登录指令→填密码或注入公钥→检测连接绿了再提交）/ 常见问题 15 条 Q&A / 排障速查表 15 行 / 安全与成本提醒（密码不落盘、关窗即断、云端计费、重启重输密码）。打包时 txt 入 zip 顶层（已落地）。
3. README 新增"遇到问题"小节（约 6 行）：先看 zip 说明第三章；按阶段号查 GUIDE 速查表；凭据先打码再求助；Python 版本口径 3.11+（已统一）。
4. UI 全部 help/建议动作统一挂锚点"动作一句（G-x.y）"；锚点双向无悬空为验收项。

## 六、实施顺序 P0/P1/P2 与不做清单

P0（止血一提交，优先正确性与"结果真实性"）：
- P0-1 run 前 [paper-repro-config] 摘要 + --help 退出码检查（remote_runner.py）。验收：本地 bash 脚本生成 + 失败场景 AppTest。
- P0-2 install 步骤失败不再吞：安装失败 exit 并打印缺包清单（remote_runner.py install_step）。验收：bash -n + 既有 88 绿。
- P0-3 run 前 GPU/CUDA 摘要与 CPU 化 warn（remote_runner.py run_step 头）。验收：生成命令含摘要段。
- P0-4 结果说明区 result_warnings：storage_utils 收尾聚合（degrade 标记/metric_verdict/dataset reason）+ app 监控顶部 amber 警示条 + 历史"结果说明"。验收：单测合成 result 断言 warnings 聚合；AppTest failed/success 各一。
- P0-5 preflight.py 8 项 + 提交前调用（fail 阻断）。验收：新增单测矩阵 8 项 × pass/warn/fail ≥24 断言。
- P0-6 render_diag_card + E_* 码替换监控/历史失败渲染（app.py），16 项模板首批 ≥6 项接线（E_CONN_UNREACH/AUTH/NOCRED/E_TORCH_CPU/E_DEP_SWALLOW/E_MODEL_ENTRY）。验收：AppTest failed 种子页无裸 trace 在主消息。
- P0-7 GUIDE.md 骨架（0-7 章+16 项模板+锚点）+ FRIEND_GUIDE 五章 + README 增节。验收：锚点 grep 双向无悬空；打包 smoke。

P1（体验）：
- P1-1 云端体检按钮与胶囊（复用 test_ssh_connection 链）+ 30 分钟缓存 + 诊断导出 download_button（app.py + preflight.py 扩展）。验收：AppTest 含两按钮渲染；缓存键无密码。
- P1-2 剪贴板诊断摘要（st.components 内联 JS，失败降级 st.code）。验收：AppTest 无异常。
- P1-3 数据集 reason_code 落地与镜像回退（承接 dataset_lead_spec：remote 层降级文案带动作锚 G-5.x）。验收：degrade 消息含 reason 与建议。
- P1-4 侧栏"遇到问题？先看这里"七问 FAQ（锚点跳转文案）。验收：文案无 emoji。

P2（后置/观察）：
- log_analyzer 升级为结构化事件解析器（若 P0 后仍暴露裸错再动）。
- 远端残留进程清理：仅结果页提示手动 kill 命令（不自动执行）。
- 模型入口扩展与 run 命令候选确认流：与"换论文/仓库自适应"专项规范合并后实施，不在本体系单独铺开。
- UI 向导式多步表单（明确不做，交互复杂且未入诉求）。

不做清单：不写密码明文于任何文件/日志/导出；不引入新框架或图标字体；不重写 remote_runner 连接主循环；不自动 kill 远端进程；不改动天气/昼夜/视觉子系统；不把"降级/空指标"记为 success 而不带 warnings；测试基线 pytest 88+、AppTest 0 异常。

验收汇总门：三机失败案例（①-⑧）各在 UI 能读到"结论+动作"消息（非裸 trace）；degrade/空指标任务有结果说明；zip 解压副本可完成 15 问自答；全库无密码明文。