# 专家评审任务书与模块化目标（Team Lead 初稿）

> 项目：Paper Repro Runner（Streamlit 论文复现控制台）
> 路径：`C:/Users/27779/Desktop/industrial-vision-repro/paper_repro_app`
> 基线：pytest 60 passed · 代码约 6600 行（含 tests）· git 仓库 · 可打包分发（make_dist）
> 本文件是专家组工作的总纲：任务书 + 模块化目标 + 分工验收 + 风险禁忌。评审与实施均以此为约束。

---

## 1. 现状诊断

### 1.1 模块地图（当前结构，已相对健康）

| 层 | 模块 | 状态 |
|---|---|---|
| 基础设施 | `paths.py`(数据归 ~/.paper_repro_app)、`config.py/config_store.py`、`logger_utils/logging_config`、`database.py`(SQLite 自动迁移 v8) | 已模块化，依赖方向清晰 |
| 领域/云端 | `remote_runner.py`、`dataset_discovery.py`、`model_discovery.py`、`repo_crawler.py`、`paper_parser.py`、`remote_workdir.py`、`_url_ds_helper.py`/`_split_helper.py`(b64 内嵌云端脚本) | 已拆包；无 streamlit 依赖 |
| 分析/产物 | `artifacts.py`、`innovation_analysis.py`、`report_generator.py`、`project_summary.py`、`comparison_table.py`、`diagnostics.py`、`log_analyzer.py` | 已拆包 |
| UI 主题 | `ui_theme.py`(CSS+HTML builder)、`weather_fx.py` | 纯模块（0 个 st 依赖），健康 |
| 测试 | `tests/test_basic.py`、`test_ui_weather.py`、`test_portability.py` | 60 项覆盖 runner/bash 语法/DB 迁移/UI builder/可移植性 |
| 门户 | `app.py`（约 1476 行） | 唯一"大件"（最大改进点） |

### 1.2 健康面（值得肯定，重构勿破坏）
- 已做过多轮工程化：数据全归家目录、conda 环境智能落盘、GPU torch 保护、数据集 URL 直链+自动划分、天气物理粒子、赛博玻璃 UI、后台线程+fragment 局部刷新、bash 落盘执行（规避截断）、每步 bash 语法在单测中被校验。
- `ui_theme.py`/`weather_fx.py`/`remote_runner.py`/`database.py` 均无 streamlit 导入，可独立单测。
- 主题 builder 与 HTML 类名稳定，测试覆盖构建函数。

### 1.3 主要问题面（按严重度）

**A. app.py 单体偏大且职责混杂（最大改进点）**
- 约 1476 行同时承载：页面编排（`render_app` 内含 tab_submit/tab_monitor/tab_history 三块大 UI）、领域纯逻辑（SSH 解析/密钥生成/SSH profile 读写/目录树推导/估算）、后台线程编排、天气 UI、HUD 水印等。
- `render_app` 整体很长（1020→1453），内部 3 个 tab 区块各 100-300 行，表单与提交逻辑（爬虫/校验/建任务/启动）耦合在 UI 回调序列中，难以单独测试与演进。
- 因 `app.py` 顶层 `import streamlit as st`，其内大量纯函数无法被普通 pytest 直接导入测试（需 AppTest 或 mock st），单元可测性下降。

**B. remote_runner 巨型方法与重复定义**
- `build_pipeline` 约 165→615（约 450 行）内嵌十余段 bash/python 字符串，虽已部分抽 helper（dep_scan、数据集、模型、collect），但单方法过长；`execute` 669→900 也偏长。
- 明确问题：`detect_ssh_auth_sources` 在 122 与 626 被定义两次（后者覆盖前者）——重复代码 + 维护陷阱，应去重。
- 云端脚本 b64 内嵌（`_url_ds_helper.py`/`_split_helper.py`）是自包含上传的必要手段；建议：源文件保留顶层可读、生成时 b64，并加"b64 与源码漂移"自动化校验。

**C. 后台任务与生命周期**
- `_EXEC_STATE` 全局 dict + 线程；应用重启后 running 悬挂已有 UI 提示（"线程不在运行"与重跑按钮）——已缓解。剩余风险：多任务并发策略为"新任务中止旧任务"，同目录多操作存在竞态可能（DB 串行写，可接受）。

**D. 测试盲区**
- app.py 内部纯函数（SSH profile、路径、目录树、估算、表单参数→task 装配）无直接单测（受 st 导入阻碍）。
- 已有：bash 语法/DB 迁移/UI builder/可移植性；缺：迁移数据完整性细节用例、远程命令注入（恶意仓库名/URL sanitize）用例、`detect_ssh_auth_sources` 正确性用例。

### 1.4 环境与基线事实
- venv `.venv`；运行入口 `app.py`；`scripts/e2e_task.py` 端到端驱动；`make_dist.py` 打包。
- UI 约束：深色玻璃赛博主题、无 emoji、用户可见文案不改（纯重构等价）；可打包结构（.venv/数据/日志不入 zip）。

---

