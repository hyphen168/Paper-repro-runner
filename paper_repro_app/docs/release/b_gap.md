# 交付阻断项分析：Paper Repro Runner（v1.5.0 zip → v2.0.0 可交付版）

依据：make_dist.py、start_app.bat/py、app.py、paper_repro_app 包内 remote_runner/storage_utils/ssh_utils/repo_profiles/model_discovery/dataset_discovery/report_generator/paper_claims.json、README、pyproject.toml、requirements.txt 逐一核查；docs/troubleshoot/GUIDE.md、docs/acceptance_test/c_universal.md、docs/paper_switch/paper_switch_lead_spec.md、docs/ui_expert/ui_lead_spec.md 对照；.pytest_cache lastfailed 为空（最近一次全绿）。未做真机/干净机执行，结论以代码与既有验收证据为准。

## 决策

**结论：1.5.0 打包物不建议原样交付给非专家朋友；先修 4 项 P0（都是小改动、零新框架、约 1 个工作日）后，以 v2.0.0 发版即具备交付条件。核心链路（解压-启动-配服务器-提交-执行-失败诊断-成功看指标-迁移数据）已真实打通，风险集中在"入口识别失败后的自助闭环"与"若干 UI 承诺与行为不符"两处，不涉及架构返工。**

### 交付旅程检查单（陌生人 13 步）

| # | 旅程步骤 | 验收判据 | 满足度与证据 |
|---|---|---|---|
| 1 | 解压与文件齐全 | zip 内含应用全代码、顶层使用说明 txt、docs；排除 logs/data/.venv/cache；无真实口令 | 满足。make_dist.py 排除清单齐全且把说明 txt 写入 zip 顶层文件夹（c_universal 旧缺口 P0-3 已修）。见风险：scripts/ 随包，e2e_task.py 含真实 AutoDL 主机与端口 |
| 2 | 安全与隐私提示 | 无明文凭据；使用说明/手册有凭据与成本警示 | 部分。代码侧达标：密码仅存 `_EXEC_STATE` 进程内存、config_store 落盘不含密码、sanitize() 日志脱敏；GUIDE 含成本与关窗警示。但 zip 内说明 txt 无独立"安全与隐私"小节（MOTW 解锁、0.0.0.0 局域网暴露、勿关控制台），仅在 GUIDE 深处 |
| 3 | 装 Python 3.11+ | 未装或版本过低时给出指引并可跳官网 | 满足（版本口径已统一为 3.11+，pyproject/requirements/start_app 一致）。遗留：`py -3` 可能选 3.13/3.14，锁版依赖在该解释器上的 wheel/镜像同步未实测（干净机不可得，属验收盲区，见下） |
| 4 | 双击 start_app.bat | 找 Python→建/修 venv（坏 venv 自动重建）→依赖指纹秒开→镜像测速逐源回退→起服务开浏览器 | 满足。start_app.py 三路探测+venv_is_healthy()+指纹+并发镜像测速+端口占用检测均具备。遗留：先开浏览器后起服务，首帧可能见"无法访问"需刷新（P2）；绑 0.0.0.0 触发 Windows 防火墙弹窗无预告文案 |
| 5 | 首屏 | AppTest 0 异常；三 tab 可切换；侧栏含求助入口；无 emoji | 满足。app.py 侧栏"遇到问题？先看这里"FAQ 折叠、三 tab、空态文案齐全。部分：无新手向导，B/C 级用户全靠文案自学 |
| 6 | 配服务器 | 支持整行 ssh 命令、user@host:port、SSH 别名、多行多机候选；测试连接；注入公钥；连接档案 | 满足。ssh_utils（parse_connection_profile 引擎/别名展开/分类诊断）+ remote_runner L1 TCP 并行排序 + L2 真实凭据连接，auth 短路给精准诊断；tests/test_ssh_engine、test_auto_hosts 覆盖。遗留：端口默认 22，AutoDL 新实例必错（须靠整行命令解析纠正，帮助文案已写但无引导步骤） |
| 7 | 提交任务 | 凭据无效提交前拦截并给排查建议；论文/仓库识别失败有中文报错 | 满足。app.py 提交前校验、AutoRepoDatasetCrawler 回退、st.toast 引导明确 |
| 8 | 云端执行与失败兜底 | torch CUDA 自动重装（cu121→cu128，禁 CPU 回退）；依赖预算 240s；verify 容错；单步超时可配 | 满足。remote_runner build_pipeline 证据充分；verify 对"收集类错误"转编译冒烟，真实用例失败才退出 |
| 9 | 失败自助排障 | 失败卡给错误码+结论+建议+GUIDE 锚点；FAQ/GUIDE 覆盖全部旅程环节 | 部分。_FAILURE_MAP 8 族 E_* 卡+LogAnalyzer+侧栏 FAQ+GUIDE G1-G7 锚点体系完备。两处不符：①"复制诊断摘要"按钮只写 session_state 不复制、无任何点击反馈，与 G-0"可贴给 AI"承诺不符；②GUIDE G-4.2 声称"识别扩展会自动给出候选清单供确认"，实际 UI 无此交互 |
| 10 | 成功看指标与对比 | 所有成功任务可见"结果说明行+指标卡+论文对比表+报告"；degrade/无指标要明示 | 满足。_render_success_result 在监控与历史共用；build_comparison_table 恒产出对比表（空匹配也给单行说明，杜绝伪造占位），历史折叠仅需该键存在即必真；结果说明行区分 degrade/无指标/stdout 兜底。遗留：对比表论文值来自 paper_claims.json 静态 3 条目，任意论文只显示"基准未录入"，无 UI 填入口（c_universal P0-1 未落地） |
| 11 | 重跑同仓库 | 原配置重执行；密码丢失可现场补输；记忆预填 | 部分。监控页"重新执行流水线"+内存密码补输链路完整。断裂点：仓库档案"成功后自动记录"未接线——终态成功路径（storage_utils._run_pipeline_in_background）无 upsert_profile/rebuild 调用，档案仅在历史页手动"从任务历史重建"后生成；故"提交页自动预填上次成功配置/秒配"对新用户实际不出现，而空态文案却写"成功跑过任务的仓库会自动记住…"（过度承诺） |
| 12 | 换论文/换仓库 | 粘贴新链接→识别→提交闭环；每论文隔离；同仓复用 | 部分。目录隔离/云端哈希隔离/同名互不覆盖健全。根因同第 9 步：非标准入口仓库（trainer.py 命名、monorepo、多候选、zoo）在 auto 模式下要等流水线走到 run 步才以退出码 65 失败（前面 20-40 分钟浪费在 clone/env/install/dataset）；失败后无"调整命令后重跑"，只能回提交页手工重填（run 命令草稿仅存于当前浏览器会话） |
| 13 | 迁移与数据归属 | 数据全在 ~/.paper_repro_app 与数据目录；应用目录纯代码；旧数据自动迁移；换机指引 | 满足。paths.py/portability 测试（test_paths_live_in_user_home 等）与说明 txt 迁移指引齐备 |

