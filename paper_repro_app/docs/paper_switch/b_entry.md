复核完成（只读：无写盘工具，本报告以全文形式交付，落盘目标 `docs/paper_switch/entrypoint_audit.md`）。证据基线已核对：`model_discovery.py` 全文、`remote_runner.py` 的 model_step/verify_step/run_step 与降级分支、`database.py` 任务表结构、`repo_crawler.py`、`tests/test_basic.py` 锁点、`docs/acceptance_test/b_pipeline_analysis.md` 既有 P1 结论。以下为审计+规范。

---

# 审计：模型入口识别从"顶层 5 文件"扩展到"大多数论文仓库"

## 决策

**1）现状规则清单与盲区（证据：model_discovery.py L15-31、remote_runner.py L565-568/L594-608）**
现行规则共 6 条，全部命中即单点产出，无候选、无评分、无置信度：
- R1 云端候选白名单仅 `train.py/tools/train.py/scripts/train.py`（L15-16），首个命中 `--help` 退出码 0 且文本含 `--data`（L24-26）即 break 采纳（L29），否则给"请填 README 训练命令"提示（L30-31）。
- R2 runner 内另有两处独立白名单 `train.py detect.py predict.py main.py app.py`（L566-568 降级安全检查、L594-596 safe 模式），仅扫仓库根目录、取第一个存在者，且完全不看参数面。
- R3 命中后命令形态固定 `python <相对路径> --data "${PAPER_REPRO_DATA_CONFIG}"`（L28），经 `.paper_repro_model.env` 与 base64 载荷回传（L33、L43-52），run 步骤环境变量替换后整串 `shlex.quote` 走 `bash -c`（remote_runner.py L547-581）。
- R4 识别与执行在同一流水线内一次完成：识别结果只在本次 run 步骤消费，**不回写 DB、不回填 UI、不跨任务复用**（⑦ 缺位）。

盲区直接对应六个活案例：① `trainer.py`（akamaster）与 ② 子目录入口（pytorch/examples/mnist/main.py）被 R1/R2 白名单整体漏掉；② chenyaofo 类 hubconf-only 仓库现行只会落到"手填命令"泛提示，无法给出"这是模型库非训练实现"的定性；③ 变体名（trainer/run/pretrain/finetune/training/demo）无规则；④ 多入口（train.py 与 main.py 并存、多子项目各带 main.py）无主次仲裁——R2 取第一个字母序，命中非训练用 app.py 会误判；⑤ 评分全缺：无语义权重（train.py 与 app.py 同权）、无目录深度惩罚、无 README/import 佐证、无 argparse 面大小比较；⑥ 参数形态只看"是否含 --data"这一个字面串，kuangliu（无 argparse、注释改模型）与 yolov5 2024（`--batch-size` 而非 `--batch`）都无法得到"可注入参数表"。

**2）扩展方案：云端扫描 → 语义评分 → Top3 候选（不是单点猜测）**
分两阶段，均在现有"云端标准库自包含脚本 + 本地纯函数"架构内完成，不引新框架：
- 云端扫描：`find . -maxdepth 3 -type f -name '*.py'` 限深 3；候选集合 = ①固定名族 `{train, trainer, training, pretrain, finetune, run, main, demo, app, detect, predict}` 全层级命中；② 文件名含 train 语义的任意 .py（截前 5 个）；③ `hubconf.py`、`setup.py` 单独标记。返回每条 `rel_path/depth/size`，加 README 前 200 行中命中"python <该路径>"的行作佐证原文。
- 语义评分（本地纯函数，可单测）：文件名权重 `train>trainer≈training>main>run>pretrain/finetune>demo/app`；目录层级惩罚 depth0 为 0、depth1 扣 2、depth2 扣 4；README 出现该路径或 import 链佐证加 3；无执行面则整体降档。多入口先按权重排序、同权看层级与佐证，产出 Top3。
- 云端 --help 探测只对 Top3 执行（每候选 15s 超时、非零退出不判死），解析 argparse usage 文本得参数名集合，映射受控键白名单 `{epochs, batch, batch-size, data, data-dir, dataset, arch, imgsz, weights}`，仅报告 --help 实际证实存在的键，供 tune 面板/自动注入用（覆盖 yolov5 2024 形态与 akamaster `--arch` 形态）。
- 载荷输出 `{entrypoint, cwd_rel, auto_command, candidates:[{id,rel_path,score,conf,help_args}], mode, reason}`，`mode ∈ {OK, MULTI_MONOREPO, MODEL_ZOO, NO_ARGPARSE, NONE}`；旧键 `entrypoint/auto_command/reason` 保留，新键全部可选，`extract_payload` 兼容旧格式（对齐既有向后兼容惯例）。