## 2. 模块化目标架构（蓝图层）

### 2.1 目标：让 `app.py` 变成"可读的编排层"，业务可测

新增/巩固 4 个内聚模块（放 `paper_repro_app/` 包内，优先保持无 streamlit 依赖）：

```text
paper_repro_app/
├── ssh_utils.py          # 迁自 app.py：parse_ssh_target/parse_ssh_config/resolve_ssh_profile/
│                         #   ensure_ssh_key_file/ensure_default_ssh_keypair/write_ssh_profile/
│                         #   render_ssh_config_block/test_ssh_connection/inject_public_key
│                         #   （纯领域 + paramiko；不 import streamlit）
├── local_fs.py           # 迁自 app.py：ensure_local_storage_tree/persist_task_artifacts/get_local_ips
│                         #   （纯路径/IO 逻辑；open_directory_dialog 可留 UI 薄壳）
├── tasks_service.py      # 迁自 app.py：get_step_order/estimate_completion/apply_task_state/
│                         #   start_pipeline_execution + _EXEC_STATE 封装成 Executor 小类
│                         #   （含线程登记与活性检查；不 import streamlit）
└── views/                # （后置可选）render_app 拆 views：header/submit_tab/monitor_tab/
                          #   history_tab/tune_panel，允许 import streamlit，由 app.py 组装
```

- 依赖方向：`app.py(编排) → views → service/领域 → 基础设施`；`ssh_utils/local_fs/tasks_service` 禁止 import streamlit（保证可单测）；`remote_runner/...` 保持现状不再向上依赖。
- 纯函数外迁优先级：先迁不依赖 st.*、无副作用的纯逻辑（SSH 解析/路径/profile/估算/步骤序），即插即走，pytest 直接可测；`_EXEC_STATE`+线程封装为 `TaskExecutor` 小类后仍被 app.py 调用。
- render 拆分（后置、分批低风险）：先抽 `_render_*` 大函数体保持等义，再逐步迁 views；每步 pytest + AppTest 冒烟。

### 2.2 分阶段实施

| 阶段 | 范围 | 验收 |
|---|---|---|
| P0 修复 | `detect_ssh_auth_sources` 重复定义去重；评审 A 列出的 P0 隐患 | pytest 绿 + 清单勾销 |
| P1 纯逻辑外迁 | 新建 ssh_utils.py / local_fs.py / tasks_service.py，从 app.py 剪切纯函数并改 import（不改行为） | 新增单测覆盖迁出函数；pytest 绿；AppTest 冒烟 UI 不变 |
| P2 可测性补强 | 迁出模块单测；database 迁移完整性；远程命令注入/sanitize 用例 | 单测通过、覆盖率明显上升 |
| P3（后置评估） | render_app 拆 views；remote_runner build_pipeline/execute 拆方法 | 时间允许再纳入，默认进路线图 |

### 2.3 分工验收标准

| 角色 | 交付 | 验收线 |
|---|---|---|
| A 质量与安全 | P0 清单（文件:行+原因+修法） | 全部可行动、无明显遗漏 |
| B 架构 | 模块化拆分清单（迁哪/依赖方向/风险） | 与 2.1 一致，指出可安全先做的纯函数 |
| C 测试 | 补测建议（优先级+理由） | 聚焦迁出函数与盲区 |
| D 静态 | 复杂度 top10/重复块/可切分函数名单 | 数据可复核（文件:行） |
| 实施 | 按定稿蓝图 P0-P2 | pytest 绿；改动记录含 deviation |
| 复审 | 抽查回归 | pytest 绿 + 无越界改动 |

---

## 3. 风险与禁忌（硬约束，全体遵守）

1. 不改业务行为与用户可见文案：无 emoji、不重排界面、不换语义；主题/文案改动必须等价（纯重构）。
2. 保持可打包分发：.venv/数据/日志不入包；start_app.py/.bat、make_dist.py、.streamlit/config.toml 结构不动。
3. app.py 迁出函数保持导入等价：不留"双实现"（detect_remote_workdir 只留一处；434 兼容委托可后续清理）。
4. 远程命令字符串高危：任何 remote_runner/dataset/model 命令改动必须以 tests 中 bash -n 校验为准；改 `_url_ds_helper.py`/`_split_helper.py` 须重新生成 b64 并保留顶层源可读。
5. 线程/DB：后台线程保持 daemon + 落库 + 活性提示；SQLite 用 store 封装，勿并发裸写。
6. 不引入新外部运行时依赖（ruff/radon 仅作分析工具，不写进 requirements）。
7. 每阶段结束跑 `./.venv/Scripts/python.exe -m pytest tests/ -q`。

---

## 4. 下一步

- 四份专家评审并行产出：`review_quality_security.md` / `review_architecture.md` / `review_testing.md` / `review_static_metrics.md`。
- 领导裁决定稿 `refactor_plan.md`（含最终阶段裁剪与本轮范围）。
- 实施产出 `refactor_impl_report.md`；终审产出 `code_quality_report.md`（评级 + 路线图 + 5 条建议）。
