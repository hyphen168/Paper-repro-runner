# 静态分析量化报告 —— Paper Repro Runner

> 专家组之「静态分析与量化专家」测量产出。
> 范围：`app.py` + `paper_repro_app/` 包 + `scripts/` + `tests/`（约 7134 行，pytest 60 passed 基线）。
> 工具：ruff 0.16.6（E/F/B）、radon 6.0.1（cc 圈复杂度 / mi 维护性指数）；pip 安装成功。
> 测量只读，未改任何业务代码。

---

## 1. 环境与命令

| 项目 | 值 |
|---|---|
| 运行时 Python | 3.12.7（.venv） |
| 安装工具 | `.venv\Scripts\python -m pip install ruff radon` ✅ |
| ruff | 0.16.6 |
| radon | 6.0.1 |
| ruff 检查 | `--select E,F,B`（E501 行长已单独计数） |

---

## 2. 文件级量化总表

| 文件 | 行数 | 函数数 | 类数 | 最长函数(行) | MI 级 |
|---|---|---|---|---|---|
| app.py | 1477 | 38 | 0 | 432 (`render_app`) | **C** |
| remote_runner.py | 998 | 12 | 2 | 449 | **C** |
| ui_theme.py | 610 | 2 | 0 | 32 | A |
| weather_fx.py | 600 | 8 | 0 | 22 | A |
| dataset_discovery.py | 203 | 3 | 1 | 135 | A |
| database.py | 186 | 14 | 2 | 41 | A |
| repo_crawler.py | 172 | 5 | 1 | 54 | A |
| innovation_analysis.py | 182 | 9 | 1 | 66 | A |
| 其余包内文件（22 个） | ≤148 | — | — | — | A |
| scripts/e2e_task.py | 132 | 4 | 0 | — | A |

**要点**：体量与复杂度集中在 `app.py` + `remote_runner.py` 两个文件（合计约 2475 行，全仓约 35%），是唯二 MI=C 的文件，重构主战场。

---

## 3. 圈复杂度 Top（radon cc，阈值 >15 命中）

| 排名 | 位置 | 函数 | 复杂度 | 等级 |
|---|---|---|---|---|
| 1 | app.py:1020 | `render_app` | **111** | F |
| 2 | remote_runner.py:669 | `RemoteRunner.execute` | **58** | F |
| 3 | app.py:868 | `_render_monitor_content` | **55** | F |
| 4 | app.py:264 | `parse_ssh_config` | 31 | E |
| 5 | app.py:198 | `parse_ssh_target` | 29 | D |
| 6 | innovation_analysis.py:92 | `PaperInnovationAnalyzer.analyze` | 28 | D |
| 7 | app.py:451 | `test_ssh_connection` | 26 | D |
| 8 | remote_runner.py:165 | `RemoteRunner.build_pipeline` | 25 | D |
| 9 | remote_runner.py:925 | `inject_public_key` | 24 | D |
| 10 | log_analyzer.py:62 | `LogAnalyzer.analyze_log` | 19 | C |
| 11 | app.py:798 | `_build_tune_args` | 19 | C |
| 12 | app.py:323 | `resolve_ssh_profile` | 14 | C |

> `render_app`(111) + `execute`(58) + `_render_monitor_content`(55) 三者即占全仓约 40% 分支复杂度——任何改动这三处都高风险，是模块化拆分的第一对象。

---

## 4. ruff 问题分级（E/F/B，除 E501）

### 4.1 总量
| 代码 | 数量 | 含义 |
|---|---|---|
| E501 | 629 | 行长 >88（多为超长字符串/bash 脚本，风格噪音） |
| **F821** | 21 | 未定义名（含 21 处 `_url_ds_helper.py` **设计性误报**） |
| E402 | 14 | import 未置顶 |
| F401 | 13 | 未使用 import |
| E701 | 10 | 一行多语句 |
| F841 | 8 | 赋值未使用 |
| B904/B905/B005/B007 | 6 | raise from / except 细节 |
| F811 | 1 | 重复定义 |

### 4.2 F821 判定
`_url_ds_helper.py` 全部 21 处 F821（`requested/root/load_candidate/shutil/...`）**为预期**：该文件是云端 `.dep_dataset.py` 的 exec 片段，命名空间由宿主注入（文件头有注释说明）。建议：保留并加 `# noqa: F821` 或标注"exec-snippet"，**不是缺陷**。

### 4.3 F841（真实冗余）
- app.py:1058 `artifact_store = ArtifactCollector()` —— 赋值后未使用（疑似死代码，原用途被 `_run_pipeline_in_background` 内部实例取代）
- app.py:874 / 1376 `storage_layout` 赋值未使用
- app.py:1201/1203/1205 `split_train/val/test` —— st.number_input 返回值未使用（值通过 session_state 读取，属可清理但功能正常）
- log_analyzer.py:86 `stdout_log` 未使用

