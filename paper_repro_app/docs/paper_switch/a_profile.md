# 仓库档案与记忆架构设计（repo_profiles 记忆层）

> 目标：同一仓库换参数、换论文再回到旧仓库、换云主机时"秒配"；陌生仓库给清晰指引。档案落于 ~/.paper_repro_app/repo_profiles.json，与任务 DB 双写共存、以 DB 为可重建源。本报告结论先行，分「决策」与「可执行变更」两节。

## 摘要

把"成功过一次"变成"下次免探"：在 ~/.paper_repro_app 增加按规范化仓库 URL 索引的 repo_profiles.json，记录成功任务的入口、实际执行命令、数据配置、环境要点与失败原因标签。提交流程在仓库解析确定后查档并预填，命中即显示"已按上次成功配置预填（时间/主机）"，支持一键清除。DB 仍是唯一史实源，JSON 是它的物化视图（读时合并、可重建）；档案永不写密码与私钥路径，只存认证类型提示。

## 决策

### 决策 1：档案文件与结构

文件：`~/.paper_repo_app/repo_profiles.json`（与 cloud_config.json 同目录，chmod 600，JSON 解析失败则改名 .corrupt 后按空档启动）。顶层含 schema_version、updated_at、profiles 字典。单仓库一条记录（多历史在读取时合并，不重复落多条）：

```
repo_url(规范化键) -> {
  entrypoint      # 上次成功实际入口，仓库根相对路径，如 trainer.py、mnist/main.py
  run_command     # 上次成功实际执行命令（run 模式原文；auto 模式取回传的 auto_command 与 ${PAPER_REPRO_DATA_CONFIG} 占位）
  data_config     # UI data_config 原文；空表示仓库自带数据集逻辑，存哨兵 __repo_managed__
  env_note        # 短句：参数风格/依赖要点，如 "--arch 风格；需 torch+torchvision"
  task_family     # 从 repo/paper 关键词归族：classification/cifar、detection/coco、gan 等
  last_status     # 最近一次尝试终态 success|failed|cancelled
  last_success_at # 最近成功时间（预填正文引用的权威时间）
  last_attempt_at # 最近一次尝试时间
  run_count / success_count
  host_hint       # {"host": "...", "user": "root", "auth_kind": "key|password|agent"}
  fail_reason_tags # 最近失败标签数组（见决策 4 映射），防重蹈
  aliases         # 加速前缀/.git/git@ 变体，命中用
}
```

键规范化规则：去尾部斜杠与 .git、http 统一 https、git@/ssh 转 https、剥掉 ghfast.top 等加速前缀；命中顺序为键精确、别名、owner/name 三段（大小写不敏感），因此换镜像或换加速地址仍能命中同一档案。

读取与合并规则（同 repo 多历史）：以 DB 历史分组聚合，最近一次 success 的记录整体优先作为预填来源；若该 success 之后还有失败尝试（上游改版、换机环境变化），保留成功配置但把 last_status 置 failed 并附 fail_reason_tags，供 UI 黄色警示"最近一次尝试已失败，仍沿用上次成功配置"；无任何 success 的仓库不预填命令，只存失败标签与一句人话建议，防止自动重复踩坑。成功永远优先于失败（更旧的 success 优于更新的失败）。

写时机：后台线程任务终态（success/failed/cancelled）在落库之后同步 upsert——成功记 entrypoint/run_command/data_config/host_hint；失败记标签与一句话建议，绝不覆盖已有的成功快照。写失败只告警不阻塞任务线程。

### 决策 2：提交流程接入（预填与清除）

仓库解析在提交路径上两处：repo_hint 输入即确定（本地可判），或论文经 crawler 排序后才确定。策略分两级：

- 轻量预检：repo_hint 或 saved.repo_hint 变化时立即本地查档（不爬网）；命中后把 run_command、data_config 写入 session_state 命名空间（前缀 rp_<规范键>，杜绝仓库间串值），run 模式文本框与高级选项数据集框直接预填；auto 模式在提交时若用户未手改命令，把档案 run_command 作为实际 run_command 落任务（历史更可回放，runner 零改动）。
- 提交级补命中：crawler 选出的 best_candidate 与用户 hint 不同但命中档案时，提示条提示并按档案静默应用默认值。
- 文案固定为「已按上次成功配置预填：{repo} · {last_success_at} · 主机 {host}」；带失败标签时追加「注意：最近一次尝试失败（原因），可一键清除档案后重新自动识别」。
- 清除：预填条旁「清除此仓库记忆」按钮删除该档案；历史记录页新增"仓库档案管理"折叠区，列出全部档案（repo、入口、命令摘要、成功次数、最近成功），可单删或「从任务历史重建」（调用决策 3 的重建函数）。清除只删 JSON，不删 DB 历史。

### 决策 3：与 DB 任务历史的冗余处理

结论：DB 是唯一事实源（原始史实、审计、可重建），repo_profiles.json 是面向秒配的物化视图/热缓存，不承载 DB 之外的第二事实。执行口径：

