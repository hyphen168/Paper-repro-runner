# 换论文/换仓库自适应规范（主导裁决版 v1.0）

四份报告（a 档案记忆 / b 入口识别 / c 候选确认流 / d 模板库）已通读，真机六活案例与代码事实已交叉复核（model_discovery.py 顶层白名单、run_step 双降级表、evaluate_and_rank 输出、TaskStore 字段、~/.paper_repro_app 配置先例均属实）。冲突裁决如下，本文为实施唯一依据。

## 一、总纲

目标一句：粘贴一篇新论文或新仓库到"提交任务"，系统按 记忆→模板族→入口评分→人工命令 四层自动适配；适配置信不足时给"候选清单+依据+一次点击确认"而非技术细节；同一仓库第二次及以后运行免重填。

原则：
1. 分层命中，记忆优先：同仓库档案 > 模板族 > 通用入口评分 > run 命令手填（权威兜底，永远可用）。
2. 宁确认勿猜：多候选等权、置信不足、模型库/需改码三类情况绝不在后台静默选单点直跑，一律交用户一次点击；auto 模式只在"唯一高置信"时才直跑。
3. 数据与命令分离：档案与模板只存配方形态（入口相对路径、参数名、data_role 枚举），不存任何数据集 URL；数据集继续走现有 data_config 直链 / YAML / __repo_managed__ 自下载。
4. 安全红线：档案、模板、记忆文件永不写密码、私钥内容/路径与日志原文；认证只记枚举类型；DB 是唯一史实源，JSON 档案是可重建物化视图。
5. 中文、无 emoji、无新框架；全量改动守住 pytest 88 基线全绿与 AppTest 0 异常，逐批提交。

## 二、仓库档案终版

裁决：采纳 a 的单一 `repo_profiles.json`（否决 b 的 entry_memory.json 第二文件方案，避免双文件漂移）；c/d 的档案联动统一挂此文件。

- 文件：`~/.paper_repro_app/repo_profiles.json`（config_store 同目录；600 权限；损坏改名 .corrupt 后空档启动；临时文件 + os.replace 原子写；模块级 Lock）。
- 键规范化：去尾部 / 与 .git；http 统一 https；git@/ssh 转 https；剥 ghfast.top 等加速前缀；owner/name 三段（大小写不敏感）与 aliases 命中。换镜像/换加速仍命中同档案。
- 字段（a 的 schema + b 补充 mode/entrypoint/candidates）：entrypoint（仓库根相对路径）、run_command、data_config（空记哨兵 __repo_managed__）、env_note、task_family、mode、last_status、last_success_at、last_attempt_at、run_count、success_count、host_hint（host/user/auth_kind 枚举）、fail_reason_tags、aliases。
- 写时机：后台线程终态落库后同步 upsert；成功写 entrypoint/run_command/data_config/host_hint/mode；失败只写标签与一句人话建议，绝不覆盖已有成功快照。写失败仅告警不阻塞。
- 读与预填：repo_hint 确定即轻量查档（不爬网）命中预填 run_command/data_config，文案「已按上次成功配置预填：仓库 · 最近成功时间 · 主机」。成功后又有失败尝试：保留成功配置、黄色警示「最近一次尝试已失败（原因），仍沿用上次成功配置」+「清除此仓库记忆」按钮。auto 模式提交若用户未手改，把档案 run_command 作为实际命令落任务。
- 读时合并与自愈：get_for_repo 返回前与 DB 该 repo 最近 success 比对，DB 更新则按"最近成功优先"合并覆写；同 repo 无 success 不预填命令，只存失败标签与指引。冲突以 DB 为准；清除档案后不因 DB 历史自动复活（重建是显式动作）。
- 重建与迁移：不加 DB 列；启动或历史页提供 rebuild_profiles_from_db() 显式重建；历史页新增"仓库档案管理"折叠区（repo/入口/命令摘要/成功次数/最近成功/单删/重建）。
- 模块：新增 `paper_repro_app/repo_profiles.py`（零 streamlit）：normalize_repo_url / load / save_atomic / get_for_repo / upsert_success / upsert_failure / rebuild_profiles_from_db / list_profiles / remove_profile。
- 失败标签→人话映射（静态表，随档案存）：模型库→「模型 zoo 仅 load 无训练脚本，建议换论文官方训练仓库」；入口非常规（trainer.py 类）→「已记住入口 trainer.py，下次自动按此运行」；monorepo→「入口在 mnist/main.py，按子目录入口执行」；需改码→「模型选择写死在代码/注释，不适配自动参数化：请改好源码后自定义命令」；上游依赖漂移→「上游已改 import 依赖，建议固定上次成功版本」。

## 三、入口识别扩展终版

