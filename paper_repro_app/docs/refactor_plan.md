# 专家组裁决：模块化重构蓝图（定稿）

> 路径：`C:/Users/27779/Desktop/industrial-vision-repro/paper_repro_app`
> 基线：pytest 60 passed · 包内 26 模块 MI=A · app.py 与 remote_runner.py 为唯一 MI=C 瓶颈
> 输入：review_lead_plan.md（领导任务书）+ review_static_metrics.md（量化）已就绪；
>       review_quality_security.md / review_architecture.md / review_testing.md 生成中/缺失，
>       本裁决已就其关键维度做第一手快速核查补齐（标注 [复核]），后续复审阶段可对照补全。

---

## 0. 裁决结论（一句话）

**本轮范围 = P0 修复 + P1 纯逻辑外迁 + P2 可测性补强**；P3（render 拆 views / runner 巨型方法拆解）进入路线图，不在本轮动 UI 结构。

硬约束（全体实施者必须遵守）：
1. 不改业务行为与用户可见文案：无 emoji、不重排界面、不换语义；主题/文案改动必须等价。
2. 保持可打包分发：`.venv`/数据/日志不入包；`start_app.*`/`make_dist.py`/`.streamlit/config.toml` 结构不动。
3. 迁出函数后 app.py 一律 `from <新模块> import ...` 改引，**不留双实现**。
4. 任何 remote_runner / dataset / model / helper 命令改动，必须通过 tests 中 bash -n 校验；`_url_ds_helper.py`/`_split_helper.py` 改动后重新生成 b64 且保留顶层源可读。
5. 不新增运行时依赖（ruff/radon 仅分析工具）。
6. 每阶段结束 `./.venv/Scripts/python.exe -m pytest tests/ -q` 全绿。

---

## 1. 目标结构（依赖方向自上而下，禁止反向 import streamlit 到领域层）

```text
app.py(编排：render_app + 3 tabs + 提交链路)          # 允许 import streamlit，只 import 不做实现
   ▼
paper_repro_app/
├── ssh_utils.py        # 迁自 app.py 纯 SSH/密钥逻辑（约 281 行）
├── task_utils.py       # 迁自 app.py：步骤序/估算/状态色/日志预览/读取/本机 IP（约 68 行）
├── storage_utils.py    # 迁自 app.py：目录树/产物落盘/repo 解析/远程目录/exec 状态/线程启动（约 95 行）
├── paths.py / config.py / config_store.py / database.py / logging_*   # 基础设施（现状不变）
├── remote_runner.py / dataset_discovery.py / model_discovery.py / repo_crawler.py / paper_parser.py
├── weather_fx.py / ui_theme.py
└── scripts/  # 云端 helper 顶层源（_url_ds_helper.py / _split_helper.py 保留可读）
```
- 依赖方向：`app.py → ssh/task/storage_utils → 基础设施`；ssh/task/storage_utils **零 streamlit 导入**（pytest 可直接测）。
- `views/`（header/submit/monitor/history/tune，允许 st）→ P3 后置，本轮不建。

---

## 2. 阶段实施步骤（含验收）

### P0-修复（先做）
| # | 事项 | 修法 | 验收 |
|---|---|---|---|
| P0-1 | 3.11 语法兼容（导入即崩，升 P0）[复核] | remote_runner.py:347 f-string 内反斜杠（PEP701，仅 3.12+）。把条件表达式提出 f-string 为普通变量拼接，f-string 内不再含反斜杠双引号 | python3.11 可编译（无 3.11 则以静态审读确认无 f-string 反斜杠）；bash -n 用例仍绿 |
| P0-2 | detect_ssh_auth_sources 重复定义去重 [复核] | remote_runner.py:122 与 626 两份，保留完整一份、删除另一份；先比对差异合并 | grep 仅 1 处定义；pytest 绿 |
| P0-3 | 密码防日志护栏 | 审计确认结果/日志不含 cloud_password 明文；加注释防回归 | grep password 无日志输出 |

### P1-纯逻辑外迁（低风险机械迁移）
| 步 | 新模块 | 迁入函数 | 验收 |
|---|---|---|---|
| P1-1 | ssh_utils.py | parse_ssh_target / resolve_ssh_profile / parse_ssh_config / get_ssh_config_path / write_ssh_profile / render_ssh_config_block / ensure_ssh_key_file / ensure_default_ssh_keypair / test_ssh_connection | app.py 改 import；新增 tests/test_ssh_utils.py |
| P1-2 | task_utils.py | get_step_order / estimate_completion / get_status_color / format_log_preview / read_log_tail / get_local_ips | 新增单测 |
| P1-3 | storage_utils.py | ensure_local_storage_tree / persist_task_artifacts / resolve_repo_url / detect_remote_workdir(唯一实现) / _get_exec_state / start_pipeline_execution | 新增单测 |
| P1-4 | 冗余清理 | app.py:1058 死代码 artifact_store；F841 未用 storage_layout(874/1376)；F401 未用 import（app.py:32 等） | 行为等价 |

> 每步结束：pytest 绿 + AppTest 冒烟（render_app 0 异常 + 3 tabs 仍在）。

### P2-可测性补强
| # | 事项 |
|---|---|
| P2-1 | 迁出模块单测（ssh/task/storage_utils） |
| P2-2 | DB 迁移完整性：v6→v7→v8 全链路用例（列存在 + 数据保留） |
| P2-3 | 远程命令注入：恶意 repo 名/URL（`;rm -rf`/空格/中文）→ detect_remote_workdir/shlex 安全 + bash -n 通过 |

### P3（路线图，本轮不做）
- render_app(111)/execute(58)/_render_monitor_content(55) 三个 F 级函数拆分 → views/ 与 runner 方法拆解。
- 远程脚本段抽 `_scripts.py` 常量 + 语法单测锁定（收敛 conda 引导与数据集下载器两处重复块）。
- 验收门槛：新函数圈复杂度 <= C；MI 不降级；ruff/radon 入门禁。

---

## 3. 快速审计补充（补缺失评审维度）
- 安全面：P0-3 已过；SSH 密钥不写仓库、数据在家目录护栏保持；后台线程 daemon 保持。
- 架构面：除三模块外迁，可顺手把 _render_monitor_content 成功/失败/运行三分支抽 3 个渲染小函数（可选低风险，实施者可做可不做并记 deviation）。
- 测试面：先验 60 绿；P1 每模块配新单测为硬验收。

---

## 4. 实施与复审指令
- 实施：按 P0 → P1-1..4 → P2 顺序执行，写 docs/refactor_impl_report.md（改动清单/新结构/pytest/AppTest/deviation）。
- 复审：pytest 全绿；抽查 app.py 瘦身且职责等价、ssh/task/storage_utils 无 st 依赖、无 emoji、无硬编码绝对路径、打包结构未动 → docs/refactor_review.md。
- 终审：读 impl+review → docs/code_quality_report.md（A–E 评级、路线图、5 条建议）。

## 5. 阶段清单（摘要用）
1. P0：3.11 语法兼容 + ssh_auth 去重 + 密码防日志注释
2. P1：ssh_utils → task_utils → storage_utils 外迁（每步 pytest+AppTest 绿）
3. P1-4：死代码/未用 import/未用赋值清理（行为等价）
4. P2：三模块单测 + DB 迁移完整性 + 命令注入用例
5. P3（路线图）：render/execute 拆分、_scripts.py 收敛重复段、ruff/radon 入门禁