### 特别审查结论

- 诊断卡/FAQ/GUIDE 覆盖面：结构上已覆盖全部旅程（G1 本地启动、G2 连接、G3 依赖、G4 入口、G5 数据集、G6 结果、G7 重跑），但文档两处超前于代码（候选确认流、"自动记住配置"），会让朋友按手册找不到按钮；"复制诊断摘要"按钮失效则直接击穿 G-0 的求助路径。
- 对比表与结果说明可见性：全部成功任务可见，degrade 任务会以 warning 明示"本次未训练"，不会假报指标；历史页对早期无 payload 任务会退化为原始日志（可接受）。
- 仓库档案首体验（zip 分发、新用户零历史）：档案文件不存在时全链路不报错、不阻碍，预填分支天然跳过——首体验安全；但档案管理区空态文案误导，且档案读取仅在用户填写"代码仓库候选"字段时触发（只贴论文链接不触发），需在文案与接线两方面修正。

### 阻断项汇总

**P0（不修不交付）**
1. 失败后自助闭环缺失（第 9/12 步同根因）：auto 模式对非常规仓库必然晚段失败，且无编辑命令重跑入口，与 GUIDE 宣称矛盾。
2. 仓库档案自动回写未接线（第 11 步）：记忆/秒配是宣传卖点，目前仅手动重建可实现。
3. "复制诊断摘要"按钮无效：承诺动作无效果，破坏求助路径。
4. 打包卫生：scripts/e2e_task.py 携带真实 AutoDL 主机域名与端口并可驱动云端任务，不宜入包；版本号双源（make_dist=1.5.0 vs pyproject=0.2.0）需统一单源。