### 4.4 F401（可清理）
- app.py:32 `_is_auth_exception` import 未用
- innovation_analysis.py:6 `Iterable/Set`；logging_config.py:4 `os`；paper_parser.py:5 `urlparse`；dataset_discovery.py:35 `base64`

---

## 5. 🔴 兼容性缺陷（P1，ruff 语法级发现）

**remote_runner.py:347** f-string 内使用反斜杠转义 `\"` 与内嵌同引号——这是 **PEP 701（Python 3.12+）** 语法；在 **Python 3.11/3.10 下解析即 SyntaxError**：

```python
f"{('for idx in \"' + configured_pip_index + '\" \"https://...' if configured_pip_index else 'for idx in \"https://...' ...)}"
```

项目 `pyproject.toml` 声明 `requires-python >=3.10`，`start_app.py` 引导要求 Python 3.11+。**用户若以 3.11 运行，导入 remote_runner 直接崩**（3.12.7 本地通过故测试未暴露）。
**修复建议（最小侵入）**：把条件表达式提到 f-string 外成为普通变量拼接，或改用 `chr(34)` / 单引号包裹内容，避免 f-string 表达式内出现反斜杠。

---

## 6. app.py 可安全机械切分候选（纯函数优先）

AST 判定：不引用 `st.*`、不引用模块级可变全局（`DATA_DB_PATH` 等）。**23 个纯函数约 550 行**，可整体迁往新模块，仅 `from app import ...` 迁移导入，无 st 依赖零 UI 风险：

### 建议新模块（依赖方向 app.py → 新模块）
| 建议模块 | 迁移函数（行数） |
|---|---|
| `ssh_utils.py`（SSH 配置/测试/密钥，纯逻辑） | `parse_ssh_target`(50) · `resolve_ssh_profile`(13) · `parse_ssh_config`(57) · `write_ssh_profile`(23) · `get_ssh_config_path`(2) · `render_ssh_config_block`(17) · `ensure_ssh_key_file`(18) · `ensure_default_ssh_keypair`(30) · `test_ssh_connection`(71) → ≈281 行 |
| `task_utils.py`（任务/进度纯逻辑） | `get_step_order`(2) · `estimate_completion`(17) · `get_status_color`(9) · `format_log_preview`(15) · `read_log_tail`(13) · `get_local_ips`(12) → ≈68 行 |
| `storage_utils.py`（本地目录） | `ensure_local_storage_tree`(18) · `persist_task_artifacts`(33) · `resolve_repo_url`(8) · `detect_remote_workdir`(3) · `open_directory_dialog`(10) · `_get_exec_state`(6) · `start_pipeline_execution`(17) → ≈95 行 |

> `main`(21)、`on_step`(5) 视拆分粒度决定是否保留；`render_*`/`_tune_*`/`live_monitor` 等 15 个函数（约 900 行）依赖 `st.*`，需与 UI 层同迁或重构回调，本轮不建议动。

### 可安全降复杂度的同文件抽取
- `render_app`(111) 内可先抽纯 HTML/markdown 片段构造函数（如天气胶囊、HUD 装饰块），将 render_app 降至 ~C 级。
- `_render_monitor_content`(55) 的状态分支可抽为 `_render_success/_render_failed/_render_running` 三个纯渲染子函数。

---

## 7. 重复块提示（人工比对定位）

1. **数据集下载 308-重定向+重试逻辑**：`dataset_discovery.py` 主脚本与 `_url_ds_helper.py`（及旧版残留）存在两份近似下载器（HEAD→urlopen→HTTPError 301/302/303/307/308→retry）。建议收敛为单一内嵌片段常量，两处引用同一 base64 或公共函数生成。
2. **conda 引导前缀**：`remote_runner.py` 各步骤命令重复内嵌同一大段 conda_bootstrap / pip fallback / env 激活文本（历史已因 .format/f-string 引号多次出 bug）。建议抽为 `_scripts.py`（生成模板常量）+ 单测锁定 bash 语法，杜绝再改坏。
3. **UI class 名与 CSS**：ui_theme.py 内 `panel/floating-card/fx-*` 等与 app.py 内 HTML 片段耦合，新增组件需同步两处——建议抽出 HTML builder 模块（见专家 B 架构报告）。

---

## 8. 结论

- **整体**：包内 26 个模块维护性指数均 A，分层清晰（database/runner/parser/theme 独立）；**瓶颈是 app.py（单体 UI+编排，MI=C）与 remote_runner.py（巨型脚本拼装，MI=C）**。
- **必做（P1）**：remote_runner.py:347 的 3.11 语法兼容修复。
- **快赢（低风险）**：23 个纯函数机械迁往 ssh_utils/task_utils/storage_utils；清理 F841/F401 冗余。
- **中期**：render_app/_render_monitor_content/execute 三个 F 级函数按 UI/编排/执行三层拆分。
- 量化工具链（ruff+radon）已可重复执行，建议进入后续每次重构的验收门槛（圈复杂度新函数 ≤ C、MI 不降级）。

*（本报告由专家组静态分析成员产出，量化只读，未改动任何代码。）*