裁决：采纳 b 的两段式评分方案 + d 的固定子目录与探针；识别对象从"顶层 5 文件"升级为"云端扫描 → 语义评分 → Top3 → --help 参数面探测"，载荷带 mode 分档。

- 云端扫描（ModelDiscovery.build_remote_script 第一段，复用自包含脚本架构）：`find . -maxdepth 3 -type f -name '*.py'`；候选 = 固定名族 {train, trainer, training, pretrain, finetune, run, main, demo, app, detect, predict} 全层级命中 + 文件名含 train 语义任意 .py（截 5）+ hubconf.py/setup.py 单独标记；另抓固定子目录（examples/、tools/、scripts/、dcgan 类按族）与 README 前 200 行中"python <路径>"佐证行。
- 语义评分（本地纯函数模块 `entry_rank.py`，可单测）：文件名权重 train>trainer≈training>main>run>pretrain/finetune>demo/app；深度惩罚 depth1 扣 2、depth2 扣 4；README/import 佐证加 3；--help 命中训练标志（epochs/arch/data/dataset/batch/config）加分。输出 Top3 + 置信度 = 权重归一 × (1−depth×0.1)。
- --help 探测仅对 Top3 执行（每候选 15s、非零不判死），解析 usage 得参数名集合，映射受控白名单 {epochs, batch, batch-size, data, data-dir, dataset, arch, imgsz, weights}，只报告实际证实键（覆盖 akamaster --arch 与 yolov5 --batch-size 形态）。
- 模式判定与载荷：`mode ∈ {OK, MULTI_MONOREPO, MODEL_ZOO, NO_ARGPARSE, NONE}`；载荷 {entrypoint, cwd_rel, auto_command, candidates:[{id,rel_path,score,conf,help_args}], mode, family, zoo_only, unsuitable_reason}；保留旧键 entrypoint/auto_command/reason，extract_payload 兼容旧格式。
- 特殊形态：hubconf.py 且仅 def load_*/entrypoints、全树无训练名族 → MODEL_ZOO，reason 明示「模型库非完整训练实现，请换官方训练仓库或自定义命令」，禁 auto_run。Top1 depth≥1 → MULTI_MONOREPO，auto_command = `cd <子目录> && python <文件名>`（run 步骤整串经 bash -c 天然兼容，tune 尾缀恰好落在 python 之后，runner 拼接零改动）。--help 非零或无选项输出 → NO_ARGPARSE，候选标记"需改代码训练，不建议"，UI 引导换带 argparse 实现或 run 手填。
- 跑侧接入：remote_runner.py 两处降级/safe 入口白名单扩展为"优先读 model 载荷 entrypoint（含 cwd_rel），否则扩展名族表（含 trainer.py）"；run 步骤真实执行成功且命令有效时，execute 返回携带 entry_used 供档案回写。

## 四、候选确认流终版

裁决：采纳 c 的"auto 提交前分流"，卡片三要素（命令+依据+置信徽标），证据优先级：档案命中 > README 佐证 > 实际探测；历史页"调整命令后重跑"复用 P0-2 密码补输流程。

- 提交流程改动点（auto/tune 模式，提交按钮点击后、创建任务前）：
  1. 查档案：同仓库成功档案 → 直接预填 run_command/data_config 直跑（标注「记忆命中：任务 xxx」），唯一高置信（conf≥0.8 且 mode=OK）也直跑。
  2. 多候选（Top3 中 ≥2 且无档案）：渲染确认卡（复用 .panel/meta-pill/status-dot 无 emoji）：每条 radio 显示 相对路径 + 依据（README 行/参数表摘要）+ 置信徽标；一次点击提交；不选则取消回提交页。
  3. 无识别（NONE）或 MODEL_ZOO/NO_ARGPARSE：转 run 模式引导区，给仓库辅助（*.py 清单截断 + README 训练命令摘录），模板文案分族，提供 GitHub 搜索该仓库"train"链接形态（仅文本提示不加裸 URL 入库）。
- 换论文 3 步引导（固定文案）：① 粘贴论文链接或仓库候选 → ② 系统自动识别仓库/入口/数据（失败走上方分流）→ ③ 确认或选候选后提交。
- 失败重跑：监控/历史失败区新增「调整命令后重跑」——新建任务复制原字段、run_command 可编辑、复用内存密码/补输（P0-2 已实现），明文不落库；重跑成功后自动 upsert 档案。
- run 模式 text_area 增加档案预填 value=（key 唯一，守住 AppTest）。

## 五、模板库终版

裁决：采纳 d 的 11 族常量表，落 `paper_repro_app/repo_templates.py`；族内不存 URL；用户级覆盖走 `~/.paper_repro_app/templates_user.json`（加载优先于内置，免改代码）。