- 双写：任务终态先写 DB，再 upsert 档案；档案写失败不影响任务结果。档案独有字段（env_note、task_family、fail_reason_tags、host_hint 摘要）本就是视图性质，允许只存在于 JSON。
- 读时校验：get_for_repo 读到档案后与 DB 该 repo 的最近 success 时间比对，若 DB 更新则按"最近成功优先"规则合并覆写后返回——保证 JSON 陈旧也能自愈，无需人工迁移。
- 迁移：不加 DB 列、不升 TaskStore schema 版本（规避迁移与回归风险）。升级首启或 DB 存在 ≥1 条 success 而档案文件缺失时，由 rebuild_profiles_from_db() 一次性回填；历史页提供手动重建按钮兜底。
- 冲突裁定：同一字段两处不一致一律以 DB 为准（JSON 只是缓存）；清除档案后不因 DB 尚存历史而自动复活（重建是显式动作）。

### 决策 4：敏感边界

档案永不含密码、私钥内容或私钥绝对路径，也不存日志原文。认证只记枚举 auth_kind（key/password/agent）：上次用 key 则本次预填并沿用本地 key 探测链；上次用 password 则提示"该仓库上次为密码认证，请输入当前实例密码"（密码仍走进程内存，符合现有安全策略）。host/user 为 UI 已明文输入内容，仅作提示展示与 host_hint。文件权限 600，损坏文件改名保留、空档启动——与 config_store 同一模式。

## 可执行变更

1. 新增 `paper_repro_app/repo_profiles.py`（零 streamlit 依赖，纯逻辑模块，与 storage_utils 同风格）：`normalize_repo_url/load/save_atomic/get_for_repo/upsert_success/upsert_failure/rebuild_profiles_from_db/list_profiles/remove_profile`。原子写用临时文件 + os.replace，模块级 threading.Lock 防多任务并发写；目录与 DB 一致取 paths.APP_HOME。
2. `storage_utils._run_pipeline_in_background` 终态钩子：success/failed/cancelled 落库后调 upsert；auto 模式 run_command 为空时取 result.model.auto_command 落档案（该字段现已在 execute() 回传，零远端改动即捕获真实命令）。再于 RemoteRunner.run_step 加一行 `echo "PAPER_REPRO_EFFECTIVE_RUN=..."` 输出实际生效命令，供非标准入口捕获。
3. `app.py` 提交区接入：repo_hint 变更回调查档预填 + 文案 + 一键清除；历史记录页档案管理折叠区。全部 UI 用 session_state 独立键与 try 守卫包裹，确保 AppTest 无异常。
4. `repo_crawler.py` 候选列表对命中档案的仓库加"记忆命中"标记并提分（已成功仓库优先于明星分排序）。
5. `model_discovery.py` 入口名单扩展以覆盖真机案例：在既有 train.py/tools/train.py/scripts/train.py 前先试档案 entrypoint（传入环境变量提示）；再补 trainer.py 与一级子目录深探（pytorch/examples 型 mnist/main.py）；hubconf.py 存在且无训练脚本时先判"模型库无训练脚本"并给出换仓指引，而不是走到空命令 exit 65。参数风格探测保持"带 --help 输出中的 --data/--arch 才拼数据参数"，宁缺勿错。
6. 失败标签到人话指引的静态映射（随档案 upsert 使用）：模型库无训练脚本（chenyaofo 型）→"该仓库是模型 zoo，只有 hubconf.py 无训练脚本，不适合直接复现实验，建议换官方训练仓库"；入口非标准（akamaster 型 trainer.py）→"已记住入口 trainer.py，下次自动按此运行"；入口在子目录（pytorch/examples 型）→"入口在 mnist/main.py，已按子目录入口执行"；改代码选模型不可命令行（kuangliu 型）→"该仓库通过改 main.py 注释选模型，不适配自动参数化，请在云端改好 main.py 后用自定义命令运行"；依赖升级漂移（yolov5 2024 import ultralytics 型）→"上游已改 import 依赖，建议换官方仓库或使用上次成功固定版本"。文案全部为操作建议，不抛技术细节。
7. 测试与验收：新增 repo_profiles 单测（规范化/别名命中/合并优先/原子写/损坏文件/并发锁，tmp_path 注入），不改存量断言，pytest 基线 88 全绿且总数增加；AppTest 全页签渲染 0 异常；无新依赖框架。档案写入为纯函数路径，storage_utils 线程内零 streamlit 调用不变。

## Sources（依据代码文件）

- paper_repro_app/database.py（tasks 字段与 status/log 结构）
- paper_repro_app/storage_utils.py（终态线程、persist 时机、model/dataset 回传）
- paper_repro_app/remote_runner.py（10 步流水线、run_step/auto_command、execute 回传 model payload）
- paper_repro_app/model_discovery.py（现状仅认 train.py 系 + --data）
- paper_repro_app/repo_crawler.py（论文到候选排序、best_candidate）
- paper_repro_app/config_store.py 与 paths.py（~/.paper_repro_app 配置模式与 600 权限先例）
- app.py（提交解析、saved 预填、历史页结构）

## Gaps 与建议下一步

- 未落库仓库远端 commit/ref，上游改版导致的档案失效只能靠失败标签提示，无法自动回退旧版本；如后续需要可增 ref_hint 并在 clone 时 checkout（需 remote_runner 配合）。
- auto 首次成功但回传 model payload 为空（非标准入口侥幸成功）的捕获依赖新增 echo 行，属远端脚本变更，需在 AppTest 覆盖的集成用例中回归。
- 论文换新仓库（无档案）时仍走现有探测链，本方案只保证失败指引更清晰，真正的"全自动适配"依赖第 5 项发现增强的逐步落地，建议按 6 项变更分批实施、每批回归 88 基线。