**3）特殊形态判定与用户指引**
- 模型库：检测到 `hubconf.py` 且其中只有 `def load_*(...)`/`entrypoints`、无 `def train/main`，全树又无训练名族命中 → `MODEL_ZOO`，reason 明确写"该仓库是模型库（hubconf.py 仅提供 load），无训练脚本，不是论文的完整实现；请换用论文官方训练仓库，或在自定义命令模式填写训练命令"。不能再给泛化"填 README 命令"。
- monorepo：Top1 的 `depth≥1` 即判定；`auto_command` 生成 `cd <子目录> && python <文件名>` 形态——因 run 步骤把 env 变量整串 `shlex.quote` 后经 `bash -c` 执行、tune_args 追加在串尾（remote_runner.py L547-551），该形态天然兼容且追加参数恰好落在 python 命令之后，无需改 runner 拼接。
- NO_ARGPARSE：`--help` 非零或输出无 `-`/`--` 选项 → 判定"模型选择/超参写死在代码或注释（如 kuangliu 改 cfg 注释）"，标记该候选"需改代码训练，不建议"，理由一并给出；UI 指引转向：换带 argparse 的官方训练仓库，或 run 模式手填。

**4）识别结果落点与"秒配"记忆**
- 载荷随 result 落库（`database.py` log 列现即含完整 step stdout），成功面板与历史任务详情"重新配置"区新增展示：候选 Top3（radio 选择）→ 一键写入 run 模式 `run_command` 预填；`MODEL_ZOO/NO_ARGPARSE/NONE` 模式给指引文案而非空表单。
- 秒配（⑦）：新增 `~/.paper_repro_app/entry_memory.json`（`LocalConfigStore` 同目录，沿用 config_store.py 模式，不含口令）；键为 repo_url 归一化（去 .git/尾斜杠/大小写），值 `{entrypoint, auto_command, run_command, data_config, mode, source_task, ts, host}`，仅 `status=success` 且本次确实走训练（auto_command 非空或 metrics 非空）的任务回写。auto/tune 提交前本地查表：同仓库命中则预填并标注"已匹配上次成功配置（任务 xxx，日期/机器）"；换参数/换机只更新 task 侧字段，记忆体命令本身与 host 无关，天然支持换机。

## 可执行变更

1. **model_discovery.py**：`build_remote_script` 改为两段（find 扫描+README 佐证 → Top3 --help 探测），新增模式判定与 Top3 载荷；`reason` 文案按 mode 分四档（上面第 3 节原文）；保留 `result_marker`、`env_file_name`、`PAPER_REPRO_AUTO_RUN_COMMAND` 契约（tests/test_basic.py L399-411、L607-620 锁点不动）。
2. **remote_runner.py**：
   - run_step 内部两条降级/safe ENTRYPOINT 白名单（L565-568、L594-596）改为"优先读 model 载荷 entrypoint（含 `cwd_rel`），否则扩展名族表"；
   - `auto_command` 支持 `cd` 前缀形态（拼接逻辑不变，因 env 整串经 `bash -c` 执行）；
   - run 步骤真实执行且成功时（`PAPER_REPRO_AUTO_RUN_COMMAND` 已解析或 configured_run_command 非空），execute 返回结果携带 `entry_used` 供记忆回写。
3. **新增本地纯函数模块 `entry_rank.py`**（不引框架）：命名权重表、深度惩罚、README 佐证、--help 参数面解析、Top3+置信度；置信度 = 权重归一 × (1−depth×0.1)，`OK` 且 Top1 命中 argparse 可注入时 ≥0.8。
4. **app.py**：
   - 提交区：auto/tune 前查 `entry_memory.json`，命中同 repo 则预填 data_config/run_command 并标注来源任务；
   - 历史记录与监控详情"重新配置"区：展示 Top3 候选（radio）与 mode 判定卡；run 模式下 text_area 增加 `value=` 预填（现 L744-751 为空串），注意控件 key 唯一以守住 AppTest 0 异常；
   - `MODEL_ZOO/NO_ARGPARSE` 在模式选择处给出上节指引文案（不弹空命令框）。
5. **记忆体落点**：`~/.paper_repro_app/entry_memory.json`（config_store.py 同构，0600 权限，仅存仓库→命令映射，无任何密码）；DB 不新增列，source_task 关联回 `database.py` tasks 表既有字段。
6. **测试**：新增 8-10 条纯函数/组装测试——命名族+深度惩罚排序、Top3 载荷解析兼容旧键、monorepo 命令形态 `cd mnist && python main.py`、MODEL_ZOO 判定与文案、NO_ARGPARSE 判定、--help 文本参数表解析、entry_memory 读写幂等、runner 降级入口表含 trainer.py；pytest 基线 88 → 96± 全绿，AppTest 0 异常，`bash -n` 全步骤既有测试不回退。

**合并结论**：方向正确且与现有架构（自包含云端脚本、extract_payload、DB 任务历史、config 目录）完全兼容。建议实施顺序为变更 1→3→2→6（先纯函数与载荷，后 runner/UI），每步跑通 88 基线再前进；无 P0 阻塞项。注：本审计未发现需改口令处理路径，且不涉及明文凭据落盘；`docs/paper_switch/` 目前不存在，需由具备写盘权限的会话按本文落盘。