**P1（可后置一个迭代）**
- 论文基准填入口（高级选项填原文指标+出处，随任务存储入对比表/报告）。
- AutoDL 三步折叠引导（复制整行登录指令→贴密码→测试变绿再提交）。
- 启动器改为服务就绪后开浏览器；说明 txt 增"安全与隐私/首次问题"小节。
- GUIDE G-4.2 与空态文案对齐实现；run 命令草稿持久化（重启不丢）。
- README 所列 docs/product-launch-record.md、docs/final-delivery-package.md 等文件核实存在性并清理死链。

**P2**
- 0.0.0.0 局域网暴露改 127.0.0.1 默认+可选 LAN 开关；侧栏/提示 8505 去硬编码；MOTW/杀软说明；C 级示例种子任务；锁版依赖镜像同步预检脚本。

## 可执行变更

### P0 变更与验收判据
1. **失败卡补"编辑命令重跑"**：监控/历史失败卡增加可编辑 run 命令输入+「带新命令重跑」（新建任务复制原字段，复用内存密码/现场补输，明文不落库）；auto 模式 run 步失败（退出码 65）时把已识别候选/README 摘录随失败 payload 回传展示。判据：构造 trainer.py 仓库 mock 失败，页面可改命令一次点按重跑成功；密码不落盘。
2. **档案自动回写接线**：storage_utils 终态处理（成功写 entrypoint/run_command/data_config/host_hint/mode；失败只写 fail_reason_tags 与一句建议，不覆盖成功快照）后调用 repo_profiles.upsert_profile；提交页读取逻辑扩展为"论文自动识别出的 repo_url 也查档"。判据：跑通一例成功任务后，不点任何按钮，提交页同仓第二次出现预填提示；失败不覆盖上次成功；grep 复核无第二入口。
3. **修复复制按钮**：失效按钮替换为对 diag_text 的 st.code 渲染（Streamlit 原生带复制），或点击后展示可复制文本块并 toast 提示。判据：AppTest 点击后页面出现诊断文本块；G-0 文案与实际行为一致。
4. **打包卫生**：make_dist 排除 scripts/（或仅排除 e2e_task.py）与 tests/；VERSION 常量在 pyproject 与 make_dist 单源（make_dist 读取常量文件）；核对 docs 无口令。判据：重新打 zip 后 grep 无真实主机域名/端口；pyproject 与 zip 文件名版本一致。

### P0 修复后的验收方法（供执行者落地）
- **解压副本冒烟**（clean-room 模拟：解压副本+现有 Python 3.11+ 解释器+删除副本 .venv 重建路径）：pytest 全绿（基线 92，lastfailed={} 复核）；AppTest 会话脚本遍历提交/监控/历史页与失败卡渲染，0 异常；断言关键 UI 元素存在（5 个运行方式 radio、"测试 SSH 连接"、"遇到问题？先看这里"、"重新执行流水线"、"仓库档案管理"）。
- **三项任务型演练（各带判据）**：
  - 成功路径：YOLOv5m-NEU-DET+coco128 类 auto 全链 success。判据：终态 success；日志含[指标结果]；结果说明行存在；对比表含行；reports 目录落盘 report.md/summary.md。
  - 失败路径：故意错误端口/凭据。判据：失败卡含 E_CONN_* 或 E_TORCH_CPU 类错误码、建议动作与 G 锚点文本；无裸 traceback；一键诊断块可复制。
  - 重跑路径：失败→监控页带密码重执行→成功；再提交同仓库验证档案预填出现、缓存复用不重下。判据：DB run_command/data_config 保存；档案 JSON 生成且无口令字段。

### v2.0.0 发布变更摘要（模板）
- 新增：失败后"调整命令重跑"闭环；仓库档案自动回写与提交页秒配；AutoDL 三步引导；数据集直链安全解压（路径穿越防护/磁盘与体积预算/308 跟随重试）；论文原文基准填入口。
- 修复："复制诊断摘要"无效按钮；GUIDE/档案文案与实现对齐；e2e 脚本与真实主机信息不再入包；版本号统一单源；README 死链清理。
- 已知限制：训练入口识别白名单仍有限（trainer.py 等非常规命名走人工命令）；GPU 实例禁 CPU torch 回退；任务随控制台窗口存活，关窗即断；密码仅进程内存（重启/换会话需现场补输）；局域网默认开放（0.0.0.0）。
- 验收口径：pytest 全绿 + AppTest 0 异常 + 解压副本三演练通过 + 中文无 emoji。
