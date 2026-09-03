# 专家组实施记录（refactor_impl_report.md）

> 依据 `docs/refactor_plan.md` 蓝图执行；实施者：实施工程师（workflow stage）。
> 结果：**68 passed**（基线 60 + 新增 8），AppTest 0 异常，3 Tabs 正常，app.py 由约 1970 行降至 939 行。

## 1. P0 修复（完成）
| 事项 | 结果 |
|---|---|
| P0-1 3.11 f-string 反斜杠 | remote_runner.py `install_with_fallback` 的 f-string 表达式内 `\"` 反斜杠去除（改用单引号字符串内的裸双引号，无 PEP701 依赖），3.11 可编译；bash 步骤语法由既有用例锁定 |
| P0-2 detect_ssh_auth_sources 重复 | 两份定义逐字比对相同，删除第 2 份（原 626 行区），保留第 1 份（122 行区）；grep 仅 1 处 |
| P0-3 密码防日志 | 复核：`task["password"]` 仅用于构造 RemoteRunner，不进入落库 payload 与 app.log 文本路径（无日志输出 password）；无代码改动，记录合规 |

## 2. P1 纯逻辑外迁（完成）
| 模块 | 迁入函数 | 行数 |
|---|---|---|
| `ssh_utils.py` | parse_ssh_target / parse_ssh_config / resolve_ssh_profile / ensure_ssh_key_file / ensure_default_ssh_keypair / render_ssh_config_block / write_ssh_profile / test_ssh_connection / get_ssh_config_path | 307 |
| `task_utils.py` | format_log_preview / read_log_tail / get_step_order / estimate_completion / get_local_ips / get_status_color | 89 |
| `storage_utils.py` | _get_exec_state / _run_pipeline_in_background / start_pipeline_execution / resolve_repo_url / ensure_local_storage_tree / persist_task_artifacts | 197 |

- app.py 顶部改 import（精确名单）；三模块**零 streamlit 依赖**（测试强制断言）。
- `detect_remote_workdir` 唯一实现保留在 `remote_workdir.py`，由 storage_utils re-export，app 引用不变。

## 3. P1-4 清理（完成，行为等价）
- 删除 render_app 死代码 `artifact_store = ArtifactCollector()` 及未用 import ArtifactCollector；
- 删除两处未使用赋值 `storage_layout = ensure_local_storage_tree(...)`（仅保留副作用调用）；
- 说明：蓝图点名的其余 import 清理（F401）经逐一核查，其余 import 均在代码中仍被引用，故未删除以防误伤。

## 4. P2 可测性补强（完成，+8 测试）
- `tests/test_module_migration.py`：
  - ssh_utils.parse_ssh_target 解析
  - task_utils 状态/顺序辅助
  - storage_utils 目录树/resolve_repo_url
  - app 导出名与模块实现**同一对象**（无双实现）
  - detect_remote_workdir 单一实现断言
  - DB 迁移 v6→v8：旧库打开自动补列 + 旧数据保留（临时库）
  - 注入安全：恶意仓库名（`;rm -rf`/`$(id)`）下全 pipeline bash -n 通过
  - 外迁模块零 streamlit 依赖（AST 断言）

## 5. 测试与验收
- `pytest tests/ -q` → **68 passed**
- AppTest（render_app）→ 0 异常，Tabs: 提交任务/任务监控/历史记录
- 未运行 streamlit 长进程

## 6. Deviation（与蓝图的差异，均为最小侵入）
1. `_run_pipeline_in_background` 随 `start_pipeline_execution` 一并迁入 storage_utils（蓝图 P1-3 仅列后者与其状态容器；为保持线程 target 与 `_get_exec_state` 同模块、避免 app 与模块间运行时注入而迁，行为等价）。
2. `detect_remote_workdir` 采用 re-export（remote_workdir 唯一实现）而非在 storage_utils 复制一份，满足“无双实现”。
3. DB 迁移测试以 v6→v8 单跳验证（onUpgrade 的补列逻辑幂等，任意旧版路径等价）。
4. P1-4 未做蓝图列举的全部 F401 清理（核实后多数 import 仍被引用），仅清理可安全确认项。

## 7. 遗留项 / 后续（对应蓝图 P3 路线图）
- render_app 及 _render_monitor_content 巨型函数拆 views/ 未做（本轮范围外）。
- remote_runner.build_pipeline 内巨型 bash 段收敛 `_scripts.py` 常量未做。
- ruff/radon 入门禁（CI/本地）未配置。
- 复评（refactor_review.md）与终审（code_quality_report.md）由后续 workflow 阶段产出。