- FAMILIES 常量：id / 关键词（仓库名与 README 词，复用 evaluate_and_rank 上下文做本地初筛）/ 云端探针 markers（hubconf.py、trainer.py、configs/、tools/train.py、requirements 含 ultralytics 等）/ 入口规则 / 参数注入模板 / data_role（枚举：coco_yaml、raw_dir、repo_self_download、hf_dataset、imagefolder）/ 坑注（中文短句）。初始 11 行：yolov5-ultralytics、torchvision-zoo、kuangliu-cifar、akamaster-resnet、pytorch-examples-monorepo、hf-transformers、timm、gan、mmdet、自定义单文件、通用 fallback。
- 纯函数：classify_by_keywords(repo_url, repo_name)（本地 0 网络）与 match_by_probes(file_list)（云探针联动）；单测覆盖 10 族正例与负例。
- 数据角色消费：coco_yaml→现有直链自动 YAML；raw_dir→G2b env 导出根目录；repo_self_download→__repo_managed__；hf_dataset→提示 HF_ENDPOINT 镜像为 registry 可编辑配置（config_store 通道，非硬编码 URL）；imagefolder→--data-dir 注入。
- 回填流程：人工确认真跑通后，成功页「记住此仓库适配方式」→ 写草稿 ~/.paper_repro_app/template_drafts.json → review（≥2 仓库验证、无 URL、中文无 emoji）后合入内置常量；用户级覆盖直接写 templates_user.json。
- 度量：report_templates_coverage.py 本地只读查询各族 auto 命中/降级/zoo 计数，落后族优先补条目。

## 六、实施顺序与不做清单

### P0（止血，一批提交；目标：换论文三个最痛案例不再技术白屏）
- P0-1 档案模块 repo_profiles.py + 终态 upsert 钩子（storage_utils）+ 预填与清除 UI（提交区 + 历史页档案管理折叠）。
- P0-2 MODEL_ZOO / NO_ARGPARSE / trainer 变体判定（model_discovery 最小扩展：加 hubconf 探测、trainer/training/run/finetune 进候选、mode 载荷），zoo 与需改码禁 auto_run。
- P0-3 run_step 两处降级入口表加 trainer.py 与 model 载荷优先；monorepo `cd 子目录 && python` 形态。
- 验收：新增单测 ≥8（档案规范化/别名/合并优先/损坏/原子写；zoo 判定与文案；NO_ARGPARSE；monorepo 命令形态；入口表含 trainer.py）；88 基线全绿增量；AppTest 0 异常；真机复跑 akamaster（自动识别 trainer.py+--arch）与 chenyaofo（提示换训练仓库而非空命令）。

### P1（主链路，一批提交；目标：秒配 + 候选确认流）
- P1-1 entry_rank.py 评分 Top3 + --help 参数面 + 载荷扩展（兼容旧键）；--help 仅 Top3、15s/候选。
- P1-2 app.py auto 提交前分流确认卡（唯一高置信直跑 / radio 一次点击 / 转 run 引导 + README 摘录）；run 模式档案预填。
- P1-3 失败重跑「调整命令后重跑」（复制字段+编辑+补密）；成功回写 entry_used。
- 验收：单测 +8（评分排序、载荷兼容、help 解析、分流分支）；AppTest 0 异常；真机案例：pytorch/examples mnist 秒配（子目录入口）；yolov5 二次运行秒配（记忆命中不再探测）。

### P2（打磨，增量）
- P2-1 repo_templates.py 11 族 + classify/match + templates_user.json + 草稿回填按钮 + coverage 度量脚本。
- P2-2 族判定卡 UI（族名/可训练性/依据/data_role 说明）；tune 面板按族默认尾缀（yolov5: batch/imgsz/epochs；CIFAR 族: arch/epochs）。
- P2-3 失败标签→人话映射全量接线（含 2024 yolov5 import ultralytics 漂移提示）。
- 验收：单测覆盖 10 族正反例；真机复跑 kuangliu 类给"需改源码"指引（非自动直跑）。

### 不做清单（明示）
- 不自动回退 git 版本（ref_hint 仅记录提示，后置）；不做 UI 全自动免确认直跑（多候选禁静默）；档案/模板/记忆不存任何数据集 URL 与口令；不自动装 mmdet 系 CUDA wheel（给 registry 配置与指引）；不引新框架/新 UI 组件；不改 DB schema；不删除既有 run 模式手填兜底（永远权威可用）。

执行纪律：每批前跑 pytest 88 基线 + AppTest；bash -n 全步骤既有测试不回退；真机验证用现有三台 AutoDL（密码仅内存注入，禁止入任何文档与提交物）；全部新增文案中文无 emoji。
